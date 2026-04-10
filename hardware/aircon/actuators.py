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
        self._circ_a    = machine.Pin(config.PIN_RELAY_CIRC_A,     machine.Pin.OUT)
        self._circ_b    = machine.Pin(config.PIN_RELAY_CIRC_B,     machine.Pin.OUT)
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
        """Both relays OFF = recirc, both ON = fresh air."""
        level = _relay_level(circulation == config.CIRC_FRESH)
        self._circ_a.value(level)
        self._circ_b.value(level)

    def all_off(self):
        for p in (self._fan_low, self._fan_med, self._fan_high, self._comp, self._circ_a, self._circ_b):
            p.value(_relay_level(False))


class RGBLed:
    """
    Single WS2812 pixel on PIN_LED_RGB.

    Foreground color + blink rate (priority high → low):
      error                  → red,   0.5 Hz
      mode/fan off           → white, 0.5 Hz
      fan on, compressor off → green, 1/2/4 Hz for low/med/high
      fan on, compressor on  → white, 1/2/4 Hz for low/med/high

    During the dark half of every blink:
      blue  if ≥1 BLE client connected
      off   if no BLE clients

    Call update() to change state; call set_ble_count() when BLE connections
    change; a background task (led.run()) handles blinking.
    asyncio.create_task(led.run()) must be called once the event loop is running.
    """

    # Brightness-limited RGB tuples (WS2812 order is GRB)
    _WHITE = (32, 32, 32)
    _GREEN = (64,  0,  0)
    _BLUE  = (0,   0, 64)
    _RED   = (0,  64,  0)
    _OFF   = (0,   0,  0)

    def __init__(self):
        self._np        = neopixel.NeoPixel(machine.Pin(config.PIN_LED_RGB), 1)
        self._fg        = self._WHITE
        self._hz        = 4.0
        self._ble_count = 0
        self._booting   = True   # suppress update() until ready() is called
        self._write(*self._OFF)

    def _write(self, r, g, b):
        self._np[0] = (r, g, b)
        self._np.write()

    def ready(self):
        """Call once startup is complete to enable normal state-driven LED logic."""
        self._booting = False

    def set_ble_count(self, count: int):
        """Update the number of connected BLE clients."""
        self._ble_count = count

    def update(self, fan_speed, compressor_on: bool, error: bool):
        """Update desired LED state; the run() loop applies it immediately."""
        if self._booting:
            return
        if error:
            self._fg = self._RED
            self._hz = 0.5
        elif fan_speed is None:
            self._fg = self._WHITE
            self._hz = 0.5
        elif compressor_on:
            self._fg = self._WHITE
            self._hz = {config.FAN_LOW: 1, config.FAN_MEDIUM: 2, config.FAN_HIGH: 4}.get(fan_speed, 1)
        else:
            self._fg = self._GREEN
            self._hz = {config.FAN_LOW: 1, config.FAN_MEDIUM: 2, config.FAN_HIGH: 4}.get(fan_speed, 1)

    async def run(self):
        """Blink loop — run as a long-lived asyncio task."""
        lit = True
        while True:
            half_ms = int(500 / self._hz)
            if lit:
                self._write(*self._fg)
            else:
                self._write(*(self._BLUE if self._ble_count > 0 else self._OFF))
            lit = not lit
            await asyncio.sleep_ms(half_ms)


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
