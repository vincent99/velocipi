# AirHeaterBLE protocol notes

Reverse-engineered from `airHeaterByBLE.apk` (a uni-app/DCloud hybrid app; JS
business logic lives unminified-enough at
`assets/apps/__UNI__9A3735B/www/app-service.js`, which retains original
source file path comments in every log call — that's what made this
tractable). App package: `com.clj.airheater`. Manufacturer bitmask in the
protocol explicitly lists this app under brand id bit 0 alongside "Booyood",
so this is very likely your device's exact protocol.

## Transport

- Classic BLE GATT (not HOGP/mesh). Device advertises a name with prefix
  `BYD-` (app's scan filter also recognizes `BYD-MD-`, `BYDOTA-`, `BACOTA-`,
  `BAC-`).
- Primary control service/characteristic (single characteristic used for
  both notify-subscribe and write, HM-10/UART-bridge style):
  - Service: `0000FFE0-0000-1000-8000-00805F9B34FB`
  - Characteristic (notify + write): `0000FFE1-0000-1000-8000-00805F9B34FB`
- Two secondary services exist, only relevant for firmware OTA, not normal
  control:
  - `0000FFF0` / notify `FFF1` / write `FFF2` — YMODEM-over-BLE firmware
    transfer (SOH/STX framing, CRC16-CCITT, standard YMODEM).
  - `0000FEE0` / `FEE1` — alternate OTA service.
- App requests MTU 247 on Android (iOS keeps default).

## Frame format (v2.1 protocol — what this app actively speaks)

```
byte 0    : 0xFE                    (head_1, fixed)
byte 1    : 0xAA                    (head_2, fixed)
byte 2    : version_num             (0 = normal heater, 10 = "ac"/heat-pump variant)
byte 3    : package_num             (sequence number, 0 for non-segmented)
byte 4-5  : total_length, uint16 LE (length of the header+payload region)
byte 6    : cmd_1                   (command family; device echoes cmd_1+128 in its response/ack)
byte 7    : cmd_2                   (sub-command)
byte 8..N : payload                 (cmd-specific, see below)
byte N+1  : checksum                (8-bit sum of bytes 0..N, mod 256)
```

Checksum implementation (`Sc` in the bundle):
```js
function checksum(buf) {           // buf.length includes the checksum byte slot
  let sum = 0;
  for (let i = 0; i < buf.length - 1; i++) sum += buf[i];
  buf[buf.length - 1] = sum & 0xFF;
}
```

Optional password/XOR layer: if the device has a password set, the app
additionally XORs the frame bytes with a repeating keystream derived from a
password string (function `gc`/`hc`), default all-frames key
`"passwordA2409PW"` combined with the per-device password on top. This is
only relevant if your unit is password-protected (most consumer units
ship without one — verify empirically).

There is also an older "v1" protocol the app still knows how to *parse*
(not build) for legacy hardware: frames start `0xAA, 0x55|0x66, cmd, ...`
with cmd meaning `{0/1:"readData", 2:"setMode", 3:"onOff", 4:"setGearOrTemp",
5:"setModeData", 6:"pumpOil", 10:"setTime", ..., 23:"enterOTA"}`. If your
device turns out to speak this instead (no 0xFE 0xAA header in notifications),
say so and I'll dig further — the app has no outgoing builder for it, so I
haven't fully reconstructed the write side.

## Command families (byte 6 = cmd_1, byte 7 = cmd_2)

| cmd_1 | cmd_2 | Meaning | Payload |
|---|---|---|---|
| 6 | 0 | Handshake / password auth | `password` as 2 bytes (`pw%100`, `pw/100`) at offset 8 when applicable |
| 0 | 3 | Read device info (MAC/HW/SW version, part number, key_mode/manufacturer bitmask) | none (query) |
| 1 | 0 | **Power OFF** | none — send header only, no payload |
| 1 | 1 | **Power ON** with run params (non-AC): `run_mode`(1B), `run_param`(1B, gear or temp), `remain_run_time`(uint16 LE); (AC/heat-pump variant, version_num=10): `run_mode`(1B), `set_temp`(int16 LE, °C×10), `fan_speed`(1B), `run_time_remaining`(uint16 LE) | see left |
| 1 | 3 | Change run_mode only while running (AC variant) | `run_mode` etc, same shape as 1/1 |
| 2 | 0 | Query timers | none |
| 2 | 2 | Write timer(s) | `timer_total`, `[timer_index]`, then per-timer: `is_enabled, week(bitmask), start_h, start_m, run_time_m(u16)`(or `end_h/end_m`)`, run_mode, run_param/set_temp, [fan_speed]` |
| 3 | 0/1/2 | Query general attributes (altitude_unit, temp_unit, time, temp_comp, broadcast_language, oil_volume, pump_model, back_light, startup/shutdown_temp_difference, wifi, i_stop) — or AC-specific attribute block | none (query) |
| 3 | 1 | Write attributes | same field layout as the query above |
| 3 | 3 | Factory reset | none |
| 3 | 4 | Enter OTA mode | none |
| 4 | 0/1 | WiFi config query/write (JSON payload, only relevant if unit has a WiFi module) | JSON string |
| 224 (0xE0) | 0/1/2 | OTA control (2 = exit OTA) | — |
| 240 (0xF0) | 0-3 | APN/module settings (JSON / binary+string blob) | — |
| 242 (0xF2) | 0 | TLV-segmented info block (`{cid,len,data}` list) | — |

Response frames use the same header shape; cmd_1 comes back as
`cmd_1 + 128` (e.g. a power command ack has byte 6 = `129`).

## Concrete confirmed flows (traced from actual UI call sites)

**Power on** (`fu()` in bundle, called from the heater control page):
```
header: FE AA <ver> 00 <len_lo> <len_hi> 01 01
payload @ offset 8: run_mode(1B), set_temp_or_gear(1-2B), fan_speed(1B, AC only), run_time_remaining(2B LE)
+ checksum
```

**Power off** (`yu()`):
```
FE AA <ver> 00 <len_lo> <len_hi> 01 00 <checksum>
```
(no payload — just the 9-byte header+checksum frame)

**Adjust while running** (change temp/gear/fan/timer without a full
power-cycle): resend the cmd_1=1 frame (cmd_2=1 if on) with the current
full state, updating only the one field you're changing — the app always
sends the complete `{run_mode, set_temp, fan_speed, run_time_remaining}`
struct each time, never a delta.

**Read live status**: subscribe to notifications on FFE1 after connecting;
the device streams unsolicited status frames matching cmd_1=1 (`run_state`
family, see the parse tables in `normalData.js`/`ac/normalData.js` byte
offsets) — you don't need to poll.

## What I couldn't confirm without real hardware

- Whether your specific unit uses the v1 or v2.1 wire format (both share
  the FFE0/FFE1 UUIDs, so you can't tell from advertising alone).
- Whether your unit has a password set (affects whether the XOR layer
  applies).
- Exact `run_mode` enum values (gear mode vs. constant-temp mode vs.
  ventilation — the app derives the button list from a capability bitmask
  read from the device, `key_mode` at cmd 0/3, rather than hardcoding it).

The fastest way to nail these down is to capture one real session: pair the
Android phone + app to the heater, enable Android's Bluetooth HCI snoop log
(Developer Options → "Enable Bluetooth HCI snoop log"), operate the heater
through the app (power on, change temp, power off), then pull
`/sdcard/btsnoop_hci.log` and open it in Wireshark. That'll confirm the
exact header byte, cmd values, and payload layout your unit actually uses
in about five minutes, versus me guessing further from static analysis.
