"""BLE GATT peripheral exposing the AirCon's multi-characteristic service,
the heater's single-characteristic service, AND the fuel sensor's own two
services (standard Battery Service + a custom one for raw voltage/
calibration) from one process, one BlessServer (cross-platform GATT
server: CoreBluetooth on macOS, BlueZ/D-Bus on Linux) -- replaces the
previous ../aircon-sim/ble_server.py + ../heater-sim/ble_server.py split,
which ran as two independent processes and turned out not to reliably
coexist on one Mac's Bluetooth radio: each process's own bless/
CoreBluetooth "did start advertising" confirmation only reflects THAT
process's local CBPeripheralManager state, not whether the shared radio
actually has room to broadcast a second, simultaneous peripheral identity
-- so both could (and did) log a clean success while only one was actually
reaching the air. One process, one CBPeripheralManager, one advertised
identity, sidesteps that entirely, and the same reasoning is exactly why
the fuel sensor joined this same process instead of getting its own --
see ../hvac-knob/fuel_ble.py's own module docstring for how that client
shares its own BLE connection/discovery with AirconClient/HeaterClient the
same way those two already share with each other, needed because all
three now resolve to one BLE address. `bless` already supports registering
multiple GATT services on a single BlessServer (add_new_service() is a
plain dict keyed by service UUID, and start()'s own advertisement-building
loop already iterates every registered service) -- that's exactly the
mechanism this relies on.

Each of the three devices is independently optional -- see main.py's
--ac-only/--heat-only/--no-fuel -- `ac_ctrl`/`heat_ctrl`/`fuel_ctrl` are
None when that device is disabled, and this class skips registering its
service/characteristics entirely rather than just ignoring traffic for
them.
"""

import json
import logging

from bless import (
    BlessServer,
    GATTCharacteristicProperties,
    GATTAttributePermissions,
)

import config
import heat_protocol

logger = logging.getLogger("hvac-sim.ble")

# ── AC wire helpers (was ../aircon-sim/ble_server.py) ────────────────────

# Wire key (as sent/received on the settings characteristic) -> controller
# attribute name. Controller attributes stay verbose (self.fan_high_thresh
# etc., unchanged) -- only the wire keys are terse, to keep the settings
# JSON payload's size down. "delta" isn't renamed; the rest drop
# "_thresh"/"_interval" and "setpoint" -> "set", matching
# ../aircon/ble_server.py exactly.
AC_SETTINGS_WIRE_KEYS = {
    "delta": "delta",
    "fan_high": "fan_high_thresh",
    "fan_med": "fan_med_thresh",
    "fan_change": "fan_change_interval",
    "auto_loop": "auto_loop_interval",
    "temp_read": "temp_read_interval",
    "set_min": "setpoint_min",
    "set_max": "setpoint_max",
}

