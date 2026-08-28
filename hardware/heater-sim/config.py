"""Constants mirrored from ../hvac-knob/heater_ble_config.py -- kept as a
plain duplicate rather than a shared import since the real panel firmware
runs on MicroPython and this runs on desktop/RPi CPython with no shared
import path between them (same reasoning, and same precedent, as
../aircon-sim/config.py's relationship to ../hvac-knob/aircon_ble_config.py).
If you change anything in that file, update this one to match.

Unlike the AirCon side, none of this is "real" in the sense of matching an
actual vendor spec -- it's reconstructed entirely from decompiling the
heater's Android app, no vendor documentation exists at all. See
../hvac-knob/heater_ble_config.py's own module docstring and
../../scratch/airheater-ble-protocol.md for the full story and every "NOT
hardware-verified" caveat that implies. This simulator assumes exactly the
protocol version documented there (called "v2.1" in that doc): `HEAD_1`/
`HEAD_2`-framed, `cmd_1`/`cmd_2`-dispatched, 8-bit sum checksum. Password/
handshake support (`CMD_HANDSHAKE`) is optional and off by default -- see
main.py's `--password` flag and ble_server.py's handling of it.
"""

VERSION = "1.0-sim"

# ── BLE identity -- generic BLE-SIG UUIDs shared with unrelated devices, not
# a fixed device name (see NAME_PREFIX) -- matches
# ../hvac-knob/heater_ble_config.py exactly, since the panel doesn't get
# to pick these, it just filters by name prefix. BLE_DEVICE_NAME below is
# this simulator's *own* choice of a name matching that prefix, analogous
# to ../aircon-sim/config.py's BLE_DEVICE_NAME (which #is# the whole
# identity there, since the AirCon side scans by service UUID + exact name
# rather than a name prefix).
BLE_SVC_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
BLE_CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"  # both notify and write
# <10 characters, deliberately -- confirmed empirically on real hardware
# (not just reasoned about), so trust this over any theory that
# contradicts it. What's actually confirmed:
#   - ../aircon-sim/'s device name ("Air-Sim", 7 chars) + its own service
#     UUID advertised *together* reaches a real ESP32 scan reliably --
#     repeatedly confirmed present in scan_for_heaters()'s own diagnostic
#     log (see heater_ble.py) while testing this exact file.
#   - A long name (>10 chars) with the service UUID dropped from the
#     advertisement -- `bless`'s own default behavior in that range (see
#     below), and the shape this file used briefly -- was *not* found on
#     real hardware, despite `bless` logging a clean, warning-free
#     "did start advertising" for it. So `bless`'s internal "this should
#     be safe" heuristic doesn't fully match what a real external
#     scanner actually receives; don't trust it over an actual scan
#     result.
# So: mirror the AirCon side's proven shape -- short name (<10 chars) +
# service UUID both advertised. This also happens to be `bless`'s own
# default (`BlessServer.start()`'s prioritize_local_name=True only drops
# the service-UUID list when len(name) > 10 -- see bless/backends/
# corebluetooth/server.py) -- but that's incidental; the name length here
# is chosen because it's the one combination actually seen working on
# real hardware, not because it satisfies that library's own heuristic.
# See main.py's --name flag if you want to override it; keep any override
# under 10 characters too.
BLE_DEVICE_NAME = "BYD-Sim"  # <10 chars, deliberately -- see comment above. Starts with NAME_PREFIX, doesn't collide with NAME_EXCLUDE_PREFIXES below
NAME_PREFIX = "BYD-"
NAME_EXCLUDE_PREFIXES = ("BYD-MD-", "BYDOTA-", "BACOTA-")
BLE_NOTIFY_INTERVAL = 2  # seconds -- how often this sim proactively pushes a status frame, connected or not, changed or not

# ── Frame format -- see ../hvac-knob/heater_ble_config.py's own comment
# for the full byte-by-byte layout; protocol.py implements it. ────────────
HEAD_1 = 0xFE
HEAD_2 = 0xAA
PROTOCOL_VERSION = 0

CMD_INFO = 0
SUB_INFO_MAC = 3

CMD_RUN = 1
SUB_RUN_OFF = 0
SUB_RUN_ON = 1

CMD_TIMER = 2

CMD_ATTR = 3
SUB_ATTR_QUERY = 0
SUB_ATTR_WRITE = 1
SUB_ATTR_RESET = 3
SUB_ATTR_ENTER_OTA = 4

CMD_HANDSHAKE = 6
SUB_HANDSHAKE = 0

RUN_MODE_GEAR = 1
RUN_MODE_THERMOSTAT = 2
RUN_MODE_VENT = 3
RUN_MODE_HIGH = 4

HEAT_LEVEL_MIN = 1
HEAT_LEVEL_MAX = 10

THERMOSTAT_TEMP_MIN_C = 8
THERMOSTAT_TEMP_MAX_C = 36

# ── Defaults ────────────────────────────────────────────────────────────
DEFAULT_RUN_MODE = RUN_MODE_GEAR
DEFAULT_RUN_PARAM = HEAT_LEVEL_MIN
