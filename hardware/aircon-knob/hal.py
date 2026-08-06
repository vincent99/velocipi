"""Hardware setup for the CrowPanel 1.28"-HMI ESP32 Rotary Display, using
LVGL directly (via the lvgl_micropython custom firmware build's built-in
GC9A01 display driver and CST816S touch driver -- see ../README.md for the
firmware build command). The rotary encoder has no built-in driver in
lvgl_micropython, so it's wired up here as a custom lv.indev on top of
encoder.py's quadrature decode.

CAVEAT: the exact keyword arguments accepted by `gc9a01.GC9A01(...)` and
`cst816s.CST816S(...)` below are reconstructed from lvgl_micropython example
code (its display driver family shares one constructor, evidenced from its
ili9341/st7796 examples), not hand-verified against this exact firmware
build. If `hal_init()` raises a TypeError on unexpected/missing kwargs,
check the actual generated stub/source for these two classes -- with the
firmware built per the README, they live at
`api_drivers/common_api_drivers/display/display_driver_framework.py` and
`api_drivers/common_api_drivers/indev/cst816s/cst816s.py` in the
lvgl_micropython source tree used for the build.
"""

import lvgl as lv
import lcd_bus
import gc9a01
import cst816s
from machine import SPI, I2C, Pin

from encoder import Encoder

# Pin assignments (CrowPanel 1.28"-HMI ESP32 Rotary Display, per Elecrow's
# wiki / Arduino lesson 1 sample) -- same board as ../temp_knob/firmware/.
_LCD_SCLK = 10
_LCD_MOSI = 11
_LCD_DC = 3
_LCD_CS = 9
_LCD_RST = 14
_LCD_BACKLIGHT = 46

_TOUCH_SDA = 6
_TOUCH_SCL = 7
_TOUCH_INT = 5
_TOUCH_RST = 13

# Not in Elecrow's documented pinout table at all -- only found in their own
# Arduino example sketch, which sets these before touching the display or
# touch hardware at all. Undocumented purpose, but labeled "power pin,
# output current" in the source; most likely gates power to a shared rail
# feeding other peripherals (possibly including the display logic and/or
# backlight boost converter -- their absence would explain both a dark
# panel *and* inconsistent/undefined backlight behavior between runs,
# rather than a clean on/off).
_POWER_PIN_1 = 1
_POWER_PIN_2 = 2

# Active-low (confirmed from the same Arduino reference:
# `digitalWrite(POWER_LIGHT_PIN, LOW)` turns it on) -- used here purely as
# a "something is running" indicator, unrelated to the display/BLE state.
_POWER_LIGHT_PIN = 40

WIDTH = 240
HEIGHT = 240


def init_board_power():
    """Board-level power bring-up an Elecrow Arduino example does at the very
    top of setup(), before touching the display/touch chips at all. Call
    this first, before hal_init_display()/hal_init_input().
    """
    Pin(_POWER_PIN_1, Pin.OUT).value(1)
    Pin(_POWER_PIN_2, Pin.OUT).value(1)
    Pin(_POWER_LIGHT_PIN, Pin.OUT).value(0)  # active-low: 0 turns it on


