"""BLE GATT peripheral exposing the same service/characteristics as
../aircon/ble_server.py, backed by `bless` (cross-platform GATT server:
CoreBluetooth on macOS, BlueZ/D-Bus on Linux) instead of MicroPython's
aioble -- see ../aircon-knob/README.md's client for the other end of this
wire protocol, which this must match byte-for-byte:
UTF-8 strings for mode/fan/setpoint/circ/panel, JSON for settings/status.
"""

import json
import logging

from bless import (
    BlessServer,
    GATTCharacteristicProperties,
    GATTAttributePermissions,
)

import config

logger = logging.getLogger("aircon-sim.ble")

# Wire key (as sent/received on the settings characteristic) -> controller
# attribute name. Controller attributes stay verbose (self.fan_high_thresh
# etc., unchanged) -- only the wire keys are terse, to keep the settings
# JSON payload's size down. "delta" and "brightness" aren't renamed; the
# rest drop "_thresh"/"_interval" and "setpoint" -> "set", matching
# ../aircon/ble_server.py exactly.
SETTINGS_WIRE_KEYS = {
    "delta": "delta",
    "fan_high": "fan_high_thresh",
    "fan_med": "fan_med_thresh",
    "fan_change": "fan_change_interval",
    "auto_loop": "auto_loop_interval",
    "temp_read": "temp_read_interval",
    "set_min": "setpoint_min",
    "set_max": "setpoint_max",
    "brightness": "brightness",
}

# Compile-time defaults reported alongside each tunable's live value in the
# settings characteristic, keyed by wire name (see SETTINGS_WIRE_KEYS
# above), same shape as the real firmware's ble_server.py.
SETTINGS_DEFAULTS = {
    "delta": config.DEFAULT_DELTA,
    "fan_high": config.DEFAULT_AUTO_FAN_HIGH_THRESH,
    "fan_med": config.DEFAULT_AUTO_FAN_MED_THRESH,
    "fan_change": config.DEFAULT_FAN_CHANGE_INTERVAL,
    "auto_loop": config.DEFAULT_AUTO_LOOP_INTERVAL,
    "temp_read": config.DEFAULT_TEMP_READ_INTERVAL,
    "set_min": config.DEFAULT_SETPOINT_MIN,
    "set_max": config.DEFAULT_SETPOINT_MAX,
    "brightness": config.DEFAULT_BRIGHTNESS,
}


def _enc_str(s):
    return bytearray(s.encode())


def _enc_f(v):
    return bytearray("{:.2f}".format(float(v) if v is not None else 0.0).encode())


def _dec_str(b):
    return bytes(b).decode().strip("\x00").lower()


def _dec_f(b):
    return float(bytes(b).decode().strip("\x00"))


def _round(v):
    return round(float(v), 2) if v is not None else None


def _unwrap_settings(d):
    """Accept flat {wire_key: value} or wrapped {wire_key: [value, default]}
    -- return flat {attr_key: value} for controller.set_settings().

    Value is a bare 2-element [value, default] array (not a {"v","d"}
    object), matching ../aircon/ble_server.py, to keep the settings
    characteristic's JSON payload under the default BLE ATT MTU's
    single-read/notification-fragment size where possible.
    """
    out = {}
    for k, v in d.items():
        attr = SETTINGS_WIRE_KEYS.get(k)
        if attr is None:
            continue
        if isinstance(v, (list, tuple)):
            if len(v) > 0 and v[0] is not None:
                out[attr] = v[0]
        else:
            out[attr] = v
    return out


