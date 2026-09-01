"""Configuration for the fuel-level BLE peripheral -- a generic ESP32-S3
running plain stock MicroPython (no custom firmware build needed, unlike
../hvac-knob/'s LVGL one -- there's no display here) that reads one analog
voltage from a resistive fuel-tank sender and reports it over BLE. See
../aircon/config.py's own "pin assignments" comment for the same "change it
in exactly one place" idea -- this project just has the one pin.
"""

# Firmware version -- shown in this project's own log lines only right now
# (see main.py); nothing on the knob side reads it yet.
VERSION = "1.0"

# ── Pin assignment ───────────────────────────────────────────────────────
# ADC-capable GPIO the fuel sender's wiper voltage is wired to. Change this
# one constant, not the call site in fuel_sensor.py, if the wiring moves to
# a different pin. Must be one of the ESP32-S3's ADC1 pins (GPIO1-10, per
# Espressif's own datasheet) -- ADC2 (GPIO11-20) shares hardware with WiFi
# and MicroPython's esp32 port can't reliably read it while WiFi's active.
# This project doesn't use WiFi, but ADC1 is the simpler/safer default
# regardless (no footgun if WiFi's ever added later for OTA or similar).
PIN_FUEL_ADC = 4

# ── ADC sampling ─────────────────────────────────────────────────────────
# How often fuel_sensor.FuelSensor.run() takes a fresh ADC reading.
SAMPLE_INTERVAL_MS = 500

# Exponential moving average smoothing factor for the raw ADC reading,
# 0.0-1.0 -- lower is smoother/slower to react, higher tracks the raw
# signal more closely. Resistive fuel senders (a wiper on a rheostat,
# physically agitated by fuel sloshing in the tank) are a genuinely noisy
# source, not just ADC quantization noise, so this is deliberately fairly
# slow. NOT tuned against a real sender -- adjust once one's on the bench.
SMOOTHING_ALPHA = 0.2

# Seconds between BLE notifications to a connected central -- matches
# ../aircon/config.py's own BLE_NOTIFY_INTERVAL.
BLE_NOTIFY_INTERVAL = 2

# ── Calibration defaults ─────────────────────────────────────────────────
# Volts the ADC reads at 0%/100% tank level. Just the starting point until
# something writes real values over BLE (see storage.py for how those get
# persisted -- these compiled-in constants are a safe-but-probably-wrong
# fallback, not meant to be accurate for any real sender out of the box).
# Spans the ADC's full nominal input range (0-3.3V -- see fuel_sensor.py's
# own ATTN_11DB comment for how confident to be in that ceiling) since
# there's no way to guess a real sender's actual swing in advance.
# CAL_ZERO_V > CAL_FULL_V is valid too (some senders read *high* empty, low
# full) -- see fuel_sensor.FuelSensor.percent's own comment for why the
# math doesn't care which direction it runs.
DEFAULT_CAL_ZERO_V = 0.0
DEFAULT_CAL_FULL_V = 3.3

STORAGE_FILE = "/fuel_calibration.json"

# ── BLE ──────────────────────────────────────────────────────────────────
BLE_DEVICE_NAME = "FuelLevel"

# Standard Bluetooth SIG assigned numbers -- see ble_server.py's own module
# docstring for why these are used as-is instead of inventing custom UUIDs,
# and where the exact wire format for each came from (confirmed against
# the Bluetooth SIG's own public GATT Specification Supplement source,
# bitbucket.org/bluetooth-SIG/public, not just assumed from a UUID name).
BLE_SVC_BATTERY = 0x180F  # Battery Service
BLE_CHAR_BATTERY_LEVEL = 0x2A19  # Battery Level -- uint8, 0-100 (%)
# Voltage -- uint16 LE, 1/64 V units, 0xFFFF = "not known"
# (org.bluetooth.characteristic.voltage). Lives under BLE_SVC_UUID below,
# not this Battery Service -- see that constant's own comment.
BLE_CHAR_VOLTAGE = 0x2B18

# Custom 128-bit service for the raw voltage + calibration characteristics
# -- no Bluetooth SIG service groups those together, so this one's ours.
# Same "cccc-00dd" family suffix as ../aircon/config.py's own BLE_SVC_UUID
# and ../hvac-sim/config.py's AC_BLE_SVC_UUID, picked purely so every
# custom peripheral this project's knob talks to is visually recognizable
# as "one of ours" at a glance in a generic BLE scanner; the two differing
# segments here (eeeeeeee-4444-...) are what actually distinguish this
# device from those.
BLE_SVC_UUID = "eeeeeeee-4444-cccc-00dd-000000000000"
# rw -- volts, same uint16/1-64V encoding as BLE_CHAR_VOLTAGE (see
# ble_server.py's _enc_v()/_dec_v()) for consistency, even though nothing
# about the calibration characteristics themselves is Bluetooth-SIG-
# standard. The voltage percent() should treat as 0%.
BLE_UUID_CAL_ZERO = "eeeeeeee-4444-cccc-00dd-000000000001"
# rw, same encoding -- the voltage percent() should treat as 100%.
BLE_UUID_CAL_FULL = "eeeeeeee-4444-cccc-00dd-000000000002"
