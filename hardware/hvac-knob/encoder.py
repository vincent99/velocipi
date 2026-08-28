"""Rotary encoder + push button on the CrowPanel knob.

Quadrature is decoded in hardware by the ESP32's PCNT (pulse counter)
peripheral, not in software. An earlier version of this file decoded it in
GPIO IRQ handlers (the same Gray-code +/-1-per-transition accumulator the
Pi uses for its SX1509-driven knobs -- see the main server's hub.go
quadTable/knobState) -- but on real hardware that measurably dropped
detents during fast spins: MicroPython's soft-IRQ scheduling couldn't
always keep up, so occasionally both A and B had already changed by the
time a handler ran and read them, corrupting the decode. PCNT counts every
A/B edge in dedicated silicon, so it can't miss one no matter how busy the
interpreter is -- confirmed clean (zero dropped counts) under the same
fast-spin test that dropped counts in software.

Signature/kwargs confirmed against the actual binding source shipped in
this project's firmware build (lvgl_micropython's
lib/micropython/ports/esp32/esp32_pcnt.c), not guessed -- PCNT bindings
vary between MicroPython forks and guessing would risk a silently-wrong
config rather than an obvious failure.

The Pi's SX1509-driven knobs are 2 valid quadrature steps per detent, but
this knob's real hardware measured 4 steps per detent on a real device (a
full Gray-code cycle per mechanical click, rather than half of one).
_STEPS_PER_DETENT reflects the measured value, not the Pi's.
"""

import esp32
from machine import Pin

PIN_A = 45
PIN_B = 42
PIN_BTN = 41

_STEPS_PER_DETENT = 4


class Encoder:
    def __init__(self):
        self._pin_btn = Pin(PIN_BTN, Pin.IN, Pin.PULL_UP)

        self._pcnt = esp32.PCNT(0)
        # Channel 0: pulse=A, control=B. Channel 1: pulse=B, control=A --
        # mirrored, so both channels' counts land in the same unit and
        # combine into one hardware-quadrature-decoded total (the standard
        # ESP-IDF two-channel quadrature-decode pattern). INCREMENT/
        # DECREMENT here are chosen to match this knob's physical wiring
        # (a clockwise turn reporting a positive delta) -- confirmed on
        # real hardware, not derived from datasheet polarity.
        self._pcnt.init(
            channel=0, pin=PIN_A, mode_pin=PIN_B,
            rising=self._pcnt.INCREMENT, falling=self._pcnt.DECREMENT,
            mode_low=self._pcnt.NORMAL, mode_high=self._pcnt.REVERSE,
            # Glitch filter in APB clock cycles (max 1023, ~12.8us @ 80MHz)
            # -- rejects contact bounce without being long enough to eat a
            # genuine fast-spin transition.
            filter=100,
        )
        self._pcnt.init(
            channel=1, pin=PIN_B, mode_pin=PIN_A,
            rising=self._pcnt.DECREMENT, falling=self._pcnt.INCREMENT,
            mode_low=self._pcnt.NORMAL, mode_high=self._pcnt.REVERSE,
        )
        self._pcnt.value(0)
        self._pcnt.start()

        # Not cleared on every read (unlike pcnt.value(0)'s read-and-clear
        # form) -- clearing mid-detent would discard whatever partial
        # progress had accumulated since the last read, silently dropping
        # steps just like the software decoder used to. Diffing the raw
        # free-running count instead preserves that partial progress
        # across reads.
        self._last_steps = 0

    def read_delta(self):
        """Returns the (possibly negative) number of detents since the last call."""
        steps = int(self._pcnt.value() / _STEPS_PER_DETENT)
        delta = steps - self._last_steps
        self._last_steps = steps
        return delta

    def button_pressed(self):
        return self._pin_btn.value() == 0
