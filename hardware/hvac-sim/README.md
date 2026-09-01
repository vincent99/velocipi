# HVAC BLE simulator (AC + heater + fuel sensor, combined)

A desktop/Raspberry Pi stand-in for **all three** real BLE peripherals
`../hvac-knob/` (the CrowPanel knob UI) talks to — the AC controller
(`../aircon/`), the parking heater, and the fuel-level sensor
(`../fuel-level/`) — running as one process, one `BlessServer`, one
advertised identity. It advertises the AC's exact GATT service (same
UUIDs, same UTF-8/JSON wire format as `../aircon/`), the heater's exact
GATT service (same UUID, same binary framed protocol), *and* the fuel
sensor's exact two services (standard Bluetooth SIG Battery Service +
`../fuel-level/`'s own custom one) side by side, so the panel can't tell
the difference from the real things over the air. Built on
[`bless`](https://github.com/kevincar/bless), a cross-platform
(macOS/CoreBluetooth, Linux/BlueZ) Python GATT *server* library (the
peripheral-mode counterpart to the more commonly-known `bleak`, which is
central/client-only).

## Why one combined process, not separate ones

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
generally can't, at least not reliably across independent processes. The
fuel sensor joined this same combined process for exactly the same reason
once it existed, rather than getting its own — see
`../hvac-knob/fuel_ble.py`'s own module docstring for how that client
shares its BLE connection/discovery with `AirconClient`/`HeaterClient` the
same way those two already share with each other, needed now that all
three resolve to one BLE address.

One process avoids the question entirely: one `CBPeripheralManager`, one
advertised identity, every device's services registered on it (`bless`
already supports this — `add_new_service()` is a plain dict keyed by
service UUID, and `start()`'s own advertisement-building loop already
iterates every registered service). See `ble_server.py`'s own module
docstring for the implementation.

**If you only ever need a subset of devices simulated at a time**,
`--ac-only`/`--heat-only`/`--no-fuel` (see "Run" below) skip registering
the others' services entirely, so their roller entries won't show up on
the panel's other Connect screens at all.

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

**Fuel half** (new):
- Reports a 0-100% tank level over the standard Bluetooth SIG Battery
  Service (`0x180F`/Battery Level `0x2A19`) plus the raw voltage a real
  sensor would report for it (standard Voltage characteristic, `0x2B18`)
  and the two calibration voltages (custom characteristics) under
  `../fuel-level/`'s own custom service — see `ble_server.py`'s module
  docstring for the exact layout, confirmed against the same Bluetooth SIG
  source `../fuel-level/ble_server.py` itself cites.
- Unlike the real firmware (which treats an ADC-read voltage as the ground
  truth and derives percent from it), this sim has no physical tank to
  read, so `fuel_controller.SimFuelController` treats **percent** as the
  ground truth and derives the voltage a real sensor would report for it
  under the current calibration — see that module's own docstring.
- Drains slowly on its own (`config.DEFAULT_FUEL_DRAIN_PCT_PER_MIN`,
  `--fuel-drain-rate`) purely so the panel's arc/percent readout has
  something to visibly change during a test session, same "watch it move
  over time" idea as the AC half's thermal model — not modeling any real
  consumption rate. `--fuel-drain-rate 0` disables draining entirely.
- Calibration (`Cal Zero Voltage`/`Cal Full Voltage`) is writable over BLE
  the same way the real sensor's is, no `../hvac-knob/` UI for it yet
  (same as that real project) — use a generic BLE tool if you want to
  exercise it.
- What it does **not** simulate: persistence across restarts (calibration
  resets to `config.py`'s defaults each run, unlike the real firmware's
  `storage.py`).

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
  not separate ones" above for exactly what goes wrong if you don't (this
  includes not leaving a stray copy running across sessions; check
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
- Keep any `--name` override reasonably short, and containing `"sim"` as
  its own space/hyphen/edge-delimited word (e.g. `"my-sim"`, not
  `"mysim"`) — see "Run" below and `../hvac-knob/heater_ble.py`'s
  `scan_for_heaters()`/`fuel_ble.py`'s `scan_for_fuel_sensors()`
  docstrings for why. Length itself: not independently re-confirmed
  against this specific combined multi-service advertisement (the
  predecessor `heater-sim/` found empirically that names 10 characters or
  longer weren't reliably found by a real panel's scan on macOS, even when
  `bless` itself logged a clean "did start advertising" for them, and
  every service registered since then only adds more advertisement-budget
  pressure, not less) — trust an actual scan result over that library's
  own internal confidence if you hit this.

