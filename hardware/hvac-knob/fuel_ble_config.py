"""BLE identity of the fuel-level sensor(s) this panel can connect to --
mirrors ../fuel-level/config.py's own UUIDs exactly (that project's the
authoritative source; update this file to match if those ever change).
Only the pieces fuel_ble.py actually reads are duplicated here -- the raw
Voltage/calibration characteristics (also defined in that project's own
config.py) have no reader on this side yet, this panel only shows the
already-converted percentage.
"""

# Custom service fuel_ble.py's scan_for_fuel_sensors() filters on -- see
# ../fuel-level/config.py's own BLE_SVC_UUID comment for why this is
# custom (no Bluetooth SIG service groups "raw sensor voltage +
# calibration" together) rather than reused from the standard pair below.
FUEL_SERVICE_UUID = "eeeeeeee-4444-cccc-00dd-000000000000"

# Standard Bluetooth SIG Battery Service / Battery Level -- see
# ../fuel-level/ble_server.py's own module docstring for the exact format
# (uint8, 0-100%) and where it's confirmed from (the SIG's own public GATT
# Specification Supplement source, not just guessed from the UUID's name).
BATTERY_SVC_UUID = 0x180F
BATTERY_LEVEL_UUID = 0x2A19
