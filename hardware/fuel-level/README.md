# fuel-level

A BLE peripheral for the parking heater's fuel tank level. Reads one
analog voltage (0-3.3V) from a resistive fuel sender via an ADC pin on a
generic ESP32-S3, converts it to a 0-100% level using a two-point
calibration, and serves both over BLE using standard Bluetooth SIG
characteristics where possible (see "GATT layout" below) so any generic
BLE client -- not just [../hvac-knob/](../hvac-knob/) -- can read it
meaningfully with zero custom parsing.

Unlike [../hvac-knob/](../hvac-knob/), this runs on stock MicroPython, not
a custom LVGL build -- there's no display here, just an ADC read and a BLE
server.

## Hardware

- Board: any generic ESP32-S3 dev board.
- Sensor input: `config.PIN_FUEL_ADC` (default GPIO4), one of the
  ESP32-S3's ADC1 pins (GPIO1-10 -- ADC2, GPIO11-20, isn't usable while
  WiFi is active on this port; ADC1 is used regardless since this project
  has no WiFi need today, just to avoid a future footgun).
- Wiring: a resistive fuel sender is a variable resistor (a float arm
  moves a wiper across a rheostat), not a voltage source on its own -- it
  needs to be wired as one leg of a voltage divider (sender + a fixed
  resistor to 3.3V/GND, wiper -> the ADC pin) to actually produce a
  voltage swing. The exact divider resistor value depends on the specific
  sender's resistance range (not specified here -- pick one that centers
  the sender's real resistance swing somewhere in the ADC's usable range,
  then use the calibration characteristics below to dial in the actual
  endpoints regardless of exactly where they land).

## Setup

1. Flash a stock MicroPython build for the ESP32-S3 -- see
   [micropython.org's download page for the `ESP32_GENERIC_S3` board](https://micropython.org/download/ESP32_GENERIC_S3/)
   -- with `make flash FIRMWARE=path/to/that.bin` (edit the Makefile's
   `FIRMWARE` default, or pass it on the command line; `esptool.py` must be
   on `PATH`).
2. `make install-aioble` (one-time, installs the `aioble` library onto the
   device's filesystem via `mip`).
3. `make sync` to copy this project's `.py` files over, then `make reset`
   (or just `make dev`, which does both).
4. Watch `make repl` for `fuel-level: starting, version ...` and
   `ble: advertising` to confirm it's up.

## GATT layout

```
Battery Service (0x180F)
  Battery Level (0x2A19)         r, notify   uint8, 0-100 (%)

Fuel Level service (custom, config.BLE_SVC_UUID)
  Voltage (0x2B18)                r, notify   uint16 LE, 1/64 V units
  Cal Zero Voltage (custom)       rw          uint16 LE, 1/64 V units -- voltage read as 0%
  Cal Full Voltage (custom)       rw          uint16 LE, 1/64 V units -- voltage read as 100%
```

`Battery Level` and `Voltage` are both real Bluetooth SIG-assigned
characteristics (`org.bluetooth.characteristic.battery_level` /
`org.bluetooth.characteristic.voltage`), confirmed against the SIG's own
public GATT Specification Supplement source
(`bitbucket.org/bluetooth-SIG/public`) -- not just guessed from the UUID's
name. A generic BLE scanner app (nRF Connect, LightBlue, ...) will decode
both correctly without this project needing to publish or document its own
format for them. `Battery Level` is the one characteristic
[../hvac-knob/](../hvac-knob/) (or anything else) actually needs to read to
show a fuel percentage; `Voltage` is the pre-calibration raw reading, handy
for sanity-checking calibration itself. See `ble_server.py`'s own module
docstring for the exact byte encoding and why the two calibration
characteristics -- which have no Bluetooth-SIG-standard home at all -- reuse
that same encoding anyway, just for consistency.

## Calibration

`Cal Zero Voltage`/`Cal Full Voltage` are the voltages (in the same
uint16/1-64V-units wire format as `Voltage`) the sensor should treat as
0%/100% tank level -- they default to 0.0V/3.3V (the ADC's own nominal full
range) until set, and persist to flash (`config.STORAGE_FILE`) once
written. To calibrate against a real tank:

1. Drain (or otherwise get to) the tank's real empty point, let the
   reading settle, read `Voltage`, and write that same value to
   `Cal Zero Voltage`.
2. Fill to the real full point, read `Voltage` again, and write it to
   `Cal Full Voltage`.

Any BLE client that can write raw bytes to a characteristic works for this
(nRF Connect's "write value" on each characteristic, a short script against
`bleak`/`aioble`/similar, ...) -- there's no dedicated calibration UI in
this repo yet.
