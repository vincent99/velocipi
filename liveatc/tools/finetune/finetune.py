#!/usr/bin/env python3
"""LoRA fine-tune Whisper on the liveatc dataset, on Apple Silicon (MPS).

Follows the standard Hugging Face Whisper fine-tuning recipe, adapted for a Mac:
  * PEFT/LoRA (small trainable adapter) instead of a full fine-tune -- feasible
    on a Mac and resistant to over-fitting on a small (few-hour) dataset.
  * fp32 on the MPS backend (fp16/bf16 support there is partial).
  * Reports eval WER so you can compare against the base model's WER
    (build_dataset.py's base_model_corpus_wer).

After training it merges the LoRA adapter into the base weights and saves a full
Hugging Face model dir, which export_ggml.sh converts for whisper.cpp / the Jetson.

Prereqs (in a venv):  pip install -r requirements.txt
Recommended env:      PYTORCH_ENABLE_MPS_FALLBACK=1   (some ops fall back to CPU)

Iterate fast with --model openai/whisper-small.en, then do a final run with the
model you actually deploy (openai/whisper-large-v3-turbo).
"""

import argparse
import os
from dataclasses import dataclass

import torch
import jiwer
from datasets import Audio, load_dataset
from transformers import (
    WhisperForConditionalGeneration,
    WhisperProcessor,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
)


@dataclass
class Collator:
    processor: WhisperProcessor

    def __call__(self, features):
        inputs = [{"input_features": f["input_features"]} for f in features]
        batch = self.processor.feature_extractor.pad(inputs, return_tensors="pt")

        labels = [{"input_ids": f["labels"]} for f in features]
        labels_batch = self.processor.tokenizer.pad(labels, return_tensors="pt")
        # Mask padding in the loss.
        lab = labels_batch["input_ids"].masked_fill(
            labels_batch.attention_mask.ne(1), -100
        )
        # Drop a leading BOS the tokenizer may have added; the model adds it back.
        if (lab[:, 0] == self.processor.tokenizer.bos_token_id).all().cpu().item():
            lab = lab[:, 1:]
        batch["labels"] = lab
        return batch


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="dataset", help="dir from build_dataset.py")
    ap.add_argument("--model", default="openai/whisper-large-v3-turbo")
    ap.add_argument("--out", default="finetuned", help="output dir")
    ap.add_argument("--epochs", type=float, default=6.0)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--grad-accum", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--full", action="store_true",
                    help="full fine-tune instead of LoRA (heavy; not advised on a Mac)")
    args = ap.parse_args()

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"device: {device}")
    is_en = ".en" in args.model

    proc_kwargs = {} if is_en else {"language": "en", "task": "transcribe"}
    processor = WhisperProcessor.from_pretrained(args.model, **proc_kwargs)

    ds = load_dataset(
        "json",
        data_files={
            "train": os.path.join(args.dataset, "train.jsonl"),
            "eval": os.path.join(args.dataset, "eval.jsonl"),
        },
    )
    ds = ds.cast_column("audio_filepath", Audio(sampling_rate=16000))

    fe, tok = processor.feature_extractor, processor.tokenizer

    def prepare(batch):
        audio = batch["audio_filepath"]
        batch["input_features"] = fe(
            audio["array"], sampling_rate=16000
        ).input_features[0]
        batch["labels"] = tok(batch["text"]).input_ids
        return batch

    ds = ds.map(prepare, remove_columns=ds["train"].column_names, num_proc=1)

    model = WhisperForConditionalGeneration.from_pretrained(args.model)
    model.config.forced_decoder_ids = None
    model.config.suppress_tokens = []
    model.generation_config.forced_decoder_ids = None
    if not is_en:
        model.generation_config.language = "en"
        model.generation_config.task = "transcribe"
    model.config.use_cache = False  # incompatible with training

    if not args.full:
        from peft import LoraConfig, get_peft_model

        lora = LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            target_modules=["q_proj", "v_proj"],
            lora_dropout=0.05,
            bias="none",
        )
        model = get_peft_model(model, lora)
        model.print_trainable_parameters()

    def compute_metrics(pred):
        pred_ids = pred.predictions
        label_ids = pred.label_ids
        label_ids[label_ids == -100] = tok.pad_token_id
        hyps = tok.batch_decode(pred_ids, skip_special_tokens=True)
        refs = tok.batch_decode(label_ids, skip_special_tokens=True)
        # Normalize a little so casing/punctuation don't dominate the metric.
        norm = jiwer.Compose([
            jiwer.ToLowerCase(),
            jiwer.RemovePunctuation(),
            jiwer.RemoveMultipleSpaces(),
            jiwer.Strip(),
        ])
        return {"wer": jiwer.wer(refs, hyps, truth_transform=norm, hypothesis_transform=norm)}

    training_args = Seq2SeqTrainingArguments(
        output_dir=args.out,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=max(1, args.batch // 2),
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_ratio=0.1,
        num_train_epochs=args.epochs,
        fp16=False,  # MPS: keep fp32
        bf16=False,
        predict_with_generate=True,
        generation_max_length=225,
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_steps=10,
        report_to=[],
        dataloader_num_workers=0,
        remove_unused_columns=False,
        load_best_model_at_end=True,
        metric_for_best_model="wer",
        greater_is_better=False,
    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=ds["train"],
        eval_dataset=ds["eval"],
        data_collator=Collator(processor),
        compute_metrics=compute_metrics,
        processing_class=processor,
    )

    print("baseline eval (base model, before training):")
    print(trainer.evaluate())

    trainer.train()

    final = trainer.evaluate()
    print("final eval:", final)

    # Save a full, merged model dir for ggml conversion (whisper.cpp can't load a
    # bare LoRA adapter).
    merged_dir = os.path.join(args.out, "merged")
    to_save = model.merge_and_unload() if not args.full else model
    to_save.save_pretrained(merged_dir)
    processor.save_pretrained(merged_dir)
    print(f"\nSaved merged model to {merged_dir}")
    print(f"Eval WER: {final.get('eval_wer')} "
          "(compare to base_model_corpus_wer in dataset/summary.json)")
    print("Next: ./export_ggml.sh", merged_dir)


if __name__ == "__main__":
    main()
