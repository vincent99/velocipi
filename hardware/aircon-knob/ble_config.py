"""BLE identity of the AirCon controller(s) this panel can connect to.

AIRCON_SERVICE_UUID and the characteristic UUIDs below match
../aircon/config.py (the real RP2350 firmware), ../aircon-sim/config.py
(the desktop BLE simulator), and the Go server's config
(server/config/config.go AirConConfig, via AIRCON_SERVICEUUID in .env) --
all need to agree if you change them on the real controller.

Unlike an earlier version of this file, there's no AIRCON_DEVICE_NAME
constant here anymore -- each physical controller can have its own custom
BLE_DEVICE_NAME (../aircon/config.py's config.BLE_DEVICE_NAME, settable at
runtime via its set_ble_name()), so this panel scans for *any* device
advertising AIRCON_SERVICE_UUID (aircon_ble.AirconClient.scan_for_aircons())
and the user picks one by name on the Connect screen (screens.ConnectTile).
The chosen name is persisted to flash by panel_settings.py, not hardcoded.
"""

AIRCON_SERVICE_UUID = "aaaaaaaa-1111-cccc-00dd-000000000000"

# Same 7 characteristic UUIDs as server/hardware/aircon/aircon.go.
UUID_MODE = "aaaaaaaa-1111-cccc-00dd-000000000001"
UUID_FAN = "aaaaaaaa-1111-cccc-00dd-000000000002"
UUID_SETPOINT = "aaaaaaaa-1111-cccc-00dd-000000000003"
UUID_CIRC = "aaaaaaaa-1111-cccc-00dd-000000000004"
UUID_PANEL = "aaaaaaaa-1111-cccc-00dd-000000000005"
UUID_SETTINGS = "aaaaaaaa-1111-cccc-00dd-000000000006"
UUID_STATUS = "aaaaaaaa-1111-cccc-00dd-000000000007"
