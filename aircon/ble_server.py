"""
BLE GATT server using aioble.

Install aioble if not already present:
    import mip
    mip.install('aioble')

Service UUID: aaaaaaaa-1111-cccc-00dd-000000000000

Characteristics (all UTF-8 strings):
  0001  mode      rw  "off" | "fan" | "auto" | "max"
  0002  fan       rw  "low" | "medium" | "high"
  0003  setpoint  rw  float as string, e.g. "72.50"
  0004  circ      rw  "recirc" | "fresh"
  0005  panel     rw  float as string (panel sensor temp, °F)
  0006  delta     rw  float as string (hysteresis, °F)
  0007  status    rn  JSON: temps, compressor state, error

Writes are validated server-side; invalid values are silently ignored.
"""

import asyncio
import json
import bluetooth
import aioble
import config
import log


def _enc_str(s: str) -> bytes:
    return s.encode()

def _enc_f(v) -> bytes:
    return '{:.2f}'.format(float(v) if v is not None else 0.0).encode()

def _dec_str(b: bytes) -> str:
    return b.decode().strip('\x00').lower()

def _dec_f(b: bytes) -> float:
    return float(b.decode().strip('\x00'))


class BLEServer:

    def __init__(self, controller):
        self._ctrl = controller

        svc = aioble.Service(bluetooth.UUID(config.BLE_SVC_UUID))

        def _rw(uuid):
            return aioble.Characteristic(
                svc, bluetooth.UUID(uuid),
                read=True, write=True, write_no_response=True, notify=True, capture=True,
            )
        def _rn(uuid):
            return aioble.Characteristic(
                svc, bluetooth.UUID(uuid),
                read=True, notify=True,
            )

        self._c_mode     = _rw(config.BLE_UUID_MODE)
        self._c_fan      = _rw(config.BLE_UUID_FAN)
        self._c_setpoint = _rw(config.BLE_UUID_SETPOINT)
        self._c_circ     = _rw(config.BLE_UUID_CIRC)
        self._c_panel    = _rw(config.BLE_UUID_PANEL)
        self._c_delta    = _rw(config.BLE_UUID_DELTA)
        self._c_status   = _rn(config.BLE_UUID_STATUS)

        aioble.register_services(svc)
        self._connections: set = set()
        self._state_event = asyncio.Event()

    def notify_state_changed(self):
        """Called by the controller after any state change."""
        self._state_event.set()

    # ── Write the current controller state into all GATT values and notify ──────
    # send_update=True makes aioble call gatts_notify for every active connection
    # that has subscribed, without needing to track connections manually.

    def _push_state(self):
        s = self._ctrl.get_state()
        self._c_mode.write(_enc_str(s['mode']),        send_update=True)
        self._c_fan.write(_enc_str(s['fan']),           send_update=True)
        self._c_setpoint.write(_enc_f(s['setpoint']),   send_update=True)
        self._c_circ.write(_enc_str(s['circulation']),  send_update=True)
        self._c_panel.write(_enc_f(s['panel_temp']),    send_update=True)
        self._c_delta.write(_enc_f(s['delta']),         send_update=True)

        def _f(v):
            return round(float(v), 2) if v is not None else None

        status = {
            'curr':    _f(s['current_temp']),
            'comp':    s['compressor'],
            'cabin':   _f(s['cabin_temp']),
            'blower':  _f(s['blower_temp']),
            'exhaust': _f(s['exhaust_temp']),
            'baggage': _f(s['baggage_temp']),
            'tail':    _f(s['tail_temp']),
            'err':     s['error'],
        }
        self._c_status.write(json.dumps(status).encode(), send_update=True)

    # ── Per-connection task: push state on connect, then on changes/heartbeat ──

    async def _connection_task(self, connection):
        self._connections.add(connection)
        log.log('ble', f'connected: {connection.device}')
        try:
            # Send current state immediately on connect.
            try:
                self._push_state()
            except Exception as e:
                log.log('ble', f'push_state error: {e}')
            while connection.is_connected():
                # Wake immediately on a state change, or after the heartbeat interval.
                try:
                    await asyncio.wait_for(
                        self._state_event.wait(),
                        config.BLE_NOTIFY_INTERVAL,
                    )
                except asyncio.TimeoutError:
                    pass
                self._state_event.clear()
                try:
                    self._push_state()
                except Exception as e:
                    log.log('ble', f'push_state error: {e}')
        finally:
            self._connections.discard(connection)
            log.log('ble', 'disconnected')

    # ── Main BLE task ─────────────────────────────────────────────────────────

    async def run(self):
        ctrl = self._ctrl

        # Pre-populate readable values before the first connection.
        try:
            self._push_state()
        except Exception:
            pass

        # Spawn one independent watch task per writable characteristic.
        # Using individual create_task calls (rather than gather inside a task)
        # is more reliable in MicroPython's uasyncio.
        async def watch(name, char, handler):
            while True:
                try:
                    _, data = await char.written()
                    log.log('ble', f'{name} write: {data}')
                    await handler(data)
                except Exception as e:
                    log.log('ble', f'{name} write error: {e}')
                    await asyncio.sleep_ms(100)

        asyncio.create_task(watch('mode',     self._c_mode,     lambda d: ctrl.set_mode(_dec_str(d),        'ble')))
        asyncio.create_task(watch('fan',      self._c_fan,      lambda d: ctrl.set_fan(_dec_str(d),         'ble')))
        asyncio.create_task(watch('setpoint', self._c_setpoint, lambda d: ctrl.set_setpoint(_dec_f(d),      'ble')))
        asyncio.create_task(watch('circ',     self._c_circ,     lambda d: ctrl.set_circulation(_dec_str(d), 'ble')))
        asyncio.create_task(watch('panel',    self._c_panel,    lambda d: ctrl.set_panel_temp(_dec_f(d),    'ble')))
        asyncio.create_task(watch('delta',    self._c_delta,    lambda d: ctrl.set_delta(_dec_f(d),         'ble')))

        while True:
            try:
                connection = await aioble.advertise(
                    500_000,  # advertising interval µs
                    name=config.BLE_DEVICE_NAME,
                    services=[bluetooth.UUID(config.BLE_SVC_UUID)],
                )
                asyncio.create_task(self._connection_task(connection))
            except Exception as e:
                log.log('ble', f'advertise error: {e}')
                await asyncio.sleep_ms(500)
