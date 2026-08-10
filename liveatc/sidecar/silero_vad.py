#!/usr/bin/env python3
"""Silero-VAD sidecar for the liveatc Go service.

Framing (see internal/vad/silero.go):
  stdin  : raw little-endian int16 PCM, exactly FRAME_SAMPLES per frame
  stdout : one ASCII float line (speech probability, 0..1) per frame

The Go side sends one frame and reads exactly one probability line, strictly in
order, so no length-prefixing or ids are needed. Keep stdout for probabilities
ONLY -- all logging goes to stderr.

Model resolution order:
  1. torch.hub 'snakers4/silero-vad' (preferred; downloads/caches the model)
  2. onnxruntime with a local silero_vad.onnx (set SILERO_ONNX=/path/to.onnx)

Dependencies (install into a venv on the Pi):
  pip install torch            # for the torch.hub path, OR
  pip install onnxruntime numpy  # for the onnx path (+ the .onnx file)
"""

import argparse
import os
import sys


def log(*a):
    print(*a, file=sys.stderr, flush=True)


class TorchVAD:
    """Silero VAD via torch.hub. Expects 512-sample frames at 16 kHz."""

    def __init__(self, sample_rate):
        import torch  # noqa: F401
        self.torch = torch
        model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            onnx=False,
            trust_repo=True,
        )
        model.eval()
        self.model = model
        self.sample_rate = sample_rate

    def score(self, int16_frame):
        t = self.torch.from_numpy(int16_frame).float() / 32768.0
        with self.torch.no_grad():
            return float(self.model(t, self.sample_rate).item())


class OnnxVAD:
    """Silero VAD via onnxruntime + a local silero_vad.onnx."""

    def __init__(self, sample_rate, onnx_path):
        import numpy as np
        import onnxruntime as ort

        self.np = np
        self.sample_rate = sample_rate
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.sess = ort.InferenceSession(onnx_path, sess_options=opts,
                                         providers=["CPUExecutionProvider"])
        # Silero onnx keeps recurrent state between calls.
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._sr = np.array(sample_rate, dtype=np.int64)

    def score(self, int16_frame):
        x = (int16_frame.astype(self.np.float32) / 32768.0).reshape(1, -1)
        out, self._state = self.sess.run(
            None, {"input": x, "state": self._state, "sr": self._sr}
        )
        return float(out.reshape(-1)[0])


def load_backend(sample_rate):
    onnx_path = os.environ.get("SILERO_ONNX")
    if onnx_path:
        log(f"silero: using onnx backend ({onnx_path})")
        return OnnxVAD(sample_rate, onnx_path)
    log("silero: using torch.hub backend")
    return TorchVAD(sample_rate)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-rate", type=int, default=16000)
    ap.add_argument("--frame-samples", type=int, default=512)
    ap.add_argument("--threshold", type=float, default=0.5)  # accepted; gating is Go-side
    args = ap.parse_args()

    import numpy as np

    backend = load_backend(args.sample_rate)
    frame_bytes = args.frame_samples * 2
    log(f"silero: ready (frame={args.frame_samples} samples, {frame_bytes} bytes)")
    # Readiness marker the Go side waits for before trusting this sidecar; if the
    # model import/load above fails, the process dies before printing this and Go
    # falls back to the energy VAD.
    log("__READY__")

    stdin = sys.stdin.buffer
    out = sys.stdout
    while True:
        buf = stdin.read(frame_bytes)
        if not buf or len(buf) < frame_bytes:
            break  # EOF / shutdown
        frame = np.frombuffer(buf, dtype="<i2")
        try:
            p = backend.score(frame)
        except Exception as e:  # never crash the stream on a bad frame
            log(f"silero: score error: {e}")
            p = 0.0
        out.write(f"{p:.6f}\n")
        out.flush()


if __name__ == "__main__":
    main()
