"""Hardware actuators: relays, WS2812 LED, servo, buzzer."""

import asyncio
import machine
import neopixel
import config


def _relay_level(on: bool) -> int:
    """Translate on/off to the correct logic level for the relay module."""
    if config.RELAY_ACTIVE_HIGH:
        return 1 if on else 0
    return 0 if on else 1


class Relays:
    """Controls the four active relay outputs."""

    def __init__(self):
        self._fan_low  = machine.Pin(config.PIN_RELAY_FAN_LOW,    machine.Pin.OUT)
        self._fan_med  = machine.Pin(config.PIN_RELAY_FAN_MED,    machine.Pin.OUT)
        self._fan_high = machine.Pin(config.PIN_RELAY_FAN_HIGH,   machine.Pin.OUT)
        self._comp     = machine.Pin(config.PIN_RELAY_COMPRESSOR, machine.Pin.OUT)
        self.all_off()

    def set_fan(self, speed):
        """
        speed: FAN_LOW | FAN_MEDIUM | FAN_HIGH | None/'off'

        All fan relays are de-energised before the new one is activated so the
        rotary-switch wiring never sees two positions asserted simultaneously.
        """
        # De-energise all fan relays first.
        for p in (self._fan_low, self._fan_med, self._fan_high):
            p.value(_relay_level(False))
        # Then assert only the requested speed.
        if speed == config.FAN_LOW:
            self._fan_low.value(_relay_level(True))
        elif speed == config.FAN_MEDIUM:
            self._fan_med.value(_relay_level(True))
        elif speed == config.FAN_HIGH:
            self._fan_high.value(_relay_level(True))
        # Any other value (None, 'off', …) leaves all fans de-energised.

    def _fan_is_on(self):
        """Return True if any fan relay is currently energised."""
        return any(
            p.value() == _relay_level(True)
            for p in (self._fan_low, self._fan_med, self._fan_high)
        )

    def set_compressor(self, on: bool):
        """
        Enforce the hardware invariant: compressor cannot run without a fan.
        If asked to turn the compressor on while no fan relay is active, the
        request is silently ignored — the caller must start the fan first.
        """
        if on and not self._fan_is_on():
            return  # refuse — no fan running
        self._comp.value(_relay_level(on))

    def all_off(self):
        for p in (self._fan_low, self._fan_med, self._fan_high, self._comp):
            p.value(_relay_level(False))


class RGBLed:
    """
    Single WS2812 pixel on PIN_LED_RGB.
      blue  → compressor running
      green → fan running, no compressor
      red   → error
      off   → everything off
    """

    def __init__(self):
        self._np = neopixel.NeoPixel(machine.Pin(config.PIN_LED_RGB), 1)
        self._write(0, 0, 0)

    def _write(self, r, g, b):
        self._np[0] = (r, g, b)
        self._np.write()

    def update(self, compressor_on: bool, fan_on: bool, error: bool):
        if error:
            self._write(64, 0, 0)    # red
        elif compressor_on:
            self._write(0, 0, 64)    # blue
        elif fan_on:
            self._write(0, 64, 0)    # green
        else:
            self._write(0, 0, 0)     # off


class Servo:
    """
    PWM servo on PIN_SERVO controlling the recirc/fresh-air flap.

    Pulse widths are defined in config.py — calibrate SERVO_RECIRC_US and
    SERVO_FRESH_US to the actual mechanical endpoints of your valve.
    """

    def __init__(self):
        self._pwm = machine.PWM(machine.Pin(config.PIN_SERVO), freq=50)
        self.set(config.CIRC_RECIRC)

    def _us_to_duty16(self, us):
        # 50 Hz → 20 ms period.  duty_u16 range is 0–65535.
        return int(us / 20_000 * 65535)

    def set(self, circulation):
        us = config.SERVO_FRESH_US if circulation == config.CIRC_FRESH else config.SERVO_RECIRC_US
        self._pwm.duty_u16(self._us_to_duty16(us))


class Buzzer:
    """Active-low piezo buzzer on PIN_BUZZER."""

    def __init__(self):
        self._pin = machine.Pin(config.PIN_BUZZER, machine.Pin.OUT, value=0)

    async def beep(self, duration_ms=100, freq=2000):
        pwm = machine.PWM(self._pin, freq=freq, duty_u16=32768)
        await asyncio.sleep_ms(duration_ms)
        pwm.deinit()
        self._pin.value(0)

    async def double_beep(self):
        await self.beep(80)
        await asyncio.sleep_ms(80)
        await self.beep(80)
