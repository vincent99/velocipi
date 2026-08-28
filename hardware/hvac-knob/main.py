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
_SAFE_MODE check below regardless: Ctrl-C only helps if the interpreter is
cooperative enough to actually deliver the interrupt, and a genuinely
wedged app (stuck in a blocking call, no await point reached) might never
see it at all.
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
# Ctrl-C alone doesn't fully cover this need: it works fine when the app
# is merely slow or misbehaving (see serial_link.py's docstring for why
# micropython.kbd_intr(-1) is no longer called at all, and the `except
# KeyboardInterrupt` clause at the bottom of this file, which just returns
# to the REPL rather than resetting), but a genuinely wedged app -- stuck
# in a blocking call with no cooperative await point for the interpreter
# to deliver the interrupt at -- might never see a Ctrl-C at all. This is
# the only way in for that case, short of racing the boot window or a full
# reflash.
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

# Half-period, not full -- toggling every _HEARTBEAT_PERIOD_MS gives a full
# on/off cycle of 2x this, i.e. 1Hz at 500ms. See hal.init_board_power()'s
# docstring for why this blinks instead of just staying lit.
_HEARTBEAT_PERIOD_MS = 500

# The 5 status LEDs (see hal.init_rgb_leds()): red/blue/white, not the
# theme's own COLOR_DANGER/COLOR_COMPRESSOR_ON hex values -- those were
# tuned as a subtle translucent *background fill* behind text (home.py's
# row1), not a standalone illuminated color, so COLOR_COMPRESSOR_ON in
# particular (a near-black navy, 0x0B1F4D) would read as barely-lit rather
# than "blue" here. Same priority order as row1's own fill logic (error
# beats compressor-on beats neutral) -- see _led_rgb_for().
#
# Component values are capped at hal.LED_MAX_PCT (100), not the usual
# 0-255 per channel -- see that constant's own comment for why (also used
# by hal.init_rgb_leds()'s own initial startup color, so both places agree
# on the same ceiling).
_LED_RED = (hal.LED_MAX_PCT, 0, 0)
_LED_BLUE = (0, 0, hal.LED_MAX_PCT)
_LED_WHITE = (hal.LED_MAX_PCT, hal.LED_MAX_PCT, hal.LED_MAX_PCT)

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


def _led_rgb_for(state, brightness_pct):
    """Same priority as home.HomeTile.refresh()'s row1 fill logic (error,
    then compressor-on, then neutral) -- except neutral is solid white
    here rather than transparent/off, since these are physical always-lit
    status LEDs, not a UI highlight that should disappear when there's
    nothing to call out, and a lost BLE connection counts as an error too
    (row1 doesn't need that case explicitly -- DisconnectedTile takes over
    the whole display whenever state.connected is False, see
    screens/__init__.py's App.refresh(), so row1 isn't even visible then;
    the LEDs have no such "different screen" to fall back on). Scaled by
    brightness_pct (clamped to hal.LED_MIN_PCT/hal.LED_MAX_PCT -- see
    hal.get_brightness_pct()) so the LEDs track the same dimming the Pi
    pushes down for the LCD backlight, not a fixed always-max brightness.
    """
    if not state.connected or state.error:
        color = _LED_RED
    elif state.compressor == "on":
        color = _LED_BLUE
    else:
        color = _LED_WHITE
    pct = min(max(brightness_pct, hal.LED_MIN_PCT), hal.LED_MAX_PCT)
    return tuple(c * pct // 100 for c in color)


async def main():
    _init_watchdog()

    heartbeat_pin = hal.init_board_power()
    _checkpoint("board power initialized")

    rgb_leds = hal.init_rgb_leds()
    _checkpoint("rgb leds initialized")

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

    # heater_ble doesn't re-import aioble/bluetooth (already loaded above)
    # or re-touch aioble.config() (aircon_ble.py already set the shared
    # radio's preferred MTU; see heater_ble.py's own module docstring for
    # why this client doesn't need a larger one anyway) -- still deferred
    # to here rather than module level, for the same splash-before-BLE
    # ordering reasoning as aircon_ble above, even though the heap-
    # fragmentation risk that originally motivated deferring aircon_ble was
    # never reproduced with the current screens/ package.
    import heater_ble

    _checkpoint("after importing heater_ble")
    heater_client = heater_ble.HeaterClient(
        panel_settings.get_heater_device_name(), panel_settings.get_heater_password()
    )
    _checkpoint("heater_client constructed")

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
    app = screens.build(client, heater_client, encoder, scr, checkpoint=_checkpoint)
    _checkpoint("screens built")
    asyncio.create_task(client.run())
    asyncio.create_task(heater_client.run())

    last_refresh_ms = 0
    last_tick_ms = time.ticks_ms()
    last_heartbeat_ms = 0
    heartbeat_on = True  # matches init_board_power()'s initial state
    last_led_rgb = None  # forces the first tick's LED write to actually happen
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

        if time.ticks_diff(now, last_heartbeat_ms) >= _HEARTBEAT_PERIOD_MS:
            last_heartbeat_ms = now
            heartbeat_on = not heartbeat_on
            heartbeat_pin.value(0 if heartbeat_on else 1)  # active-low

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

        # heater_client.dirty (not just client.dirty) so a heater-only
        # change -- e.g. its own status notification updating now_gear/
        # fault_code, see heater_ble.py -- still triggers a redraw promptly
        # rather than waiting out the rest of this refresh period.
        if (
            client.dirty.is_set()
            or heater_client.dirty.is_set()
            or time.ticks_diff(now, last_refresh_ms) >= _REFRESH_PERIOD_MS
        ):
            client.dirty.clear()
            heater_client.dirty.clear()
            last_refresh_ms = now
            app.refresh()

        # Checked every tick (cheap -- pure computation, no hardware I/O
        # unless it actually changed) rather than only on the screen's own
        # refresh cadence above, so a brightness push takes effect on the
        # LEDs immediately instead of waiting for the next state change.
        led_rgb = _led_rgb_for(client.state, hal.get_brightness_pct())
        if led_rgb != last_led_rgb:
            last_led_rgb = led_rgb
            rgb_leds.fill(led_rgb)
            rgb_leds.write()

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
        # calling machine.soft_reset() (or any reset) here: mpremote's own
        # raw-REPL entry (used by `mpremote cp`/`make sync`) sends this same
        # Ctrl-C and then does its own Ctrl-A/Ctrl-D reset handshake --
        # resetting again here raced that handshake against the board's USB
        # CDC re-enumeration, producing "OSError: [Errno 6] Device not
        # configured" and aborting the copy. Letting Ctrl-C propagate
        # normally instead leaves the interpreter idle where mpremote
        # expects it. No peripheral-collision risk either: mpremote's own
        # soft-reset (its Ctrl-D) only re-runs boot.py, not main.py, so
        # nothing re-claims hal.py's peripherals until a real reset
        # (`make dev`/`make reset`) happens.
        print("KeyboardInterrupt: returning to REPL")
    except Exception as e:
        # Any other uncaught exception -- a real crash, not a dev-session
        # Ctrl-C. Left alone, _wdt (see _init_watchdog()) would reset the
        # board anyway once _WATCHDOG_TIMEOUT_MS elapses with nothing left
        # running to feed it, but resetting immediately here recovers
        # faster than waiting out that timeout. machine.reset() (a real
        # hardware reset), not soft_reset() -- unlike the Ctrl-C case above,
        # there's no mpremote handshake to stay in step with here, and a
        # crash may have left SPI/I2C hosts claimed in a broken state that
        # only a hardware reset reliably clears.
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
