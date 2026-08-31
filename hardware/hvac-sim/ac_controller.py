"""Simulated AC state machine + thermal model -- a desktop-Python analog of
../aircon/controller.py's ACController, minus actual relay/servo/sensor
hardware. Mode semantics (off/fan/auto/cool) and the auto-mode
compressor-hysteresis + 3-step fan speed logic are ported directly from that
file so this behaves the same way the real unit would for anything driven
over BLE.

Thermal model: each of the 6 probes exponentially approaches a target
temperature that depends only on whether the compressor is on (cooling
floor) or off (ambient ceiling) -- e.g. "temp += (target - temp) * rate"
each tick. That's a asymptotic approach, so probes get cooler while the
compressor runs and warmer while it doesn't, capped at the ceiling/floor by
construction ("warmer up to a point"), with each probe's own rate constant
giving blower/exhaust (right at the vents) bigger, faster swings than
baggage/tail (in the back, thermally lagged) -- like a real cabin.

"compressor" (the probe on/near the compressor body itself, not to be
confused with `compressor_on`/the "comp" wire field, which is its run
state) uses this exact same simplified model too, purely for consistency
with the other five -- a real compressor's own casing plausibly runs
*hotter* while active (compressing refrigerant is exothermic), the
opposite direction from this model's cooling-floor/ambient-ceiling target,
but nothing in this codebase documents what that probe is actually
expected to read, so this doesn't try to guess a more accurate model.
"""

import random
import time

import config

# °F. The compressor pulls every probe toward the floor; with it off, probes
# drift toward the ceiling (roughly "AC blowing cold" / "car soaking in the
# sun") -- change these if you want a hotter/colder test environment.
COOLING_FLOOR = 55.0
AMBIENT_CEILING = 88.0

# Per-tick (1s) approach rate toward the target; bigger = faster/twitchier.
# blower/exhaust sit right at the vents so they swing hardest; baggage/tail
# are furthest from the vents and have more thermal mass.
PROBE_RATES = {
    "blower": 0.05,
    "exhaust": 0.04,
    "compressor": 0.045,  # near the vents/refrigerant lines -- see module docstring for why this still uses the same cooling-floor model as the others
    "cabin": 0.015,
    "baggage": 0.006,
    "tail": 0.006,
}
PANEL_RATE = 0.012  # the dash-mounted panel sensor, simulated independently

_FAN_ORDER = {config.FAN_LOW: 0, config.FAN_MEDIUM: 1, config.FAN_HIGH: 2}


