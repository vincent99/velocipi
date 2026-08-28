# VelociPi

## About

This runs on a Raspberry Pi 5 to control the screens, cameras, joysticks, audio, and various other toys in my Velocity V-Twin-7 N711ME.

I don't know why you're here, but good luck.

## System setup

### Dependencies

These should be installed on the system:

```
sudo apt install chromium chromium-headless-shell ffmpeg mpv libchromaprint-tools
```

| Binary                           | Package                   | For                                                    |
| -------------------------------- | ------------------------- | ------------------------------------------------------ |
| `chromium-browser` or `chromium` | `chromium`                | Browser for local screen video streaming               |
| `chromium-headless-shell`        | `chromium-headless-shell` | Headless browser for OLED screen                       |
| `ffmpeg`                         | `ffmpeg`                  | DVR recording/streaming, music transcoding             |
| `ffprobe`                        | `ffmpeg`                  | Music duration/metadata extraction (comes with ffmpeg) |
| `mpv`                            | `mpv`                     | Music playback                                         |
| `fpcalc`                         | `libchromaprint-tools`    | Music fingerprinting (optional)                        |

### Hardware config

Enable I2C and SPI interfaces via `raspi-config` (Interface Options)

### Hiding the mouse cursor

Run this once to install a package that will hide the mouse cursor from the local screen

`sudo ./util/install-hideaway.sh`

## Dev

`npm run dev`

## Build

`npm run build`

## Configuration

See `config.yaml`

## WebSocket API

`/ws` carries JSON text frames in both directions (every message has a top-level `type` field). A separate `/screen` endpoint carries only binary PNG frames (the browser screencast) — no JSON messages.

Field-level types live in `ui/src/types/ws.ts` (frontend) and `server/messages.go` / the relevant subsystem's own `messages.go` (backend, e.g. `server/music/messages.go`, `server/dvr/dvr.go`) — this table is a human-readable index, not the source of truth. **Update this table whenever a message type is added, removed, renamed, or changes shape.**

### Server → client

| Type            | Key fields                                                                     | Description                                                       |
| --------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `ping`          | `time`                                                                           | Periodic heartbeat carrying the server's current time              |
| `airReading`    | `reading` (temp/pressure/humidity/dewpoint, °C+°F)                              | BME280 air sensor reading                                          |
| `luxReading`    | `lux`                                                                            | Ambient light sensor reading                                       |
| `tpms`          | `tire` (position, temp, pressure, voltage, battery, inflation/rotation state)   | One tire pressure sensor reading                                   |
| `ledState`      | `r`, `w`, `b`, `y` (each `{mode, rate?}`)                                        | Full state of all four expander LED channels                       |
| `keyEcho`       | `eventType`, `key`                                                               | Echoes a dispatched key event back to all clients, for UI feedback |
| `cameraStatus`  | `name`, `recording`                                                              | One camera's DVR recording status                                  |
| `recordingReady`| `camera`, `session`, `filename`                                                  | A DVR segment's thumbnails have finished generating                |
| `dvrState`      | `state` (`on`, `paused`, or `off`)                                               | Overall DVR recording state                                        |
| `diskSpace`     | `totalGB`, `usedGB`, `freeGB`, `usedPct`                                         | DVR storage disk space reading                                     |
| `localCamera`   | `camera`                                                                         | Camera currently shown on the local panel display                  |
| `axisState`     | `lat`, `lon`, `altFt`, `heading`, `roll`, `pitch`, `yaw`, `speedKts`, `oatCelsius`| Axis avionics state                                                 |
| `siyiAttitude`  | `camera`, `yaw`, `pitch`, `roll`, `yawRate`, `pitchRate`, `rollRate`             | Siyi gimbal attitude for one camera                                 |
| `musicState`    | `currentSongId`, `queueIndex`, `status`, `shuffle`, `repeat`, `elapsedSec`, `queueLength` | Music player state                                        |
| `musicQueue`    | `currentIndex`, `entries`                                                        | Full music queue snapshot                                          |
| `airConState`   | `state` (mode, fan, setpoint, temps, compressor, error, ...)                     | Aircon controller state                                             |
| `airConHistory` | `history` (array of temp samples)                                               | Temperature history, sent to a client on connect                    |
| `airConSample`  | `sample`                                                                         | One new temperature sample                                          |
| `btDevices`     | `devices` (address, name, paired, connected, trusted)                           | Known classic Bluetooth devices (paired + discovered)                |
| `btNowPlaying`  | `player` (track title/artist/album, status, position) or `null`                  | Current AVRCP now-playing metadata, `null` if no active session      |

