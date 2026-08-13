# liveatc — cockpit intercom STT

A standalone Go service that continuously records cockpit-intercom audio,
detects individual radio transmissions (VAD), transcribes them with
whisper.cpp, tags each with GPS metadata, and writes timestamped audio segments
plus a structured transcript to disk — while exposing the transcript data over
an internal HTTP/websocket API for later frontend integration.

It runs as its **own process**, separate from the main velocipi backend, with
its own `go.mod` so it can move to a dedicated repo later. It shares no code
with velocipi, but it now reads the **same** `config.default.yaml` /
`config.yaml` as the main backend (the parent repo root by default): its
settings live under the `liveatc:` key, and the aircraft/tail identifier comes
from the top-level `tailNumber`.

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
| `ui/`                         | Vue 3 + Vite web UI (sessions, live feed, audio, edits)|
| `systemd/intercom-stt.service`| Sample unit file                                     |

## Build & run

For local development there's a `package.json` mirroring the main velocipi repo
(`concurrently` runs the Go API + the Vite UI together):

```bash
yarn install && yarn install:ui   # once (root gets concurrently; ui gets its deps)
yarn dev                           # runs the API (air, hot-reload) + UI (Vite :8091)
yarn build                         # build:ui then build:go -> ./intercom-stt
yarn test                          # go test ./...
```

Any args after `yarn dev` are forwarded to the Go server, so you can feed it a
test source instead of ALSA hardware:

```bash
yarn dev --stream https://example.liveatc.net/feed.mp3
yarn dev --file testdata/clip.wav
```

`dev:go` uses [air](https://github.com/air-verse/air) for hot-reload, same as the
main repo — install it with `go install github.com/air-verse/air@latest` if you
don't have it. On a non-Pi dev box ALSA capture fails and retries (harmless); the
API + UI still serve any sessions already on disk.

There's also a `Makefile` for ops-style tasks — run `make help` to list them
(`make build-pi`, `make check`, `make ui`, `make venv`, `make model MODEL=small.en-q5_1`,
`make deploy PI=pi@host`). The raw commands, if you prefer:

```bash
go build -o intercom-stt ./cmd/intercom-stt   # native (Pi: run this on the Pi)
GOOS=linux GOARCH=arm64 go build ./cmd/intercom-stt   # cross-compile for a Pi 5

# Live capture from the USB adapter (device from config or AUDIO_DEVICE env):
./intercom-stt

# Test off-aircraft from a live stream or a local file (uses ffmpeg, no ALSA):
./intercom-stt --stream https://example.liveatc.net/somefeed.mp3
./intercom-stt --file testdata/clip.wav
./intercom-stt --device hw:2,0            # override ALSA device
./intercom-stt --config /path/to/velocipi # dir holding the shared config.default.yaml (defaults to `..`)

# Multiple named streams (each transmission tagged with the stream name):
./intercom-stt --stream com1=https://host/a.mp3 --stream com2=https://host/b.mp3
```

### Channels / split radios

Set `liveatc.audio.channels: 2` to capture the USB adapter in stereo. liveatc
then detects, frame by frame, whether the two channels are **joined** (identical
— comms mixed into both ears → one transmission tagged `mono`) or **split**
(independent radios → the left and right sides are VAD'd and transcribed
separately, tagged `com1`/`com2`). The join/split state can change at will. Each
transmission's `channel` is recorded in the JSONL, the text log, the WAV
(`IART`), and shown in the UI. With `channels: 1` (default) it's plain mono.

Split detection applies to whichever single source honors `channels: 2` — the
ALSA device, a `--file`, **or a single `--stream`** (a stereo stream is join/split
detected; a mono one just reads as `mono`). **Multiple** `--stream name=url`
sources are instead one mono channel each, named after the stream — naming them
is how you separate the radios, so each is transcribed independently (no split
detection per stream) into the shared session.

Run `go test ./...` for the VAD segmenter unit tests.

## Configuration

liveatc reads the shared velocipi `config.default.yaml` (baseline, always read
first) and an optional sibling `config.yaml` override — by default from the
parent repo root (`--config ..`). All liveatc settings live under the
`liveatc:` key; the aircraft/tail identifier is the top-level `tailNumber`; the
audio/transcript output root is `storage.liveatc`. `AUDIO_DEVICE` overrides the
capture device. See the parent `config.default.yaml` for the full annotated
schema.

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

## Web UI

A Vue 3 + Vite single-page app in `ui/` provides:

- a **session sidebar** (live session flagged) to browse the current flight or past ones,
- a **transcript view** that loads a session's records from disk and, for the live
  session, appends new transmissions in real time over `/ws/transcripts`,
- a **Listen** button per transmission that streams the segment WAV (with seeking),
- an inline **correction editor** — edits are saved to a separate `correction`
  field on the record (the machine `transcript` is never overwritten) for use as
  corrective training material later.

Build it with `make ui` (outputs `ui/dist`, which the Go binary serves at `/`);
develop it with `make ui-dev` (Vite dev server on :8091, proxying `/api` + `/ws`
to a running backend). Set `liveatc.uiDir: ""` to run API-only.

## Internal API

- `GET  /api/sessions` — all sessions (from disk manifests), newest first, `live` flagged
- `GET  /api/transcripts/session/{session_id}` — records for a session, read from the
  durable JSONL (works for the live session and past ones; includes corrections)
- `GET  /api/transcripts/recent?n=20` — last N records (in-memory cache)
- `PUT  /api/transcripts/session/{session_id}/{id}/correction` — save `{ "correction": "..." }`
  onto a record; returns the updated record and broadcasts it to live viewers
- `GET  /api/media/{path...}` — serve a file (e.g. a segment WAV) from under the
  storage root, with Range support (confined to the root; traversal is blocked)
- `POST /api/transcripts/session/{session_id}/{id}/merge` — combine a transmission
  with the next (later) one into a single record: audio concatenated into the
  earlier record's WAV, text/metadata merged, later record deleted
- `DELETE /api/transcripts/session/{session_id}/{id}` — delete one transmission
  (its audio + JSONL entry + text-log line)
- `DELETE /api/transcripts/session/{session_id}` — delete a whole session (audio,
  transcripts, manifest, now-empty dirs); refuses the active session (409)
- `GET  /api/session` — current session manifest; `GET /healthz`
- `WS   /ws/transcripts` — pushes each new/edited `TransmissionRecord` (with a small backlog on connect)
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
- **Decoding prompt**: `liveatc.whisper.prompt` is passed as whisper's initial
  prompt (`--prompt`) to bias decoding toward ATC phraseology, this aircraft's
  callsign, and digit formatting (altitudes/headings/runways/frequencies). The
  default is a representative ATC sample; edit it for your callsign/airport.
- **Callsign hint** in the WAV filename is left empty for now (callsign parsing
  is out of scope; add it later as a rename/symlink post-pass on the JSONL).
