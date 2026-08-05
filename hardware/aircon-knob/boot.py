"""Runs once before main.py on every boot (standard MicroPython convention).
Bumps the CPU to full speed -- LVGL rendering plus BLE benefit from the
extra headroom.
"""

import machine

try:
    machine.freq(240_000_000)
except Exception:
    pass
