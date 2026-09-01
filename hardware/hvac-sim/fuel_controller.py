"""Simulated fuel-tank level -- a desktop-Python analog of ac_controller.py/
heat_controller.py's own SimController/SimHeaterController, but for
../fuel-level/fuel_sensor.py's ADC-voltage-to-percent model run in reverse:
that real firmware treats voltage as the ground truth (an actual ADC
reading) and derives percent from it via a two-point calibration. This sim
has no physical tank or ADC to read at all, so it's simpler -- and just as
useful for exercising the panel -- to treat percent as the ground truth
instead and derive the voltage a real sensor would report for it, under
whatever calibration is currently set. self.voltage below is that reverse
conversion, not a separately-tracked value of its own.

Drains linearly over time (config.DEFAULT_FUEL_DRAIN_PCT_PER_MIN, main.py's
--fuel-drain-rate) purely so the panel's own arc/percent readout has
something to visibly change during a test session -- the same "watch it
move over time" reasoning as ac_controller.py's thermal model and
heat_controller.py's cooldown timer, not modeling any real consumption
rate. Clamped at 0%, never goes negative.
"""

import time

import config


class SimFuelController:
    def __init__(self, percent=None, drain_rate=None):
        self.percent = min(
            max(float(config.DEFAULT_FUEL_PERCENT if percent is None else percent), 0.0), 100.0
        )
        self.drain_rate = (
            config.DEFAULT_FUEL_DRAIN_PCT_PER_MIN if drain_rate is None else float(drain_rate)
        )

        # Calibration -- same two fields (and same defaults) as ../fuel-
        # level/fuel_sensor.py's own cal_zero_v/cal_full_v, writable over
        # BLE the same way (see ble_server.py's _on_write_fuel()). No
        # storage.py-style persistence here (unlike that real firmware) --
        # this sim starts fresh from config.py's defaults every run, which
        # is fine for a test rig that's normally started fresh each session
        # anyway.
        self.cal_zero_v = config.DEFAULT_FUEL_CAL_ZERO_V
        self.cal_full_v = config.DEFAULT_FUEL_CAL_FULL_V

        self.on_change = None  # set by the BLE glue

    # ── Calibration (called by the BLE write callbacks) ─────────────────

    def set_cal_zero(self, volts):
        self.cal_zero_v = float(volts)
        self._notify()

    def set_cal_full(self, volts):
        self.cal_full_v = float(volts)
        self._notify()

    # ── State snapshot ───────────────────────────────────────────────────

    @property
    def voltage(self):
        """The raw voltage a real sensor would report for self.percent
        under the current calibration -- see this module's own docstring
        for why this runs ../fuel-level/fuel_sensor.py's own percent()
        property in reverse instead of tracking voltage independently.
        Not clamped to the real Voltage characteristic's own 0-1022V wire
        range here (see ble_server.py's own _enc_v(), which does that right
        at the wire boundary instead) -- a wildly out-of-range calibration
        is a legitimate thing to want to exercise the panel's own display
        against.
        """
        return self.cal_zero_v + (self.percent / 100.0) * (self.cal_full_v - self.cal_zero_v)

    def get_state(self):
        return {
            "percent": self.percent,
            "voltage": self.voltage,
            "cal_zero_v": self.cal_zero_v,
            "cal_full_v": self.cal_full_v,
        }

    def _notify(self):
        if self.on_change:
            self.on_change()

    # ── Background loop ─────────────────────────────────────────────────

    async def run(self):
        import asyncio

        last = time.monotonic()
        while True:
            await asyncio.sleep(1.0)
            now = time.monotonic()
            dt_min = (now - last) / 60.0
            last = now
            if self.drain_rate:
                new_percent = max(self.percent - self.drain_rate * dt_min, 0.0)
                if new_percent != self.percent:
                    self.percent = new_percent
                    self._notify()
