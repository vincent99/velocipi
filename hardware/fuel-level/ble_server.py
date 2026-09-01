"""BLE GATT peripheral exposing fuel level over two services -- standard
Bluetooth SIG characteristics wherever one actually fits, so a generic BLE
client (nRF Connect, LightBlue, a phone's own battery-device UI on some
platforms, ...) can read this device meaningfully with zero custom
parsing, not just ../hvac-knob/'s own purpose-built client.

  Battery Service (config.BLE_SVC_BATTERY, 0x180F)
    Battery Level (config.BLE_CHAR_BATTERY_LEVEL, 0x2A19)   r, notify
      uint8, 0-100 (%). Standard Bluetooth SIG characteristic -- this is
      the ONE thing a client actually needs to read to show a fuel
      percentage; it happens to reuse the "battery" vocabulary (a fuel
      tank isn't a battery), but the wire format -- "a 0-100 level that
      empties over time" -- is exactly the same shape, and reusing it is
      what makes this device auto-recognized by generic battery-level UIs
      instead of needing a bespoke one. Confirmed against the Bluetooth
      SIG's own public GATT Specification Supplement source
      (bitbucket.org/bluetooth-SIG/public,
      gss/org.bluetooth.characteristic.battery_level.yaml) -- not just
      assumed from the UUID's name.

  Fuel Level service (config.BLE_SVC_UUID, custom -- no Bluetooth SIG
  service groups "raw sensor voltage + calibration" together, so this
  one's ours)
    Voltage (config.BLE_CHAR_VOLTAGE, 0x2B18)   r, notify
      uint16 little-endian, unit volt, resolution 1/64 V (so raw = round(
      volts * 64), volts = raw / 64.0), 0xFFFF = "not known". Standard
      Bluetooth SIG characteristic (org.bluetooth.characteristic.voltage),
      reused here under this project's own custom service rather than
      under a SIG-defined one (none fits) -- a generic client that already
      knows this characteristic UUID's format decodes it correctly
      regardless of which service UUID happens to contain it. This is the
      pre-calibration raw sensor reading, in case the 0-100% figure alone
      isn't enough (e.g. to sanity-check calibration itself). Format
      confirmed the same way as Battery Level above (gss/org.bluetooth.
      characteristic.voltage.yaml).
    Cal Zero Voltage (config.BLE_UUID_CAL_ZERO)   rw
      Same uint16/1-64V encoding as Voltage above, for consistency -- not
      a Bluetooth-SIG-standard characteristic itself (nothing standard
      covers "calibration input" at all), just reusing that format rather
      than inventing a second one. The voltage percent() should treat as
      0%.
    Cal Full Voltage (config.BLE_UUID_CAL_FULL)   rw
      Same encoding -- the voltage percent() should treat as 100%.

Install aioble if not already present:
    import mip
    mip.install('aioble')
"""

import asyncio

import aioble
import bluetooth

import config

# Characteristic User Description (0x2901) -- plain UTF-8 label, same
# descriptor ../aircon/ble_server.py's own _rw()/_rn() helpers attach to
# every characteristic there. Skipped here for the two standard
# characteristics (a generic client that already recognizes 0x2A19/0x2B18
# by UUID doesn't need one to know what they are), kept for the two custom
# calibration characteristics where a label is the only hint a generic
# client has.
_LABEL_CAL_ZERO = b"Calibration: 0% Voltage"
_LABEL_CAL_FULL = b"Calibration: 100% Voltage"


def _enc_v(volts):
    """Standard Voltage characteristic wire format (see this module's own
    docstring): uint16 little-endian, 1/64 V units, clamped into the
    format's own 0-1022V representable range (0xFFFF is reserved for
    "not known") -- nowhere close to this project's real ~0-3.3V input,
    just matching the spec's own stated bounds instead of silently
    wrapping on a nonsensical one.
    """
    raw = min(max(int(round(volts * 64)), 0), 0xFFFE)
    return raw.to_bytes(2, "little")


def _dec_v(data):
    raw = int.from_bytes(bytes(data), "little")
    return raw / 64.0


