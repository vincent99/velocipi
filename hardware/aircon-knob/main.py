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
imports aioble/bluetooth, which touches the BLE stack -- once suspected of
leaving less heap for LVGL's own allocations shortly after, given
lv.group_create() failed with a huge garbage allocation size right after
lv.init() when aircon_ble was imported at module level, despite that exact
call succeeding fine in check_lvgl_api.py (which never imports
aircon_ble/aioble/bluetooth at all). That didn't reproduce with the current
screens/ package -- real BLE and the desktop simulator (../aircon-sim/)
both now work end-to-end -- but the splash-before-BLE ordering is worth
keeping regardless, so the import stays deferred here.

serial_link IS imported at module level (unlike theme/screens/aircon_ble
above) -- it only touches machine/sys/select/json/asyncio plus hal
(already proven safe to import this early, see the block above), no LVGL
objects or aioble/bluetooth. It does NOT disable Ctrl-C on this connection
(an earlier version did, via micropython.kbd_intr(-1) -- see its own
docstring for why that turned out to be unnecessary) -- but see the
_SAFE_MODE check below regardless: Ctrl-C alone still only reaches the
`except KeyboardInterrupt: machine.soft_reset()` handler at the bottom of
this file, which reboots straight back into this same app rather than
leaving you at a lasting REPL prompt.
"""

import asyncio
import gc
import machine
import micropython
import time

# Physical safe-mode escape hatch: hold the knob's push-button (pin 41,
# matching encoder.py's PIN_BTN -- read directly here rather than via
# encoder.Encoder, since that isn't set up this early and this check needs
# to happen before anything else that could plausibly be what's wedged)
# while powering on/resetting, and this file skips running the app
# entirely below, dropping straight to a normal, idle REPL prompt instead.
# Checked immediately once `machine` is available, before lvgl/hal/
# anything else.
#
# Ctrl-C alone doesn't cover this need: it works fine on its own now (see
# serial_link.py's docstring for why micropython.kbd_intr(-1) is no longer
# called at all), but it only reaches the `except KeyboardInterrupt:
# machine.soft_reset()` handler at the very bottom of this file, which
# just reboots straight back into this same app rather than leaving a
# lasting REPL -- if the app itself is what's wedged (BLE hang, LVGL
# crash-loop, etc.), that handler alone can't get you back to a working
# prompt. This is the only way in short of racing the boot window or a
# full reflash.
_SAFE_MODE_PIN = 41
_SAFE_MODE = machine.Pin(_SAFE_MODE_PIN, machine.Pin.IN, machine.Pin.PULL_UP).value() == 0
if _SAFE_MODE:
    print("main: knob button held at boot -- safe mode, skipping app entirely")

import lvgl as lv

import hal
import panel_settings
import serial_link

_REFRESH_PERIOD_MS = 250
_SPLASH_MS = 2000
_SPLASH_IMAGE = "images/splash.bin"

# Hold the knob's push-button continuously for this long, on any screen, and
# main()'s loop reboots the panel -- a physical-only escape hatch for a
# wedged UI that doesn't depend on BLE, touch, or anything else that might
# itself be part of what's wedged. Deliberately handled here at the
# top-level loop rather than inside screens/, since it needs to work
# regardless of which tile is active or whether a touch point is also down
# (unlike the Home tile's mode/recirc buttons, which require touch+button
# together -- see screens/widgets.py's _wire_button docstring).
_REBOOT_HOLD_MS = 5000

# See _init_watchdog(). Kept as a module global (rather than threaded
# through every function that might want to feed it) because machine.WDT
# can't be stopped once created, so there's only ever at most one for the
# life of the process -- same rationale as theme.py's FONT_* globals.
_WATCHDOG_TIMEOUT_MS = 8000
_wdt = None


def _init_watchdog():
    """Arms the hardware watchdog: if nothing feeds it for
    _WATCHDOG_TIMEOUT_MS, the ESP32 resets itself. Covers both a startup
    hang (fed from _checkpoint(), called after each major init step below)
    and a runtime hang/crash (fed once per main-loop iteration) -- either
    way, a wedged panel recovers on its own instead of needing a manual
    power cycle.

    Called as the very first thing in main(), before anything else that
    could plausibly hang (display/touch/BLE init), so startup itself is
    covered too, not just the steady-state loop.

    NOT hardware-verified: machine.WDT's constructor signature and its
    actual min/max timeout range on this specific ESP32 build are assumed
    from MicroPython's documented machine.WDT API, not confirmed against
    this firmware. Also per that same API: once started, a WDT cannot be
    stopped/disabled for the rest of the process's life -- if
    _WATCHDOG_TIMEOUT_MS turns out too tight for some legitimate slow path
    (e.g. aioble's multi-second scan window in aircon_ble.py), the fix is
    to raise the timeout or feed more often around that path, not to try
    to disable it.
    """
    global _wdt
    try:
        _wdt = machine.WDT(timeout=_WATCHDOG_TIMEOUT_MS)
        print("main: watchdog armed, timeout=%dms" % _WATCHDOG_TIMEOUT_MS)
    except Exception as e:
        print("main: watchdog init failed, continuing without one:", type(e), e.args)


def _checkpoint(label):
    # Cheap and allocation-light on purpose: if memory is critically low,
    # even string formatting can itself raise, masking the real error (this
    # is suspected to have happened once already -- see _show_splash()'s
    # except clause). gc.collect() first so mem_free() reflects reality
    # rather than accumulated garbage.
    gc.collect()
    print("checkpoint:", label, "mem_free=", gc.mem_free(), "stack_use=", micropython.stack_use())
    if _wdt is not None:
        _wdt.feed()


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


async def main():
    _init_watchdog()

    hal.init_board_power()
    _checkpoint("board power initialized")

    lv.init()
    _checkpoint("lv.init()")

    # Tried hooking lv.log_register_print_cb() here for visibility into
    # LVGL's internal log messages -- confirmed absent on this build
    # (clean AttributeError, not a naming mismatch), most likely because
    # LV_USE_LOG isn't compiled in. Not pursued further.

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
    hal.set_brightness(display, 100)

    splash = _show_splash()
    await asyncio.sleep_ms(_SPLASH_MS)
    if splash is not None:
        splash.delete()
    _checkpoint("splash phase done")

    encoder = hal.hal_init_input()
    _checkpoint("touch/encoder initialized")

    _checkpoint("before importing aircon_ble (pulls in aioble/bluetooth)")
    import aircon_ble

    _checkpoint("after importing aircon_ble")
    client = aircon_ble.AirconClient(panel_settings.get_aircon_device_name())
    _checkpoint("client constructed")

    link = serial_link.SerialLink(display, client)

    # The real screen construction (lv.tileview + widgets) was cleared of
    # suspicion via a hand-built minimal version of this same screen: the
    # actual cause of the original hard crash was theme.load_fonts()'s
    # custom Nasalization binfont loading (lv.binfont_create()), which was
    # unreliable in its own right -- see theme.py's docstring. theme.py now
    # points FONT_BODY/FONT_TITLE at LVGL's built-in font instead, so
    # load_fonts() is cheap and solid again.
    import theme

    theme.load_fonts()
    _checkpoint("fonts loaded")

    import screens

    _checkpoint("screens imported")

    scr = lv.screen_active()
    app = screens.build(client, encoder, scr, checkpoint=_checkpoint)
    _checkpoint("screens built")
    asyncio.create_task(client.run())

    last_refresh_ms = 0
    last_tick_ms = time.ticks_ms()
    btn_hold_start_ms = None
    while True:
        now = time.ticks_ms()
        if _wdt is not None:
            _wdt.feed()

        # See _pump()'s comment above: without this, LVGL's tick never
        # advances and it never redraws after its one forced initial
        # render -- this is the loop that drives the actual running UI, so
        # this matters even more here than in the splash's own pumping.
        lv.tick_inc(time.ticks_diff(now, last_tick_ms))
        last_tick_ms = now

        lv.timer_handler()

        # Long-press-to-reboot: see _REBOOT_HOLD_MS's comment above. A
        # plain continuous read of button_pressed() (not an edge-detected
        # one like App.poll_input() does for Connect/Disconnected's bare
        # knob push), tracked independently of anything screens/ is doing
        # with the same button state this same tick.
        if encoder.button_pressed():
            if btn_hold_start_ms is None:
                btn_hold_start_ms = now
            elif time.ticks_diff(now, btn_hold_start_ms) >= _REBOOT_HOLD_MS:
                print("main: knob held for %dms, rebooting" % _REBOOT_HOLD_MS)
                machine.reset()
        else:
            btn_hold_start_ms = None

        # Polled every loop iteration (not just on the ~250ms refresh
        # cadence below) so turning the knob feels immediate: it reads and
        # applies the encoder's accumulated delta directly to whichever
        # control is "current" on the active screen -- see
        # screens.App.poll_input()/HomeTile.handle_knob().
        app.poll_input()

        if client.dirty.is_set() or time.ticks_diff(now, last_refresh_ms) >= _REFRESH_PERIOD_MS:
            client.dirty.clear()
            last_refresh_ms = now
            app.refresh()

        # Non-blocking: drains+dispatches whatever the Pi has sent since the
        # last tick, and pushes a state/settings message for whatever
        # changed since the last one -- see serial_link.py.
        link.poll()
        if client.state_dirty.is_set():
            client.state_dirty.clear()
            link.send_state()
        if client.settings_dirty.is_set():
            client.settings_dirty.clear()
            link.send_settings()

        await asyncio.sleep_ms(10)


if not _SAFE_MODE:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # mpremote translates a terminal Ctrl-C into this. Deliberately NOT
        # calling machine.soft_reset() (or any reset) here -- an earlier
        # version did, to keep repeated `mpremote mount . run main.py`
        # sessions from colliding over hal.py's un-deinit'd SPI/I2C host
        # claims, but that workflow is gone now (dev flashes + `mpremote
        # reset` instead, see ../Makefile). Worse, self-resetting on this
        # exact Ctrl-C actively broke plain `mpremote cp` (used by `make
        # sync`): mpremote's own raw-REPL entry handshake (transport_serial.
        # py's enter_raw_repl()) sends this same Ctrl-C and then follows up
        # with its own Ctrl-A/Ctrl-D reset sequence, reading specific
        # "raw REPL"/"soft reboot" text back at each step -- resetting
        # immediately here fired a second, earlier, differently-timed reset
        # that raced the board's native USB CDC re-enumeration against
        # mpremote's read, producing "OSError: [Errno 6] Device not
        # configured" and aborting the copy. Letting Ctrl-C propagate
        # normally (no reset at all) leaves the interpreter idle at the
        # point mpremote's handshake expects, matching how any ordinary
        # MicroPython program behaves under mpremote. No peripheral-
        # collision risk either: mpremote's own soft-reset (its Ctrl-D)
        # only re-runs boot.py, not main.py, so nothing re-claims hal.py's
        # peripherals until a real reset (`make dev`/`make reset`) happens.
        print("KeyboardInterrupt: returning to REPL")
    except Exception as e:
        # Any other uncaught exception -- a real crash, not a dev-session
        # Ctrl-C. Left alone, _wdt (see _init_watchdog()) would reset the
        # board anyway once _WATCHDOG_TIMEOUT_MS elapses with nothing left
        # running to feed it, but resetting immediately here recovers
        # faster than waiting out that timeout. machine.reset() (a real
        # hardware reset), not soft_reset() -- unlike the deliberate-Ctrl-C
        # case above, there's no `mpremote mount` session to stay polite to
        # here, and a crash may have left SPI/I2C hosts claimed in a broken
        # state that only a hardware reset reliably clears (same reasoning
        # as that case's own comment).
        #
        # sys.print_exception (MicroPython's traceback.print_exc
        # equivalent -- there's no `traceback` module in core MicroPython)
        # logs the full traceback before resetting, not just the
        # exception's bare args, since this is the one path here where the
        # *cause* of the reset matters for debugging and would otherwise be
        # lost the instant machine.reset() fires.
        import sys

        print("main: uncaught exception, rebooting:")
        sys.print_exception(e)
        machine.reset()
