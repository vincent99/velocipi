"""
BLE GATT server using aioble.

Install aioble if not already present:
    import mip
    mip.install('aioble')

Service UUID:  a1b2c3d4-0000-0000-abcd-ef1234567890
One characteristic per attribute; string values are UTF-8, float values are
little-endian IEEE 754 float32 (4 bytes).

Writable characteristics (mode, fan, setpoint, circulation, panel_temp, delta)
accept writes from any connected central. Writes are validated and applied to
the controller; invalid values are silently ignored.
"""

import asyncio
import struct
import bluetooth
import aioble
import config


def _enc_str(s: str) -> bytes:
    return s.encode()

def _enc_f(v) -> bytes:
    return struct.pack('<f', float(v) if v is not None else 0.0)

def _dec_str(b: bytes) -> str:
    return b.decode().strip('\x00')

def _dec_f(b: bytes) -> float:
    return struct.unpack('<f', b)[0]


class BLEServer:

    def __init__(self, controller):
        self._ctrl = controller

        svc = aioble.Service(bluetooth.UUID(config.BLE_SVC_UUID))

        def _rw(uuid):
            return aioble.Characteristic(
                svc, bluetooth.UUID(uuid),
                read=True, write=True, notify=True, capture=True,
            )
        def _rn(uuid):
            return aioble.Characteristic(
                svc, bluetooth.UUID(uuid),
                read=True, notify=True,
            )

        self._c_mode      = _rw(config.BLE_UUID_MODE)
        self._c_fan       = _rw(config.BLE_UUID_FAN)
        self._c_setpoint  = _rw(config.BLE_UUID_SETPOINT)
        self._c_circ      = _rw(config.BLE_UUID_CIRC)
        self._c_panel     = _rw(config.BLE_UUID_PANEL)
        self._c_curr_temp = _rn(config.BLE_UUID_CURR_TEMP)
        self._c_comp_st   = _rn(config.BLE_UUID_COMP_ST)
        self._c_rear      = _rn(config.BLE_UUID_REAR_TEMP)
        self._c_blower    = _rn(config.BLE_UUID_BLOW_TEMP)
        self._c_exhaust   = _rn(config.BLE_UUID_EXHU_TEMP)
        self._c_baggage   = _rn(config.BLE_UUID_BAGG_TEMP)
        self._c_comp_temp = _rn(config.BLE_UUID_COMP_TEMP)
        self._c_delta     = _rw(config.BLE_UUID_DELTA)
        self._c_error     = _rn(config.BLE_UUID_ERROR)

        aioble.register_services(svc)
        self._connections: set = set()

    # ── Write the current controller state into all GATT values ──────────────

    def _push_state(self):
        s = self._ctrl.get_state()
        self._c_mode.write(_enc_str(s['mode']))
        self._c_fan.write(_enc_str(s['fan']))
        self._c_setpoint.write(_enc_f(s['setpoint']))
        self._c_circ.write(_enc_str(s['circulation']))
        self._c_panel.write(_enc_f(s['panel_temp']))
        self._c_curr_temp.write(_enc_f(s['current_temp']))
        self._c_comp_st.write(_enc_str(s['compressor']))
        self._c_rear.write(_enc_f(s['cabin_temp']))
        self._c_blower.write(_enc_f(s['blower_temp']))
        self._c_exhaust.write(_enc_f(s['exhaust_temp']))
        self._c_baggage.write(_enc_f(s['baggage_temp']))
        self._c_comp_temp.write(_enc_f(s['tail_temp']))
        self._c_delta.write(_enc_f(s['delta']))
        self._c_error.write(_enc_str(s['error']))

    # ── Notify a single connection on all read/notify characteristics ─────────

    async def _notify_all(self, connection):
        read_notify = (
            self._c_mode, self._c_fan, self._c_setpoint, self._c_circ,
            self._c_panel, self._c_curr_temp, self._c_comp_st,
            self._c_rear, self._c_blower, self._c_exhaust,
            self._c_baggage, self._c_comp_temp, self._c_delta, self._c_error,
        )
        for char in read_notify:
            try:
                await char.notify(connection)
            except Exception:
                return  # connection dropped

    # ── Per-connection task: push state updates while connected ───────────────

    async def _connection_task(self, connection):
        self._connections.add(connection)
        try:
            while connection.is_connected():
                self._push_state()
                await self._notify_all(connection)
                await asyncio.sleep(config.BLE_NOTIFY_INTERVAL)
        finally:
            self._connections.discard(connection)

    # ── Write-handler tasks (one per writable characteristic) ─────────────────

    async def _watch_writes(self):
        """Await writes on all writable characteristics concurrently."""
        ctrl = self._ctrl

        async def watch(char, handler):
            while True:
                try:
                    _, data = await char.written()
                    handler(data)
                except Exception:
                    await asyncio.sleep_ms(100)

        await asyncio.gather(
            watch(self._c_mode,     lambda d: ctrl.set_mode(_dec_str(d))),
            watch(self._c_fan,      lambda d: ctrl.set_fan(_dec_str(d))),
            watch(self._c_setpoint, lambda d: ctrl.set_setpoint(_dec_f(d))),
            watch(self._c_circ,     lambda d: ctrl.set_circulation(_dec_str(d))),
            watch(self._c_panel,    lambda d: ctrl.set_panel_temp(_dec_f(d))),
            watch(self._c_delta,    lambda d: ctrl.set_delta(_dec_f(d))),
        )

    # ── Main BLE task ─────────────────────────────────────────────────────────

    async def run(self):
        asyncio.create_task(self._watch_writes())

        while True:
            try:
                connection = await aioble.advertise(
                    500_000,  # advertising interval µs
                    name=config.BLE_DEVICE_NAME,
                    services=[bluetooth.UUID(config.BLE_SVC_UUID)],
                )
                asyncio.create_task(self._connection_task(connection))
            except Exception:
                await asyncio.sleep_ms(500)