class FuelBLEServer:
    def __init__(self, sensor):
        self._sensor = sensor

        battery_svc = aioble.Service(bluetooth.UUID(config.BLE_SVC_BATTERY))
        self._c_level = aioble.Characteristic(
            battery_svc,
            bluetooth.UUID(config.BLE_CHAR_BATTERY_LEVEL),
            read=True,
            notify=True,
        )

        fuel_svc = aioble.Service(bluetooth.UUID(config.BLE_SVC_UUID))
        self._c_voltage = aioble.Characteristic(
            fuel_svc,
            bluetooth.UUID(config.BLE_CHAR_VOLTAGE),
            read=True,
            notify=True,
        )
        self._c_cal_zero = aioble.Characteristic(
            fuel_svc,
            bluetooth.UUID(config.BLE_UUID_CAL_ZERO),
            read=True,
            write=True,
            write_no_response=True,
            capture=True,
        )
        aioble.Descriptor(self._c_cal_zero, bluetooth.UUID(0x2901), read=True, initial=_LABEL_CAL_ZERO)
        self._c_cal_full = aioble.Characteristic(
            fuel_svc,
            bluetooth.UUID(config.BLE_UUID_CAL_FULL),
            read=True,
            write=True,
            write_no_response=True,
            capture=True,
        )
        aioble.Descriptor(self._c_cal_full, bluetooth.UUID(0x2901), read=True, initial=_LABEL_CAL_FULL)

        self._svcs = (battery_svc, fuel_svc)
        self._connections = set()
        self._state_event = asyncio.Event()
        self._last = {}  # dedup -- see _write()

    def notify_state_changed(self):
        """Called by FuelSensor.on_change after any new reading/calibration
        change."""
        self._state_event.set()

    # ── Push helpers ─────────────────────────────────────────────────────

    def _write(self, name, char, value, notify):
        if self._last.get(name) == value:
            return
        self._last[name] = value
        try:
            char.write(value, send_update=notify)
        except OSError:
            char.write(value)  # no subscribers -- write without notify

    def _push_state(self, notify):
        s = self._sensor.get_state()
        self._write("level", self._c_level, bytes([int(round(s["percent"]))]), notify)
        self._write("voltage", self._c_voltage, _enc_v(s["voltage"]), notify)
        # Calibration characteristics are read/write, not read/notify (see
        # __init__) -- pushed here with notify hardcoded False regardless
        # of this call's own `notify` param, so a fresh connection's
        # initial read sees whatever was last set/persisted without ever
        # spamming a notification for values that only ever change when a
        # client itself writes them.
        self._write("cal_zero", self._c_cal_zero, _enc_v(s["cal_zero_v"]), False)
        self._write("cal_full", self._c_cal_full, _enc_v(s["cal_full_v"]), False)

    # ── Per-connection task: push state on connect, then on changes ───────

    async def _connection_task(self, connection):
        self._connections.add(connection)
        self._last = {}  # force a full push for this connection's initial read
        print("ble: connected:", connection.device)
        try:
            self._push_state(notify=False)
            while connection.is_connected():
                # Same "wait up to the interval, drain, hard-sleep the
                # interval regardless" shape as ../aircon/ble_server.py's
                # own _connection_task() -- never notifies faster than
                # config.BLE_NOTIFY_INTERVAL even if on_change fires in a
                # tight loop.
                try:
                    await asyncio.wait_for(self._state_event.wait(), config.BLE_NOTIFY_INTERVAL)
                except asyncio.TimeoutError:
                    pass
                self._state_event.clear()
                self._push_state(notify=True)
                await asyncio.sleep(config.BLE_NOTIFY_INTERVAL)
        finally:
            self._connections.discard(connection)
            print("ble: disconnected")

    # ── Main BLE task ─────────────────────────────────────────────────────

    async def run(self):
        print("ble: registering services")
        aioble.register_services(*self._svcs)
        print("ble: services registered")

        try:
            self._push_state(notify=False)
        except Exception:
            pass

        async def watch(name, char, handler):
            while True:
                try:
                    _, data = await char.written()
                    print("ble: %s write: %s" % (name, bytes(data)))
                    handler(data)
                except Exception as e:
                    print("ble: %s write error: %s" % (name, e))
                    await asyncio.sleep_ms(100)

        asyncio.create_task(
            watch("cal_zero", self._c_cal_zero, lambda d: self._sensor.set_cal_zero(_dec_v(d)))
        )
        asyncio.create_task(
            watch("cal_full", self._c_cal_full, lambda d: self._sensor.set_cal_full(_dec_v(d)))
        )

        while True:
            try:
                print("ble: advertising")
                connection = await aioble.advertise(
                    500_000,  # advertising interval µs
                    name=config.BLE_DEVICE_NAME,
                    services=[
                        bluetooth.UUID(config.BLE_SVC_BATTERY),
                        bluetooth.UUID(config.BLE_SVC_UUID),
                    ],
                )
                print("ble: advertise returned")
                asyncio.create_task(self._connection_task(connection))
            except Exception as e:
                print("ble: advertise error:", e)
                await asyncio.sleep_ms(500)
