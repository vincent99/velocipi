"""Rotary encoder + push button on the CrowPanel knob.

Same Gray-code +/-1-per-transition accumulator the Pi uses for its
SX1509-driven knobs (see the main server's hub.go quadTable/knobState).
Decoded in GPIO IRQ handlers since polling on the UI's own tick rate would
be far too coarse to sample quadrature reliably.

The Pi's SX1509-driven knobs are 2 valid quadrature steps per detent, but
this knob's real hardware measured 4 steps per detent on a real device (a
full Gray-code cycle per mechanical click, rather than half of one) --
confirmed by counting read_delta() events against actual physical clicks:
every click produced two separate delta=1 events instead of one.
_STEPS_PER_DETENT reflects the measured value, not the Pi's.
"""

from machine import Pin

PIN_A = 45
PIN_B = 42
PIN_BTN = 41

_STEPS_PER_DETENT = 4

_QUAD_TABLE = (
    0, -1, 1, 0,
    1, 0, 0, -1,
    -1, 0, 0, 1,
    0, 1, -1, 0,
)


class Encoder:
    def __init__(self):
        self._pin_a = Pin(PIN_A, Pin.IN, Pin.PULL_UP)
        self._pin_b = Pin(PIN_B, Pin.IN, Pin.PULL_UP)
        self._pin_btn = Pin(PIN_BTN, Pin.IN, Pin.PULL_UP)

        self._accum = 0
        self._steps = 0
        self._last_steps = 0
        self._last_state = (self._pin_a.value() << 1) | self._pin_b.value()

        self._pin_a.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=self._on_change)
        self._pin_b.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=self._on_change)

    def _on_change(self, _pin):
        curr = (self._pin_a.value() << 1) | self._pin_b.value()
        idx = (self._last_state << 2) | curr
        self._accum += _QUAD_TABLE[idx]
        self._last_state = curr
        if self._accum >= _STEPS_PER_DETENT:
            self._steps += 1
            self._accum = 0
        elif self._accum <= -_STEPS_PER_DETENT:
            self._steps -= 1
            self._accum = 0

    def read_delta(self):
        """Returns the (possibly negative) number of detents since the last call."""
        steps = self._steps
        delta = steps - self._last_steps
        self._last_steps = steps
        return delta

    def button_pressed(self):
        return self._pin_btn.value() == 0