# Compile-time defaults reported alongside each tunable's live value in the
# settings characteristic, keyed by wire name (see AC_SETTINGS_WIRE_KEYS
# above), same shape as the real firmware's ble_server.py.
AC_SETTINGS_DEFAULTS = {
    "delta": config.DEFAULT_DELTA,
    "fan_high": config.DEFAULT_AUTO_FAN_HIGH_THRESH,
    "fan_med": config.DEFAULT_AUTO_FAN_MED_THRESH,
    "fan_change": config.DEFAULT_FAN_CHANGE_INTERVAL,
    "auto_loop": config.DEFAULT_AUTO_LOOP_INTERVAL,
    "temp_read": config.DEFAULT_TEMP_READ_INTERVAL,
    "set_min": config.DEFAULT_SETPOINT_MIN,
    "set_max": config.DEFAULT_SETPOINT_MAX,
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


# ── Fuel wire helpers (was ../fuel-level/ble_server.py) ──────────────────
# Copied (not imported -- no shared path, see config.py's own module
# docstring) directly from that real firmware's own _enc_v()/_dec_v(),
# which encode the standard Voltage characteristic's own wire format
# (org.bluetooth.characteristic.voltage, confirmed against the Bluetooth
# SIG's own public GATT Specification Supplement source -- see that
# file's own module docstring for the full citation): uint16 little-
# endian, 1/64 V units, 0xFFFF reserved for "not known". Reused here for
# the two calibration characteristics too, same as that real firmware
# does, purely for encoding consistency -- see config.py's own
# FUEL_BLE_UUID_CAL_ZERO/CAL_FULL comment.


def _enc_v(volts):
    raw = min(max(int(round(volts * 64)), 0), 0xFFFE)
    return bytearray(raw.to_bytes(2, "little"))


def _dec_v(data):
    raw = int.from_bytes(bytes(data), "little")
    return raw / 64.0


def _unwrap_settings(d):
    """Accept flat {wire_key: value} or wrapped {wire_key: [value, default]}
    -- return flat {attr_key: value} for ac_controller.SimController.
    set_settings().

    Value is a bare 2-element [value, default] array (not a {"v","d"}
    object), matching ../aircon/ble_server.py, to keep the settings
    characteristic's JSON payload under the default BLE ATT MTU's
    single-read/notification-fragment size where possible.
    """
    out = {}
    for k, v in d.items():
        attr = AC_SETTINGS_WIRE_KEYS.get(k)
        if attr is None:
            continue
        if isinstance(v, (list, tuple)):
            if len(v) > 0 and v[0] is not None:
                out[attr] = v[0]
        else:
            out[attr] = v
    return out


class SimBLEServer:
    def __init__(self, ac_ctrl, heat_ctrl, fuel_ctrl, device_name=None):
        """`ac_ctrl`/`heat_ctrl`/`fuel_ctrl` are this package's
        ac_controller.SimController/heat_controller.SimHeaterController/
        fuel_controller.SimFuelController instances, or None to skip that
        device's service/characteristics entirely (see main.py's
        --ac-only/--heat-only/--no-fuel). `device_name` overrides config.
        BLE_DEVICE_NAME for the one combined identity this whole process
        advertises as -- there's no separate per-device name anymore, see
        config.py's own BLE_DEVICE_NAME comment.
        """
        self.ac_ctrl = ac_ctrl
        self.heat_ctrl = heat_ctrl
        self.fuel_ctrl = fuel_ctrl
        self.device_name = device_name or config.BLE_DEVICE_NAME
        self.server = None
        self._last_sent = {}

        self._ac_name_uuid = (
            {
                "mode": config.BLE_UUID_MODE,
                "fan": config.BLE_UUID_FAN,
                "setpoint": config.BLE_UUID_SETPOINT,
                "circ": config.BLE_UUID_CIRC,
                "panel": config.BLE_UUID_PANEL,
                "settings": config.BLE_UUID_SETTINGS,
                "status": config.BLE_UUID_STATUS,
            }
            if ac_ctrl is not None
            else {}
        )
        self._ac_uuid_name = {v.lower(): k for k, v in self._ac_name_uuid.items()}
        self._heat_char_uuid = config.HEAT_BLE_CHAR_UUID.lower() if heat_ctrl is not None else None

        # Spans BOTH of the fuel sensor's services (Battery Service +
        # config.FUEL_BLE_SVC_UUID) in one flat map -- fine for _on_read()/
        # _on_write()'s own purposes, which only ever need "which field is
        # this characteristic's UUID" and don't care which service it
        # happens to live under; _fuel_name_svc below is the one place that
        # distinction actually matters (push_fuel()'s update_value() calls,
        # which need the *right* service UUID per characteristic).
        self._fuel_name_uuid = (
            {
                "level": config.FUEL_BLE_CHAR_BATTERY_LEVEL,
                "voltage": config.FUEL_BLE_CHAR_VOLTAGE,
                "cal_zero": config.FUEL_BLE_UUID_CAL_ZERO,
                "cal_full": config.FUEL_BLE_UUID_CAL_FULL,
            }
            if fuel_ctrl is not None
            else {}
        )
        self._fuel_uuid_name = {v.lower(): k for k, v in self._fuel_name_uuid.items()}
        self._fuel_name_svc = {
            "level": config.FUEL_BLE_SVC_BATTERY,
            "voltage": config.FUEL_BLE_SVC_UUID,
            "cal_zero": config.FUEL_BLE_SVC_UUID,
            "cal_full": config.FUEL_BLE_SVC_UUID,
        }

    async def start(self, loop):
        server = BlessServer(name=self.device_name, loop=loop)
        server.read_request_func = self._on_read
        server.write_request_func = self._on_write
        self.server = server

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
        # read-only". So every characteristic starts empty here and gets
        # its real value assigned dynamically via push_ac()/push_heat()
        # below, only *after* server.start() -- setting .value before that
        # point makes it look "cached" too and triggers the same rejection
        # even with value=None used at creation.
        if self.ac_ctrl is not None:
            await server.add_new_service(config.AC_BLE_SVC_UUID)
            for name in ("mode", "fan", "setpoint", "circ", "panel", "settings"):
                await server.add_new_characteristic(
                    config.AC_BLE_SVC_UUID, self._ac_name_uuid[name], rw_notify, None, rw_perms
                )
            await server.add_new_characteristic(
                config.AC_BLE_SVC_UUID, self._ac_name_uuid["status"], ro_notify, None, ro_perms
            )

        if self.heat_ctrl is not None:
            await server.add_new_service(config.HEAT_BLE_SVC_UUID)
            await server.add_new_characteristic(
                config.HEAT_BLE_SVC_UUID, config.HEAT_BLE_CHAR_UUID, rw_notify, None, rw_perms
            )

        if self.fuel_ctrl is not None:
            # Two services, matching ../fuel-level/ble_server.py's own
            # split exactly -- see this file's module docstring and
            # config.py's own FUEL_BLE_* comments for why: standard
            # Battery Service (just Battery Level) kept "clean" for
            # generic-client recognition, custom Fuel Level service for
            # everything the Bluetooth SIG has no standard slot for.
            await server.add_new_service(config.FUEL_BLE_SVC_BATTERY)
            await server.add_new_characteristic(
                config.FUEL_BLE_SVC_BATTERY,
                config.FUEL_BLE_CHAR_BATTERY_LEVEL,
                ro_notify,
                None,
                ro_perms,
            )
            await server.add_new_service(config.FUEL_BLE_SVC_UUID)
            await server.add_new_characteristic(
                config.FUEL_BLE_SVC_UUID, config.FUEL_BLE_CHAR_VOLTAGE, ro_notify, None, ro_perms
            )
            await server.add_new_characteristic(
                config.FUEL_BLE_SVC_UUID, config.FUEL_BLE_UUID_CAL_ZERO, rw_notify, None, rw_perms
            )
            await server.add_new_characteristic(
                config.FUEL_BLE_SVC_UUID, config.FUEL_BLE_UUID_CAL_FULL, rw_notify, None, rw_perms
            )

        await server.start()

        # server.start() returning without raising does NOT guarantee
        # CoreBluetooth is actually broadcasting -- authorization/power-state
        # issues on macOS can leave it silently not advertising. Check and
        # say so explicitly instead of just hoping.
        advertising = await server.is_advertising()
        if advertising:
            logger.info(
                "advertising as %r (ac=%s heat=%s fuel=%s)",
                self.device_name,
                self.ac_ctrl is not None,
                self.heat_ctrl is not None,
                self.fuel_ctrl is not None,
            )
        else:
            logger.warning(
                "server.start() returned but is_advertising() is False -- "
                "not actually broadcasting. On macOS this usually means "
                "Bluetooth permission/power state changed *after* this "
                "process's CBPeripheralManager was created; restart the "
                "script (a fresh process gets a fresh manager) rather than "
                "expecting it to pick up a permission grant live."
            )

        if self.ac_ctrl is not None:
            self.push_ac(force=True)
            self.ac_ctrl.on_change = self.push_ac
        if self.heat_ctrl is not None:
            self.push_heat()
            self.heat_ctrl.on_change = self.push_heat
        if self.fuel_ctrl is not None:
            self.push_fuel()
            self.fuel_ctrl.on_change = self.push_fuel

    # ── bless callbacks ──────────────────────────────────────────────────
    # Same threading caveat both predecessor sims' own docstrings noted: on
    # macOS these run on a background thread (bless's CoreBluetooth
    # backend), not the asyncio loop -- kept simple (plain attribute reads/
    # writes on each controller, no compound cross-attribute state), so
    # that's safe without extra locking, same as before the merge.

    def _on_read(self, characteristic, **kwargs):
        uuid = str(characteristic.uuid).lower()
        if uuid in self._ac_uuid_name:
            logger.info(
                "read ac.%s (%s): %r", self._ac_uuid_name[uuid], characteristic.uuid, bytes(characteristic.value or b"")
            )
        elif uuid == self._heat_char_uuid:
            logger.info("read heat (%s): %r", characteristic.uuid, bytes(characteristic.value or b""))
        elif uuid in self._fuel_uuid_name:
            logger.info(
                "read fuel.%s (%s): %r",
                self._fuel_uuid_name[uuid],
                characteristic.uuid,
                bytes(characteristic.value or b""),
            )
        return characteristic.value

    def _on_write(self, characteristic, value, **kwargs):
        uuid = str(characteristic.uuid).lower()
        if uuid in self._ac_uuid_name:
            self._on_write_ac(self._ac_uuid_name[uuid], characteristic, value)
        elif uuid == self._heat_char_uuid:
            self._on_write_heat(value)
        elif uuid in self._fuel_uuid_name:
            self._on_write_fuel(self._fuel_uuid_name[uuid], characteristic, value)
        else:
            logger.warning("write to unrecognized characteristic %s, ignoring", characteristic.uuid)

    # ── AC write dispatch (was ../aircon-sim/ble_server.py's _on_write) ────

    def _on_write_ac(self, name, characteristic, value):
        characteristic.value = value
        logger.info("write request ac.%s (%s): %r", name, characteristic.uuid, bytes(value))
        try:
            if name == "mode":
                self.ac_ctrl.set_mode(_dec_str(value))
            elif name == "fan":
                self.ac_ctrl.set_fan(_dec_str(value))
            elif name == "setpoint":
                self.ac_ctrl.set_setpoint(_dec_f(value))
            elif name == "circ":
                self.ac_ctrl.set_circulation(_dec_str(value))
            elif name == "panel":
                self.ac_ctrl.set_panel_temp(_dec_f(value))
            elif name == "settings":
                self.ac_ctrl.set_settings(_unwrap_settings(json.loads(bytes(value).decode())))
            logger.info("write ac.%s applied: %r", name, bytes(value))
        except Exception:
            logger.exception("write ac.%s failed (value=%r)", name, bytes(value))

    # ── Heater write dispatch (was ../heater-sim/ble_server.py's _on_write) ─

    def _on_write_heat(self, value):
        raw = bytes(value)
        logger.info("write request heat: %s", raw.hex())
        try:
            password, cmd, param1, param2 = heat_protocol.decode_frame(raw)
        except heat_protocol.FrameError as e:
            logger.warning("bad heater frame, ignoring: %s", e)
            return
        # Every frame carries a password in this protocol version -- see
        # heat_protocol.py's decode_frame() docstring -- checked here, per
        # frame, rather than via a dedicated handshake command this
        # protocol version doesn't have. NOT hardware-verified what a real
        # unit actually does on a wrong password (silently ignore, like
        # this does? some explicit reject we just can't decode yet? see
        # ../hvac-knob/heater_ble.py's module docstring, point 3) -- this
        # is a documented guess, not a confirmed behavior.
        if self.heat_ctrl.password is not None and password != self.heat_ctrl.password:
            logger.info(
                "wrong heater password (got %04d, want %04d) -- ignoring, no response",
                password,
                self.heat_ctrl.password,
            )
            return
        try:
            self._dispatch_heat(cmd, param1, param2)
        except Exception:
            logger.exception("heater dispatch failed for cmd=%d param1=%d param2=%d", cmd, param1, param2)

    def _dispatch_heat(self, cmd, param1, param2):
        if cmd == config.CMD_READ:
            logger.info("heat -> read/poll")
        elif cmd == config.CMD_SET_MODE:
            logger.info("heat -> set mode=%d", param1)
            self.heat_ctrl.set_mode(param1)
        elif cmd == config.CMD_ON_OFF:
            if param1:
                logger.info("heat -> power on")
                self.heat_ctrl.power_on()
            else:
                logger.info("heat -> power off")
                self.heat_ctrl.power_off()
        elif cmd == config.CMD_SET_GEAR_OR_TEMP:
            logger.info("heat -> set gear/temp=%d", param1)
            self.heat_ctrl.set_gear_or_temp(param1)
        else:
            logger.info("heat: unhandled cmd=%d param1=%d param2=%d (not implemented in this sim)", cmd, param1, param2)
            return
        # Every recognized command gets an immediate status push in
        # response -- confirmed in the real capture for all four of these
        # (CMD_READ included: it's a poll, and every real one observed was
        # followed shortly by a notification).
        self.push_heat(cmd_echo=cmd)

    # ── Fuel write dispatch (was ../fuel-level/ble_server.py's watch()) ────
    # Only the two calibration characteristics are ever written -- Battery
    # Level/Voltage are read/notify-only on the real firmware too (this
    # sim's own percent/voltage are entirely internally driven, see
    # fuel_controller.py).

    def _on_write_fuel(self, name, characteristic, value):
        characteristic.value = value
        logger.info("write request fuel.%s (%s): %r", name, characteristic.uuid, bytes(value))
        try:
            if name == "cal_zero":
                self.fuel_ctrl.set_cal_zero(_dec_v(value))
            elif name == "cal_full":
                self.fuel_ctrl.set_cal_full(_dec_v(value))
            else:
                logger.warning("write to read-only fuel.%s, ignoring", name)
                return
            logger.info("write fuel.%s applied: %r", name, bytes(value))
        except Exception:
            logger.exception("write fuel.%s failed (value=%r)", name, bytes(value))

    # ── push state -> characteristics, notify only what changed ───────────

    def push_ac(self, force=False):
        s = self.ac_ctrl.get_state()
        values = {
            "mode": _enc_str(s["mode"]),
            "fan": _enc_str(s["fan"]),
            "setpoint": _enc_f(s["setpoint"]),
            "circ": _enc_str(s["circulation"]),
            "panel": _enc_f(s["panel_temp"]),
            # [value, default], not {"v":.., "d":..} -- see
            # _unwrap_settings()'s docstring. wire_key/attr_key per
            # AC_SETTINGS_WIRE_KEYS above.
            "settings": bytearray(
                json.dumps(
                    {
                        wire: [s[attr], AC_SETTINGS_DEFAULTS[wire]]
                        for wire, attr in AC_SETTINGS_WIRE_KEYS.items()
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
                        # "comptemp", not "comp" -- that key's already taken
                        # by the compressor on/off status above.
                        "comptemp": _round(s["compressor_temp"]),
                        "baggage": _round(s["baggage_temp"]),
                        "tail": _round(s["tail_temp"]),
                        "err": s["error"],
                        "ver": s["version"],
                    }
                ).encode()
            ),
        }
        for name, data in values.items():
            key = "ac." + name
            if not force and self._last_sent.get(key) == data:
                continue
            self._last_sent[key] = data
            uuid = self._ac_name_uuid[name]
            char = self.server.get_characteristic(uuid)
            if char is None:
                continue
            char.value = data
            self.server.update_value(config.AC_BLE_SVC_UUID, uuid)

    def push_heat(self, cmd_echo=config.CMD_READ):
        """cmd_echo defaults to CMD_READ for the background loop's
        unprompted periodic pushes (see heat_controller.py's run()), which
        have no real triggering command to echo -- NOT hardware-verified
        what a real unit's own unprompted pushes actually echo in that
        byte, if anything in particular; see heat_protocol.py's
        encode_status() for which fields this sim actually encodes vs.
        leaves zeroed.

        Unconditionally writes + notifies every call -- no dedup against
        the previous push (unlike push_ac(), which only actually
        write+notify a given field when its encoded bytes change -- see
        push_fuel()'s own docstring for why it now matches this method
        instead of push_ac(), despite starting out closer to push_ac()'s
        own shape). Confirmed to matter, not just needless traffic: this
        controller has no continuous jitter the way ac_controller.py's
        thermal model does (whose random.uniform() noise means some field
        differs on nearly every tick, so its own dedup rarely actually
        suppresses anything in practice) -- once state settles (e.g. fully
        off after a cooldown), every subsequent encoded frame is byte-for-
        byte identical to the last. A dedup gate here means the *one*
        notification carrying a real transition (like COOLING -> OFF) is
        the only opportunity the panel ever gets to learn about it -- if
        that single BLE notification is ever dropped (a real, if
        uncommon, possibility, not something this sim can rule out),
        heater_ble.HeaterClient's own state.cooling_off has no way left to
        ever self-correct, since no future push would ever differ from
        the stale value it already has. Unconditional writes turn every
        one of heat_controller.py's own HEAT_NOTIFY_INTERVAL heartbeat
        ticks into another chance to self-heal instead.
        """
        s = self.heat_ctrl.get_state()
        data = heat_protocol.encode_status(
            cmd_echo, s["on"], s["cooling"], s["now_gear"], fault_code=s["fault_code"]
        )
        char = self.server.get_characteristic(config.HEAT_BLE_CHAR_UUID)
        if char is None:
            return
        char.value = bytearray(data)
        self.server.update_value(config.HEAT_BLE_SVC_UUID, config.HEAT_BLE_CHAR_UUID)

    def push_fuel(self):
        """Unconditionally writes + notifies every field, every call -- see
        push_heat()'s own docstring for why a dedup-against-last-push gate
        (like push_ac()'s own, which is fine for that controller -- see
        that reasoning) is actively harmful here instead of just wasted
        traffic: with --fuel-drain-rate 0 (a documented, supported way to
        run this sim), fuel_controller.SimFuelController's own state is
        exactly as static as the heater's once settled, and a single
        dropped notification carrying a real change (e.g. a fresh
        calibration write) would otherwise never have a second chance to
        reach a connected panel.
        """
        s = self.fuel_ctrl.get_state()
        values = {
            # int(round(...)), not a bare int(...) truncation -- matches
            # ../fuel-level/ble_server.py's own _push_state(). Clamped
            # 0-100 the same way that real firmware's own FuelSensor.
            # percent property is (this sim's own percent should already
            # be in range -- see fuel_controller.py -- but this is the
            # wire boundary, the same place that real firmware enforces it
            # too).
            "level": bytearray([min(max(int(round(s["percent"])), 0), 100)]),
            "voltage": _enc_v(s["voltage"]),
            "cal_zero": _enc_v(s["cal_zero_v"]),
            "cal_full": _enc_v(s["cal_full_v"]),
        }
        for name, data in values.items():
            uuid = self._fuel_name_uuid[name]
            char = self.server.get_characteristic(uuid)
            if char is None:
                continue
            char.value = data
            self.server.update_value(self._fuel_name_svc[name], uuid)
