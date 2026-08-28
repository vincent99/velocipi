"""Simulated heater state -- a desktop-Python analog of
../aircon-sim/controller.py's SimController, but for the heater's
run_mode/run_param model instead of the AirCon's mode/fan/setpoint one, and
with no thermal model: unlike the AirCon (whose cabin temp is what
../hvac-knob/screens/home.py's auto mode actually reads to decide whether
to heat), the heater client (../hvac-knob/heater_ble.py) doesn't consume
any temperature field from this device at all today -- only now_gear and
fault_code (see _apply_notification() there) -- so simulating a thermal
response here wouldn't exercise anything on the panel side. If you extend
heater_ble.py to read more of the status frame, this is the file to extend
alongside it.

power_on()/power_off() are called directly from ble_server.py's write
dispatch -- no validation-and-reject the way ../aircon-sim/controller.py's
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
        self.remain_run_time = 0
        # now_gear mirrors run_param whenever run_mode is gear -- a real
        # unit's "actual current gear" can plausibly lag a commanded one by
        # a tick or two; this sim doesn't bother modeling that lag, it's
        # just always in sync.
        self.now_gear = config.DEFAULT_RUN_PARAM
        self.fault_code = fault_code
        # None (the default, and main.py's --password's own default) means
        # this simulated unit doesn't require a password at all -- and,
        # importantly, doesn't answer CMD_HANDSHAKE at all either (see
        # ble_server.py's _dispatch()), matching how most real units
        # apparently behave and exercising ../hvac-knob/heater_ble.py's
        # client-side "no response -> assume no password gate" heuristic.
        # An int 0-9999 means this unit *does* require a password, and
        # ble_server.py checks handshake attempts against it directly.
        self.password = password

        self.on_change = None  # set by the BLE glue

    def power_on(self, run_mode, run_param, remain_run_time=0):
        if run_mode == config.RUN_MODE_GEAR:
            run_param = min(max(run_param, config.HEAT_LEVEL_MIN), config.HEAT_LEVEL_MAX)
            self.now_gear = run_param
        elif run_mode == config.RUN_MODE_THERMOSTAT:
            run_param = min(max(run_param, config.THERMOSTAT_TEMP_MIN_C), config.THERMOSTAT_TEMP_MAX_C)
        self.on = True
        self.run_mode = run_mode
        self.run_param = run_param
        self.remain_run_time = remain_run_time & 0xFFFF
        self._notify()

    def power_off(self):
        self.on = False
        self._notify()

    def get_state(self):
        return {
            "on": self.on,
            "run_mode": self.run_mode,
            "run_param": self.run_param,
            "remain_run_time": self.remain_run_time,
            "now_gear": self.now_gear,
            "fault_code": self.fault_code,
        }

    def _notify(self):
        if self.on_change:
            self.on_change()

    # ── Background loop ─────────────────────────────────────────────────
    # No thermal model to step (see this module's own docstring) -- this
    # just re-pushes a status frame on a fixed interval regardless of
    # whether anything changed (config.BLE_NOTIFY_INTERVAL, matching
    # ../aircon-sim/config.py's BLE_NOTIFY_INTERVAL in spirit), so a
    # connected panel keeps seeing signs of life even if you never touch
    # the knob.

    async def run(self):
        import asyncio

        while True:
            await asyncio.sleep(config.BLE_NOTIFY_INTERVAL)
            self._notify()