class SimController:
    def __init__(self):
        # Set by main.py after both controllers exist (this sim's heater
        # is its own independent SimHeaterController instance, constructed
        # separately -- see main.py) -- None whenever the heater half is
        # disabled entirely (--ac-only). Read by _heater_cabin_target()
        # only; nothing else here reaches into the heater controller.
        self.heater_ctrl = None
        self.mode = config.DEFAULT_MODE
        self.fan = config.DEFAULT_FAN
        self.setpoint_min = config.DEFAULT_SETPOINT_MIN
        self.setpoint_max = config.DEFAULT_SETPOINT_MAX
        self.setpoint = min(max(config.DEFAULT_SETPOINT, self.setpoint_min), self.setpoint_max)
        self.circulation = config.DEFAULT_CIRCULATION
        self.delta = config.DEFAULT_DELTA
        self.fan_high_thresh = config.DEFAULT_AUTO_FAN_HIGH_THRESH
        self.fan_med_thresh = config.DEFAULT_AUTO_FAN_MED_THRESH
        self.fan_change_interval = config.DEFAULT_FAN_CHANGE_INTERVAL
        self.auto_loop_interval = config.DEFAULT_AUTO_LOOP_INTERVAL
        self.temp_read_interval = config.DEFAULT_TEMP_READ_INTERVAL

        self.compressor_on = False
        self.active_fan_speed = None
        self.error = ""

        # Start warm, like a vehicle that's been sitting -- makes "turn on
        # cool and watch it come down" an obvious, satisfying test.
        start = AMBIENT_CEILING - 4.0
        self.temps = {name: start + random.uniform(-1, 1) for name in PROBE_RATES}
        self.panel_temp = start
        self._panel_external = False  # True once something writes `panel` over BLE

        self._last_fan_change = 0.0
        self.on_change = None  # optional callback, set by the BLE glue

        self._apply()

    # ── current_temp mirrors controller.py's property exactly ─────────────

    @property
    def current_temp(self):
        cabin = self.temps.get("cabin") or None
        panel = self.panel_temp or None
        if cabin and panel:
            return (panel + cabin) / 2.0
        return cabin or panel

    # ── Setters (called by the BLE write callbacks) ────────────────────────

    def set_mode(self, mode):
        if mode not in (config.MODE_OFF, config.MODE_FAN, config.MODE_AUTO, config.MODE_COOL):
            return False
        self.error = ""
        self.mode = mode
        self._apply()
        return True

    def set_fan(self, fan):
        if fan not in (config.FAN_LOW, config.FAN_MEDIUM, config.FAN_HIGH):
            return False
        self.error = ""
        self.fan = fan
        if self.mode in (config.MODE_FAN, config.MODE_COOL):
            self.active_fan_speed = fan
        self._notify()
        return True

    def set_setpoint(self, temp):
        try:
            v = float(temp)
        except (ValueError, TypeError):
            return False
        # Reject out-of-range writes outright (no clamping) -- matches
        # ../aircon/controller.py's set_setpoint() exactly.
        if v < self.setpoint_min or v > self.setpoint_max:
            return False
        self.setpoint = v
        self._notify()
        return True

    def set_circulation(self, circ):
        if circ not in (config.CIRC_RECIRC, config.CIRC_FRESH):
            return False
        self.circulation = circ
        self._notify()
        return True

    def set_panel_temp(self, temp):
        try:
            self.panel_temp = float(temp)
            self._panel_external = True
            self._notify()
            return True
        except (ValueError, TypeError):
            return False

    def set_settings(self, settings):
        try:
            if "delta" in settings:
                v = float(settings["delta"])
                if v >= 0:
                    self.delta = v
            if "fan_high_thresh" in settings:
                self.fan_high_thresh = float(settings["fan_high_thresh"])
            if "fan_med_thresh" in settings:
                self.fan_med_thresh = float(settings["fan_med_thresh"])
            if "fan_change_interval" in settings:
                self.fan_change_interval = float(settings["fan_change_interval"])
            if "auto_loop_interval" in settings:
                self.auto_loop_interval = float(settings["auto_loop_interval"])
            if "temp_read_interval" in settings:
                self.temp_read_interval = float(settings["temp_read_interval"])
            if "setpoint_min" in settings or "setpoint_max" in settings:
                # Matches ../aircon/controller.py's set_settings() exactly:
                # both bounds move together (so a single min-only or
                # max-only write still validates against the other current
                # bound), only applied if the result is still min < max,
                # and the current setpoint gets pulled back inside the new
                # range rather than left dangling outside it.
                new_min = float(settings.get("setpoint_min", self.setpoint_min))
                new_max = float(settings.get("setpoint_max", self.setpoint_max))
                if new_min < new_max:
                    self.setpoint_min = new_min
                    self.setpoint_max = new_max
                    self.setpoint = min(max(self.setpoint, new_min), new_max)
            self._notify()
            return True
        except (ValueError, TypeError):
            return False

    # ── State snapshot (for the BLE glue to encode) ─────────────────────────

    def get_state(self):
        return {
            "version": config.AC_VERSION,
            "mode": self.mode,
            "fan": self.fan,
            "setpoint": self.setpoint,
            "circulation": self.circulation,
            "panel_temp": self.panel_temp,
            "current_temp": self.current_temp,
            "compressor": "on" if self.compressor_on else "off",
            "cabin_temp": self.temps.get("cabin"),
            "blower_temp": self.temps.get("blower"),
            "exhaust_temp": self.temps.get("exhaust"),
            "compressor_temp": self.temps.get("compressor"),
            "baggage_temp": self.temps.get("baggage"),
            "tail_temp": self.temps.get("tail"),
            "error": self.error,
            "delta": self.delta,
            "fan_high_thresh": self.fan_high_thresh,
            "fan_med_thresh": self.fan_med_thresh,
            "fan_change_interval": self.fan_change_interval,
            "auto_loop_interval": self.auto_loop_interval,
            "temp_read_interval": self.temp_read_interval,
            "setpoint_min": self.setpoint_min,
            "setpoint_max": self.setpoint_max,
        }

    # ── Mode transitions, ported from ../aircon/controller.py's _apply() ──

    def _apply(self):
        mode = self.mode
        if mode == config.MODE_OFF:
            self.compressor_on = False
            self.active_fan_speed = None
        elif mode == config.MODE_FAN:
            self.compressor_on = False
            self.active_fan_speed = self.fan
        elif mode == config.MODE_AUTO:
            self.compressor_on = False
            self.active_fan_speed = self.active_fan_speed or config.FAN_LOW
        elif mode == config.MODE_COOL:
            self.active_fan_speed = self.active_fan_speed or config.FAN_HIGH
            self.compressor_on = True
        self._notify()

    # ── Auto-mode control loop, ported from _auto_control() ───────────────

    def _auto_control(self, now):
        current = self.current_temp
        if current is None:
            self.error = "No temperature reading"
            self._notify()
            return
        self.error = ""

        if not self.compressor_on:
            if current > self.setpoint + self.delta:
                self.compressor_on = True
        else:
            if current < self.setpoint - self.delta:
                self.compressor_on = False

        diff = abs(current - self.setpoint)
        cabin = self.temps.get("cabin") or current
        gradient = abs(self.panel_temp - cabin) if self.panel_temp else 0.0
        max_diff = max(diff, gradient)

        if max_diff >= self.fan_high_thresh:
            target_fan = config.FAN_HIGH
        elif max_diff >= self.fan_med_thresh:
            target_fan = config.FAN_MEDIUM
        else:
            target_fan = config.FAN_LOW

        increasing = _FAN_ORDER.get(target_fan, 0) > _FAN_ORDER.get(self.active_fan_speed, 0)
        rate_ok = now - self._last_fan_change >= self.fan_change_interval
        if target_fan != self.active_fan_speed and (increasing or rate_ok):
            self.active_fan_speed = target_fan
            self._last_fan_change = now

        self._notify()

    # ── Thermal model ───────────────────────────────────────────────────────

    def _heater_cabin_target(self, default_target):
        """"cabin"/panel_temp's target while the heater (a separate device,
        this sim's own SimHeaterController -- see self.heater_ctrl's own
        comment) is actively heating -- lets ../hvac-knob/screens/home.py's
        current_temp readout visibly climb while heat/heat_auto mode is
        active, the heating analog of watching it fall while the compressor
        runs. Only "cabin"/panel_temp use this (see _step_temps()) -- the
        AC-specific probes (blower/exhaust/compressor/baggage/tail) keep
        approaching `default_target` regardless, since a cabin heater
        wouldn't run air through the AC's own ducts/compressor.

        hc.on specifically (not hc.cooling) -- mid-cooldown the heater
        isn't actively adding heat anymore, so cabin/panel should drift
        back toward default_target same as if it were fully off already;
        see heat_controller.SimHeaterController's own state-machine
        docstring.

        RUN_MODE_GEAR's target (80 + 2*gear) is a made-up ceiling -- this
        sim has no real thermal spec to model against, same as everywhere
        else in this class -- picked so higher gears visibly plateau
        higher. RUN_MODE_THERMOSTAT's target is just the heater's own
        commanded setpoint (run_param, Celsius), converted to this class's
        native Fahrenheit.
        """
        hc = self.heater_ctrl
        if hc is None or not hc.on:
            return default_target
        if hc.run_mode == config.RUN_MODE_GEAR:
            return 80.0 + 2.0 * hc.run_param
        if hc.run_mode == config.RUN_MODE_THERMOSTAT:
            return hc.run_param * 9.0 / 5.0 + 32.0
        return default_target

    def _step_temps(self):
        target = COOLING_FLOOR if self.compressor_on else AMBIENT_CEILING
        # Compressor takes priority if it's ever running at the same time
        # as the heater (not expected in normal panel use -- apply_mode()
        # forces the AirCon to "off" before turning the heater on -- but
        # this sim shouldn't assume that invariant holds, e.g. against a
        # test script driving both independently over BLE).
        cabin_target = target if self.compressor_on else self._heater_cabin_target(target)
        for name, rate in PROBE_RATES.items():
            t = self.temps[name]
            probe_target = cabin_target if name == "cabin" else target
            t += (probe_target - t) * rate
            t += random.uniform(-0.05, 0.05)
            self.temps[name] = t

        if not self._panel_external:
            self.panel_temp += (cabin_target - self.panel_temp) * PANEL_RATE
            self.panel_temp += random.uniform(-0.05, 0.05)

    def _notify(self):
        if self.on_change:
            self.on_change()

    # ── Background loop ─────────────────────────────────────────────────────

    async def run(self):
        import asyncio

        last_auto = 0.0
        while True:
            await asyncio.sleep(1.0)
            now = time.monotonic()
            if self.mode == config.MODE_AUTO and now - last_auto >= self.auto_loop_interval:
                last_auto = now
                self._auto_control(now)
            self._step_temps()
            self._notify()