def _init_display():
    spi_bus = SPI.Bus(host=1, mosi=_LCD_MOSI, miso=-1, sck=_LCD_SCLK)
    display_bus = lcd_bus.SPIBus(
        spi_bus=spi_bus,
        dc=_LCD_DC,
        cs=_LCD_CS,
        freq=40_000_000,
    )

    # Double buffers, in PSRAM (matching Elecrow's own Arduino reference's
    # heap_caps_malloc(..., MALLOC_CAP_SPIRAM) for this board's LVGL
    # buffers) -- rather than letting DisplayDriver.__init__ auto-allocate
    # when frame_buffer1/2 aren't passed, which sizes the buffer at *1/10th*
    # of a full frame. Confirmed on real hardware: with that partial
    # buffer, a full-screen color change visibly tore/wiped top-to-bottom
    # across ~10 separate flushes, spaced out by however often the caller
    # happens to call lv.timer_handler().
    #
    # Deliberately HALF the full frame, not exactly full: display_driver_
    # framework.py's init() has a one-time-setup fast path that only
    # triggers when the buffer size exactly equals the full frame size, and
    # that path computes the RAMWR address window as
    # `x1 + display_width`/`y1 + display_height` -- exclusive-style bounds
    # instead of the inclusive 0..239 GC9A01 actually wants, an off-by-one
    # in the vendored framework code that isn't ours to patch. Confirmed on
    # real hardware: switching to an exact full-size buffer (this file's
    # previous version) introduced a ~1-2px sliver at the bottom/right edge
    # that never got drawn. Half-size buffers still only need 2 flushes to
    # cover the whole screen (versus the original 10), avoiding both the
    # visible tear and this fast path's bug, since every flush then goes
    # through the ordinary per-area addressing in _flush_cb() instead
    # (which uses LVGL's own already-inclusive area.x1/x2).
    buf_size = (WIDTH * HEIGHT * 2) // 2  # RGB565 = 2 bytes/pixel
    frame_buffer1 = display_bus.allocate_framebuffer(buf_size, lcd_bus.MEMORY_SPIRAM | lcd_bus.MEMORY_DMA)
    frame_buffer2 = display_bus.allocate_framebuffer(buf_size, lcd_bus.MEMORY_SPIRAM | lcd_bus.MEMORY_DMA)

    display = gc9a01.GC9A01(
        data_bus=display_bus,
        display_width=WIDTH,
        display_height=HEIGHT,
        frame_buffer1=frame_buffer1,
        frame_buffer2=frame_buffer2,
        reset_pin=_LCD_RST,
        # GC9A01's RST line is active-low. display_driver_framework.py's
        # DisplayDriver.__init__ sets the pin to `not reset_state` at
        # construction time and never touches it again on its own --
        # reset_state=STATE_LOW here means that initial value is HIGH
        # (inactive/not-in-reset), and the explicit .reset() call below
        # then does LOW-for-120ms-then-HIGH, the correct pulse for an
        # active-low reset line.
        reset_state=gc9a01.STATE_LOW,
        backlight_pin=_LCD_BACKLIGHT,
        backlight_on_state=gc9a01.STATE_HIGH,
        color_space=lv.COLOR_FORMAT.RGB565,
        # Confirmed on real hardware: a solid-red test fill rendered as
        # solid blue -- a clean R/B channel swap, not a garbled/scrambled
        # color (which a byte-endianness issue would look like). Also
        # matches the Arduino reference's `cfg.rgb_order = false`, which in
        # LovyanGFX's convention means BGR, not RGB.
        color_byte_order=gc9a01.BYTE_ORDER_BGR,
        rgb565_byte_swap=True,
    )
    # Confirmed from display_driver_framework.py's source: neither __init__
    # nor _init_bus() ever calls .reset() automatically -- it's on the
    # caller. Skipping it (as the previous version of this code did) leaves
    # RST sitting at its construction-time value forever, i.e. the panel
    # stays in hardware reset and silently ignores every command .init()
    # sends it -- backlight still turns on fine (unrelated GPIO), but
    # nothing ever renders. This was found and confirmed on real hardware;
    # see the README.
    display.reset()
    # set_power() is a no-op here (display_driver_framework.py returns
    # immediately when power_pin is None, which it is -- this board has no
    # separate panel power-enable line) but left out entirely rather than
    # calling a do-nothing function.
    display.init()
    # Backlight is turned on by the caller (main.py), *after* the first
    # black fill has actually been flushed to the panel -- not here.
    # GC9A01's init sequence never clears the screen itself, so whatever
    # was already in GRAM from a previous run stays visible until the first
    # real draw; turning the backlight on immediately here means that stale
    # content is what the user sees first. Confirmed on real hardware.
    return display


class _I2CRegDevice:
    """Adapts machine.I2C to the .write()/.write_readinto() two-method
    interface cst816s.CST816S() expects as its `device` argument.

    cst816s.py's _read_reg()/_write_reg() always call these two methods in
    exactly one shape: "register address byte, then optionally read/write
    the associated data" -- e.g. write_readinto(tx[:1], rx[:1]) where tx[0]
    is the register to read. That's precisely what machine.I2C's own
    writeto_mem()/readfrom_mem_into() convenience methods are for, and
    they're implemented as two separate well-supported transactions rather
    than whichever single combined write+read operation the naive
    "just pass machine.I2C directly" attempt used -- confirmed on real
    hardware to raise `OSError: I2C operation not supported` (a driver/
    hardware-level rejection, not a missing-method one: machine.I2C does
    have a `write` method, per its own dir(), so that AttributeError never
    happened; the combined operation itself just isn't supported here).
    """

    def __init__(self, i2c, addr):
        self._i2c = i2c
        self._addr = addr

    def write(self, buf):
        # buf is [register, value, ...]: register + payload byte(s).
        self._i2c.writeto_mem(self._addr, buf[0], buf[1:])

    def write_readinto(self, out_buf, in_buf):
        # out_buf is [register]: the register to read from.
        self._i2c.readfrom_mem_into(self._addr, out_buf[0], in_buf)


