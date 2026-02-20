# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Development (hot-reload via air)
npm run dev        # or: air

# Build
npm run build      # or: go build -o velocipi-go .
go build ./...     # build all packages including hardware modules

# Run a specific test
go test ./hardware/expander/...
go test ./...

# UI formatting / linting (run from ui/)
yarn format        # prettier --write src
yarn lint          # eslint src

# Go formatting
gofmt -w ./server/
```

After editing any file under `ui/src/`, run `yarn format` from `ui/` to auto-format.
After editing any `.go` file, run `gofmt -w ./server/` from the repo root.

`air` watches `*.go` files and rebuilds into `tmp/velocipi-go` on change. It sends SIGINT before SIGKILL so the app can shut down gracefully.

## Architecture

This is a Go server running on a Raspberry Pi 5. It bridges physical hardware (OLED, expander I/O, sensors) with a headless Chromium browser (via chromedp), exposing the browser output to web clients.

### Request / data flow

```
Hardware (I2C/SPI/BT)
  → hardware/* singletons
    → hub.go loops (runAirSensorLoop, runInputLoop, etc.)
      → WebSocket clients via /ws (JSON text frames)
      → OLED display (direct blit)

Chromium browser (chromedp)
  ← hub.go loads app/index.html via data: URL
  → Page.startScreencast frames → /screen WebSocket (binary PNG)
                                 → OLED display (after splash)
  ← keyboard events from /ws clients (hub.handleKeyMsg → DispatchKeyEvent)
  ← keyboard events from expander input loop (hub.handleChange → dispatchKey)
```

### Key files

- **`main.go`** — HTTP server setup, WebSocket handlers (`/ws`, `/screen`), startup sequence (LED blink → OLED splash → screencast)
- **`hub.go`** — `Hub` struct, all broadcast/send helpers, sensor loops, screencast loop, input loop, chromedp key dispatch, LED state management
- **`config/config.go`** — All configuration via env vars / `.env` file using `envconfig`
- **`hardware/hardware.go`** — `sync.Once` singletons: `AirSensor()`, `LightSensor()`, `TPMS()`, `Expander()`, `LED()`
- **`frontend/index.html`** — Admin/debug UI: screenshot viewer, sensor readings, key relay to chromedp, LED control
- **`frontend/app/index.html`** — The app page rendered inside headless Chromium and mirrored to the OLED

### Hardware modules (`hardware/`)

Each module is a standalone package; hardware.go provides the singleton accessors.

| Package       | Hardware                               | Notes                                                                              |
| ------------- | -------------------------------------- | ---------------------------------------------------------------------------------- |
| `expander`    | SX1509 16-bit I2C GPIO expander        | Polls `INPUT_VALUE` register every 2ms; emits `Change{Value, Previous}` on channel |
| `led`         | Single LED on expander bit 6           | `Controller` with `On/Off/Blink`; tracks state and fires `OnChange` callback       |
| `oled`        | SSD1327 256×64 grayscale OLED over SPI | `Blit(image.Image)` converts to 4-bit grayscale; double-buffered                   |
| `airsensor`   | BME280 (temp/humidity/pressure)        |                                                                                    |
| `lightsensor` | VEML6030 ambient light                 |                                                                                    |
| `tpms`        | Bluetooth TPMS tire sensors            |                                                                                    |

### Expander bit assignments (config defaults)

| Bit   | Signal                      |
| ----- | --------------------------- |
| 0     | Knob center button          |
| 1–2   | Inner knob quadrature (A/B) |
| 3–4   | Outer knob quadrature (A/B) |
| 6     | LED (output)                |
| 8     | Joystick center             |
| 9     | Joystick down               |
| 10    | Joystick up                 |
| 11    | Joystick right              |
| 12    | Joystick left               |
| 13–14 | Joy knob quadrature (A/B)   |

### WebSocket message types

**Outbound (server → client, JSON on `/ws`):** `ping`, `airReading`, `luxReading`, `tpms`, `ledState`

**Inbound (client → server, JSON on `/ws`):** `reload`, `key` (`{eventType, key}`), `led` (`{state, rate}`)

**Screen socket (`/screen`):** binary PNG frames only

### Quadrature encoder decoding

All three rotary encoders use the same `knobState` accumulator in `hub.go`. The Gray code `quadTable` scores each 2-bit transition ±1; an accumulated score of ±2 (one detent = two valid steps on this hardware) emits a key event. Key mappings: outer `[`/`]`, inner `;`/`'`, joy knob `,`/`.`

### Chromedp / key dispatch

- `kb.Encode(rune)` returns `[]*DispatchKeyEventParams` — one entry per event type
- Non-printable JS key names (`ArrowLeft` etc.) are mapped to kb private Unicode codepoints via `jsKeyToKb` in `hub.go` before encoding
- Joystick directions use keydown-on-center-press / keyup-on-center-release logic
- Knob keys are always sent as a keydown+keyup pair (no held state)

### Chromedp navigation quirks (Raspberry Pi / chromium-headless-shell)

- `page.Navigate` never returns a CDP response for HTTP/HTTPS URLs on this platform — it blocks until context cancellation
- Lifecycle events (`EventLifecycleEvent`) **do** fire correctly, but only on `browserCtx` directly — listeners registered on derived child contexts miss the events entirely
- `navigateTo()` in `hub.go` works around this: fires `page.Navigate` in a goroutine on `browserCtx`, registers the listener on `browserCtx`, waits for `networkIdle`
- `chromedp.ListenTarget` does not return a cancel/remove function in this version (v0.14.2)
