"""BLE identity of the AirCon controller this panel connects to.

Values below match ../aircon/config.py (the real RP2350 firmware) and
../aircon-sim/config.py (the desktop BLE simulator) exactly -- all three
need to agree, along with the Go server's config
(server/config/config.go AirConConfig, set via AIRCON_DEVICENAME /
AIRCON_SERVICEUUID in .env) if you also want the Pi connecting to the same
device. If you change the device name or UUIDs on the real controller,
update all of these to match.
"""

AIRCON_DEVICE_NAME = "AirCon"
AIRCON_SERVICE_UUID = "aaaaaaaa-1111-cccc-00dd-000000000000"

# Same 7 characteristic UUIDs as server/hardware/aircon/aircon.go.
UUID_MODE = "aaaaaaaa-1111-cccc-00dd-000000000001"
UUID_FAN = "aaaaaaaa-1111-cccc-00dd-000000000002"
UUID_SETPOINT = "aaaaaaaa-1111-cccc-00dd-000000000003"
UUID_CIRC = "aaaaaaaa-1111-cccc-00dd-000000000004"
UUID_PANEL = "aaaaaaaa-1111-cccc-00dd-000000000005"
UUID_SETTINGS = "aaaaaaaa-1111-cccc-00dd-000000000006"
UUID_STATUS = "aaaaaaaa-1111-cccc-00dd-000000000007"
