#!/usr/bin/env bash
# Convert a fine-tuned Hugging Face Whisper model dir to ggml for whisper.cpp
# (and optionally quantize), so it runs on the Pi / Jetson via whisper-cli.
#
# Usage:
#   ./export_ggml.sh <merged_model_dir> [quant]
# e.g.
#   ./export_ggml.sh finetuned/merged q5_0
#
# Needs a whisper.cpp checkout for the conversion script + quantize tool. Point
# WHISPER_CPP at it (default ../../../whisper.cpp), and build it first if you
# want quantization:  cmake -B build && cmake --build build -j
set -euo pipefail

MODEL_DIR="${1:?usage: export_ggml.sh <merged_model_dir> [quant]}"
QUANT="${2:-}"
WHISPER_CPP="${WHISPER_CPP:-../../../whisper.cpp}"
OUT="${MODEL_DIR%/}/ggml-model.bin"

conv="$WHISPER_CPP/models/convert-h5-to-ggml.py"
if [[ ! -f "$conv" ]]; then
  echo "convert-h5-to-ggml.py not found at $conv" >&2
  echo "Set WHISPER_CPP=/path/to/whisper.cpp (a recent checkout)." >&2
  exit 1
fi

echo ">> converting $MODEL_DIR -> ggml (fp16)"
# convert-h5-to-ggml.py <model_dir> <whisper_repo> <out_dir>; writes ggml-model.bin
python3 "$conv" "$MODEL_DIR" "$WHISPER_CPP" "$MODEL_DIR"
echo "wrote $OUT"

if [[ -n "$QUANT" ]]; then
  q="$WHISPER_CPP/build/bin/quantize"
  [[ -x "$q" ]] || q="$WHISPER_CPP/quantize"
  if [[ ! -x "$q" ]]; then
    echo "quantize tool not found; build whisper.cpp first. Skipping quantization." >&2
    exit 0
  fi
  QOUT="${MODEL_DIR%/}/ggml-model-${QUANT}.bin"
  echo ">> quantizing -> $QOUT ($QUANT)"
  "$q" "$OUT" "$QOUT" "$QUANT"
  echo "wrote $QOUT"
  echo "Point liveatc.whisper.model (or atcModel) at it and restart intercom-stt."
fi
