"""
BLE GATT server using aioble.

Install aioble if not already present:
    import mip
    mip.install('aioble')

Service UUID: aaaaaaaa-1111-cccc-00dd-000000000000

Characteristics (all UTF-8 strings):
  0001  mode      rw  "off" | "fan" | "auto" | "cool"
  0002  fan       rw  "low" | "medium" | "high"
  0003  setpoint  rw  float as string, e.g. "72.50"
  0004  circ      rw  "recirc" | "fresh"
  0005  panel     rw  float as string (panel sensor temp, °F)
  0006  settings  rw  JSON: delta, fan_high_thresh, fan_med_thresh, fan_change_interval, auto_loop_interval, temp_read_interval
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

# Compile-time defaults for the 0006 settings characteristic.
_SETTINGS_DEFAULTS = {
    'delta':               config.DEFAULT_DELTA,
    'fan_high_thresh':     config.DEFAULT_AUTO_FAN_HIGH_THRESH,
    'fan_med_thresh':      config.DEFAULT_AUTO_FAN_MED_THRESH,
    'fan_change_interval': config.DEFAULT_FAN_CHANGE_INTERVAL,
    'auto_loop_interval':  config.DEFAULT_AUTO_LOOP_INTERVAL,
    'temp_read_interval':  config.DEFAULT_TEMP_READ_INTERVAL,
}

def _unwrap_settings(d):
    """Accept flat {key: value} or wrapped {key: {value: v, default: d}} — return flat."""
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            vv = v.get('value')
            if vv is not None:
                out[k] = vv
        else:
            out[k] = v
    return out


class BLEServer:

    def __init__(self, controller, led=None):
        self._ctrl   = controller
        self._led    = led  # RGBLed instance for BLE connection count updates
        self._notify = controller.ble_notify
        log.log('ble', f'notifications {"enabled" if self._notify else "disabled"}')

        svc = aioble.Service(bluetooth.UUID(config.BLE_SVC_UUID))

        # Characteristic Presentation Format descriptor (0x2904) — UTF-8 string.
        # Format=0x19, Exponent=0x00, Unit=0x2700 (unitless LE), Namespace=0x01, Description=0x0000
        _CPF_UTF8 = b'\x19\x00\x00\x27\x01\x00\x00'

        def _rw(uuid, label):
            c = aioble.Characteristic(
                svc, bluetooth.UUID(uuid),
                read=True, write=True, write_no_response=True,
                notify=self._notify, capture=True,
            )
            aioble.Descriptor(c, bluetooth.UUID(0x2904), read=True, initial=_CPF_UTF8)
            aioble.Descriptor(c, bluetooth.UUID(0x2901), read=True, initial=label.encode())
            return c

        def _rn(uuid, label):
            c = aioble.Characteristic(
                svc, bluetooth.UUID(uuid),
                read=True, notify=self._notify,
            )
            aioble.Descriptor(c, bluetooth.UUID(0x2904), read=True, initial=_CPF_UTF8)
            aioble.Descriptor(c, bluetooth.UUID(0x2901), read=True, initial=label.encode())
            return c

        self._c_mode     = _rw(config.BLE_UUID_MODE,     'Mode (off/fan/cool/auto)')
        self._c_fan      = _rw(config.BLE_UUID_FAN,      'Fan Speed (low/medium/high)')
        self._c_setpoint = _rw(config.BLE_UUID_SETPOINT, 'Setpoint (°F)')
        self._c_circ     = _rw(config.BLE_UUID_CIRC,     'Circulation (recirc/fresh')
        self._c_panel    = _rw(config.BLE_UUID_PANEL,    'Panel Temp (°F)')
        self._c_settings = _rw(config.BLE_UUID_SETTINGS, 'Settings (JSON)')
        self._c_status   = _rn(config.BLE_UUID_STATUS,   'Status (JSON)')

        self._svc = svc  # registered lazily in run()
        self._connections: set = set()
        self._state_event = asyncio.Event()
        self._last_status: bytes = b''   # dedup for status characteristic
        self._last_char: dict = {}       # dedup for writable characteristics

    def notify_state_changed(self):
        """Called by the controller after any state change."""
        self._state_event.set()

    # ── Push helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _fmt(v):
        return round(float(v), 2) if v is not None else None

    def _push_state(self, s=None):
        """Update all characteristic values; notify only on changes."""
        if s is None:
            s = self._ctrl.get_state()

        def _write(name, char, value: bytes):
            if self._last_char.get(name) != value:
                self._last_char[name] = value
                try:
                    char.write(value, send_update=self._notify)
                except OSError:
                    char.write(value)  # no subscribers — write without notify

        _write('mode',     self._c_mode,     _enc_str(s['mode']))
        _write('fan',      self._c_fan,      _enc_str(s['fan']))
        _write('setpoint', self._c_setpoint, _enc_f(s['setpoint']))
        _write('circ',     self._c_circ,     _enc_str(s['circulation']))
        _write('panel',    self._c_panel,    _enc_f(s['panel_temp']))
        _write('settings', self._c_settings, json.dumps({
            k: {'value': s[k], 'default': _SETTINGS_DEFAULTS[k]}
            for k in _SETTINGS_DEFAULTS if k in s
        }).encode())
        self._push_status(s)

    def _push_status(self, s=None):
        """Notify only the status characteristic (temps + compressor + error)."""
        if s is None:
            s = self._ctrl.get_state()
        status = {
            'curr':    self._fmt(s['current_temp']),
            'comp':    s['compressor'],
            'cabin':   self._fmt(s['cabin_temp']),
            'blower':  self._fmt(s['blower_temp']),
            'exhaust': self._fmt(s['exhaust_temp']),
            'baggage': self._fmt(s['baggage_temp']),
            'tail':    self._fmt(s['tail_temp']),
            'err':     s['error'],
        }
        if not self._notify:
            return
        payload = json.dumps(status).encode()
        if payload == self._last_status:
            return
        self._last_status = payload
        import time
        t0 = time.ticks_ms()
        try:
            self._c_status.write(payload, send_update=True)
        except OSError:
            self._c_status.write(payload)
        t1 = time.ticks_ms()
        log.log('ble', f'notify status: curr={status["curr"]}  comp={status["comp"]}  err={status["err"]!r}  write_ms={time.ticks_diff(t1, t0)}')

    # ── Per-connection task: push state on connect, then on changes/heartbeat ──

    async def _connection_task(self, connection):
        self._connections.add(connection)
        self._last_status = b''  # force full push on connect
        self._last_char = {}
        if self._led:
            self._led.set_ble_count(len(self._connections))
        log.log('ble', f'connected: {connection.device}')
        try:
            # Full state push on connect so the client has all current values.
            try:
                self._push_state()
            except Exception as e:
                log.log('ble', f'push_state error: {e}')
            while connection.is_connected():
                # Wait up to BLE_NOTIFY_INTERVAL for a state-change event.
                # If events fire faster than the interval (e.g. the auto loop
                # calling _update_led every few seconds) we drain them all and
                # push once, then enforce a hard sleep so we never notify faster
                # than BLE_NOTIFY_INTERVAL regardless of how often the event fires.
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
                # Hard rate limit: sleep the full interval before the next push.
                # This ensures notifications never come faster than BLE_NOTIFY_INTERVAL
                # even if notify_state_changed() is called in a tight loop.
                await asyncio.sleep(config.BLE_NOTIFY_INTERVAL)
        finally:
            self._connections.discard(connection)
            if self._led:
                self._led.set_ble_count(len(self._connections))
            log.log('ble', 'disconnected')

    # ── Main BLE task ─────────────────────────────────────────────────────────

    async def run(self):
        ctrl = self._ctrl

        await asyncio.sleep(0)  # yield so control loop keeps running before BLE init
        log.log('ble', 'registering services')
        aioble.register_services(self._svc)
        log.log('ble', 'services registered')

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
        asyncio.create_task(watch('panel',    self._c_panel,    lambda d: ctrl.set_panel_temp(_dec_f(d), 'ble')))
        asyncio.create_task(watch('settings', self._c_settings, lambda d: ctrl.set_settings(_unwrap_settings(json.loads(d.decode())), 'ble')))

        while True:
            try:
                log.log('ble', 'advertising')
                connection = await aioble.advertise(
                    500_000,  # advertising interval µs
                    name=config.BLE_DEVICE_NAME,
                    services=[bluetooth.UUID(config.BLE_SVC_UUID)],
                )
                log.log('ble', 'advertise returned')
                asyncio.create_task(self._connection_task(connection))
            except Exception as e:
                log.log('ble', f'advertise error: {e}')
                await asyncio.sleep_ms(500)
