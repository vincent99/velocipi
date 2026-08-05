"""Entry point. Order matters here, deliberately:

1. lv.init(), then just the display (hal.hal_init_display()) -- enough to
   show the startup splash immediately, before anything riskier runs.
2. Splash held on screen for a couple seconds, so there's visible
   proof-of-life on the panel even if step 3 or 4 breaks.
3. Touch + encoder (hal.hal_init_input()), then fonts/screens/BLE.
4. The asyncio loop: pumps LVGL's timer handler (which itself polls the
   touch/encoder indevs and redraws only what's dirty) alongside
   aircon_ble.AirconClient.run() as its own task, and periodically pushes
   the latest AirconState into the widgets since LVGL has no way to know on
   its own when new BLE data has arrived.

theme/screens/aircon_ble are imported from inside main(), not at module
level: theme.py's load_fonts() (called explicitly, after lv.init(), for the
same reason -- see theme.py) touches LVGL font state, and importing a
module runs its top-level code immediately, so an early `import screens`
would have pulled that in before lv.init() ever ran. Found on real
hardware: it doesn't raise a catchable Python exception, it crashes hard
enough to take the USB serial port down with it.

aircon_ble is deferred for a related but distinct reason: it transitively
imports aioble/bluetooth, which touches the BLE stack -- also suspected
(not yet confirmed) of leaving less heap for LVGL's own allocations shortly
after, given lv.group_create() failed with a huge garbage allocation size
right after lv.init() when aircon_ble was imported at module level, despite
that exact call succeeding fine in check_lvgl_api.py (which never imports
aircon_ble/aioble/bluetooth at all). This also better matches showing the
splash before touching BLE/hardware at all, which was the point of adding
it.
"""

import asyncio
import gc
import micropython
import time

import lvgl as lv

import hal

_REFRESH_PERIOD_MS = 250
_SPLASH_MS = 2000
_SPLASH_IMAGE = "images/splash.bin"

# Temporary diagnostic switch: a hard, uncatchable crash (kills the USB
# serial port mid-print, no traceback) was seen right around screens.build()
# on real hardware -- immediately after importing aircon_ble (which pulls in
# aioble/bluetooth) and constructing AirconClient, but *before* client.run()
# is ever started (AirconClient.__init__ itself does nothing but set plain
# attributes -- see aircon_ble.py). Set this False to skip importing
# aioble/bluetooth entirely and drive the UI off _DummyClient instead, to
# check whether the BLE stack's own init (not an active scan/connection) is
# implicated. Flip back to True once that's settled either way.
_ENABLE_BLE = False


def _checkpoint(label):
    # Cheap and allocation-light on purpose: if memory is critically low,
    # even string formatting can itself raise, masking the real error (this
    # is suspected to have happened once already -- see _show_splash()'s
    # except clause). gc.collect() first so mem_free() reflects reality
    # rather than accumulated garbage.
    gc.collect()
    print("checkpoint:", label, "mem_free=", gc.mem_free(), "stack_use=", micropython.stack_use())


def _pump(ms):
    # Nowhere in this file was anything calling lv.tick_inc() -- without it,
    # LVGL's internal tick never advances, so lv.timer_handler() always sees
    # zero elapsed time and never considers the periodic refresh period
    # reached, meaning it never redraws again after whatever *forced* the
    # very first render (LVGL typically forces one initial full render when
    # a display/screen is first created, independent of the timer-driven
    # refresh path). This matches every symptom seen so far exactly: one
    # successful render, then nothing, regardless of what was drawn or how
    # long lv.timer_handler() was pumped for.
    lv.tick_inc(ms)
    lv.timer_handler()
    time.sleep_ms(ms)


def _show_splash():
    """Full-screen startup image. Best-effort: this is cosmetic, not load-
    bearing, so any failure just logs and moves on rather than blocking
    startup. Confirmed working on real hardware.

    Loads images/splash.bin by constructing an lv.image_dsc_t directly from
    its raw RGB565 pixel bytes (skipping the file's 12-byte LVGLImage.py
    header), rather than handing the file path to img.set_src(). That's not
    the obvious approach -- LVGL's own file-based image decoder silently
    produces nothing for this file on this build (no exception, and neither
    an unprefixed path nor "S:"/"A:" drive-letter prefixes made a
    difference), while constructing the descriptor in memory and passing
    that object directly works. See ../README.md for the full story.

    The except clause avoids any string formatting (which itself
    allocates): a MemoryError under low memory can itself raise while
    trying to format "%s" % e to explain the first one, masking it. This
    bit once already, when aircon_ble was still imported before the
    display/splash instead of deferred -- see the module docstring.
    """
    try:
        with open(_SPLASH_IMAGE, "rb") as f:
            raw = f.read()
        pixel_data = raw[12:]  # strip LVGLImage.py's 12-byte header

        img = lv.image(lv.screen_active())
        img.set_src(
            lv.image_dsc_t(
                {
                    "header": {"cf": lv.COLOR_FORMAT.RGB565, "w": hal.WIDTH, "h": hal.HEIGHT},
                    "data_size": len(pixel_data),
                    "data": pixel_data,
                }
            )
        )
        img.center()
        for _ in range(5):
            _pump(30)
        return img
    except Exception as e:
        print("splash: failed to show, continuing without it. Exception type:")
        print(type(e))
        print("Exception args:")
        print(e.args)
        return None


