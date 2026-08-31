"""Simulated heater state -- a desktop-Python analog of ac_controller.py's
SimController, but for the heater's run_mode/run_param model instead of the
AirCon's mode/fan/setpoint one, and with no thermal model of its own: unlike
the AirCon (whose cabin temp is what ../hvac-knob/screens/home.py's auto
mode actually reads), the heater client (../hvac-knob/heater_ble.py)
doesn't consume any temperature field from this device at all today -- only
on/off and now_gear (see _apply_status() there) -- so simulating a thermal
response *here* wouldn't exercise anything on the panel side. The cabin-
warming effect of this controller actually running is instead modeled over
in ac_controller.py's own _heater_cabin_target() (reaching into this
class's `on`/run_mode/run_param through main.py's SimController.
heater_ctrl wiring), since AirCon's cabin/panel probes are what the panel's
current_temp readout actually reflects regardless of which device is
driving it.

Command shape matches the real v1 protocol (see ../hvac-knob/
heater_ble_config.py): CMD_ON_OFF carries no mode/gear/temp payload of its
own -- set_mode()/set_gear_or_temp() persist independently of power_on()/
power_off(), matching the real device's own confirmed behavior (three
separate writes on a real "turn on at level N" from the panel, not one
combined command). No validation-and-reject the way ac_controller.py's
set_*() methods do (returning False on a bad value); this simulator instead
clamps anything out of range, since the point here is exercising the panel,
not fuzzing this simulator's own input handling.

Power state is a 3-way state machine, not a plain on/off bool: OFF -> ON
(power_on()) -> COOLING (power_off(), see that method's own docstring) ->
back to OFF once run()'s poll notices config.HEATER_COOLDOWN_SECONDS has
elapsed. Mirrors a real forced-air heater's own behavior -- it keeps
blowing to purge residual heat from the exchanger for a while after being
told to shut off, rather than cutting instantly -- and gives
../hvac-knob/screens/home.py's "Cooling Off" indicator (heater_ble.
HeaterState.cooling_off) something real to react to; see config.
NOTIFY_ON_COOLING for how that state reaches the wire.
"""

import time

import config

_OFF = "off"
_ON = "on"
_COOLING = "cooling"


class SimHeaterController:
    def __init__(self, fault_code=0, password=None):
        self._power_state = _OFF
        self._cooldown_until = None  # time.monotonic() deadline, only set while _COOLING
        self.run_mode = config.DEFAULT_RUN_MODE
        self.run_param = config.DEFAULT_RUN_PARAM
        # Static for this sim's whole lifetime -- there's no simulated
        # fault condition that clears itself, just a fixed value seeded at
        # startup (main.py's --heat-fault) for exercising the panel's error
        # display. See config.py's NOTIFY_OFF_FAULT comment for why this is
        # a guess, not a confirmed byte.
        self.fault_code = fault_code
        # now_gear mirrors run_param whenever run_mode is gear -- a real
        # unit's "actual current gear" can plausibly lag a commanded one by
        # a tick or two; this sim doesn't bother modeling that lag, it's
        # just always in sync. 1-indexed, matching HEAT_LEVEL_MIN/MAX --
        # only converted to the wire's 0-indexed form at heat_protocol.py's
        # own encode_status() boundary.
        self.now_gear = config.DEFAULT_RUN_PARAM
        # None (the default, and main.py's --heat-password's own default)
        # means this simulated unit doesn't require a password at all --
        # every frame is accepted regardless of its embedded password bytes
        # (see ble_server.py's _on_write_heat()). An int 0-9999 means this
        # unit *does* require one, and ble_server.py checks every incoming
        # frame's embedded password against it directly -- there's no
        # separate handshake/login frame in this protocol version to check
        # instead.
        self.password = password

        self.on_change = None  # set by the BLE glue

    @property
    def on(self):
        return self._power_state == _ON

    @property
    def cooling(self):
        return self._power_state == _COOLING

    def power_on(self):
        self._power_state = _ON
        self._cooldown_until = None
        self._notify()

    def power_off(self):
        """Starts the cooldown rather than cutting power immediately -- see
        this module's own docstring for the state machine and why. A no-op
        if already OFF or already COOLING: this protocol's CMD_ON_OFF
        carries no data of its own to distinguish "still holding the off
        button" from "first press" (see heater_ble_config.py), and there's
        nothing hardware-confirmed suggesting a repeated off command
        restarts an in-progress cooldown, so this doesn't either.
        """
        if self._power_state == _ON:
            self._power_state = _COOLING
            self._cooldown_until = time.monotonic() + config.HEATER_COOLDOWN_SECONDS
            self._notify()

    def set_mode(self, run_mode):
        self.run_mode = run_mode
        self._notify()

    def set_gear_or_temp(self, value):
        if self.run_mode == config.RUN_MODE_GEAR:
            value = min(max(value, config.HEAT_LEVEL_MIN), config.HEAT_LEVEL_MAX)
            self.now_gear = value
        elif self.run_mode == config.RUN_MODE_THERMOSTAT:
            value = min(max(value, config.THERMOSTAT_TEMP_MIN_C), config.THERMOSTAT_TEMP_MAX_C)
        self.run_param = value
        self._notify()

    def get_state(self):
        return {
            "on": self.on,
            "cooling": self.cooling,
            "run_mode": self.run_mode,
            "run_param": self.run_param,
            "now_gear": self.now_gear,
            "fault_code": self.fault_code,
        }

    def _notify(self):
        if self.on_change:
            self.on_change()

    # ── Background loop ─────────────────────────────────────────────────
    # No thermal model to step (see this module's own docstring) -- besides
    # expiring an in-progress cooldown, this just re-pushes a status frame
    # on a fixed interval regardless of whether anything changed (config.
    # HEAT_NOTIFY_INTERVAL), so a connected panel keeps seeing signs of life
    # even if you never touch the knob. Polls every second (finer than
    # HEAT_NOTIFY_INTERVAL) so COOLING -> OFF fires close to config.
    # HEATER_COOLDOWN_SECONDS rather than up to one whole notify interval
    # late, and pushes a status frame immediately on that transition rather
    # than waiting for the next periodic one -- the panel's "Cooling Off"
    # label should clear as soon as it actually does, not up to
    # HEAT_NOTIFY_INTERVAL seconds afterward.

    async def run(self):
        import asyncio

        last_notify = time.monotonic()
        while True:
            await asyncio.sleep(1.0)
            now = time.monotonic()
            if self._power_state == _COOLING and now >= self._cooldown_until:
                self._power_state = _OFF
                self._cooldown_until = None
                last_notify = now
                self._notify()
            elif now - last_notify >= config.HEAT_NOTIFY_INTERVAL:
                last_notify = now
                self._notify()
