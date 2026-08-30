"""Simulated heater state -- a desktop-Python analog of ac_controller.py's
SimController, but for the heater's run_mode/run_param model instead of the
AirCon's mode/fan/setpoint one, and with no thermal model: unlike the
AirCon (whose cabin temp is what ../hvac-knob/screens/home.py's auto mode
actually reads), the heater client (../hvac-knob/heater_ble.py) doesn't
consume any temperature field from this device at all today -- only on/off
and now_gear (see _apply_status() there) -- so simulating a thermal
response here wouldn't exercise anything on the panel side.

Command shape matches the real v1 protocol (see ../hvac-knob/
heater_ble_config.py): CMD_ON_OFF carries no mode/gear/temp payload of its
own -- set_mode()/set_gear_or_temp() persist independently of power_on()/
power_off(), matching the real device's own confirmed behavior (three
separate writes on a real "turn on at level N" from the panel, not one
combined command). No validation-and-reject the way ac_controller.py's
set_*() methods do (returning False on a bad value); this simulator instead
clamps anything out of range, since the point here is exercising the panel,
not fuzzing this simulator's own input handling.
"""

import config


class SimHeaterController:
    def __init__(self, fault_code=0, password=None):
        self.on = False
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

    def power_on(self):
        self.on = True
        self._notify()

    def power_off(self):
        self.on = False
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
            "run_mode": self.run_mode,
            "run_param": self.run_param,
            "now_gear": self.now_gear,
            "fault_code": self.fault_code,
        }

    def _notify(self):
        if self.on_change:
            self.on_change()

    # ── Background loop ─────────────────────────────────────────────────
    # No thermal model to step (see this module's own docstring) -- this
    # just re-pushes a status frame on a fixed interval regardless of
    # whether anything changed (config.HEAT_NOTIFY_INTERVAL), so a
    # connected panel keeps seeing signs of life even if you never touch
    # the knob.

    async def run(self):
        import asyncio

        while True:
            await asyncio.sleep(config.HEAT_NOTIFY_INTERVAL)
            self._notify()
