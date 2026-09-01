"""Fuel-level sensing: reads config.PIN_FUEL_ADC, smooths it, and converts
to a 0-100% level using a two-point calibration (config.DEFAULT_CAL_ZERO_V/
DEFAULT_CAL_FULL_V until storage.load() overrides them). Standalone from
ble_server.py the same way ../aircon/controller.py is standalone from its
own ble_server.py -- this class knows nothing about BLE at all, just the
sensor and the math.
"""

import machine

import config
import storage


class FuelSensor:
    def __init__(self):
        self._adc = machine.ADC(machine.Pin(config.PIN_FUEL_ADC))
        # 11dB attenuation -- the ESP32(-S3)'s widest input range, nominally
        # 0-3.3V per Espressif's own datasheet. NOT linear across that
        # whole span in practice, especially near either rail (a well-known
        # ESP32 ADC characteristic) -- the two-point calibration (see
        # percent() below) compensates for whatever this specific board's/
        # sender's actual swing turns out to be, rather than trusting this
        # attenuation setting's nominal range to be accurate on its own.
        self._adc.atten(machine.ADC.ATTN_11DB)

        saved = storage.load()
        self.cal_zero_v = float(saved.get("cal_zero_v", config.DEFAULT_CAL_ZERO_V))
        self.cal_full_v = float(saved.get("cal_full_v", config.DEFAULT_CAL_FULL_V))

        self.voltage = 0.0  # smoothed, volts -- see poll()
        self._have_reading = False  # seeds smoothing from the first real reading, not 0.0

        self.on_change = None  # set by the BLE glue

    # ── Calibration (persisted) ─────────────────────────────────────────
    # Called from ble_server.py's write-watch tasks, one per characteristic
    # -- see that module's own docstring for the wire format these accept.

    def set_cal_zero(self, volts):
        self.cal_zero_v = float(volts)
        storage.save(self)
        self._notify()

    def set_cal_full(self, volts):
        self.cal_full_v = float(volts)
        storage.save(self)
        self._notify()

    # ── Reading ──────────────────────────────────────────────────────────

    def _read_voltage_once(self):
        """One raw ADC sample, converted to volts. Prefers read_uv()
        (microvolts, calibrated against this chip's own eFuse reference
        curve -- present on MicroPython's esp32 port since v1.17-ish) over
        read_u16() * 3.3/65535 (a flat, uncalibrated scale against
        ATTN_11DB's nominal ceiling) whenever it's available, since it
        accounts for this specific chip's own reference-voltage variance
        instead of assuming every board reads exactly the same. Falls back
        to the flat scale on a MicroPython build old enough not to have
        read_uv() at all -- NOT hardware-verified which path this specific
        generic ESP32-S3 firmware build actually takes.
        """
        try:
            return self._adc.read_uv() / 1_000_000.0
        except AttributeError:
            return self._adc.read_u16() * 3.3 / 65535.0

    def poll(self):
        """Call every config.SAMPLE_INTERVAL_MS -- takes one reading,
        smooths it into self.voltage (config.SMOOTHING_ALPHA -- see that
        constant's own comment), and fires on_change so the BLE layer can
        push a fresh value.
        """
        v = self._read_voltage_once()
        if not self._have_reading:
            self.voltage = v
            self._have_reading = True
        else:
            a = config.SMOOTHING_ALPHA
            self.voltage = self.voltage + a * (v - self.voltage)
        self._notify()

    @property
    def percent(self):
        """0-100, clamped. Doesn't assume cal_zero_v < cal_full_v -- some
        senders read *high* empty, low full (see config.DEFAULT_CAL_ZERO_V's
        own comment), and this formula inverts correctly either way since
        `span` just flips sign along with the direction voltage actually
        moves as the tank fills. A zero span (both calibrated to the same
        voltage, e.g. never actually calibrated past each other) reads 0%
        rather than dividing by zero.
        """
        span = self.cal_full_v - self.cal_zero_v
        if span == 0:
            return 0
        pct = (self.voltage - self.cal_zero_v) / span * 100.0
        return min(max(pct, 0.0), 100.0)

    def get_state(self):
        return {
            "voltage": self.voltage,
            "percent": self.percent,
            "cal_zero_v": self.cal_zero_v,
            "cal_full_v": self.cal_full_v,
        }

    def _notify(self):
        if self.on_change:
            self.on_change()

    # ── Background loop ─────────────────────────────────────────────────

    async def run(self):
        import asyncio

        while True:
            self.poll()
            await asyncio.sleep_ms(config.SAMPLE_INTERVAL_MS)
