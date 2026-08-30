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
            password, cmd, param1, param2 = protocol.decode_frame(raw)
        except protocol.FrameError as e:
            logger.warning("bad frame, ignoring: %s", e)
            return
        # Every frame carries a password in this protocol version -- see
        # protocol.py's decode_frame() docstring -- checked here, per
        # frame, rather than via a dedicated handshake command this
        # protocol version doesn't have. NOT hardware-verified what a real
        # unit actually does on a wrong password (silently ignore, like
        # this does? some explicit reject we just can't decode yet? see
        # ../hvac-knob/heater_ble.py's module docstring, point 3) -- this
        # is a documented guess, not a confirmed behavior.
        if self.ctrl.password is not None and password != self.ctrl.password:
            logger.info(
                "wrong password (got %04d, want %04d) -- ignoring, no response",
                password,
                self.ctrl.password,
            )
            return
        try:
            self._dispatch(cmd, param1, param2)
        except Exception:
            logger.exception("dispatch failed for cmd=%d param1=%d param2=%d", cmd, param1, param2)

    def _dispatch(self, cmd, param1, param2):
        if cmd == config.CMD_READ:
            logger.info("-> read/poll")
        elif cmd == config.CMD_SET_MODE:
            logger.info("-> set mode=%d", param1)
            self.ctrl.set_mode(param1)
        elif cmd == config.CMD_ON_OFF:
            if param1:
                logger.info("-> power on")
                self.ctrl.power_on()
            else:
                logger.info("-> power off")
                self.ctrl.power_off()
        elif cmd == config.CMD_SET_GEAR_OR_TEMP:
            logger.info("-> set gear/temp=%d", param1)
            self.ctrl.set_gear_or_temp(param1)
        else:
            logger.info("unhandled cmd=%d param1=%d param2=%d (not implemented in this sim)", cmd, param1, param2)
            return
        # Every recognized command gets an immediate status push in
        # response -- confirmed in the real capture for all four of these
        # (CMD_READ included: it's a poll, and every real one observed was
        # followed shortly by a notification).
        self.push(force=True, cmd_echo=cmd)

    # ── push state → characteristic, notify only what changed ─────────────

    def push(self, force=False, cmd_echo=config.CMD_READ):
        """cmd_echo defaults to CMD_READ for the background loop's
        unprompted periodic pushes (see controller.py's run()), which have
        no real triggering command to echo -- NOT hardware-verified what a
        real unit's own unprompted pushes actually echo in that byte, if
        anything in particular; see protocol.py's encode_status() for
        which fields this sim actually encodes vs. leaves zeroed.
        """
        s = self.ctrl.get_state()
        data = protocol.encode_status(cmd_echo, s["on"], s["now_gear"], fault_code=s["fault_code"])

        if not force and self._last_sent == data:
            return
        self._last_sent = data
        self._send_frame(data)

    def _send_frame(self, frame):
        char = self.server.get_characteristic(config.BLE_CHAR_UUID)
        if char is None:
            return
        char.value = bytearray(frame)
        self.server.update_value(config.BLE_SVC_UUID, config.BLE_CHAR_UUID)
