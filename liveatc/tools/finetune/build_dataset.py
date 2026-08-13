#!/usr/bin/env python3
"""Build a Whisper fine-tuning dataset from liveatc corrected transcripts.

Scans the storage transcripts (JSONL) for human-verified records and emits a
train/eval split plus a summary, ready for finetune.py. Verified means:

  * a correction was provided  -> reference text = the correction, OR
  * the record was marked reviewed (transcript confirmed correct as-is)
    -> reference text = the machine transcript.

Records that are neither corrected nor reviewed are unverified and skipped.

Design notes (see the README for the reasoning):
  * We ALWAYS rebuild from the full set of verified records. Corrections are
    permanent labels; each fine-tune run should train on the cumulative data.
    Nothing is marked "consumed".
  * The train/eval split is deterministic per record id (hash bucket), so the
    eval set is stable as you add more data -- WER stays comparable across runs.
  * Per-record WER (machine transcript vs. reference) is computed for curation
    and reporting only; it is NOT a training signal.

Pure standard library -- no pip installs needed for this step.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone


def norm_words(text: str) -> list[str]:
    """Lightly normalize for the WER *metric* only (lowercase, strip most
    punctuation, collapse whitespace). Training uses the raw reference text."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)  # keep word chars + spaces
    return text.split()


def wer_counts(ref: list[str], hyp: list[str]) -> tuple[int, int]:
    """Word-level Levenshtein: returns (edit_distance, len(ref))."""
    n, m = len(ref), len(hyp)
    if n == 0:
        return (m, 0)
    d = list(range(m + 1))
    for i in range(1, n + 1):
        prev, d[0] = d[0], i
        for j in range(1, m + 1):
            cur = d[j]
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + cost)
            prev = cur
    return (d[m], n)


def bucket(record_id: str) -> float:
    """Deterministic [0,1) bucket from the record id (stable across runs)."""
    h = hashlib.md5(record_id.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def iter_records(storage: str):
    pattern = os.path.join(storage, "transcripts", "*", "*.jsonl")
    for path in sorted(glob.glob(pattern)):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def reference_for(rec: dict) -> tuple[str, str] | None:
    """Return (reference_text, source) or None if unverified/unusable."""
    corr = (rec.get("correction") or "").strip()
    if corr:
        return corr, "corrected"
    if rec.get("reviewed"):
        t = (rec.get("transcript") or "").strip()
        if t:
            return t, "reviewed"
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--storage", default="data/liveatc",
                    help="storage.liveatc root (contains audio/ and transcripts/)")
    ap.add_argument("--out", default="dataset",
                    help="output dataset directory")
    ap.add_argument("--eval-frac", type=float, default=0.15,
                    help="fraction held out for eval (deterministic per id)")
    ap.add_argument("--min-words", type=int, default=1,
                    help="skip references shorter than this many words")
    ap.add_argument("--include-blocked", action="store_true",
                    help="include records whose reference is just [blocked] noise")
    args = ap.parse_args()

    storage = os.path.abspath(args.storage)
    os.makedirs(args.out, exist_ok=True)

    train, evl = [], []
    skipped = {"unverified": 0, "no_audio": 0, "too_short": 0, "blocked": 0}
    tot_edits = tot_refwords = 0
    tot_ms = 0
    by_source = {"corrected": 0, "reviewed": 0}

    for rec in iter_records(storage):
        ref = reference_for(rec)
        if ref is None:
            skipped["unverified"] += 1
            continue
        text, source = ref

        if not args.include_blocked and text.strip().lower() in ("[blocked]", "blocked"):
            skipped["blocked"] += 1
            continue
        if len(text.split()) < args.min_words:
            skipped["too_short"] += 1
            continue

        audio_rel = rec.get("audio_file", "")
        audio_abs = os.path.join(storage, audio_rel)
        if not audio_rel or not os.path.exists(audio_abs):
            skipped["no_audio"] += 1
            continue

        edits, refn = wer_counts(norm_words(text), norm_words(rec.get("transcript", "")))
        tot_edits += edits
        tot_refwords += refn
        tot_ms += int(rec.get("duration_ms", 0))
        by_source[source] += 1

        item = {
            "id": rec["id"],
            "session_id": rec.get("session_id", ""),
            "audio_filepath": audio_abs,
            "text": text,  # raw reference, formatting preserved
            "source": source,
            "wer": round(edits / refn, 4) if refn else None,
            "duration_ms": rec.get("duration_ms", 0),
        }
        (evl if bucket(rec["id"]) < args.eval_frac else train).append(item)

    def dump(name, rows):
        p = os.path.join(args.out, name)
        with open(p, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return p

    dump("train.jsonl", train)
    dump("eval.jsonl", evl)

    corpus_wer = (tot_edits / tot_refwords) if tot_refwords else None
    summary = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "storage": storage,
        "counts": {
            "train": len(train),
            "eval": len(evl),
            "total_used": len(train) + len(evl),
            "by_source": by_source,
            "skipped": skipped,
        },
        "audio_hours": round(tot_ms / 3_600_000, 3),
        "base_model_corpus_wer": round(corpus_wer, 4) if corpus_wer is not None else None,
        "eval_frac": args.eval_frac,
    }
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))
    if len(train) + len(evl) == 0:
        print("\nNo verified records found. Correct or mark transmissions reviewed "
              "in the UI first.", file=sys.stderr)
        sys.exit(1)
    print(f"\nWrote {args.out}/train.jsonl, {args.out}/eval.jsonl, summary.json")
    print("Base model corpus WER on your data: "
          f"{summary['base_model_corpus_wer']} (target: lower after fine-tuning)")


if __name__ == "__main__":
    main()
