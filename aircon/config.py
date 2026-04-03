# Pin assignments — change each pin in exactly one place here.

# Relay outputs
PIN_RELAY_FAN_LOW    = 1   # Relay 1 — blower fan low speed
PIN_RELAY_FAN_MED    = 2   # Relay 2 — blower fan medium
PIN_RELAY_FAN_HIGH   = 41  # Relay 3 — blower fan high
PIN_RELAY_COMPRESSOR = 42  # Relay 4 — compressor on
PIN_RELAY_5          = 45  # Relay 5 — unused
PIN_RELAY_6          = 46  # Relay 6 — unused

# Relay logic level (set False for active-low relay modules)
RELAY_ACTIVE_HIGH = True

# Buzzer
PIN_BUZZER = 21

# WS2812 RGB LED (single pixel)
PIN_LED_RGB = 38

# DS18B20 1-wire temperature probes (one per pin)
PIN_TEMP_CABIN   = 16
PIN_TEMP_BLOWER  = 17
PIN_TEMP_EXHAUST = 18
PIN_TEMP_BAGGAGE = 19
PIN_TEMP_TAIL    = 20

# Mystery PWM signal from compressor
PIN_PWM_MONITOR = 22

# PWM servo — recirc/fresh-air valve
PIN_SERVO = 15

# Servo pulse widths in microseconds — calibrate to actual hardware
SERVO_RECIRC_US = 1000
SERVO_FRESH_US  = 2000

# ── Mode constants ────────────────────────────────────────────────────────────
MODE_OFF  = 'off'   # everything off
MODE_FAN  = 'fan'   # fan only, no compressor
MODE_AUTO = 'auto'  # manage fan + compressor to reach setpoint
MODE_MAX  = 'max'   # full fan, compressor on, always recirc

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
AUTO_FAN_HIGH_THRESH = 6.0   # °F — use HIGH fan
AUTO_FAN_MED_THRESH  = 3.0   # °F — use MEDIUM fan (below this → LOW)

# Minimum seconds between fan speed changes (prevents hunting)
FAN_CHANGE_INTERVAL = 30

# How often auto-mode runs its control loop (seconds)
AUTO_LOOP_INTERVAL = 5

# How often temperature probes are read (seconds, after 750 ms conversion)
TEMP_READ_INTERVAL = 3

# ── Persistence ───────────────────────────────────────────────────────────────
STORAGE_FILE = '/aircon_settings.json'

# ── WiFi ─────────────────────────────────────────────────────────────────────
WIFI_SSID     = 'your-ssid'
WIFI_PASSWORD = 'your-password'

# ── Web server ────────────────────────────────────────────────────────────────
WEB_PORT = 80

# ── BLE ───────────────────────────────────────────────────────────────────────
BLE_DEVICE_NAME   = 'AirCon'
BLE_NOTIFY_INTERVAL = 2  # seconds between GATT notifications

# ── BLE UUIDs (128-bit custom service) ───────────────────────────────────────
BLE_SVC_UUID       = 'a1b2c3d4-0000-0000-abcd-ef1234567890'
BLE_UUID_MODE      = 'a1b2c3d4-0001-0000-abcd-ef1234567890'
BLE_UUID_FAN       = 'a1b2c3d4-0002-0000-abcd-ef1234567890'
BLE_UUID_SETPOINT  = 'a1b2c3d4-0003-0000-abcd-ef1234567890'
BLE_UUID_CIRC      = 'a1b2c3d4-0004-0000-abcd-ef1234567890'
BLE_UUID_PANEL     = 'a1b2c3d4-0005-0000-abcd-ef1234567890'
BLE_UUID_CURR_TEMP = 'a1b2c3d4-0006-0000-abcd-ef1234567890'
BLE_UUID_COMP_ST   = 'a1b2c3d4-0007-0000-abcd-ef1234567890'
BLE_UUID_REAR_TEMP = 'a1b2c3d4-0008-0000-abcd-ef1234567890'
BLE_UUID_BLOW_TEMP = 'a1b2c3d4-0009-0000-abcd-ef1234567890'
BLE_UUID_EXHU_TEMP = 'a1b2c3d4-000a-0000-abcd-ef1234567890'
BLE_UUID_BAGG_TEMP = 'a1b2c3d4-000b-0000-abcd-ef1234567890'
BLE_UUID_COMP_TEMP = 'a1b2c3d4-000c-0000-abcd-ef1234567890'
BLE_UUID_DELTA     = 'a1b2c3d4-000d-0000-abcd-ef1234567890'
BLE_UUID_ERROR     = 'a1b2c3d4-000e-0000-abcd-ef1234567890'
