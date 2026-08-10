# liveatc — cockpit intercom STT

A standalone Go service that continuously records cockpit-intercom audio,
detects individual radio transmissions (VAD), transcribes them with
whisper.cpp, tags each with GPS metadata, and writes timestamped audio segments
plus a structured transcript to disk — while exposing the transcript data over
an internal HTTP/websocket API for later frontend integration.

It runs as its **own process**, separate from the main velocipi backend, with
its own `go.mod` so it can move to a dedicated repo later. It intentionally
mirrors velocipi's patterns (layered `config.default.yaml` + `config.yaml`) but
shares no code.

## Data flow

```
USB audio adapter ──(arecord, s16le mono 16k)──┐
liveatc.net stream / file ──(ffmpeg)───────────┤
                                               ▼
                                     audio.Capture (ring buffer, 512-sample frames)
                                               ▼
                     vad.Scorer (Silero sidecar | energy fallback)
                                               ▼
                     vad.Segmenter  (min-speech / min-silence / max-dur / pre-roll)
                                               ▼  per transmission
        WAV segment (+ RIFF LIST/INFO: ICRD / ICMT gps / ISRC / IKEY transcript)
                                               ▼
                     stt.Transcriber  (whisper-cli subprocess, worker pool)
                                               ▼
     transcript.Writer (JSONL + text log)  +  transcript.Store  ──►  API / websocket
```

GPS position is pushed in from outside (today via the API; later the Garmin
Axis feed) and snapshotted at each transmission's start and end.

## Layout

| Path                          | Purpose                                              |
| ----------------------------- | ---------------------------------------------------- |
| `cmd/intercom-stt/main.go`    | Entrypoint, flags, wiring, graceful shutdown         |
| `internal/config`             | Reusable layered YAML loader + liveatc config schema |
| `internal/audio`              | Capture (arecord/ffmpeg), ring buffer, WAV writer    |
| `internal/vad`                | Segmenter, Silero client, energy fallback, factory   |
| `internal/stt`                | whisper.cpp CLI wrapper + JSON parsing               |
| `internal/gps`                | `GPSFix` + concurrency-safe position store           |
| `internal/ptt`                | GPIO PTT monitor (Linux build tag) for tx/rx         |
| `internal/transcript`         | Record model, in-memory store, JSONL+text writers    |
| `internal/session`            | Session id, on-disk paths, manifest                  |
| `internal/pipeline`           | Orchestration of all of the above                    |
| `sidecar/silero_vad.py`       | Silero VAD sidecar (stdin PCM → stdout probabilities)|
| `systemd/intercom-stt.service`| Sample unit file                                     |

## Build & run

```bash
go build -o intercom-stt ./cmd/intercom-stt   # native (Pi: run this on the Pi)
GOOS=linux GOARCH=arm64 go build ./cmd/intercom-stt   # cross-compile for a Pi 5

# Live capture from the USB adapter (device from config or AUDIO_DEVICE env):
./intercom-stt

# Test off-aircraft from a live stream or a local file (uses ffmpeg, no ALSA):
./intercom-stt --stream https://example.liveatc.net/somefeed.mp3
./intercom-stt --file testdata/clip.wav
./intercom-stt --device hw:2,0            # override ALSA device
./intercom-stt --config /etc/liveatc      # where config.default.yaml lives
```

Run `go test ./...` for the VAD segmenter unit tests.

## Configuration

`config.default.yaml` is the baseline and is always read first; create a sibling
`config.yaml` to override only the keys you want to change (it is git-ignored).
`AUDIO_DEVICE` overrides the capture device. See `config.default.yaml` for the
full annotated schema.

## Dependencies on the Pi

- **arecord** (`alsa-utils`) for live capture; **ffmpeg** for `--stream`/`--file`.
- **whisper.cpp** built with the `whisper-cli` binary, plus a GGML model
  (`ggml-base.en.bin` by default). Point `liveatc.whisper.binary` / `model` at
  them. A fine-tuned ATC model can be dropped into `modelDir` and selected via
  `atcModel`.
- **Silero VAD sidecar** (optional but preferred): a Python venv with either
  `torch` (torch.hub path) or `onnxruntime` + a local `silero_vad.onnx`
  (`SILERO_ONNX=/path`). If the sidecar can't start, the service logs a warning
  and falls back to the built-in energy (RMS) VAD so it still runs.

## Internal API

- `GET  /api/transcripts/session/{session_id}` — records for a session (JSON array)
- `GET  /api/transcripts/recent?n=20` — last N records
- `GET  /api/session` — current session manifest; `GET /healthz`
- `WS   /ws/transcripts` — pushes each new `TransmissionRecord` (with a small backlog on connect)
- `POST /api/gps` and `WS /ws/gps` — feed the current `GPSFix` in (until the Garmin Axis integration lands)

## TX vs RX detection

1. **GPIO PTT (definitive).** Wire the radio's PTT line to a Pi GPIO and set
   `liveatc.pttPin` (GPIO offset) + `pttChip`/`pttActiveLow`. Keyed during a
   transmission ⇒ `tx`, otherwise `rx`. GPIO support is Linux-only (build tag).
2. **Audio-level heuristic (fallback).** With no PTT pin, the louder TX sidetone
   is approximated by mean segment RMS; above `txRmsThreshold` ⇒ `tx`, else
   `unknown` (`0` disables it — everything is `unknown`).

## Notes / deviations from the original spec

- **Logging** uses the stdlib `log/slog` JSON handler rather than zerolog —
  structured JSON with a configurable level and zero extra dependencies.
- **whisper flags**: whisper.cpp has no `--word-timestamps` flag; word timing
  comes from the token offsets in `--output-json-full` (`-ojf`), which the
  parser merges back into whole words. `--no-prints` = `-np`.
- **Callsign hint** in the WAV filename is left empty for now (callsign parsing
  is out of scope; add it later as a rename/symlink post-pass on the JSONL).
