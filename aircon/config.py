# Pin assignments — change each pin in exactly one place here.

# Relay outputs
PIN_RELAY_FAN_LOW    = 26  # Relay 1 — blower fan low speed
PIN_RELAY_FAN_MED    = 27  # Relay 2 — blower fan medium
PIN_RELAY_FAN_HIGH   = 28  # Relay 3 — blower fan high
PIN_RELAY_COMPRESSOR = 29  # Relay 4 — compressor on
PIN_RELAY_FRESH_AIR  = 30  # Relay 5 — circulation: off=recirc, on=fresh air
PIN_RELAY_6          = 31  # Relay 6 — unused

# Relay logic level (set False for active-low relay modules)
RELAY_ACTIVE_HIGH = True

# Buzzer
PIN_BUZZER = 21

# WS2812 RGB LED (single pixel)
PIN_LED_RGB = 36

# DS18B20 1-wire temperature probes (one per pin)
PIN_TEMP_CABIN   = 5
PIN_TEMP_BLOWER  = 14
PIN_TEMP_EXHAUST = 15
PIN_TEMP_BAGGAGE = 17
PIN_TEMP_TAIL    = 42

# Mystery PWM signal from compressor
PIN_PWM_MONITOR = 2

# ── Mode constants ────────────────────────────────────────────────────────────
MODE_OFF  = 'off'   # everything off
MODE_FAN  = 'fan'   # fan only, no compressor
MODE_AUTO = 'auto'  # manage fan + compressor to reach setpoint
MODE_COOL = 'cool'  # compressor always on, servo follows circ setting, fan speed is user-chosen

# ── Fan speed constants ───────────────────────────────────────────────────────
FAN_LOW    = 'low'
FAN_MEDIUM = 'medium'
FAN_HIGH   = 'high'

# ── Circulation constants ─────────────────────────────────────────────────────
CIRC_RECIRC = 'recirc'
CIRC_FRESH  = 'fresh'

# ── Defaults (used when no saved state exists) ────────────────────────────────
DEFAULT_MODE        = MODE_OFF
DEFAULT_FAN         = FAN_LOW
DEFAULT_SETPOINT    = 72.0   # °F
DEFAULT_CIRCULATION = CIRC_RECIRC
DEFAULT_DELTA       = 2.0    # °F hysteresis around setpoint

# ── Auto-mode fan speed thresholds ───────────────────────────────────────────
# |current - setpoint| or |panel - cabin| >= these values selects that speed.
DEFAULT_AUTO_FAN_HIGH_THRESH = 4.0   # °F — use HIGH fan
DEFAULT_AUTO_FAN_MED_THRESH  = 2.0   # °F — use MEDIUM fan (below this → LOW)

# Minimum seconds between fan speed changes (prevents hunting)
DEFAULT_FAN_CHANGE_INTERVAL = 30

# How often auto-mode runs its control loop (seconds)
DEFAULT_AUTO_LOOP_INTERVAL = 5

# How often temperature probes are read (seconds, after 750 ms conversion)
DEFAULT_TEMP_READ_INTERVAL = 3

# ── Persistence ───────────────────────────────────────────────────────────────
STORAGE_FILE = '/aircon_settings.json'

# ── WiFi ─────────────────────────────────────────────────────────────────────
# Credentials are read from /wifi.json on the Pico filesystem so they are
# never stored in source control.  File format: {"ssid": "...", "password": "..."}
def _load_wifi():
    import json as _json
    try:
        with open('/wifi.json') as _f:
            _d = _json.load(_f)
        return _d['ssid'], _d['password']
    except Exception:
        return '', ''

WIFI_SSID, WIFI_PASSWORD = _load_wifi()

# ── Web server ────────────────────────────────────────────────────────────────
WEB_PORT = 80

# ── BLE ───────────────────────────────────────────────────────────────────────
# Device name is read from /name.txt (one line, no trailing newline needed).
# If the file is absent the default 'AirCon' is used.  Add /name.txt to the
# Pico filesystem via mpremote/Thonny; it is listed in .gitignore.
def _load_device_name():
    try:
        with open('/name.txt') as _f:
            _name = _f.read().strip()
        return _name if _name else 'AirCon'
    except Exception:
        return 'AirCon'

BLE_DEVICE_NAME   = _load_device_name()
BLE_NOTIFY_INTERVAL = 2  # seconds between GATT notifications

# ── BLE UUIDs (128-bit custom service) ───────────────────────────────────────
# Writable: mode, fan, setpoint, circ, panel, delta
# Read/notify: status (JSON snapshot of temps, compressor state, error)
BLE_SVC_UUID      = 'aaaaaaaa-1111-cccc-00dd-000000000000'
BLE_UUID_MODE     = 'aaaaaaaa-1111-cccc-00dd-000000000001'
BLE_UUID_FAN      = 'aaaaaaaa-1111-cccc-00dd-000000000002'
BLE_UUID_SETPOINT = 'aaaaaaaa-1111-cccc-00dd-000000000003'
BLE_UUID_CIRC     = 'aaaaaaaa-1111-cccc-00dd-000000000004'
BLE_UUID_PANEL    = 'aaaaaaaa-1111-cccc-00dd-000000000005'
BLE_UUID_SETTINGS = 'aaaaaaaa-1111-cccc-00dd-000000000006'
BLE_UUID_STATUS   = 'aaaaaaaa-1111-cccc-00dd-000000000007'