### Client → server

| Type              | Key fields                                                  | Description                                                        |
| ----------------- | ------------------------------------------------------------ | -------------------------------------------------------------------- |
| `reload`          | —                                                              | Reload the chromedp browser page                                    |
| `key`             | `eventType`, `key`                                            | Dispatch a logical key event to chromedp / the expander input loop   |
| `led`             | `channel`, `state`, `rate?`                                   | Set one expander LED channel's state                                 |
| `navigate`        | `path`                                                         | Navigate the chromedp browser to a URL path                          |
| `setLocalCamera`  | `camera`                                                       | Change which camera is shown on the local panel display              |
| `musicControl`    | `action` (play/pause/stop/next/prev/seek/...), `value?`, `str?`| Control the music player                                            |
| `btControl`       | `action` (scan/pair/connect/.../playPause/next/previous), `address?` | Control Bluetooth device pairing (`btmedia`) or transport control (`bthid`) |

## Hardware

Display: Generic grayscale [SSD1322 OLED](https://www.amazon.com/dp/B0F7LBQM5N) module (256x64 assumed) or black & white [Noritake-Itron GE256X64B](https://www.noritake-elec.com/products/model?part=GE256X64B-7032B)
Joystick: [RKJXT1F42001](https://www.amazon.com/dp/B0DC623B3S) multi-function switch
Rotary encoder: [Dual concentric](https://www.propwashsim.com/store/p/dual-encoder-kit) with switch
I2C expander: [SX1509](https://www.adafruit.com/product/2260)
I2C air sensors: [BME280](https://www.adafruit.com/product/2652)
I2C light sensor: [VEML6030](https://www.adafruit.com/product/4396)

## Raspberry Pi GPIO pins

| BCM | Physical | Function  | Direction | Connected to                                                         |
| --- | -------- | --------- | --------- | -------------------------------------------------------------------- |
| 2   | 3        | I2C1 SDA  | Bidir     | SX1509 expander, BME280 air sensor, VEML6030 light sensor            |
| 3   | 5        | I2C1 SCL  | Output    | SX1509 expander, BME280 air sensor, VEML6030 light sensor            |
| 5   | 29       | Status/DC | In or Out | OLED status pin (SSD1327: D/C select output; GE256X64B: SBUSY input) |
| 6   | 31       | /RESET    | Output    | OLED reset (active low)                                              |
| 8   | 24       | SPI0 CE0  | Output    | OLED /CS                                                             |
| 10  | 19       | SPI0 MOSI | Output    | OLED data in                                                         |
| 11  | 23       | SPI0 SCLK | Output    | OLED clock                                                           |

I2C address defaults: expander `0x20`, air sensor `0x77`, light sensor `0x48`.
SPI0 port: `/dev/spidev0.0`, default clock `2.40 MHz`.

## SX1509 expander pins

The SX1509 is a 16-bit I2C GPIO expander (pins 0–15). All pins are inputs except the LED (pin 6, output).

| Pin | Function        | Notes                                     |
| --- | --------------- | ----------------------------------------- |
| 0   | Knob center     | Input, active low                         |
| 1   | Inner knob A    | Quadrature encoder (A/B pair with pin 2)  |
| 2   | Inner knob B    |                                           |
| 3   | Outer knob A    | Quadrature encoder (A/B pair with pin 4)  |
| 4   | Outer knob B    |                                           |
| 6   | LED             | Output                                    |
| 8   | Joystick center | Input, active low                         |
| 9   | Joystick down   | Input, active low                         |
| 10  | Joystick up     | Input, active low                         |
| 11  | Joystick right  | Input, active low                         |
| 12  | Joystick left   | Input, active low                         |
| 13  | Joy knob A      | Quadrature encoder (A/B pair with pin 14) |
| 14  | Joy knob B      |                                           |
