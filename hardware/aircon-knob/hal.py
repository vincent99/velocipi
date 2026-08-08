"""Hardware setup for the CrowPanel 1.28"-HMI ESP32 Rotary Display, using
LVGL directly (via the lvgl_micropython custom firmware build's built-in
GC9A01 display driver and CST816S touch driver -- see ../README.md for the
firmware build command). The rotary encoder has no built-in driver in
lvgl_micropython, so it's wired up here as a custom lv.indev on top of
encoder.py's quadrature decode.
"""

import lvgl as lv
import lcd_bus
import gc9a01
import cst816s
import neopixel
from machine import SPI, I2C, Pin

from encoder import Encoder

# Pin assignments (CrowPanel 1.28"-HMI ESP32 Rotary Display, per Elecrow's
# wiki / Arduino lesson 1 sample)
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
_TOUCH_I2C_FREQ = 400_000
_TOUCH_I2C_ADDR = 0x15

_POWER_PIN_1 = 1
_POWER_PIN_2 = 2
_POWER_LIGHT_PIN = 40

_LED_PIN = 48
_LED_COUNT = 5

# Public (no leading underscore): main.py's _led_rgb_for() also uses these
# to scale its red/blue/white base colors -- full 0-255 RGB output measured
# painfully bright in person, so each channel is capped at LED_MAX_PCT
# instead, which conveniently also makes 100% brightness == rgb(100,100,100),
# a direct 1:1 read against the brightness percentage itself.
# LED_MIN_PCT keeps them from going fully dark at the lowest brightness
# setting, same reasoning as _BACKLIGHT_MIN_PCT below.
LED_MIN_PCT = 1
LED_MAX_PCT = 100

WIDTH = 240
HEIGHT = 240


def init_board_power():
    """Returns the power-light Pin, left ON (active-low) -- main()'s own
    loop blinks it at 1Hz from there (see _HEARTBEAT_PERIOD_MS) rather
    than this just leaving it solidly lit: a steady blink is a much more
    useful "is the main loop still actually running" signal than a light
    that looks identical whether the app's fine or the main loop has hung.
    """
    Pin(_POWER_PIN_1, Pin.OUT).value(1)
    Pin(_POWER_PIN_2, Pin.OUT).value(1)
    heartbeat = Pin(_POWER_LIGHT_PIN, Pin.OUT)
    heartbeat.value(0)  # active-low: starts on
    return heartbeat


def init_rgb_leds():
    """5 WS2812 status LEDs on _LED_PIN, driven by MicroPython's built-in
    `neopixel` module (frozen into this project's firmware build, per
    ../README.md -- not a separate `mip install`). NOT hardware-verified
    yet. Starts lit solid white at LED_MAX_PCT (not full 0-255 white -- see
    that constant's own comment) -- main() updates the actual color once
    real state is available (see its _led_rgb_for()), same
    proof-of-life-before-real-data reasoning as init_board_power()'s
    heartbeat light.
    """
    pixels = neopixel.NeoPixel(Pin(_LED_PIN), _LED_COUNT)
    pixels.fill((LED_MAX_PCT, LED_MAX_PCT, LED_MAX_PCT))
    pixels.write()
    return pixels


def hal_init_display():
    spi_bus = SPI.Bus(host=1, mosi=_LCD_MOSI, miso=-1, sck=_LCD_SCLK)
    display_bus = lcd_bus.SPIBus(
        spi_bus=spi_bus,
        dc=_LCD_DC,
        cs=_LCD_CS,
        freq=60_000_000,
    )

    # Double buffers, in PSRAM
    buf_size = WIDTH * HEIGHT * 2  # RGB565 = 2 bytes/pixel
    frame_buffer1 = display_bus.allocate_framebuffer(buf_size, lcd_bus.MEMORY_SPIRAM | lcd_bus.MEMORY_DMA)
    frame_buffer2 = display_bus.allocate_framebuffer(buf_size, lcd_bus.MEMORY_SPIRAM | lcd_bus.MEMORY_DMA)

    display = gc9a01.GC9A01(
        data_bus=display_bus,
        display_width=WIDTH,
        display_height=HEIGHT,
        frame_buffer1=frame_buffer1,
        frame_buffer2=frame_buffer2,
        reset_pin=_LCD_RST,
        reset_state=gc9a01.STATE_LOW,
        backlight_pin=_LCD_BACKLIGHT,
        # Must be STATE_PWM, not STATE_HIGH: with a plain digital pin,
        # display_driver_framework.py's set_backlight() only does
        # `pin.value(bool(value))`, so every nonzero value reads as "fully
        # on" and dimming does nothing -- confirmed on real hardware twice
        # now (this got reverted once already). STATE_PWM wraps the pin in
        # machine.PWM and drives it via duty_u16() for real dimming.
        backlight_on_state=gc9a01.STATE_PWM,
        color_space=lv.COLOR_FORMAT.RGB565,
        color_byte_order=gc9a01.BYTE_ORDER_BGR,
        rgb565_byte_swap=True,
    )
    display.reset()
    display.init()
    display._backup_set_memory_location(0, 0, WIDTH - 1, HEIGHT - 1)

    # Backlight is turned on later, not here
    return display


class _I2CRegDevice:
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
    i2c_dev = I2C(0, scl=Pin(_TOUCH_SCL), sda=Pin(_TOUCH_SDA), freq=_TOUCH_I2C_FREQ)
    addr = getattr(cst816s, "I2C_ADDR", _TOUCH_I2C_ADDR)
    device = _I2CRegDevice(i2c_dev, addr)
    return cst816s.CST816S(device, reset_pin=_TOUCH_RST)


_BACKLIGHT_MIN_PCT = 1
_BACKLIGHT_MAX_PCT = 100

# Last percentage passed to set_brightness() -- main.py's _led_rgb_for()
# scales the RGB status LEDs by this too (see get_brightness_pct()), so
# they dim/brighten together with the backlight instead of staying at a
# fixed, possibly painfully-bright level in a dark cabin.
_brightness_pct = 100


def set_brightness(display, pct):
    global _brightness_pct
    pct = min(max(pct, _BACKLIGHT_MIN_PCT), _BACKLIGHT_MAX_PCT)
    _brightness_pct = pct
    display.set_backlight(pct)


def get_brightness_pct():
    return _brightness_pct


def hal_init_input():
    try:
        _init_touch()
    except Exception as e:
        print("hal: touch init failed, continuing without it:", type(e), e.args)

    return Encoder()
