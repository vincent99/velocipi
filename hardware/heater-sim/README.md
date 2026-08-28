# Heater BLE simulator

A desktop/Raspberry Pi stand-in for the real BLE parking heater, for testing
`../hvac-knob/`'s "heat" mode and "auto" mode's heating branch (see that
project's `screens/home.py`) without the physical heater. Advertises a name
matching the same prefix (`"BYD-"`) the real thing does and speaks the same
binary framed protocol (see `protocol.py`), so `../hvac-knob/heater_ble.py`
can't tell the difference from the real thing over the air. Built on
[`bless`](https://github.com/kevincar/bless), the same cross-platform
(macOS/CoreBluetooth, Linux/BlueZ) Python GATT *server* library
`../aircon-sim/` uses.

**Unlike `../aircon-sim/`**, this protocol isn't documented anywhere by the
vendor — it was reconstructed entirely by decompiling the heater's Android
app. See `../hvac-knob/heater_ble_config.py`'s module docstring and
`../../scratch/airheater-ble-protocol.md` for the full story and every "NOT
hardware-verified" caveat that implies. This simulator assumes exactly the
protocol variant documented there: the "v2.1" frame format, one
read/write/notify characteristic instead of one per field. Password/
handshake support (`CMD_HANDSHAKE`) is real but optional — see `--password`
in "Run" below.

## What it simulates

- The full power-on/off + `run_mode`/`run_param` command surface
  (`../hvac-knob/heater_ble_config.py`'s `RUN_MODE_GEAR` for `screens/
  home.py`'s "heat" mode, `RUN_MODE_THERMOSTAT` for "auto" mode's heating
  branch) — logs every frame it receives and applies it to an in-memory
  `SimHeaterController`.
- A status frame pushed back on every state change (and once every
  `config.BLE_NOTIFY_INTERVAL` regardless, so a connected panel shows signs
  of life even if you never touch the knob), encoding `now_gear`/
  `fault_code`/`run_mode`/`run_param` at the same byte offsets the real
  protocol uses.
- What it does **not** simulate: any temperature/thermal response. Unlike
  the AirCon simulator (whose cabin temp is what `screens/home.py`'s auto
  mode actually reads to decide whether to heat in the first place), the
  panel's heater client doesn't consume any temperature field from this
  device *at all* — only `now_gear`/`fault_code`, purely for display (see
  `heater_ble.py`'s `_apply_notification()`) — so there'd be nothing on the
  panel side for a thermal model here to exercise. See `controller.py`'s
  module docstring if you extend `heater_ble.py` to read more of the
  status frame later.
- The password/handshake path (`CMD_HANDSHAKE`) — off by default (no
  `--password` flag given), in which case it deliberately does **not**
  respond to a handshake attempt at all, matching how most real units
  apparently behave and exercising `../hvac-knob/heater_ble.py`'s "no
  response at all -> assume no password gate" detection heuristic (see
  that module's own docstring, point 3). Pass `--password NNNN` to make
  this sim require that exact 4-digit PIN instead — it'll then explicitly
  accept or reject each attempt, for testing `../hvac-knob/screens/
  heater_password.py`'s entry screen end-to-end (including a wrong-then-
  right sequence).
- Still not simulated: MAC/version/capability queries (`CMD_INFO`) and
  attribute queries (`CMD_ATTR`) — logged but not implemented, since
  `heater_ble.py`'s client never sends either (it has no read-back path at
  all, see that module's own docstring).

## Testing the full "auto mode heats when setpoint > cabin" behavior

This simulator only proves the panel sends the *right commands* to the
heater — it has no cabin temperature of its own. To see `screens/home.py`'s
auto-mode heating branch actually trigger, run `../aircon-sim/` at the same
time (its `cabin_temp` is what that logic compares the setpoint against)
and turn the knob's setpoint above whatever `../aircon-sim/`'s current cabin
temp is. Both sims can run simultaneously and advertise independently —
they're unrelated BLE peripherals, exactly like the real hardware.

## Setup

```bash
cd hardware/heater-sim
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Platform notes

Mostly the same as `../aircon-sim/README.md`'s, plus one real divergence
(the name-length note below) that doesn't apply there the same way:

- **macOS**: the first run will prompt for Bluetooth permission for your
  terminal/Python — grant it (System Settings ▸ Privacy & Security ▸
  Bluetooth), or the server never advertises. A Mac generally can't
  discover its own advertised peripheral via its own central/scan session
  — test from a second device, i.e. the physical CrowPanel running
  `../hvac-knob/` (or its own `../hvac-knob/` running against a
  desktop `aioble` port, if you have one set up). This also means you
  can't use another local BLE central library (`bleak`, etc.) on the same
  Mac to double-check what this sim is actually advertising — it won't see
  it either, for the same reason, so don't read anything into that if you
  try it.
- **macOS, specifically for this sim** (confirmed empirically against a
  real ESP32 panel, after two theories reasoned from `bless`'s own source
  and macOS forum reports both turned out wrong or incomplete -- see
  `config.py`'s `BLE_DEVICE_NAME` comment for the full history): keep the
  name **under 10 characters**. `../aircon-sim/`'s name ("Air-Sim", 7
  chars) advertised *together with* its service UUID is the one
  configuration actually confirmed reaching a real panel's scan reliably
  -- a longer name (with the service UUID correctly, deliberately omitted
  from the advertisement by `bless`'s own default logic, and `bless`
  itself logging a clean, warning-free "did start advertising" for it)
  was tried and did **not** get found. So `bless`'s internal assessment of
  what's "safe" doesn't reliably predict what an external scanner actually
  receives here -- trust an actual scan result over that library's own
  warnings. This sim is only ever found by name *prefix*
  (`config.NAME_PREFIX`, `"BYD-"`); a mismatch here means the panel's
  Connect screen never finds it at all, with nothing to suggest why (this
  sim logs "advertising" just fine regardless; the failure is entirely on
  the scanning side, silently). `config.BLE_DEVICE_NAME`'s default
  (`"BYD-Sim"`, 7 characters) is already under the threshold; keep any
  `--name` override under 10 characters too if you're on macOS (`main.py`
  warns if you don't). Not a concern on Linux/BlueZ, and not a concern for
  a real heater either — this is purely a `bless`-on-macOS
  peripheral-advertising artifact, nothing to do with the real device or
  protocol.
- **Raspberry Pi / Linux**: `bless` talks to `bluetoothd` over D-Bus
  (BlueZ). If advertising fails with a D-Bus permission error, run as root:
  `sudo $(which python3) main.py` (inside the venv) — or configure a D-Bus
  policy/capabilities for your user instead. Make sure `bluetoothd` is
  running and the adapter is powered (`bluetoothctl power on`).
- Only one thing can advertise as this device's identity at a time — don't
  run two copies of this at once, and if you're also running
  `../aircon-sim/` on the same machine, that's fine (different service
  UUID, different advertised name), just don't run either one twice.
- If you're running this on the *same* machine as `../aircon-sim/`, note
  `../hvac-knob/README.md`'s "Still open" caveat about whether the
  panel's own BLE stack can hold two central connections open at once —
  that's about the *panel's* radio, not this simulator's, so it doesn't
  affect running both sims here, only whether a real panel can stay
  connected to both simultaneously.

## Run

```bash
python3 main.py
```

Logs the state every 5s, and on every BLE read/write/frame. Ctrl-C to stop.
Then, on the panel: once the AirCon connects, its heater Connect screen
comes up automatically the first time (see `../hvac-knob/README.md`'s
"Connect / Disconnected screens") — scan will find `"BYD-Sim"` (or
whatever `--name`/`config.BLE_DEVICE_NAME` is set to — see "Platform
notes" above before lengthening it on macOS) in its roller; pick it like
any other heater. Unlike `../aircon-sim/`, there's no config file on the
panel side to point at this in advance — the whole point of the real
protocol's name-prefix scan is that the panel doesn't know the heater's
exact name ahead of time either.

`--fault N` seeds `state.fault_code` with a nonzero value at startup, for
testing the notification-driven `fault_code` plumbing — `screens/home.py`
doesn't currently display it anywhere, so this is only useful for watching
this sim's own log line and confirming the value round-trips into
`heater_ble.HeaterState.fault_code` (e.g. over `make repl`), not yet for
seeing anything change on-screen.

`--password NNNN` (0-9999) makes this sim require that PIN before
accepting a handshake — the panel should show its
`screens.heater_password.HeaterPasswordTile` entry screen once it connects
(`../hvac-knob/README.md`'s "Password screen"), and this sim's own log
line shows each attempted candidate and whether it was accepted or
rejected. Omit entirely (the default) to simulate a unit with no password
at all — see "What it simulates" above for why that's silence, not an
automatic accept.

`--name NAME` overrides `config.BLE_DEVICE_NAME` — must start with
`config.NAME_PREFIX` (`"BYD-"`) or the panel will never find it at all;
rejected outright (not just warned) if it doesn't. Warns (doesn't reject)
if it's 10 characters or more, since that's only fatal on macOS
specifically — see "Platform notes" above.

## Files

Deliberately parallels `../aircon-sim/`'s layout, with one addition
(`protocol.py`) this protocol's binary framing needs and that one didn't:

| File | Purpose |
| --- | --- |
| `config.py` | Same constants as `../hvac-knob/heater_ble_config.py` (UUIDs, name prefix, frame/command constants) — kept as a plain duplicate since the two run on different Python runtimes with no shared import path. |
| `protocol.py` | Frame encode/decode (checksum, header, the `cmd1+128` response convention) — mirrors `../hvac-knob/heater_ble.py`'s own frame builder/parser exactly, from the peripheral side instead of the central side. Split out from `ble_server.py` (unlike `../aircon-sim/`, which inlines its much simpler UTF-8/float codecs directly) since this protocol's framing is meaningfully more involved than a plain string/float encode. |
| `controller.py` | `SimHeaterController`: on/off + `run_mode`/`run_param` state, no thermal model (see this file's own module docstring for why) and no real hardware. |
| `ble_server.py` | `SimBLEServer`: the `bless` GATT service/characteristic setup (one characteristic, not seven) and write-dispatch/notify-push glue — the `bless` analog of `../hvac-knob/heater_ble.py`'s `aioble` usage. |
| `main.py` | Entry point: wires the two together and runs them. |
