"""
AC state machine and control logic.

Modes
-----
off   — all relays off, servo to recirc
fan   — fan at the stored speed, no compressor, servo follows circulation setting
auto  — manage compressor (hysteresis around setpoint) and fan speed automatically
cool  — compressor always on, servo follows circulation setting; fan speed is
        user-chosen (keeps current speed if already running, else defaults to high)
"""

import asyncio
import time
import config
import log
import storage


class ACController:

    def __init__(self, relays, led, sensors, pwm_monitor):
        self._relays  = relays
        self._led     = led
        self._sensors = sensors
        self._pwm     = pwm_monitor

        # Load persisted state.
        saved = storage.load()
        self.mode        = saved.get('mode',        config.DEFAULT_MODE)
        self.fan         = saved.get('fan',          config.DEFAULT_FAN)
        self.setpoint    = float(saved.get('setpoint',    config.DEFAULT_SETPOINT))
        self.circulation        = saved.get('circulation',        config.DEFAULT_CIRCULATION)
        self.delta              = float(saved.get('delta',              config.DEFAULT_DELTA))
        self.fan_high_thresh     = float(saved.get('fan_high_thresh',     config.DEFAULT_AUTO_FAN_HIGH_THRESH))
        self.fan_med_thresh      = float(saved.get('fan_med_thresh',      config.DEFAULT_AUTO_FAN_MED_THRESH))
        self.fan_change_interval = float(saved.get('fan_change_interval', config.DEFAULT_FAN_CHANGE_INTERVAL))
        self.auto_loop_interval  = float(saved.get('auto_loop_interval',  config.DEFAULT_AUTO_LOOP_INTERVAL))
        self.temp_read_interval  = float(saved.get('temp_read_interval',  config.DEFAULT_TEMP_READ_INTERVAL))
        self.ble_notify          = bool(saved.get('ble_notify',           config.DEFAULT_BLE_NOTIFY))

        # panel_temp is never persisted; 0 means "not available".
        self.panel_temp = 0.0

        # Internal runtime state.
        self._compressor_on    = False
        self._active_fan_speed = None   # what is actually running now
        self._error            = ''
        self._last_fan_change  = 0      # time.time() of last fan speed change
        self.on_state_change   = None   # optional callback, set by BLEServer

        self._sensors.temp_read_interval = self.temp_read_interval

        log.log('system', f'startup: mode={self.mode}, fan={self.fan}, setpoint={self.setpoint}°F, circ={self.circulation}, delta=±{self.delta}°F')
        asyncio.create_task(self._apply())

    # ── Public properties ────────────────────────────────────────────────────

    @property
    def current_temp(self):
        """
        Effective current temperature:
          • both available: average of panel and cabin
          • only one available: whichever is non-zero/non-None
          • neither available: None
        """
        cabin = self._sensors.get('cabin') or None
        panel = self.panel_temp or None  # treat 0 as unavailable
        if cabin and panel:
            return (panel + cabin) / 2.0
        return cabin or panel

    @property
    def compressor_on(self):
        return self._compressor_on

    @property
    def error(self):
        return self._error

    # ── Setters (called by BLE and web server) ────────────────────────────────

    async def set_mode(self, mode, source='system'):
        if mode not in (config.MODE_OFF, config.MODE_FAN, config.MODE_AUTO, config.MODE_COOL):
            return False
        self._error = ''
        self.mode = mode
        log.log(source, f'mode → {mode}')
        await self._apply()
        self._save()
        return True

    async def set_fan(self, fan, source='system'):
        if fan not in (config.FAN_LOW, config.FAN_MEDIUM, config.FAN_HIGH):
            return False
        self._error = ''
        self.fan = fan
        log.log(source, f'fan setting → {fan}')
        if self.mode in (config.MODE_FAN, config.MODE_COOL):
            # In fan/cool mode it's safe to switch fan speeds directly.
            # Relay.set_fan de-energises all before asserting the new speed.
            await self._relays.set_fan(fan)
            self._active_fan_speed = fan
            self._update_led()
        self._save()
        return True

    async def set_setpoint(self, temp, source='system'):
        try:
            self.setpoint = float(temp)
            log.log(source, f'setpoint → {self.setpoint:.1f}°F')
            self._save()
            return True
        except (ValueError, TypeError):
            return False

    async def set_circulation(self, circ, source='system'):
        if circ not in (config.CIRC_RECIRC, config.CIRC_FRESH):
            return False
        self.circulation = circ
        log.log(source, f'circulation → {circ}')
        if self.mode in (config.MODE_FAN, config.MODE_AUTO, config.MODE_COOL):
            self._relays.set_circulation(circ)
        self._save()
        return True

    async def set_panel_temp(self, temp, source='system'):
        try:
            self.panel_temp = float(temp)
            log.log(source, f'panel_temp → {self.panel_temp:.1f}°F')
            return True
        except (ValueError, TypeError):
            return False

    async def set_delta(self, delta, source='system'):
        try:
            v = float(delta)
            if v < 0:
                return False
            self.delta = v
            log.log(source, f'delta → ±{self.delta:.1f}°F')
            self._save()
            return True
        except (ValueError, TypeError):
            return False

    async def set_ble_notify(self, value, source='system'):
        self.ble_notify = value not in (False, 'false', '0', 0)
        log.log(source, f'ble_notify → {self.ble_notify}  (takes effect on restart)')
        self._save()
        return True

    async def set_ble_name(self, name, source='system'):
        name = name.strip()
        if not name:
            return False
        try:
            with open('/name.txt', 'w') as f:
                f.write(name)
            config.BLE_DEVICE_NAME = name
            log.log(source, f'ble_name → {name}')
            return True
        except Exception as e:
            self._error = 'BLE name save failed: ' + str(e)
            return False

    async def set_settings(self, settings, source='system'):
        """Update tunable settings from a dict. Unknown keys are ignored."""
        try:
            changed = []
            if 'delta' in settings:
                v = float(settings['delta'])
                if v >= 0:
                    self.delta = v
                    changed.append(f'delta={v}')
            if 'fan_high_thresh' in settings:
                self.fan_high_thresh = float(settings['fan_high_thresh'])
                changed.append(f'fan_high_thresh={self.fan_high_thresh}')
            if 'fan_med_thresh' in settings:
                self.fan_med_thresh = float(settings['fan_med_thresh'])
                changed.append(f'fan_med_thresh={self.fan_med_thresh}')
            if 'fan_change_interval' in settings:
                self.fan_change_interval = float(settings['fan_change_interval'])
                changed.append(f'fan_change_interval={self.fan_change_interval}')
            if 'auto_loop_interval' in settings:
                self.auto_loop_interval = float(settings['auto_loop_interval'])
                changed.append(f'auto_loop_interval={self.auto_loop_interval}')
            if 'temp_read_interval' in settings:
                self.temp_read_interval = float(settings['temp_read_interval'])
                self._sensors.temp_read_interval = self.temp_read_interval
                changed.append(f'temp_read_interval={self.temp_read_interval}')
            if changed:
                log.log(source, 'settings: ' + '  '.join(changed))
            self._save()
            return True
        except (ValueError, TypeError):
            return False

    # ── State snapshot (for web / BLE) ───────────────────────────────────────

    def get_state(self):
        temps = self._sensors.get_all()
        return {
            'mode':         self.mode,
            'fan':          self.fan,
            'setpoint':     self.setpoint,
            'circulation':  self.circulation,
            'panel_temp':   self.panel_temp,
            'current_temp': self.current_temp,
            'compressor':   'on' if self._compressor_on else 'off',
            'cabin_temp':   temps.get('cabin'),
            'blower_temp':  temps.get('blower'),
            'exhaust_temp': temps.get('exhaust'),
            'baggage_temp': temps.get('baggage'),
            'tail_temp':    temps.get('tail'),
            'delta':               self.delta,
            'fan_high_thresh':     self.fan_high_thresh,
            'fan_med_thresh':      self.fan_med_thresh,
            'fan_change_interval': self.fan_change_interval,
            'auto_loop_interval':  self.auto_loop_interval,
            'temp_read_interval':  self.temp_read_interval,
            'error':               self._error,
            'pwm_freq':            self._pwm.frequency,
            'pwm_duty':            self._pwm.duty_cycle,
            'ble_device_name':     config.BLE_DEVICE_NAME,
            'ble_notify':          self.ble_notify,
        }

    # ── Async control loop ────────────────────────────────────────────────────

    async def run(self):
        while True:
            if self.mode == config.MODE_AUTO:
                await self._auto_control()
            await asyncio.sleep(self.auto_loop_interval)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _save(self):
        try:
            storage.save(self)
        except Exception as e:
            self._error = 'Save failed: ' + str(e)

    def _update_led(self):
        self._led.update(
            self._active_fan_speed,
            self._compressor_on,
            bool(self._error),
        )
        if self.on_state_change:
            self.on_state_change()

    async def _apply(self):
        """Drive relays and servo to match the current mode."""
        mode = self.mode

        if mode == config.MODE_OFF:
            self._relays.all_off()
            self._relays.set_circulation(config.CIRC_RECIRC)
            self._compressor_on    = False
            self._active_fan_speed = None

        elif mode == config.MODE_FAN:
            # Compressor off first, then switch fan speed.
            self._relays.set_compressor(False)
            self._compressor_on = False
            await self._relays.set_fan(self.fan)
            self._relays.set_circulation(self.circulation)
            self._active_fan_speed = self.fan

        elif mode == config.MODE_AUTO:
            # Fan and compressor are managed by _auto_control().
            # On entry ensure compressor is off before touching the fan.
            self._relays.set_compressor(False)
            self._compressor_on = False
            await self._relays.set_fan(self._active_fan_speed or config.FAN_LOW)
            self._relays.set_circulation(self.circulation)
            if self._active_fan_speed is None:
                self._active_fan_speed = config.FAN_LOW

        elif mode == config.MODE_COOL:
            # Keep current fan speed if already running, else default to high.
            target_fan = self._active_fan_speed if self._active_fan_speed else config.FAN_HIGH
            await self._relays.set_fan(target_fan)
            self._active_fan_speed = target_fan
            self._relays.set_compressor(True)
            self._relays.set_circulation(self.circulation)
            self._compressor_on = True

        self._update_led()

    async def _auto_control(self):
        """Run one iteration of the auto-mode control loop."""
        current = self.current_temp
        if current is None:
            if not self._error:
                log.log('auto', 'error: no temperature reading')
            self._error = 'No temperature reading'
            self._update_led()
            return
        self._error = ''

        # ── Compressor: on/off with hysteresis ────────────────────────────────
        # Fan is always running in auto mode before we touch the compressor,
        # but guard the ordering explicitly: fan on before compressor on,
        # compressor off before fan changes.
        if not self._compressor_on:
            if current > self.setpoint + self.delta:
                # Fan is already running; safe to start compressor.
                self._compressor_on = True
                self._relays.set_compressor(True)
                log.log('auto', f'compressor ON  (temp={current:.1f}°F, setpoint={self.setpoint:.1f}°F)')
        else:
            if current < self.setpoint - self.delta:
                # Stop compressor first; fan adjustment follows below.
                self._compressor_on = False
                self._relays.set_compressor(False)
                log.log('auto', f'compressor OFF (temp={current:.1f}°F, setpoint={self.setpoint:.1f}°F)')

        # ── Fan speed: 3-step selection with rate limiting ────────────────────
        now = time.time()
        diff = abs(current - self.setpoint)

        # Also consider the front-to-back cabin temperature gradient.
        panel = self.panel_temp
        cabin = self._sensors.get('cabin') or current
        gradient = abs(panel - cabin) if panel else 0.0

        max_diff = max(diff, gradient)

        if max_diff >= self.fan_high_thresh:
            target_fan = config.FAN_HIGH
        elif max_diff >= self.fan_med_thresh:
            target_fan = config.FAN_MEDIUM
        else:
            target_fan = config.FAN_LOW

        # Rate-limit only speed reductions to prevent hunting.
        # Speed increases are applied immediately.
        _order = {config.FAN_LOW: 0, config.FAN_MEDIUM: 1, config.FAN_HIGH: 2}
        increasing = _order.get(target_fan, 0) > _order.get(self._active_fan_speed, 0)
        rate_ok = now - self._last_fan_change >= self.fan_change_interval

        if target_fan != self._active_fan_speed and (increasing or rate_ok):
            log.log('auto', f'fan {self._active_fan_speed} → {target_fan} (Δ={max_diff:.1f}°F)')
            self._active_fan_speed = target_fan
            await self._relays.set_fan(target_fan)
            self._last_fan_change = now

        # ── Servo follows circulation preference ──────────────────────────────
        self._relays.set_circulation(self.circulation)

        self._update_led()
