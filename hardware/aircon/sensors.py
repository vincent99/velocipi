"""Temperature probes (DS18B20 1-wire) and mystery PWM signal monitor."""

import asyncio
import machine
import onewire
import ds18x20
import time
import config


class TemperatureSensors:
    """Five DS18B20 probes, each on its own 1-wire bus (one pin each)."""

    PROBE_PINS = (
        config.PIN_TEMP_CABIN,
        config.PIN_TEMP_BLOWER,
        config.PIN_TEMP_EXHAUST,
        config.PIN_TEMP_BAGGAGE,
        config.PIN_TEMP_TAIL,
    )
    PROBE_NAMES = ('cabin', 'blower', 'exhaust', 'baggage', 'tail')

    def __init__(self):
        self._temps = {name: None for name in self.PROBE_NAMES}
        self.temp_read_interval = config.DEFAULT_TEMP_READ_INTERVAL
        # Build one DS18X20 object per pin.
        self._buses = []
        for pin_num in self.PROBE_PINS:
            ow = onewire.OneWire(machine.Pin(pin_num))
            self._buses.append(ds18x20.DS18X20(ow))

    @staticmethod
    def _c_to_f(celsius):
        return celsius * 9.0 / 5.0 + 32.0

    async def run(self):
        """Continuously read all probes. Runs forever as an asyncio task."""
        while True:
            # Scan for ROM addresses and trigger conversion on all buses at once.
            roms = []
            for ds in self._buses:
                try:
                    found = ds.scan()
                    roms.append(found[0] if found else None)
                    if found:
                        ds.convert_temp()
                except Exception:
                    roms.append(None)

            # DS18B20 needs up to 750 ms to complete conversion.
            await asyncio.sleep_ms(750)

            # Read converted values.
            for i, (ds, name) in enumerate(zip(self._buses, self.PROBE_NAMES)):
                rom = roms[i]
                try:
                    if rom is not None:
                        self._temps[name] = self._c_to_f(ds.read_temp(rom))
                    else:
                        self._temps[name] = None
                except Exception:
                    self._temps[name] = None

            await asyncio.sleep(self.temp_read_interval)

    def get(self, name):
        """Return the latest °F reading for a probe, or None."""
        return self._temps.get(name)

    def get_all(self):
        return dict(self._temps)


class PWMMonitor:
    """
    Measures frequency and duty cycle of the compressor's PWM output (GP22).

    Uses edge-triggered interrupts so it never blocks the event loop.
    The signal characteristics are unknown; this just collects what's there.
    """

    def __init__(self):
        self._freq = 0.0
        self._duty = 0.0
        self._last_rise_us = 0
        self._high_us = 0
        self._period_us = 0
        pin = machine.Pin(config.PIN_PWM_MONITOR, machine.Pin.IN)
        pin.irq(
            handler=self._irq,
            trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING,
        )

    def _irq(self, pin):
        now = time.ticks_us()
        if pin.value():  # rising edge
            if self._last_rise_us:
                p = time.ticks_diff(now, self._last_rise_us)
                if p > 0:
                    self._period_us = p
                    if self._high_us > 0:
                        self._freq = 1_000_000 / p
                        self._duty = min(100.0, self._high_us / p * 100.0)
            self._last_rise_us = now
        else:  # falling edge
            if self._last_rise_us:
                h = time.ticks_diff(now, self._last_rise_us)
                if h > 0:
                    self._high_us = h

    @property
    def frequency(self):
        return self._freq

    @property
    def duty_cycle(self):
        return self._duty
