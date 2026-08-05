# AirCon BLE simulator

A desktop/Raspberry Pi stand-in for the real RP2350 AC controller
(`../aircon/`), for testing `../aircon-knob/` (the CrowPanel knob UI) without
the physical AC hardware. It advertises the **exact same BLE GATT
service** — same device name, same service/characteristic UUIDs, same
UTF-8/JSON wire format — so the panel can't tell the difference from the
real thing over the air. Built on [`bless`](https://github.com/kevincar/bless),
a cross-platform (macOS/CoreBluetooth, Linux/BlueZ) Python GATT *server*
library (the peripheral-mode counterpart to the more commonly-known `bleak`,
which is central/client-only).

## What it simulates

- The full mode/fan/setpoint/circulation/settings read-write surface, and
  the same `off`/`fan`/`auto`/`cool` mode semantics as `../aircon/controller.py`
  — including auto mode's compressor hysteresis and 3-step fan speed logic,
  ported directly from that file.
- **Temperature**: 5 simulated probes (cabin/blower/exhaust/baggage/tail)
  each exponentially approach a target that depends only on whether the
  compressor is on — a cooling floor (55°F default) when it's running, an
  ambient ceiling (88°F default) when it's not — so turning the AC on visibly
  cools the cabin over the next several minutes, and it drifts back up
  (**up to that ceiling, not past it**) once it's off. Vent-adjacent probes
  (blower/exhaust) move faster than back-of-cabin ones (baggage/tail), like
  a real vehicle. See `controller.py`'s module docstring and the
  `COOLING_FLOOR`/`AMBIENT_CEILING`/`PROBE_RATES` constants if you want a
  faster demo or a different starting temperature.
- What it does **not** simulate: relays, the servo, the compressor's PWM
  monitor, or persistence across restarts (state resets to
  `config.py`'s defaults each run).

## Setup

```bash
cd hardware/aircon-sim
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Platform notes

- **macOS**: the first run will prompt for Bluetooth permission for your
  terminal/Python — grant it (System Settings ▸ Privacy & Security ▸
  Bluetooth), or the server never advertises. `bless`'s CoreBluetooth
  backend runs its callbacks on a background thread, which `ble_server.py`
  accounts for (see its module docstring). **Note:** a Mac generally can't
  discover its own advertised peripheral via its own central/scan session
  (a CoreBluetooth restriction, confirmed while building this — the server
  advertises fine, but a `bleak` scan from the same machine simply never
  sees it). Test from a second device — which is the real use case anyway,
  i.e. the physical CrowPanel running `../aircon-knob/`.
- **Raspberry Pi / Linux**: `bless` talks to `bluetoothd` over D-Bus
  (BlueZ). If advertising fails with a D-Bus permission error, the quickest
  fix is running as root: `sudo $(which python3) main.py` (inside the venv,
  so it still finds `bless`) — or configure a D-Bus policy / capabilities
  for your user if you'd rather not sudo. Make sure `bluetoothd` is running
  (`systemctl status bluetooth`) and the adapter is powered
  (`bluetoothctl power on`).
- Only one thing can advertise a given BLE peripheral's identity at a time —
  don't run this alongside the real AC controller on the same channel/name,
  and if the Pi's main `velocipi` server is also configured with an AirCon
  section, it'll try to connect as a *central* to whatever's advertising as
  `"AirCon"`, real or simulated.

## Run

```bash
python3 main.py
```

Logs the state every 5s, and on every BLE read/write. Ctrl-C to stop. Then
point `../aircon-knob/`'s firmware at it — `ble_config.py` there already
matches this simulator's `config.py` by default (same device name, same
UUIDs) — and it should connect, show live values, and respond to knob/touch
input exactly like the real controller would.

## Files

Deliberately parallels the real firmware's layout so it's easy to
cross-reference:

| File | Purpose |
| --- | --- |
| `config.py` | Same constants as `../aircon/config.py` (UUIDs, defaults) — kept as a plain duplicate since the two run on different Python runtimes with no shared import path. |
| `controller.py` | `SimController`: the mode state machine (ported from `../aircon/controller.py`) plus the thermal model — no real hardware. |
| `ble_server.py` | `SimBLEServer`: the `bless` GATT service/characteristic setup and read/write/notify glue — the `bless` analog of `../aircon/ble_server.py`'s `aioble` usage. |
| `main.py` | Entry point: wires the two together and runs them. |
