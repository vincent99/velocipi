"""Standalone display/backlight diagnostic for the CrowPanel knob.

Shows a solid, saturated color fill plus a live brightness percentage
readout, and lets the knob (0-100%, clamped) drive hal.set_brightness()
directly -- nothing else here touches the backlight (no BLE, no
aircon_ble import at all). Written to answer one question before wiring
the Pi<->knob serial brightness link discussed separately: does
hal.set_brightness()/display.set_backlight() actually change anything
visible on this hardware, independent of whatever value the AC
controller's BLE settings characteristic would normally supply.

Same init ordering as main.py, for the same hardware-confirmed reasons
(see hal.py/main.py's own comments): board power first, then just the
display, then a solid fill pumped through for real before ever touching
the backlight (so a stale previous-run image never flashes up first), and
only then touch/encoder.

Run with `mpremote run test_brightness.py` (or `mpremote mount . run
test_brightness.py`). Turn the knob to change brightness; Ctrl-C exits and
soft-resets, same as main.py, to release the SPI/I2C hosts hal.py claims
(otherwise the next `mpremote` run fails to re-claim them without
unplugging the board).
"""

import machine
import time

import lvgl as lv

import hal
import theme

_STEP_PCT = 2  # brightness change per detent -- 50 detents for a full 0-100 sweep

hal.init_board_power()

lv.init()

display = hal.hal_init_display()

# Solid, saturated fill -- not black/white, so a working backlight change
# is obvious at a glance without needing to compare against anything else
# on screen.
lv.screen_active().set_style_bg_color(lv.color_hex(0x2060C0), 0)
lv.screen_active().set_style_bg_opa(lv.OPA.COVER, 0)
for _ in range(5):
    lv.tick_inc(30)
    lv.timer_handler()
    time.sleep_ms(30)

encoder = hal.hal_init_input()

theme.load_fonts()

label = lv.label(lv.screen_active())
label.set_style_text_font(theme.FONT_TITLE, 0)
label.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
label.center()

brightness = 50
hal.set_brightness(display, brightness)
label.set_text("%d%%" % brightness)

print("Brightness diagnostic running. Turn the knob to adjust 0-100%. Ctrl-C to exit.")
print("brightness ->", brightness)

last_tick_ms = time.ticks_ms()

try:
    while True:
        now = time.ticks_ms()
        lv.tick_inc(time.ticks_diff(now, last_tick_ms))
        last_tick_ms = now
        lv.timer_handler()

        delta = encoder.read_delta()
        if delta:
            brightness = min(max(brightness + delta * _STEP_PCT, 0), 100)
            hal.set_brightness(display, brightness)
            label.set_text("%d%%" % brightness)
            print("brightness ->", brightness)

        time.sleep_ms(10)
except KeyboardInterrupt:
    print("KeyboardInterrupt: soft-resetting for a clean slate")
    machine.soft_reset()
