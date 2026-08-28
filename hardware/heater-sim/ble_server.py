"""BLE GATT peripheral exposing the same single read/write/notify
characteristic as the real heater (see ../hvac-knob/heater_ble_config.py),
backed by `bless` (cross-platform GATT server: CoreBluetooth on macOS,
BlueZ/D-Bus on Linux) -- see ../aircon-sim/ble_server.py for the AirCon
side's analog of this file, which this deliberately parallels in structure
even though the actual wire format (one binary framed protocol over one
characteristic, not one characteristic per field) is completely different.
"""

import logging

from bless import (
    BlessServer,
    GATTCharacteristicProperties,
    GATTAttributePermissions,
)

import config
import protocol

logger = logging.getLogger("heater-sim.ble")


class SimBLEServer:
    def __init__(self, controller, device_name=None):
        self.ctrl = controller
        # None -> config.BLE_DEVICE_NAME, the default -- device_name only
        # ever comes from main.py's --name override (see config.py's
        # BLE_DEVICE_NAME comment for why the default is deliberately
        # short: confirmed on real hardware, not just reasoned about, that
        # this is what actually gets found by the panel's scan on macOS).
        self.device_name = device_name or config.BLE_DEVICE_NAME
        self.server = None
        self._last_sent = None

    async def start(self, loop):
        server = BlessServer(name=self.device_name, loop=loop)
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
        rw_perms = GATTAttributePermissions.readable | GATTAttributePermissions.writeable

        # value=None, not a real starting frame -- see
        # ../aircon-sim/ble_server.py's identical comment: CoreBluetooth
        # (macOS) rejects a writable characteristic created with a non-None
        # cached value outright. Populated for real via push() below, only
        # after server.start() (same ordering requirement, same reason).
        await server.add_new_characteristic(
            config.BLE_SVC_UUID, config.BLE_CHAR_UUID, rw_notify, None, rw_perms
        )

        await server.start()

        advertising = await server.is_advertising()
        if advertising:
            logger.info("advertising as %r, service %s", self.device_name, config.BLE_SVC_UUID)
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
    # Same threading caveat as ../aircon-sim/ble_server.py: on macOS these
    # run on a background thread (bless's CoreBluetooth backend), not the
    # asyncio loop. Kept simple here too (one dict of plain attributes on
    # SimHeaterController, no compound cross-attribute state), so this is
    # safe without extra locking for the same reason that file's is.

    def _on_read(self, characteristic, **kwargs):
        value = bytes(characteristic.value or b"")
        logger.info("read: %s", value.hex())
        return characteristic.value

    def _on_write(self, characteristic, value, **kwargs):
        raw = bytes(value)
        logger.info("write request: %s", raw.hex())
        try:
            cmd1, cmd2, payload = protocol.decode_frame(raw)
        except protocol.FrameError as e:
            logger.warning("bad frame, ignoring: %s", e)
            return
        try:
            self._dispatch(cmd1, cmd2, payload)
        except Exception:
            logger.exception("dispatch failed for cmd1=%d cmd2=%d payload=%r", cmd1, cmd2, payload)

    def _dispatch(self, cmd1, cmd2, payload):
        if cmd1 == config.CMD_RUN:
            if cmd2 == config.SUB_RUN_OFF:
                logger.info("-> power off")
                self.ctrl.power_off()
            elif cmd2 == config.SUB_RUN_ON:
                if len(payload) < 4:
                    logger.warning("SUB_RUN_ON payload too short: %r", payload)
                    return
                run_mode, run_param = payload[0], payload[1]
                remain_run_time = payload[2] | (payload[3] << 8)
                logger.info(
                    "-> power on run_mode=%d run_param=%d remain_run_time=%d",
                    run_mode,
                    run_param,
                    remain_run_time,
                )
                self.ctrl.power_on(run_mode, run_param, remain_run_time)
            else:
                logger.info("unhandled CMD_RUN cmd2=%d payload=%r", cmd2, payload)
        elif cmd1 == config.CMD_INFO and cmd2 == config.SUB_INFO_MAC:
            # Real device would answer with MAC/HW/SW version/part number/
            # mode-capability bitmask -- heater_ble.py's client never sends
            # this query (see its module docstring, point 1: no read-back),
            # so there's nothing exercising this path today. Logged, not
            # implemented, so it's visible if that ever changes.
            logger.info("CMD_INFO/SUB_INFO_MAC query received (not implemented in this sim)")
        elif cmd1 == config.CMD_ATTR and cmd2 == config.SUB_ATTR_QUERY:
            logger.info("CMD_ATTR/SUB_ATTR_QUERY query received (not implemented in this sim)")
        elif cmd1 == config.CMD_HANDSHAKE and cmd2 == config.SUB_HANDSHAKE:
            self._handle_handshake(payload)
        else:
            logger.info("unhandled cmd1=%d cmd2=%d payload=%r", cmd1, cmd2, payload)

    def _handle_handshake(self, payload):
        """CMD_HANDSHAKE/SUB_HANDSHAKE -- see ../hvac-knob/heater_ble.py's
        _attempt_handshake()/_encode_password() for the client side of
        this exact exchange (this sim's payload decoding is that
        function's inverse).

        If this sim wasn't started with --password (config.ctrl.password
        is None), it deliberately does NOT respond at all here, matching
        how most real units apparently behave (never seen replying to this
        command) and exercising the client's "no response at all -> this
        unit must not gate on a password" heuristic -- see that module's
        own docstring, point 3. Only responds (accept or explicit reject)
        when this sim was actually configured to require one.
        """
        if self.ctrl.password is None:
            logger.info(
                "CMD_HANDSHAKE received -- no --password configured for this "
                "sim, not responding at all (see this method's own docstring)"
            )
            return
        if len(payload) < 2:
            logger.warning("CMD_HANDSHAKE payload too short: %r", payload)
            return
        # Inverse of heater_ble.py's _encode_password(): byte0 = pw % 100,
        # byte1 = pw // 100.
        candidate = payload[1] * 100 + payload[0]
        ok = candidate == self.ctrl.password
        logger.info("CMD_HANDSHAKE candidate=%04d -- %s", candidate, "accepted" if ok else "REJECTED")
        self._send_frame(protocol.encode_response(config.CMD_HANDSHAKE, config.SUB_HANDSHAKE, bytes([1 if ok else 0])))

    def _send_frame(self, frame):
        char = self.server.get_characteristic(config.BLE_CHAR_UUID)
        if char is None:
            return
        char.value = bytearray(frame)
        self.server.update_value(config.BLE_SVC_UUID, config.BLE_CHAR_UUID)

    # ── push state → characteristic, notify only what changed ─────────────

    def push(self, force=False):
        s = self.ctrl.get_state()
        # Absolute frame-byte offsets 8-17, matching
        # ../hvac-knob/heater_ble_config.py's documented status-frame
        # layout (mainboard_type@8, mesh_sub_devices_num@9, run_state@10,
        # run_mode@11, run_param@12, now_gear@13, run_step@14,
        # fault_display@15, fault_code@16, temp_unit@17) -- this sim only
        # actually varies now_gear/fault_code/run_mode/run_param (the
        # fields heater_ble.py's client either reads directly off a
        # notification or that are simply useful to see in this sim's own
        # logs); the rest are fixed placeholders. See
        # heater_ble.py's _apply_notification() for exactly which of these
        # the client itself currently consumes (now_gear and fault_code
        # only -- run_state/run_mode/run_param stay client-side-optimistic
        # by design, see that module's docstring point 1).
        payload = bytearray(10)
        payload[0] = 0  # mainboard_type -- unused by this sim
        payload[1] = 0  # mesh_sub_devices_num -- unused by this sim
        payload[2] = 1 if s["on"] else 0  # run_state -- NOT hardware-verified encoding, see heater_ble_config.py
        payload[3] = s["run_mode"] & 0xFF
        payload[4] = s["run_param"] & 0xFF
        payload[5] = s["now_gear"] & 0xFF
        payload[6] = 0  # run_step -- unused by this sim
        payload[7] = 0  # fault_display -- unused by this sim
        payload[8] = s["fault_code"] & 0xFF
        payload[9] = 0  # temp_unit -- 0 = Celsius, this sim always reports Celsius

        data = bytearray(protocol.encode_response(config.CMD_RUN, 0, bytes(payload)))

        if not force and self._last_sent == data:
            return
        self._last_sent = data
        self._send_frame(data)
