"""BLE identity of the AirCon controller(s) this panel can connect to --
custom UUIDs unique to ../aircon/config.py's own firmware, unlike the
heater's (see heater_ble_config.py), which reuses generic BLE-SIG UUIDs
shared with a whole family of unrelated white-label devices and is
identified by advertised name prefix instead.

Renamed from ble_config.py now that there are two BLE peripherals in play
-- this one is AirCon-specific (custom service, one characteristic per
field), the heater's is a completely separate wire protocol (see
heater_ble_config.py/heater_ble.py). ble_shared.py holds the one thing
genuinely common to both: serializing aioble.scan() calls.
"""

AIRCON_SERVICE_UUID = "aaaaaaaa-1111-cccc-00dd-000000000000"

# 7 characteristic UUIDs matching ../aircon/config.py
UUID_MODE = "aaaaaaaa-1111-cccc-00dd-000000000001"
UUID_FAN = "aaaaaaaa-1111-cccc-00dd-000000000002"
UUID_SETPOINT = "aaaaaaaa-1111-cccc-00dd-000000000003"
UUID_CIRC = "aaaaaaaa-1111-cccc-00dd-000000000004"
UUID_PANEL = "aaaaaaaa-1111-cccc-00dd-000000000005"
UUID_SETTINGS = "aaaaaaaa-1111-cccc-00dd-000000000006"
UUID_STATUS = "aaaaaaaa-1111-cccc-00dd-000000000007"
