"""Constants for the combined AC + heater BLE simulator -- mirrors
../aircon/config.py and ../hvac-knob/heater_ble_config.py as plain
duplicates, since both real firmwares run on MicroPython/RP2350 with no
shared import path to this desktop/RPi CPython process. If you change
UUIDs or defaults in either real firmware's config.py, update the matching
half of this file to match.

This file replaces ../aircon-sim/config.py + ../heater-sim/config.py (see
git history for those) now that both simulators run as one process -- see
ble_server.py's own module docstring for why. Named AC_*/HEAT_* only where
a name would otherwise collide between the two devices (VERSION,
BLE_SVC_UUID, *_NOTIFY_INTERVAL) or where a device's own GATT service UUID
specifically needs disambiguating now that both live under one BLE
peripheral -- everything else keeps its original, already-unique name from
whichever of the two predecessor files it came from.
"""

# ── Shared BLE identity ──────────────────────────────────────────────────
# One process, one BlessServer, one advertised local name -- see ble_server.
# py's own module docstring for why (a single Mac generally only reliably
# advertises one BLE peripheral identity at a time; two separate processes
# each running their own simulator, as this used to be split into, silently
# starved each other on the same radio even though each looked like it
# advertised successfully in isolation).
#
# AirconClient.scan_for_aircons() finds this by AC_BLE_SVC_UUID regardless
# of name; HeaterClient.scan_for_heaters() primarily wants a name starting
# with "BYD-" but also falls back to matching HEAT_BLE_SVC_UUID directly
# when the name doesn't (see that method's own docstring's FALLBACK
# paragraph) -- this name deliberately does NOT start with "BYD-" (there's
# only one name for the whole combined identity, and "AC+heater" has no
# single sensible "BYD-..." spelling), so heater discovery against this sim
# always goes through that fallback path, by design, not as a workaround.
BLE_DEVICE_NAME = "HVAC-Sim"

# ── AC (was ../aircon-sim/config.py) ─────────────────────────────────────

# Deliberately NOT mirrored to match ../aircon/config.py's VERSION -- shown
# on the knob's Info screen (see ../hvac-knob/screens/info.py), so it
# should read differently there when talking to this sim instead of a real
# controller.
AC_VERSION = "1.0-sim"

MODE_OFF = "off"
MODE_FAN = "fan"
MODE_AUTO = "auto"
MODE_COOL = "cool"

FAN_LOW = "low"
FAN_MEDIUM = "medium"
FAN_HIGH = "high"

CIRC_RECIRC = "recirc"
CIRC_FRESH = "fresh"

DEFAULT_MODE = MODE_OFF
DEFAULT_FAN = FAN_LOW
DEFAULT_SETPOINT = 72.0
DEFAULT_SETPOINT_MIN = 60.0
DEFAULT_SETPOINT_MAX = 80.0
DEFAULT_CIRCULATION = CIRC_RECIRC
DEFAULT_DELTA = 2.0

DEFAULT_AUTO_FAN_HIGH_THRESH = 4.0
DEFAULT_AUTO_FAN_MED_THRESH = 2.0
DEFAULT_FAN_CHANGE_INTERVAL = 30
DEFAULT_AUTO_LOOP_INTERVAL = 5
DEFAULT_TEMP_READ_INTERVAL = 3

AC_NOTIFY_INTERVAL = 2  # seconds; matches the real firmware's push rate

# Must match ../aircon/config.py exactly, and whatever
# ../hvac-knob/aircon_ble_config.py the panel is flashed with.
AC_BLE_SVC_UUID = "aaaaaaaa-1111-cccc-00dd-000000000000"
BLE_UUID_MODE = "aaaaaaaa-1111-cccc-00dd-000000000001"
BLE_UUID_FAN = "aaaaaaaa-1111-cccc-00dd-000000000002"
BLE_UUID_SETPOINT = "aaaaaaaa-1111-cccc-00dd-000000000003"
BLE_UUID_CIRC = "aaaaaaaa-1111-cccc-00dd-000000000004"
BLE_UUID_PANEL = "aaaaaaaa-1111-cccc-00dd-000000000005"
BLE_UUID_SETTINGS = "aaaaaaaa-1111-cccc-00dd-000000000006"
BLE_UUID_STATUS = "aaaaaaaa-1111-cccc-00dd-000000000007"

# ── Heater (was ../heater-sim/config.py) ─────────────────────────────────

HEAT_VERSION = "1.0-sim"  # currently unused -- nothing reads it yet, same as in the predecessor file this came from

# Standard BLE-SIG "UART bridge" service, shared with a whole family of
# unrelated cheap BLE peripherals -- matches ../hvac-knob/
# heater_ble_config.py's SERVICE_UUID/CHAR_UUID exactly (128-bit string
# form of the same short-form 0xFFE0/0xFFE1 the real heater and the panel's
# own bluetooth.UUID(0xFFE0) constant use -- see that file's own comment
# for why the panel can't just compare these two forms directly, which is
# irrelevant here since bless/CoreBluetooth handles the 128<->16-bit
# canonicalization on its own when advertising).
HEAT_BLE_SVC_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
HEAT_BLE_CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"  # both notify and write

# The vendor app's own scan filter, mirrored from ../hvac-knob/
# heater_ble_config.py -- NAME_EXCLUDE_PREFIXES are advertising names seen
# only while a unit is in bootloader/OTA mode (BYDOTA-/BACOTA-) or a
# different product line entirely (BYD-MD-); this sim never advertises any
# of them, kept here only so a --name override could be checked against it
# if that's ever added.
NAME_PREFIX = "BYD-"
NAME_EXCLUDE_PREFIXES = ("BYD-MD-", "BYDOTA-", "BACOTA-")

HEAT_NOTIFY_INTERVAL = 2  # seconds -- how often this sim proactively pushes a status frame, connected or not, changed or not

# --- Frame format (v1, app -> device) -------------------------------------
#
# Fixed 8 bytes always -- see ../hvac-knob/heater_ble_config.py's own
# comment for the full byte-by-byte layout; heat_protocol.py implements it.
# Every frame carries the password (bytes 2-3) -- there's no separate
# handshake/login command in this protocol version at all -- ble_server.py
# checks it per-frame instead of via a dedicated handshake dispatch branch.
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

# Confirmed against real hardware (see ../hvac-knob/heater_ble_config.py) --
# this sim matches the real unit's actual gear range.
HEAT_LEVEL_MIN = 1
HEAT_LEVEL_MAX = 10

THERMOSTAT_TEMP_MIN_C = 8
THERMOSTAT_TEMP_MAX_C = 36

# --- Status notification format (v1, device -> app) -----------------------
#
# Fixed 48 bytes, XOR-obfuscated with a repeating 15-byte keystream --
# CONFIRMED against real hardware for the header, on/off, and gear; see
# ../hvac-knob/heater_ble_config.py's own NOTIFY_XOR_KEY comment for the
# full field-by-field confidence breakdown. NOTIFY_OFF_FAULT is a best
# guess, not confirmed (see that constant's own comment there) -- included
# anyway so --heat-fault has something to exercise on the panel side.
NOTIFY_XOR_KEY = b"passwordA2409PW"
NOTIFY_LEN = 48
NOTIFY_OFF_ON = 3
NOTIFY_OFF_FAULT = 4
NOTIFY_OFF_GEAR = 5

DEFAULT_RUN_MODE = RUN_MODE_GEAR
DEFAULT_RUN_PARAM = HEAT_LEVEL_MIN