class _DummyState:
    """Same attributes aircon_ble.AirconState has, so screens.py's tiles
    can read them without caring which client built them. Fixed placeholder
    values -- this is only for exercising the UI/fonts with BLE out of the
    picture, not a real simulator (../aircon-sim/ is that).
    """

    def __init__(self):
        self.connected = False
        self.mode = "off"
        self.fan = "low"
        self.setpoint = 72.0
        self.circulation = "fresh"
        self.current_temp = 68.0
        self.compressor = "off"
        self.cabin_temp = 68.0
        self.blower_temp = 70.0
        self.exhaust_temp = 65.0
        self.baggage_temp = 66.0
        self.tail_temp = 64.0
        self.error = ""
        self.settings = {"delta": {"value": 2.0, "default": 2.0}}


class _DummyClient:
    """Stand-in for aircon_ble.AirconClient used when _ENABLE_BLE is False.
    Never imports aioble/bluetooth at all, so the UI can be exercised on
    real hardware with the BLE stack fully out of the picture.
    """

    def __init__(self):
        self.state = _DummyState()
        self.dirty = asyncio.Event()

    async def run(self):
        while True:
            await asyncio.sleep(3600)

    async def _noop(self, *args):
        return False

    set_mode = _noop
    set_fan = _noop
    set_circulation = _noop
    set_setpoint = _noop
    set_setting = _noop


async def main():
    hal.init_board_power()
    _checkpoint("board power initialized")

    lv.init()
    _checkpoint("lv.init()")

    # Tried hooking lv.log_register_print_cb() here for visibility into
    # LVGL's internal log messages -- confirmed absent on this build
    # (clean AttributeError, not a naming mismatch), most likely because
    # LV_USE_LOG isn't compiled in. Not pursued further.

    group = lv.group_create()
    group.set_default()
    _checkpoint("group created")

    display = hal.hal_init_display()
    _checkpoint("display initialized")

    # GC9A01's init sequence (_gc9a01_init.py) never clears the screen --
    # it just configures registers and turns the panel on -- so whatever
    # was already in its GRAM from before (a previous run/power cycle)
    # stays visible until the first real draw. hal.hal_init_display() no
    # longer turns the backlight on itself for exactly this reason: clear
    # to black *first*, flush it for real (several pumps, not just one --
    # a single 50ms pump wasn't reliably enough on real hardware), and only
    # then turn the backlight on, so the user never sees the stale content
    # at all rather than just seeing it more briefly.
    lv.screen_active().set_style_bg_color(lv.color_hex(0x000000), 0)
    for _ in range(5):
        _pump(30)
    display.set_backlight(100)

    splash = _show_splash()
    await asyncio.sleep_ms(_SPLASH_MS)
    if splash is not None:
        splash.delete()
    _checkpoint("splash phase done")

    hal.hal_init_input(group)
    _checkpoint("touch/encoder initialized")

    if _ENABLE_BLE:
        _checkpoint("before importing aircon_ble (pulls in aioble/bluetooth)")
        import aircon_ble

        _checkpoint("after importing aircon_ble")
        client = aircon_ble.AirconClient()
    else:
        print("main: _ENABLE_BLE=False, using _DummyClient (no aioble/bluetooth import)")
        client = _DummyClient()
    _checkpoint("client constructed")

    # The real screen construction (lv.tileview + widgets) was cleared of
    # suspicion via a hand-built minimal version of this same screen: the
    # actual cause of the original hard crash was theme.load_fonts()'s
    # custom Nasalization binfont loading (lv.binfont_create()), which was
    # unreliable in its own right -- see theme.py's docstring. theme.py now
    # points FONT_BODY/FONT_DISPLAY at LVGL's built-in font instead, so
    # load_fonts() is cheap and solid again.
    import theme

    theme.load_fonts()
    _checkpoint("fonts loaded")

    import screens

    scr = lv.screen_active()
    app = screens.build(client, group, scr)
    _checkpoint("screens built")
    asyncio.create_task(client.run())

    last_refresh_ms = 0
    last_tick_ms = time.ticks_ms()
    while True:
        now = time.ticks_ms()
        # See _pump()'s comment above: without this, LVGL's tick never
        # advances and it never redraws after its one forced initial
        # render -- this is the loop that drives the actual running UI, so
        # this matters even more here than in the splash's own pumping.
        lv.tick_inc(time.ticks_diff(now, last_tick_ms))
        last_tick_ms = now

        lv.timer_handler()

        if client.dirty.is_set() or time.ticks_diff(now, last_refresh_ms) >= _REFRESH_PERIOD_MS:
            client.dirty.clear()
            last_refresh_ms = now
            app.refresh()

        await asyncio.sleep_ms(10)


try:
    asyncio.run(main())
except KeyboardInterrupt:
    # mpremote translates a terminal Ctrl-C into this. Hardware peripherals
    # set up by hal.py (SPI/I2C host claims, framebuffers, etc.) have no
    # explicit deinit calls anywhere in this codebase, so without this
    # they're left in whatever state they were mid-run in -- the next
    # `mpremote mount . run main.py` then fails trying to re-claim the same
    # SPI/I2C hosts, previously only recoverable by unplugging the board.
    # machine.soft_reset() is the standard MicroPython way to get back to a
    # clean slate without a power cycle. NOT hardware-verified yet -- in
    # particular, how this interacts with an active `mpremote mount .`
    # session (soft reset re-runs boot.py/main.py from the device's own
    # flash afterward, which may or may not respect the mount) is untested.
    print("KeyboardInterrupt: soft-resetting for a clean slate")
    import machine

    machine.soft_reset()