def _init_touch():
    # Confirmed from the real cst816s.py source (CST816S.__init__(self,
    # device, reset_pin=None, touch_cal=None, startup_rotation=..., debug=False)):
    # - no interrupt_pin param at all -- the driver polls registers
    #   directly rather than using the INT line, so _TOUCH_INT is unused
    #   here. (Kept as a module constant for documentation of the physical
    #   pinout, and in case a future revision of this driver wants it.)
    # - reset_pin is fine as a plain int; CST816S wraps it in machine.Pin
    #   itself (`machine.Pin(reset_pin, machine.Pin.OUT)`), then calls it
    #   like `self._reset_pin(0)`/`(1)` -- machine.Pin objects support
    #   that call syntax as a value setter.
    # - `device` (positional) needs a .write()/.write_readinto() adapter --
    #   see _I2CRegDevice above for why and how.
    i2c_dev = I2C(0, scl=Pin(_TOUCH_SCL), sda=Pin(_TOUCH_SDA), freq=400_000)
    # cst816s.I2C_ADDR (0x15 in the source) is a plain module attribute, not
    # wrapped in const() like the register constants are, so it should
    # survive as a real runtime attribute -- but fall back to the literal
    # in case this build's compiler inlined/dropped it anyway.
    addr = getattr(cst816s, "I2C_ADDR", 0x15)
    device = _I2CRegDevice(i2c_dev, addr)
    return cst816s.CST816S(device, reset_pin=_TOUCH_RST)


def _init_encoder():
    """No built-in lvgl_micropython driver for a plain quadrature knob.

    Unlike the earlier version of this file, this no longer wraps the knob
    as an lv.indev of type ENCODER driving an lv.group. That convention
    couples turning the knob to *focus movement* between group members and
    an explicit "edit mode" toggle on push -- a fundamentally different
    interaction than what the screens/ package now wants: the knob always
    adjusts whichever control is the current screen's "most important
    thing" (no focus/edit-mode concept), and a push only ever matters
    together with a touch point (see screens/widgets.py's _wire_button).
    So the raw encoder.Encoder object is just handed back for
    screens/main.py to poll directly (read_delta()/button_pressed()) every
    frame, instead of being registered as an lv.indev at all.
    """
    return Encoder()


def hal_init_display():
    """Sets up just the display. Split out from hal_init() so main.py can
    get something on screen (the startup splash) before touching touch/
    encoder hardware, which are more likely to still have bring-up issues.
    """
    return _init_display()


# display.set_backlight()'s own range is 0-100 with 0 meaning fully off --
# the AC controller's "brightness" BLE setting is also 0-100, but 0 there
# means "as dim as possible", not "off" (screens/__init__.py's App reads
# that setting and calls set_brightness() below with it directly). This is
# the floor set_backlight() gets clamped to instead of 0, so the panel
# never goes dark just because the AC's brightness setting was turned all
# the way down.
_BACKLIGHT_MIN_PCT = 5


def set_brightness(display, pct):
    """Maps an 0-100 "brightness" percentage (as reported by the AC
    controller's BLE settings characteristic) onto set_backlight()'s own
    0-100 range, floored at _BACKLIGHT_MIN_PCT instead of letting 0 turn
    the backlight fully off.
    """
    pct = min(max(pct, 0), 100)
    backlight_pct = _BACKLIGHT_MIN_PCT + (pct / 100.0) * (100 - _BACKLIGHT_MIN_PCT)
    display.set_backlight(backlight_pct)


def hal_init_input():
    """Sets up touch + the encoder, returning the raw Encoder object.

    Touch (cst816s) self-registers as an LVGL pointer-type indev from its
    own constructor -- it hit-tests widgets by coordinate and has no notion
    of a focus group (that's an encoder/keypad concept), so there's nothing
    further to wire up here for it. The encoder no longer needs a group
    either -- see _init_encoder()'s docstring.
    """
    # Best-effort on purpose: letting a touch init failure raise would also
    # prevent the encoder from ever getting initialized, blocking all
    # further testing on an unrelated path.
    try:
        _init_touch()
    except Exception as e:
        print("hal: touch init failed, continuing without it:", type(e), e.args)

    return _init_encoder()


def hal_init():
    """Sets up display, touch and encoder in one call, returning
    (display, encoder). Equivalent to hal_init_display() + hal_init_input();
    kept for anything that doesn't need the splash-first ordering main.py
    uses.
    """
    display = hal_init_display()
    encoder = hal_init_input()
    return display, encoder
