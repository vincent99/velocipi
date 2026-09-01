"""Runs once before main.py on every boot (standard MicroPython
convention). Bumps the CPU to full speed -- same reasoning as
../hvac-knob/boot.py's own (BLE benefits from the extra headroom); this
board has no display to justify it otherwise.
"""

import machine

try:
    machine.freq(240_000_000)
except Exception:
    pass
