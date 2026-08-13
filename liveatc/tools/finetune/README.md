# Fine-tuning Whisper from liveatc corrections

Turn your reviewed/corrected transmissions into a fine-tuned Whisper model for
whisper.cpp (Pi / Jetson). Runs on an Apple Silicon Mac.

## The idea

1. In the UI, **correct** transmissions with errors and mark error-free ones
   **reviewed**. These become ground-truth labels on the recorded audio.
2. `build_dataset.py` gathers every verified `(audio, reference text)` pair into
   a train/eval split.
3. `finetune.py` LoRA-fine-tunes Whisper on the MPS (Apple GPU) backend and
   reports eval WER vs. the base model.
4. `export_ggml.sh` converts the result to `ggml` for whisper.cpp.

Why LoRA and not a full fine-tune: a few hours of audio is a *small* dataset for
an 809M model. LoRA trains a tiny adapter — feasible on a Mac, and far less
likely to over-fit or forget the base model's general ability. Start small.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTORCH_ENABLE_MPS_FALLBACK=1     # some ops fall back to CPU

# 1. Build the dataset from your storage root (storage.liveatc)
python3 build_dataset.py --storage /path/to/data/liveatc --out dataset
# -> dataset/train.jsonl, dataset/eval.jsonl, dataset/summary.json
#    summary.json includes base_model_corpus_wer (your baseline).

# 2. Fine-tune. Iterate with a small model first, then the deploy model.
python3 finetune.py --dataset dataset --model openai/whisper-small.en --out ft-small
python3 finetune.py --dataset dataset --model openai/whisper-large-v3-turbo --out finetuned

# 3. Convert to ggml (needs a whisper.cpp checkout; see the script header)
./export_ggml.sh finetuned/merged q5_0
```

Then point `liveatc.whisper.model` (or drop it in `modelDir` and set `atcModel`)
at the exported `.bin` and restart `intercom-stt`.

## WER: what it means here

`build_dataset.py` computes, per record, the **base model's** WER (its transcript
vs. your correction — your correction is the truth), plus a corpus aggregate in
`summary.json`. `finetune.py` reports **eval WER** on the held-out split before
and after training.

- WER is an **evaluation/curation metric, not a training signal** — training
  optimizes token likelihood, not WER. Use it to (a) know your baseline, (b) see
  if fine-tuning helped (final eval WER < baseline on the **held-out** set), and
  (c) spot the informative clips (high WER = model struggled).
- Metric normalization (lowercase, strip punctuation) is applied only for the
  *number*. Training uses your raw correction text, so formatting like `28R`,
  `FL310`, `13,000`, `[blocked]` is learned verbatim.

## Adding more data later

Reuse everything. Each run **rebuilds from all verified records** and restarts
from the base model — that's deliberate and better than incremental training on
only-new clips (which shrinks the data and forgets the old). So:

- **Do** re-run `build_dataset.py` after adding corrections; old + new together.
- **Don't** re-run STT on old audio hoping for better labels — the label is your
  correction, and the audio is fixed; re-transcribing changes nothing.
- No per-record "already trained" flag exists **on purpose**; `reviewed` /
  `correction` already mark "verified, usable," and excluding old data would hurt.
- The train/eval split is a **deterministic hash of the record id**, so a record
  never moves buckets as the dataset grows — eval WER stays comparable run over
  run. For a frozen benchmark, snapshot a `dataset/eval.jsonl` and reuse it.

Keep each run's `dataset/summary.json` + the eval WER to track progress over time.

## Notes / caveats

- `large-v3-turbo` is multilingual; training pins `language=en, task=transcribe`.
  The `.en` models are English-only and much faster to iterate on.
- MPS training is fp32 (fp16/bf16 there is partial) and slower than CUDA; keep
  batch sizes modest. `predict_with_generate` eval is the slow part — the eval
  split is small by design.
- This is the standard HF Whisper recipe; it hasn't been run end-to-end in CI
  here, so expect to tweak batch size / epochs for your data and Mac's memory.
- Alternative worth knowing: Apple's **MLX** has Whisper support and can be
  faster on Apple Silicon, but its fine-tuning path is less turnkey than
  transformers+PEFT; this uses the well-trodden route.
