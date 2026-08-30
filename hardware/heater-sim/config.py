"""Constants mirrored from ../hvac-knob/heater_ble_config.py -- kept as a
plain duplicate rather than a shared import since the real panel firmware
runs on MicroPython and this runs on desktop/RPi CPython with no shared
import path between them (same reasoning, and same precedent, as
../aircon-sim/config.py's relationship to ../hvac-knob/aircon_ble_config.py).
If you change anything in that file, update this one to match.

Frame format below is the real "v1" protocol, CONFIRMED against an actual
unit via a BLE capture of the vendor iOS app (see ../hvac-knob/
heater_ble_config.py's own module docstring for the full story) -- this
sim used to speak a different, entirely-decompiled-JS-guessed variant
("v2.1" in ../../scratch/airheater-ble-protocol.md) that turned out to be
the wrong protocol version, never actually built by the real app. If
you're comparing against an old copy of this file, everything below is a
replacement, not a patch.
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

# --- Frame format (v1, app -> device) -------------------------------------
#
# Fixed 8 bytes always -- see ../hvac-knob/heater_ble_config.py's own
# comment for the full byte-by-byte layout; protocol.py implements it.
# Every frame carries the password (bytes 2-3) -- there's no separate
# handshake/login command in this protocol version at all, unlike this
# sim's own earlier (wrong) assumption -- ble_server.py checks it per-frame
# instead of via a dedicated CMD_HANDSHAKE dispatch branch.
HEAD_1 = 0xAA
HEAD_2 = 0x55

CMD_READ = 1  # "readData" -- query/poll; this sim answers with a fresh push
CMD_SET_MODE = 2  # "setMode" -- param1: RUN_MODE_* below
CMD_ON_OFF = 3  # "onOff" -- param1: 1=on, 0=off (no mode/gear/temp payload -- those persist device-side, set separately via CMD_SET_MODE/CMD_SET_GEAR_OR_TEMP)
CMD_SET_GEAR_OR_TEMP = 4  # "setGearOrTemp" -- param1: gear level (RUN_MODE_GEAR) or target temp (RUN_MODE_THERMOSTAT), depending on whatever mode is currently set
# CMD_SET_MODE_DATA(5)/CMD_PUMP_OIL(6)/CMD_SET_TIME(10)/CMD_ENTER_OTA(23)
# exist in the real protocol (see heater_ble_config.py) but the real panel
# client never sends them -- not implemented here either, nothing to
# exercise.

RUN_MODE_GEAR = 1  # "gMode": manual heat-level -- run_param = level (see HEAT_LEVEL_MIN/MAX)
RUN_MODE_THERMOSTAT = 2  # "hMode": constant-temperature -- run_param = target temp, deg C
RUN_MODE_VENT = 3  # "aMode": ventilation only (fan, no heat) -- unused by this codebase
RUN_MODE_HIGH = 4  # "stMode": high-heat boost -- unused by this codebase

# Confirmed against real hardware (see heater_ble_config.py) -- this sim
# matches the real unit's actual gear range.
HEAT_LEVEL_MIN = 1
HEAT_LEVEL_MAX = 10

THERMOSTAT_TEMP_MIN_C = 8
THERMOSTAT_TEMP_MAX_C = 36

# --- Status notification format (v1, device -> app) -----------------------
#
# Fixed 48 bytes, XOR-obfuscated with a repeating 15-byte keystream --
# CONFIRMED against real hardware (two independent captures, diffed against
# the specific command that preceded each push) for the header, on/off,
# and gear; see ../hvac-knob/heater_ble_config.py's own NOTIFY_XOR_KEY
# comment for the full field-by-field confidence breakdown, including
# which bytes move but aren't decoded yet (mode, temperature) -- this sim
# does NOT attempt to simulate those. NOTIFY_OFF_FAULT is a best guess, not
# confirmed (see that constant's own comment there) -- included here
# anyway so --fault has something to exercise on the panel side.
NOTIFY_XOR_KEY = b"passwordA2409PW"
NOTIFY_LEN = 48
NOTIFY_OFF_ON = 3
NOTIFY_OFF_FAULT = 4
NOTIFY_OFF_GEAR = 5

# ── Defaults ────────────────────────────────────────────────────────────
DEFAULT_RUN_MODE = RUN_MODE_GEAR
DEFAULT_RUN_PARAM = HEAT_LEVEL_MIN
