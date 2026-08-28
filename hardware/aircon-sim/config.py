"""Constants mirrored from ../aircon/config.py -- kept as a plain duplicate
rather than a shared import since the real firmware runs on MicroPython and
this runs on desktop/RPi CPython with no shared import path between them.
If you change UUIDs or defaults in the real firmware's config.py, update
this file to match.
"""

# Deliberately NOT mirrored to match ../aircon/config.py's VERSION -- shown
# on the knob's Info screen (see ../hvac-knob/screens/info.py), so it
# should read differently there when talking to this sim instead of a real
# controller.
VERSION = "1.0-sim"

# ── Mode / fan / circulation constants (same wire values as the real unit) ──
MODE_OFF = "off"
MODE_FAN = "fan"
MODE_AUTO = "auto"
MODE_COOL = "cool"

FAN_LOW = "low"
FAN_MEDIUM = "medium"
FAN_HIGH = "high"

CIRC_RECIRC = "recirc"
CIRC_FRESH = "fresh"

# ── Defaults (matches ../aircon/config.py's DEFAULT_* values) ──────────────
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

# ── BLE identity/UUIDs -- must match ../aircon/config.py exactly, and match
# whatever hardware/hvac-knob/ble_config.py the panel is flashed with. ───
BLE_DEVICE_NAME = "Air-Sim"
BLE_NOTIFY_INTERVAL = 2  # seconds; matches the real firmware's push rate

BLE_SVC_UUID = "aaaaaaaa-1111-cccc-00dd-000000000000"
BLE_UUID_MODE = "aaaaaaaa-1111-cccc-00dd-000000000001"
BLE_UUID_FAN = "aaaaaaaa-1111-cccc-00dd-000000000002"
BLE_UUID_SETPOINT = "aaaaaaaa-1111-cccc-00dd-000000000003"
BLE_UUID_CIRC = "aaaaaaaa-1111-cccc-00dd-000000000004"
BLE_UUID_PANEL = "aaaaaaaa-1111-cccc-00dd-000000000005"
BLE_UUID_SETTINGS = "aaaaaaaa-1111-cccc-00dd-000000000006"
BLE_UUID_STATUS = "aaaaaaaa-1111-cccc-00dd-000000000007"
