"""Hardware actuators: relays, WS2812 LED, buzzer."""

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
        self._fan_low   = machine.Pin(config.PIN_RELAY_FAN_LOW,    machine.Pin.OUT)
        self._fan_med   = machine.Pin(config.PIN_RELAY_FAN_MED,    machine.Pin.OUT)
        self._fan_high  = machine.Pin(config.PIN_RELAY_FAN_HIGH,   machine.Pin.OUT)
        self._comp      = machine.Pin(config.PIN_RELAY_COMPRESSOR, machine.Pin.OUT)
        self._fresh_air = machine.Pin(config.PIN_RELAY_FRESH_AIR,  machine.Pin.OUT)
        self.all_off()

    async def set_fan(self, speed):
        """
        speed: FAN_LOW | FAN_MEDIUM | FAN_HIGH | None/'off'

        All fan relays are de-energised before the new one is activated so the
        rotary-switch wiring never sees two positions asserted simultaneously.
        A 500 ms dead-time is observed after switching off before the new relay
        is energised.
        """
        # De-energise all fan relays first.
        if self._fan_is_on():
            for p in (self._fan_low, self._fan_med, self._fan_high):
                p.value(_relay_level(False))
            await asyncio.sleep_ms(500)

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

    def set_circulation(self, circulation):
        """off=recirc, on=fresh air."""
        self._fresh_air.value(_relay_level(circulation == config.CIRC_FRESH))

    def all_off(self):
        for p in (self._fan_low, self._fan_med, self._fan_high, self._comp, self._fresh_air):
            p.value(_relay_level(False))


class RGBLed:
    """
    Single WS2812 pixel on PIN_LED_RGB.

    Color encodes system state:
      white → fan and compressor off
      green → fan on, no compressor
      blue  → fan on, compressor on
      red   → error (overrides all)

    Blink rate encodes fan speed:
      solid  → fan off (or error)
      1 Hz   → low
      2 Hz   → medium
      4 Hz   → high

    Call update() to change state; a background task handles blinking.
    asyncio.create_task(led.run()) must be called once the event loop is running.
    """

    # Brightness-limited RGB tuples
    _WHITE = (32, 32, 32)
    _GREEN = (64,  0,  0)
    _BLUE  = (0,   0, 64)
    _RED   = (0,  64,  0)
    _OFF   = (0,   0,  0)

    def __init__(self):
        self._np    = neopixel.NeoPixel(machine.Pin(config.PIN_LED_RGB), 1)
        self._color = self._OFF
        self._hz    = 0   # 0 = solid
        self._write(*self._OFF)

    def _write(self, r, g, b):
        self._np[0] = (r, g, b)
        self._np.write()

    def update(self, fan_speed, compressor_on: bool, error: bool):
        """Update desired LED state; the run() loop applies it immediately."""
        if error:
            self._color = self._RED
            self._hz    = 0
        elif fan_speed is None:
            self._color = self._WHITE
            self._hz    = 0
        else:
            self._color = self._BLUE if compressor_on else self._GREEN
            self._hz    = {
                config.FAN_LOW:    1,
                config.FAN_MEDIUM: 2,
                config.FAN_HIGH:   4,
            }.get(fan_speed, 0)

    async def run(self):
        """Blink loop — run as a long-lived asyncio task."""
        lit = True
        while True:
            hz = self._hz
            if hz == 0:
                self._write(*self._color)
                await asyncio.sleep_ms(50)
            else:
                self._write(*(self._color if lit else self._OFF))
                lit = not lit
                await asyncio.sleep_ms(500 // hz)


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