class SimBLEServer:
    def __init__(self, controller):
        self.ctrl = controller
        self.server = None
        self._last_sent = {}

        self._name_uuid = {
            "mode": config.BLE_UUID_MODE,
            "fan": config.BLE_UUID_FAN,
            "setpoint": config.BLE_UUID_SETPOINT,
            "circ": config.BLE_UUID_CIRC,
            "panel": config.BLE_UUID_PANEL,
            "settings": config.BLE_UUID_SETTINGS,
            "status": config.BLE_UUID_STATUS,
        }
        self._uuid_name = {v.lower(): k for k, v in self._name_uuid.items()}

    async def start(self, loop):
        # bless's backend (CoreBluetooth/BlueZ) already logs central
        # subscribe/unsubscribe and raw read/write requests -- but only at
        # DEBUG, which main.py's basicConfig(level=INFO) suppresses. Turn it
        # on here so "did a client even connect/subscribe" is visible.
        # logging.getLogger("bless").setLevel(logging.DEBUG)

        server = BlessServer(name=config.BLE_DEVICE_NAME, loop=loop)
        server.read_request_func = self._on_read
        server.write_request_func = self._on_write
        self.server = server

        await server.add_new_service(config.BLE_SVC_UUID)

        rw_notify = (
            GATTCharacteristicProperties.read
            | GATTCharacteristicProperties.write
            | GATTCharacteristicProperties.write_without_response
            | GATTCharacteristicProperties.notify
        )
        ro_notify = GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify
        rw_perms = GATTAttributePermissions.readable | GATTAttributePermissions.writeable
        ro_perms = GATTAttributePermissions.readable

        # value=None for every characteristic (not just the writable ones):
        # CoreBluetooth (macOS) treats any characteristic created with a
        # non-None value as a static/cached one and rejects it outright if
        # it's also writable -- "Characteristics with cached values must be
        # read-only". So every characteristic starts empty here and gets its
        # real value assigned dynamically via push() below.
        for name in ("mode", "fan", "setpoint", "circ", "panel", "settings"):
            await server.add_new_characteristic(
                config.BLE_SVC_UUID, self._name_uuid[name], rw_notify, None, rw_perms
            )
        await server.add_new_characteristic(
            config.BLE_SVC_UUID, self._name_uuid["status"], ro_notify, None, ro_perms
        )

        # Also order-sensitive on macOS: server.start() is what actually
        # registers the service with CoreBluetooth (addService_), and it
        # applies that same cached-value check at registration time. Setting
        # .value on a characteristic *before* that point makes it look
        # "cached" and triggers the same rejection even though value=None
        # was used above -- so populate real values only *after* start().
        await server.start()

        # server.start() returning without raising does NOT guarantee
        # CoreBluetooth is actually broadcasting -- authorization/power-state
        # issues on macOS can leave it silently not advertising. Check and
        # say so explicitly instead of just hoping.
        advertising = await server.is_advertising()
        if advertising:
            logger.info("advertising as %r, service %s", config.BLE_DEVICE_NAME, config.BLE_SVC_UUID)
        else:
            logger.warning(
                "server.start() returned but is_advertising() is False -- "
                "not actually broadcasting. On macOS this usually means "
                "Bluetooth permission/power state changed *after* this "
                "process's CBPeripheralManager was created; restart the "
                "script (a fresh process gets a fresh manager) rather than "
                "expecting it to pick up a permission grant live."
            )

        self.push(force=True)
        self.ctrl.on_change = self.push

    # ── bless callbacks ──────────────────────────────────────────────────
    # NOTE: on macOS these run on a background thread (bless's CoreBluetooth
    # backend), not the asyncio loop -- kept deliberately simple (plain
    # attribute reads/writes on SimController, no compound state spanning
    # multiple attributes) so that's safe without extra locking.

    def _on_read(self, characteristic, **kwargs):
        name = self._uuid_name.get(str(characteristic.uuid).lower())
        logger.info("read %s (%s): %r", name or "?", characteristic.uuid, bytes(characteristic.value or b""))
        return characteristic.value

    def _on_write(self, characteristic, value, **kwargs):
        characteristic.value = value
        name = self._uuid_name.get(str(characteristic.uuid).lower())
        logger.info("write request %s (%s): %r", name or "?", characteristic.uuid, bytes(value))
        if name is None:
            logger.warning("write to unrecognized characteristic %s, ignoring", characteristic.uuid)
            return
        try:
            if name == "mode":
                self.ctrl.set_mode(_dec_str(value))
            elif name == "fan":
                self.ctrl.set_fan(_dec_str(value))
            elif name == "setpoint":
                self.ctrl.set_setpoint(_dec_f(value))
            elif name == "circ":
                self.ctrl.set_circulation(_dec_str(value))
            elif name == "panel":
                self.ctrl.set_panel_temp(_dec_f(value))
            elif name == "settings":
                self.ctrl.set_settings(_unwrap_settings(json.loads(bytes(value).decode())))
            logger.info("write %s applied: %r", name, bytes(value))
        except Exception:
            logger.exception("write %s failed (value=%r)", name, bytes(value))

    # ── push state → characteristics, notify only what changed ────────────

    def push(self, force=False):
        s = self.ctrl.get_state()
        values = {
            "mode": _enc_str(s["mode"]),
            "fan": _enc_str(s["fan"]),
            "setpoint": _enc_f(s["setpoint"]),
            "circ": _enc_str(s["circulation"]),
            "panel": _enc_f(s["panel_temp"]),
            # [value, default], not {"v":.., "d":..} -- see
            # _unwrap_settings()'s docstring. wire_key/attr_key per
            # SETTINGS_WIRE_KEYS above.
            "settings": bytearray(
                json.dumps(
                    {
                        wire: [s[attr], SETTINGS_DEFAULTS[wire]]
                        for wire, attr in SETTINGS_WIRE_KEYS.items()
                    }
                ).encode()
            ),
            "status": bytearray(
                json.dumps(
                    {
                        "curr": _round(s["current_temp"]),
                        "comp": s["compressor"],
                        "cabin": _round(s["cabin_temp"]),
                        "blower": _round(s["blower_temp"]),
                        "exhaust": _round(s["exhaust_temp"]),
                        "baggage": _round(s["baggage_temp"]),
                        "tail": _round(s["tail_temp"]),
                        "err": s["error"],
                    }
                ).encode()
            ),
        }
        for name, data in values.items():
            if not force and self._last_sent.get(name) == data:
                continue
            self._last_sent[name] = data
            uuid = self._name_uuid[name]
            char = self.server.get_characteristic(uuid)
            if char is None:
                continue
            char.value = data
            self.server.update_value(config.BLE_SVC_UUID, uuid)