## Run

```bash
python3 main.py
python3 main.py --ac-only
python3 main.py --heat-only
python3 main.py --no-fuel
python3 main.py --ac-error "This is a test"
python3 main.py --heat-fault 3
python3 main.py --heat-password 1234
python3 main.py --fuel-percent 40
python3 main.py --fuel-drain-rate 0
python3 main.py --name my-sim
```

Logs every enabled device's state every 5s, and on every BLE
read/write/frame. Ctrl-C to stop. Then point the panel's Connect screens
at it — `AirconClient.scan_for_aircons()` finds the AC half by its service
UUID regardless of advertised name, so it isn't affected by any of this;
`HeaterClient.scan_for_heaters()` and `FuelClient.scan_for_fuel_sensors()`
both find their own half via a dedicated SIM NAME MATCH path — any
advertised name containing `"sim"` as its own space/hyphen/edge-delimited
word (`"HVAC-Sim"`, `"hvac-sim"`, `"HVAC Sim"`, bare `"Sim"` all count;
`"AirSim"`/`"Simulator"` don't) — added specifically so this sim doesn't
need to follow the real heater's own `"BYD-"` naming convention (heater;
the fuel sensor has no real-hardware name convention of its own to match
against in the first place) (see each method's own docstring's SIM NAME
MATCH paragraph; heater's real convention and its FALLBACK service-UUID
match still work too, just aren't what this sim's default identity relies
on).
**Keep any `--name` override containing `"sim"` as its own word** (and
under 10 characters total, same empirical macOS limit as before) or
heater/fuel-sensor discovery both fall back to depending on their own
service UUID surviving the same over-budget advertisement trim that
motivated this in the first place (see `config.py`'s `BLE_DEVICE_NAME`
comment for the byte math) — which is even less likely for the fuel
sensor's own 128-bit custom UUID than it already was for the heater's.

- `--ac-only`/`--heat-only` (mutually exclusive): only register/advertise
  that one device's GATT service (also excludes the fuel sensor — see
  `--no-fuel` below for keeping it while dropping just AC or heat) — the
  others' Connect screens won't find anything at all.
- `--no-fuel`: don't register/advertise the fuel sensor's services, on its
  own (independent of `--ac-only`/`--heat-only`, either of which already
  implies it too).
- `--fuel-percent N` (0-100) sets the simulated tank's starting level
  (default: `config.DEFAULT_FUEL_PERCENT`).
- `--fuel-drain-rate N` (%/minute, `>= 0`) overrides how fast the
  simulated tank drains on its own (default: `config.
  DEFAULT_FUEL_DRAIN_PCT_PER_MIN`) — `0` disables draining entirely.
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
| `config.py` | Constants for all three devices — mirrors `../aircon/config.py`, `../hvac-knob/heater_ble_config.py`, and `../fuel-level/config.py` as plain duplicates (no shared import path from this desktop/RPi CPython process to any of the three MicroPython firmwares). `AC_*`/`HEAT_*`/`FUEL_*` prefixes only where a name would otherwise collide between devices — see its own module docstring. |
| `ac_controller.py` | `SimController`: the AC's mode state machine (ported from `../aircon/controller.py`) plus its thermal model — no real hardware. |
| `heat_controller.py` | `SimHeaterController`: the heater's on/off + `run_mode`/`run_param` state, no thermal model (see its own module docstring for why) and no real hardware. |
| `heat_protocol.py` | The heater's binary frame encode/decode (checksum, header, XOR-obfuscated status) — mirrors `../hvac-knob/heater_ble.py`'s own frame builder/parser exactly, from the peripheral side instead of the central side. |
| `fuel_controller.py` | `SimFuelController`: the fuel sensor's percent/voltage/calibration state — percent is the ground truth here (reverse of the real firmware's voltage-is-ground-truth model, see its own module docstring), no real hardware. |
| `ble_server.py` | `SimBLEServer`: one `bless` GATT server registering every enabled device's services/characteristics and read/write/notify glue — see its own module docstring for why this is one class/one server now instead of separate ones. |
| `main.py` | Entry point: wires all three controllers + the combined server together and runs them, with `--ac-only`/`--heat-only`/`--no-fuel`/`--ac-error`/`--heat-fault`/`--heat-password`/`--fuel-percent`/`--fuel-drain-rate`/`--name` on the command line. |
