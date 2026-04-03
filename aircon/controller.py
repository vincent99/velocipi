"""
AC state machine and control logic.

Modes
-----
off   — all relays off, servo to recirc
fan   — fan at the stored speed, no compressor, servo follows circulation setting
auto  — manage compressor (hysteresis around setpoint) and fan speed automatically
max   — high fan, compressor on, always recirc
"""

import asyncio
import time
import config
import storage


class ACController:

    def __init__(self, relays, servo, led, sensors, pwm_monitor):
        self._relays  = relays
        self._servo   = servo
        self._led     = led
        self._sensors = sensors
        self._pwm     = pwm_monitor

        # Load persisted state.
        saved = storage.load()
        self.mode        = saved.get('mode',        config.DEFAULT_MODE)
        self.fan         = saved.get('fan',          config.DEFAULT_FAN)
        self.setpoint    = float(saved.get('setpoint',    config.DEFAULT_SETPOINT))
        self.circulation = saved.get('circulation',  config.DEFAULT_CIRCULATION)
        self.delta       = float(saved.get('delta',       config.DEFAULT_DELTA))

        # panel_temp is never persisted; 0 means "not available".
        self.panel_temp = 0.0

        # Internal runtime state.
        self._compressor_on    = False
        self._active_fan_speed = None   # what is actually running now
        self._error            = ''
        self._last_fan_change  = 0      # time.time() of last fan speed change

        self._apply()

    # ── Public properties ────────────────────────────────────────────────────

    @property
    def current_temp(self):
        """
        Effective current temperature:
          • panel_temp == 0: just the cabin probe
          • panel_temp != 0: average of panel and cabin
        """
        cabin = self._sensors.get('cabin')
        if cabin is None:
            return None
        if self.panel_temp:
            return (self.panel_temp + cabin) / 2.0
        return cabin

    @property
    def compressor_on(self):
        return self._compressor_on

    @property
    def error(self):
        return self._error

    # ── Setters (called by BLE and web server) ────────────────────────────────

    def set_mode(self, mode):
        if mode not in (config.MODE_OFF, config.MODE_FAN, config.MODE_AUTO, config.MODE_MAX):
            return False
        self.mode = mode
        self._apply()
        self._save()
        return True

    def set_fan(self, fan):
        if fan not in (config.FAN_LOW, config.FAN_MEDIUM, config.FAN_HIGH):
            return False
        self.fan = fan
        if self.mode == config.MODE_FAN:
            # Compressor is already off in fan mode, so it's safe to switch
            # speeds directly. Relay.set_fan de-energises all before asserting
            # the new speed, so the rotary switch is never double-driven.
            self._relays.set_fan(fan)
            self._active_fan_speed = fan
            self._update_led()
        self._save()
        return True

    def set_setpoint(self, temp):
        try:
            self.setpoint = float(temp)
            self._save()
            return True
        except (ValueError, TypeError):
            return False

    def set_circulation(self, circ):
        if circ not in (config.CIRC_RECIRC, config.CIRC_FRESH):
            return False
        self.circulation = circ
        if self.mode in (config.MODE_FAN, config.MODE_AUTO):
            self._servo.set(circ)
        self._save()
        return True

    def set_panel_temp(self, temp):
        try:
            self.panel_temp = float(temp)
            return True
        except (ValueError, TypeError):
            return False

    def set_delta(self, delta):
        try:
            v = float(delta)
            if v < 0:
                return False
            self.delta = v
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
            'delta':        self.delta,
            'error':        self._error,
            'pwm_freq':     self._pwm.frequency,
            'pwm_duty':     self._pwm.duty_cycle,
        }

    # ── Async control loop ────────────────────────────────────────────────────

    async def run(self):
        while True:
            if self.mode == config.MODE_AUTO:
                self._auto_control()
            await asyncio.sleep(config.AUTO_LOOP_INTERVAL)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _save(self):
        try:
            storage.save(self)
        except Exception as e:
            self._error = 'Save failed: ' + str(e)

    def _update_led(self):
        self._led.update(
            self._compressor_on,
            self._active_fan_speed is not None,
            bool(self._error),
        )

    def _apply(self):
        """Drive relays and servo to match the current mode."""
        mode = self.mode

        if mode == config.MODE_OFF:
            self._relays.all_off()
            self._servo.set(config.CIRC_RECIRC)
            self._compressor_on    = False
            self._active_fan_speed = None

        elif mode == config.MODE_FAN:
            # Compressor off first, then switch fan speed.
            self._relays.set_compressor(False)
            self._compressor_on = False
            self._relays.set_fan(self.fan)
            self._servo.set(self.circulation)
            self._active_fan_speed = self.fan

        elif mode == config.MODE_AUTO:
            # Fan and compressor are managed by _auto_control().
            # On entry ensure compressor is off before touching the fan.
            self._relays.set_compressor(False)
            self._compressor_on = False
            self._relays.set_fan(self._active_fan_speed or config.FAN_LOW)
            self._servo.set(self.circulation)
            if self._active_fan_speed is None:
                self._active_fan_speed = config.FAN_LOW

        elif mode == config.MODE_MAX:
            # Fan must come up before compressor.
            self._relays.set_fan(config.FAN_HIGH)
            self._active_fan_speed = config.FAN_HIGH
            self._relays.set_compressor(True)
            self._servo.set(config.CIRC_RECIRC)
            self._compressor_on = True

        self._update_led()

    def _auto_control(self):
        """Run one iteration of the auto-mode control loop."""
        current = self.current_temp
        if current is None:
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
        else:
            if current < self.setpoint - self.delta:
                # Stop compressor first; fan adjustment follows below.
                self._compressor_on = False
                self._relays.set_compressor(False)

        # ── Fan speed: 3-step selection with rate limiting ────────────────────
        now = time.time()
        if now - self._last_fan_change >= config.FAN_CHANGE_INTERVAL:
            diff = abs(current - self.setpoint)

            # Also consider the front-to-back cabin temperature gradient.
            panel = self.panel_temp
            cabin = self._sensors.get('cabin') or current
            gradient = abs(panel - cabin) if panel else 0.0

            max_diff = max(diff, gradient)

            if max_diff >= config.AUTO_FAN_HIGH_THRESH:
                target_fan = config.FAN_HIGH
            elif max_diff >= config.AUTO_FAN_MED_THRESH:
                target_fan = config.FAN_MEDIUM
            else:
                target_fan = config.FAN_LOW

            if target_fan != self._active_fan_speed:
                self._active_fan_speed = target_fan
                self._relays.set_fan(target_fan)
                self._last_fan_change = now

        # ── Servo follows circulation preference ──────────────────────────────
        self._servo.set(self.circulation)

        self._update_led()
