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

# Compile-time defaults reported alongside each tunable's live value in the
# settings characteristic, same shape as the real firmware's ble_server.py.
SETTINGS_DEFAULTS = {
    "delta": config.DEFAULT_DELTA,
    "fan_high_thresh": config.DEFAULT_AUTO_FAN_HIGH_THRESH,
    "fan_med_thresh": config.DEFAULT_AUTO_FAN_MED_THRESH,
    "fan_change_interval": config.DEFAULT_FAN_CHANGE_INTERVAL,
    "auto_loop_interval": config.DEFAULT_AUTO_LOOP_INTERVAL,
    "temp_read_interval": config.DEFAULT_TEMP_READ_INTERVAL,
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
    """Accept flat {key: value} or wrapped {key: {v: value, d: default}}.

    Wire keys are the terse "v"/"d" (not "value"/"default", matching
    ../aircon/ble_server.py) to keep the settings characteristic's JSON
    payload under the default BLE ATT MTU's single-read/notification-
    fragment size where possible.
    """
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            if v.get("v") is not None:
                out[k] = v["v"]
        else:
            out[k] = v
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
            # "v"/"d", not "value"/"default" -- see _unwrap_settings()'s docstring.
            "settings": bytearray(
                json.dumps(
                    {k: {"v": s[k], "d": SETTINGS_DEFAULTS[k]} for k in SETTINGS_DEFAULTS}
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
