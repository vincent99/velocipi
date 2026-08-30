# HVAC BLE simulator (AC + heater, combined)

A desktop/Raspberry Pi stand-in for **both** real BLE peripherals
`../hvac-knob/` (the CrowPanel knob UI) talks to — the AC controller
(`../aircon/`) and the parking heater — running as one process, one
`BlessServer`, one advertised identity. It advertises the AC's exact GATT
service (same UUIDs, same UTF-8/JSON wire format as `../aircon/`) *and* the
heater's exact GATT service (same UUID, same binary framed protocol) side
by side, so the panel can't tell the difference from the real things over
the air. Built on [`bless`](https://github.com/kevincar/bless), a
cross-platform (macOS/CoreBluetooth, Linux/BlueZ) Python GATT *server*
library (the peripheral-mode counterpart to the more commonly-known
`bleak`, which is central/client-only).

## Why one combined process, not two separate ones

This replaces what used to be two independent simulators, `aircon-sim/`
and `heater-sim/` (see git history) — each ran as its own process with its
own `BlessServer`/`CBPeripheralManager`, and each logged a clean "did start
advertising" when run alone. Running **both at once**, though, only one of
them actually reached the air at a time — confirmed with a live `bleak`
scan on the same Mac finding neither, and separately confirmed a stray
second copy of one of them (left running from a previous session) was
enough on its own to make a *fresh* copy of the other invisible too. Each
process's own bless/CoreBluetooth success callback only reflects that
process's local peripheral-manager state — it has no visibility into
whether the OS's shared Bluetooth radio can actually broadcast a second,
simultaneous peripheral identity alongside it. A single Mac's radio
generally can't, at least not reliably across independent processes.

One process avoids the question entirely: one `CBPeripheralManager`, one
advertised identity, both GATT services registered on it (`bless` already
supports this — `add_new_service()` is a plain dict keyed by service UUID,
and `start()`'s own advertisement-building loop already iterates every
registered service). See `ble_server.py`'s own module docstring for the
implementation.

**If you only ever need one device simulated at a time**, `--ac-only`/
`--heat-only` (see "Run" below) skip registering the other one's service
entirely, so its roller entry won't show up on the panel's other Connect
screen at all.

## What it simulates

**AC half** (was `aircon-sim/`):
- The full mode/fan/setpoint/circulation/settings read-write surface, and
  the same `off`/`fan`/`auto`/`cool` mode semantics as
  `../aircon/controller.py` — including auto mode's compressor hysteresis
  and 3-step fan speed logic, ported directly from that file.
- **Temperature**: 5 simulated probes (cabin/blower/exhaust/baggage/tail)
  each exponentially approach a target that depends only on whether the
  compressor is on — a cooling floor (55°F default) when it's running, an
  ambient ceiling (88°F default) when it's not — so turning the AC on
  visibly cools the cabin over the next several minutes, and it drifts
  back up (**up to that ceiling, not past it**) once it's off. Vent-
  adjacent probes (blower/exhaust) move faster than back-of-cabin ones
  (baggage/tail), like a real vehicle. See `ac_controller.py`'s module
  docstring and the `COOLING_FLOOR`/`AMBIENT_CEILING`/`PROBE_RATES`
  constants if you want a faster demo or a different starting temperature.
- What it does **not** simulate: relays, the servo, the compressor's PWM
  monitor, or persistence across restarts (state resets to `config.py`'s
  defaults each run).

**Heater half** (was `heater-sim/`):
- The full power-on/off + `run_mode`/`run_param` command surface
  (`../hvac-knob/heater_ble_config.py`'s `RUN_MODE_GEAR` for
  `screens/home.py`'s "heat" mode, `RUN_MODE_THERMOSTAT` for "heat_auto"
  mode) — logs every frame it receives and applies it to an in-memory
  `SimHeaterController`.
- A status frame pushed back on every state change (and once every
  `config.HEAT_NOTIFY_INTERVAL` regardless, so a connected panel shows
  signs of life even if you never touch the knob), encoding `now_gear`/
  `fault_code`/on-off at the same byte offsets the real protocol uses (see
  `../hvac-knob/heater_ble_config.py`'s `NOTIFY_XOR_KEY` comment for
  exactly what's confirmed vs. not).
- What it does **not** simulate: any temperature/thermal response — unlike
  the AC half (whose cabin temp `screens/home.py`'s heat_auto mode
  actually reads), the panel's heater client doesn't consume any
  temperature field from this device at all today, only `now_gear`/
  `fault_code`, purely for display.
- Password support: off by default (every frame accepted regardless of
  its embedded password bytes). Pass `--heat-password NNNN` to make this
  sim require that exact 4-digit PIN instead, for testing
  `../hvac-knob/screens/heater_password.py`'s entry screen end-to-end.

## Setup

```bash
cd hardware/hvac-sim
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Platform notes

- **macOS**: the first run will prompt for Bluetooth permission for your
  terminal/Python — grant it (System Settings ▸ Privacy & Security ▸
  Bluetooth), or the server never advertises. `bless`'s CoreBluetooth
  backend runs its callbacks on a background thread, which `ble_server.py`
  accounts for (see its module docstring).
- **Only run one copy of this at a time** — see "Why one combined process,
  not two separate ones" above for exactly what goes wrong if you don't
  (this includes not leaving a stray copy running across sessions; check
  `ps aux | grep hvac-sim` if something that used to work suddenly stops
  being found).
- **Raspberry Pi / Linux**: `bless` talks to `bluetoothd` over D-Bus
  (BlueZ). If advertising fails with a D-Bus permission error, the
  quickest fix is running as root: `sudo $(which python3) main.py` (inside
  the venv, so it still finds `bless`) — or configure a D-Bus policy /
  capabilities for your user if you'd rather not sudo. Make sure
  `bluetoothd` is running (`systemctl status bluetooth`) and the adapter
  is powered (`bluetoothctl power on`).
- Don't run this alongside the real AC controller or a real heater on the
  same channel/name — and if the Pi's main `velocipi` server is also
  configured with an AirCon section, it'll try to connect as a *central*
  to whatever's advertising the AC's service UUID, real or simulated.
- Keep any `--name` override reasonably short. Not independently
  re-confirmed against this specific combined two-service advertisement
  (the predecessor `heater-sim/` found empirically that names 10
  characters or longer weren't reliably found by a real panel's scan on
  macOS, even when `bless` itself logged a clean "did start advertising"
  for them) — trust an actual scan result over that library's own
  internal confidence if you hit this.

## Run

```bash
python3 main.py
python3 main.py --ac-only
python3 main.py --heat-only
python3 main.py --ac-error "This is a test"
python3 main.py --heat-fault 3
python3 main.py --heat-password 1234
python3 main.py --name HVAC-2
```

Logs both halves' state every 5s (whichever are enabled), and on every BLE
read/write/frame. Ctrl-C to stop. Then point the panel's Connect screens
at it — `AirconClient.scan_for_aircons()` finds the AC half by its service
UUID regardless of advertised name; `HeaterClient.scan_for_heaters()`
finds the heater half either by name prefix (`"BYD-"`, which this sim's
default name deliberately does *not* start with — see `config.py`'s
`BLE_DEVICE_NAME` comment) or by falling back to the heater's own service
UUID directly (see that method's own docstring's FALLBACK paragraph) —
either way, it should show up in the Heater Connect screen's roller under
whatever `--name`/`config.BLE_DEVICE_NAME` this sim is advertising as.

- `--ac-only`/`--heat-only` (mutually exclusive): only register/advertise
  that one device's GATT service — the other one's Connect screen won't
  find anything at all.
- `--ac-error MSG` seeds the AC's `state.error` at startup, for testing
  the knob's error display (red current-temp background, Info screen's
  error text).
- `--heat-fault N` seeds the heater's `state.fault_code` at startup, for
  testing the same error display's heater-fault branch (see
  `screens/home.py`'s `refresh()` and `screens/info.py`).
- `--heat-password NNNN` (0-9999) makes the heater half require that PIN
  — the panel should show its `screens.heater_password.HeaterPasswordTile`
  entry screen once it connects. Omit entirely (the default) for a heater
  with no password at all.
- `--name NAME` overrides `config.BLE_DEVICE_NAME` for the one combined
  advertised identity (see "Platform notes" above before lengthening it
  on macOS).

## Testing the full "heat_auto heats when target > cabin" behavior

The heater half has no cabin temperature of its own — `screens/home.py`'s
`heat_auto` mode compares its target against the AC half's `cabin_temp`,
so run both together (the default, no `--ac-only`/`--heat-only`) and turn
the knob's heat_auto target above whatever the AC half's current cabin
temp is.

## Files

| File | Purpose |
| --- | --- |
| `config.py` | Constants for both halves — mirrors `../aircon/config.py` and `../hvac-knob/heater_ble_config.py` as plain duplicates (no shared import path from this desktop/RPi CPython process to either MicroPython firmware). `AC_*`/`HEAT_*` prefixes only where a name would otherwise collide between the two devices — see its own module docstring. |
| `ac_controller.py` | `SimController`: the AC's mode state machine (ported from `../aircon/controller.py`) plus its thermal model — no real hardware. |
| `heat_controller.py` | `SimHeaterController`: the heater's on/off + `run_mode`/`run_param` state, no thermal model (see its own module docstring for why) and no real hardware. |
| `heat_protocol.py` | The heater's binary frame encode/decode (checksum, header, XOR-obfuscated status) — mirrors `../hvac-knob/heater_ble.py`'s own frame builder/parser exactly, from the peripheral side instead of the central side. |
| `ble_server.py` | `SimBLEServer`: one `bless` GATT server registering both devices' services/characteristics (when enabled) and both devices' read/write/notify glue — see its own module docstring for why this is one class/one server now instead of two. |
| `main.py` | Entry point: wires both controllers + the combined server together and runs them, with `--ac-only`/`--heat-only`/`--ac-error`/`--heat-fault`/`--heat-password`/`--name` on the command line. |
