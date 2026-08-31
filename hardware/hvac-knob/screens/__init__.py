"""The panel's screens package. `App` (this module) owns which full-screen
"screen" is currently showing and dispatches knob input to it; each
screen's own widgets/logic live in their own module -- home.py (the main
screen), connect.py, disconnected.py -- with LVGL widget-construction
helpers shared across them factored into widgets.py.

Two BLE devices, symmetric gates: both `client` (AirconClient) and
`heater_client` (HeaterClient) are optional now, asked about once each at
boot (AirCon first, then heater) -- pick a device or explicitly skip
("(No AirCon)"/"(No Heater)", see screens.ConnectTile's
allow_skip) -- persisted via panel_settings.get/set_aircon_skipped() and
get/set_heater_skipped() respectively so neither is ever asked again. See
refresh()'s _setup_done handling for exactly how this sequences, including
the give-up timeout for a picked-but-currently-unreachable device (either
one -- neither device blocks the other's setup, and once setup is done a
device dropping later is never a hard blocker on its own; see below).

Once setup is done, Home is reachable as long as whatever the currently
selected mode needs is available: home.MODE_DEVICE records which device
(if any) each mode requires, "off" needing neither. If neither device is
connected at all, or the current mode's specific requirement isn't met,
App shows the Disconnected screen instead (reusing aircon_disconnected_tile/
heater_disconnected_tile -- whichever's the actual problem, or
aircon_disconnected_tile as a generic fallback if both are down and the
mode needs neither, e.g. "off" at a cold boot before anything's connected
yet) -- see refresh()'s steady-state handling.

A picked heater can additionally require a password (see heater_ble.py's
module docstring, point 3, for how that's detected -- it's a heuristic, not
a certainty) -- if so, App shows heater_password_tile
(screens.heater_password.HeaterPasswordTile) in the same one-time setup
sequence, right after the heater connects and before Home (and again,
inline, if the heater is later manually re-picked via InfoTile's device
button -- see request_reconnect()). Unlike the Connect screen's explicit
"(No Heater)" entry, giving up here is a timeout
(App._HEATER_PASSWORD_TIMEOUT_MS) rather than a dedicated control on the
screen itself, and deliberately does NOT persist via panel_settings.
set_heater_skipped() -- see that function's own docstring for why "don't
have the PIN handy this boot" is treated as temporary rather than a
permanent opt-out.

Interaction model (deliberately different from a typical LVGL encoder+group
setup, which moves focus between widgets -- there's no "focused widget"
concept here at all, just a single fixed "current" control per screen):
  - Turning the knob adjusts whichever control is "current" on the active
    screen (fan speed/power on the main screen when mode is off/fan/cool,
    setpoint when mode is auto/heat_auto, heat level when mode is heat) --
    see home.HomeTile.handle_knob(). It moves the highlighted slice on
    Home's radial mode menu instead, while that's open -- see home.HomeTile.
    handle_mode_menu_knob() and this module's own poll_input() -- moves
    which tunable is selected (or adjusts it, mid-edit) on the Settings
    tile -- see settings.SettingsTile -- scrubs the graph's cursor on
    History -- see history.HistoryTile.handle_knob() -- does nothing on
    Temps or Info (both are plain read-outs), and moves the highlighted
    device on Connect -- see connect.ConnectTile.handle_knob().
  - A touch tap alone never triggers anything by itself.
  - A "click" on Home's mode/recirc cells requires a touch point on that
    cell *and* the knob's push-button, since on this hardware pressing down
    on the screen is what mechanically presses the encoder's button -- see
    widgets._wire_button(). The mode cell's click opens the radial menu
    (home.HomeTile._open_mode_menu()); navigating and confirming *within*
    that menu, once open, is bare knob-turn + knob-button instead (no
    touch needed), same as Connect/Disconnected's bare-push pattern below.
  - Connect and Disconnected are simpler: a bare knob push (edge-detected
    in App.poll_input()) is enough, since neither shares panel space with
    a swipe gesture.
  - Swipes (no push needed) navigate between Home/History/Settings/Temps/Info --
    not the tileview's own built-in scrolling/gesture engine (disabled
    entirely by removing its SCROLLABLE flag, see App.__init__: it was
    stealing drags away from Home's mode/recirc buttons, its sliding-snap
    animation felt laggy, and even with per-tile dir_=NONE it still
    rubber-banded under a touch-drag), but App._wire_tile_swipe()'s own
    press/release distance tracking -- a drag has to clear
    App._SWIPE_THRESHOLD_* (half the screen height/width) before it jumps
    straight to the target tile, with no transition animation at all.
    Swiping away from Home while the radial mode menu is open closes it
    without applying whatever was highlighted -- see home.HomeTile.
    close_mode_menu(), wired in as this tile's on_leave below.

CAVEAT: written against the LVGL Python binding's well-established naming
convention (widget constructors take `parent`, C function
`lv_foo_set_bar()` becomes Python `foo.set_bar()`, C enums like
`LV_EVENT_VALUE_CHANGED` become `lv.EVENT.VALUE_CHANGED`) but not run
against the actual generated binding. If a name doesn't resolve, check the
`lvgl.pyi` stub your lvgl_micropython firmware build produces -- see
../README.md. ../test/check_lvgl_api.py exercises the LVGL API
surface these modules add (lv.SYMBOL.*, arc.set_bg_angles, obj
add/remove_flag, tileview.get_tile_active, lv.line/lv.point_t, etc.) -- run
that before main.py on a fresh setup.

Relative imports (`from .widgets import ...` etc.) are used throughout this
package -- already exercised in practice by aioble's own source (a
dependency of this project, structured the same way), so this isn't a new,
unverified assumption about this MicroPython build's import support.
"""

import time

import hal
import lvgl as lv
import panel_settings
import theme

from .widgets import _set_visible, _wire_swipe

# The other seven tile modules (.connect, .disconnected, .history, .home,
# .info, .settings, .temps) are deliberately NOT imported here at module
# level -- see App.__init__, which imports each one individually,
# interleaved with a checkpoint() call. `import screens` always fully
# executes this file first (Python import semantics: `import pkg.submodule`
# runs `pkg/__init__.py` top to bottom before the submodule), so having all
# seven here would still pay their combined compile/transfer cost in one
# uninterrupted stretch -- exactly the same failure mode .mpy precompilation
# alone was fixing (see ../Makefile's `mpy` target), just moved one level
# down. Deferring them into __init__ instead gives the watchdog (and
# `mount`-mode's per-file round-trip transfer, see ../Makefile's `dev`
# target comment) a checkpoint between each one. .widgets stays here at
# module level because _set_visible/_wire_swipe are used from other App
# methods too (_show, poll_input, etc.), not just __init__ -- a local import
# inside __init__ wouldn't be visible there.


class App:
    # Minimum drag distance (pixels) for a swipe to register -- "half the
    # screen height/width", not LVGL's own much smaller built-in gesture
    # limit (irrelevant now regardless, since tileview's touch-scrolling is
    # disabled below in favor of this project's own _wire_swipe()).
    _SWIPE_THRESHOLD_Y = hal.HEIGHT // 2
    _SWIPE_THRESHOLD_X = hal.WIDTH // 2

    # How long to wait for a *previously-picked* device's first connection
    # of this boot (for the heater, also including its handshake resolving
    # out of "unknown" -- see heater_ble.py's HeaterState.password_required
    # -- which normally takes a few seconds at most, well inside this)
    # before giving up and letting setup proceed anyway -- see refresh()'s
    # _setup_done handling. Without this, a device that was picked once but
    # is now permanently gone (removed, dead battery) would wedge the panel
    # waiting on it forever, exactly the "neither device may ever be a hard
    # blocker" property this whole design is supposed to guarantee. Both
    # clients' own run() loops keep retrying in the background regardless
    # of this timeout -- if a device does eventually connect, its state.
    # connected flips true and whatever mode needs it starts working live,
    # same as any other later drop-and-reconnect.
    _DEVICE_CONNECT_TIMEOUT_MS = 15000

    # Separate, much longer timeout for the heater's password screen
    # specifically (see heater_password_tile) -- entering a 4-digit PIN one
    # knob-turn-and-tap at a time is an active, deliberate user task, not a
    # passive wait for hardware, so it gets a generous allowance instead of
    # _DEVICE_CONNECT_TIMEOUT_MS's 15s. Same "never a hard blocker"
    # guarantee either way: past this, setup proceeds regardless, and the
    # password screen will be offered again next boot (this give-up is
    # deliberately NOT persisted via panel_settings.set_heater_skipped() --
    # see that function's own docstring). Also reused, on its own (not
    # stacked with _DEVICE_CONNECT_TIMEOUT_MS), as the combined budget for
    # both the "wait for handshake to resolve" and "wait for a correct
    # password" phases when the heater is manually re-picked later via
    # InfoTile's device button -- see refresh()'s _manual_reconnect
    # handling.
    _HEATER_PASSWORD_TIMEOUT_MS = 90000

    # Hold the knob's push-button continuously for this long, on any screen,
    # and _enter_cooldown() fires -- a physical-only gesture that works
    # regardless of which tile is active or whether a touch point is also
    # down (unlike Home's mode/recirc buttons, which require touch+button
    # together -- see screens/widgets.py's _wire_button docstring), tracked
    # unconditionally at the top of poll_input() for exactly that reason.
    # Replaces main.py's old reboot-on-hold gesture (formerly
    # _REBOOT_HOLD_MS, same 5000ms duration and same "any screen" scope) --
    # see this module's own docstring for why.
    _COOLDOWN_HOLD_MS = 5000
    # How long the cooldown screen itself stays up once triggered, before
    # refresh() lets normal screen selection resume -- see refresh()'s own
    # top-priority cooldown check.
    _COOLDOWN_DISPLAY_MS = 5000

    def __init__(
        self, client, heater_client, encoder, scr, checkpoint=lambda label: None
    ):
        self.client = client
        self.heater_client = heater_client
        self.encoder = encoder

        self.tileview = lv.tileview(scr)
        self.tileview.set_size(lv.pct(100), lv.pct(100))
        self.tileview.set_style_bg_color(theme.COLOR_BG, 0)
        self.tileview.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        # Two earlier attempts here BOTH turned out insufficient, confirmed
        # on real hardware: set_scroll_dir(NONE) on the tileview itself,
        # and (after that) creating every tile with dir_=NONE instead of
        # DIR.TOP/BOTTOM/LEFT. Both were still-visible-scrollbar/rubber-
        # band-when-dragged failures -- dir_ turned out to only govern
        # which tile a completed *gesture* is allowed to snap to, not
        # whether the tileview can be drag-scrolled at all in the first
        # place; that base scrolling capability comes from the object
        # being SCROLLABLE (inherited from plain lv_obj), same as any other
        # scrollable container, and neither of the tileview-specific knobs
        # above touches that. Removing SCROLLABLE outright is the
        # unambiguous fix: no scroll capability at all means no drag
        # response, no rubber-band overscroll, no scrollbar, full stop.
        #
        # NOT hardware-verified: whether set_tile_by_index() (used just
        # below, and by App._wire_tile_swipe() for all navigation) and
        # get_tile_active() (used by poll_input() to gate the knob to only
        # the active tile) still work without SCROLLABLE. Both are
        # programmatic calls, not simulated touch input, so they
        # *shouldn't* depend on the flag that only gates input-driven
        # scrolling -- but if tile-switching or knob input silently breaks
        # after this change, this flag is the first thing to suspect.
        self.tileview.remove_flag(lv.obj.FLAG.SCROLLABLE)

        # A + shaped grid around the main tile at (1,1): History above,
        # Settings below, Temps to the left, Info to the right. dir_=NONE on
        # every tile (not DIR.TOP/BOTTOM/LEFT) -- on its own (see comment
        # above) this doesn't stop drag-scrolling, but it's still correct
        # to leave in place: it stops a completed swipe gesture from ever
        # being treated as a valid snap-to-adjacent-tile target, belt-and-
        # suspenders alongside removing SCROLLABLE. Each tile's *actual*
        # swipe-out directions are declared via _wire_tile_swipe()'s
        # `allowed` argument below instead.
        #
        # History above/Settings below/Temps left (not some other
        # arrangement): chosen so on_swipe()'s dx/dy-to-row/col arithmetic
        # stays completely literal (up really does mean row-1, no separate
        # inversion layer to track) while still matching the intuitive feel
        # that swiping down-to-up reveals whatever's "above" -- the same
        # way dragging a page down reveals content further down it.
        from .home import MODE_COOLDOWN_TARGET, MODE_DEVICE, HomeTile

        self._mode_device = MODE_DEVICE
        self._mode_cooldown_target = MODE_COOLDOWN_TARGET
        checkpoint("screens: imported home")
        self.home = HomeTile(client, heater_client, encoder, self.tileview)

        from .settings import SettingsTile

        checkpoint("screens: imported settings")
        self.settings_tile = SettingsTile(client, encoder, self.tileview)

        from .info import InfoTile

        checkpoint("screens: imported info")
        self.info_tile = InfoTile(
            client, heater_client, encoder, self.tileview, self.request_reconnect
        )

        from .history import HistoryTile

        checkpoint("screens: imported history")
        self.history_tile = HistoryTile(client, encoder, self.tileview)

        from .temps import TempsTile

        checkpoint("screens: imported temps")
        self.temps_tile = TempsTile(client, self.tileview)

        # Directions here are the finger's actual motion (see
        # _classify_swipe()) and on_swipe() below applies them completely
        # literally (up subtracts from row, left subtracts from col, etc.)
        # -- from Home: down-to-up reaches History (now above), up-to-down
        # reaches Settings (now below), right-to-left reaches Temps (now to
        # the left), left-to-right reaches Info (to the right, the mirror
        # of Temps). Each other tile's own entry is simply the reverse
        # gesture, back to Home. Settings' own entry also cancels any
        # in-progress ACTIVE edit on the way out -- see settings.
        # SettingsTile.cancel_active()'s docstring. Home's own entry
        # similarly closes the radial mode menu on the way out, if it was
        # open -- see home.HomeTile.close_mode_menu()'s docstring.
        self._wire_tile_swipe(
            self.home.tile,
            1,
            1,
            ("up", "down", "left", "right"),
            on_leave=self.home.close_mode_menu,
        )
        self._wire_tile_swipe(self.history_tile.tile, 1, 0, ("down",))
        self._wire_tile_swipe(
            self.settings_tile.tile,
            1,
            2,
            ("up",),
            on_leave=self.settings_tile.cancel_active,
        )
        self._wire_tile_swipe(self.temps_tile.tile, 0, 1, ("right",))
        self._wire_tile_swipe(self.info_tile.tile, 2, 1, ("left",))

        # A tileview's initial scroll position is grid cell (0,0) regardless
        # of whether any tile was actually added there -- our + shaped grid
        # has nothing at (0,0) (Home is at (1,1)), so without this it opens
        # on an empty cell with no tile to swipe *from* (no dir_ bitmask
        # applies to a nonexistent tile), which is exactly the "have to
        # swipe around to find the main screen" bug this fixes.
        self.tileview.set_tile_by_index(1, 1, False)

        # Connect/Disconnected are full-screen siblings of the tileview,
        # shown/hidden in its place -- see _show(). Not part of the
        # swipeable grid at all. One pair per device kind, both optional/
        # skippable now (see this module's own docstring) -- allow_skip on
        # both, told apart only by which client/scan_fn/label each is
        # built with; _skip_device() (below) is the shared on_skip target
        # for both.
        from .connect import ConnectTile

        checkpoint("screens: imported connect")
        self.aircon_connect_tile = ConnectTile(
            client,
            scr,
            label="AirCon",
            scan_fn=client.scan_for_aircons,
            allow_skip=True,
            on_skip=lambda: self._skip_device("aircon"),
        )
        self.heater_connect_tile = ConnectTile(
            heater_client,
            scr,
            label="Heater",
            scan_fn=heater_client.scan_for_heaters,
            allow_skip=True,
            on_skip=lambda: self._skip_device("heater"),
        )

        from .disconnected import DisconnectedTile

        checkpoint("screens: imported disconnected")
        self.aircon_disconnected_tile = DisconnectedTile(scr)
        self.heater_disconnected_tile = DisconnectedTile(scr, label="Heater")

        from .heater_password import HeaterPasswordTile

        checkpoint("screens: imported heater_password")
        self.heater_password_tile = HeaterPasswordTile(heater_client, scr)

        from .cooldown import CooldownTile

        checkpoint("screens: imported cooldown")
        self.cooldown_tile = CooldownTile(scr)

        # "home" | "aircon_connect" | "aircon_disconnected" |
        # "heater_connect" | "heater_disconnected" | "heater_password" |
        # "cooldown" -- see _show().
        self._screen = None
        self._btn_prev = (
            False  # for edge-detecting the knob's push-button in poll_input()
        )
        # Set True once _setup_done (below) first becomes True -- governs
        # "Connecting…" vs. "Disconnected" wording on both *_disconnected
        # screens (DisconnectedTile.on_show()'s ever_connected param) for
        # the rest of the boot, in both the initial setup phase and any
        # later steady-state drop.
        self._ever_connected = False
        # One-time gate: resolved once BOTH devices have been picked (or
        # skipped, or timed out waiting to connect -- see
        # _advance_device_setup()) and, if the heater ended up connected,
        # its password phase (if any) has also resolved one way or
        # another. See refresh().
        self._setup_done = False
        # ticks_ms() of when _DEVICE_CONNECT_TIMEOUT_MS's wait started for
        # each device's setup-phase connect wait, or None -- keyed "aircon"/
        # "heater". See _advance_device_setup().
        self._connect_wait_start_ms = {"aircon": None, "heater": None}
        # ticks_ms() of when the heater's setup-phase password wait started
        # (handshake-resolve and PIN-entry phases share one timer, unlike
        # _connect_wait_start_ms above -- see _advance_device_setup()'s own
        # comment for why one combined budget is enough here), or None.
        self._heater_password_wait_start_ms = None
        # "aircon" | "heater" | None -- set by request_reconnect() (called
        # from info.InfoTile's device buttons, or a *_disconnected screen's
        # knob push once setup is done -- see poll_input()), see that
        # method and refresh()'s own handling of it for the full flow.
        self._manual_reconnect = None
        # device_name the relevant client had at the moment
        # request_reconnect() was called -- refresh() compares against
        # this (not state.connected) to tell "nothing picked yet, stay on
        # the picker" apart from "a new device_name showed up, now watch
        # for it to connect". Deliberately NOT keyed off state.connected
        # alone: a device that's never been paired at all has
        # state.connected == False from the very start (nothing to be
        # "still connected to" in the first place), which an earlier
        # version of this mistook for "the old connection already
        # dropped" and bounced straight to *_disconnected before the
        # picker ever got a chance to be used.
        self._manual_reconnect_prev_name = None
        # True once refresh() has seen the manually-requested client
        # actually drop its (old) connection, *after* a new device_name
        # has been picked -- see refresh() for why this matters:
        # state.connected can still read True for a little while after a
        # pick is made (the old connection hasn't been told to drop yet,
        # or the drop hasn't completed), and refresh() needs to tell that
        # apart from the *new* pick having connected.
        self._manual_reconnect_dropped = False
        # ticks_ms() of when the heater's post-manual-reconnect password
        # wait started (see refresh()'s _manual_reconnect handling), or
        # None. Reset on every fresh request_reconnect() call.
        self._manual_reconnect_password_wait_start_ms = None

        # ticks_ms() of when the knob's push-button was last continuously
        # pressed down, or None -- tracked unconditionally at the top of
        # poll_input() regardless of which screen/tile is active (same
        # "works no matter what's on screen" scope main.py's old reboot-
        # hold had, see _COOLDOWN_HOLD_MS's comment), reset to None the
        # instant the button is released.
        self._btn_hold_start_ms = None
        # ticks_ms() of when _enter_cooldown() last fired, or None the rest
        # of the time -- see refresh()'s own top-priority cooldown check.
        self._cooldown_start_ms = None

        self._show(
            "aircon_connect" if not client.device_name else "aircon_disconnected"
        )

    def _skip_device(self, kind):
        """*_connect_tile's on_skip callback -- the user explicitly chose
        "no AirCon"/"no heater" rather than picking one. Persisted so this
        is never asked again; refresh() picks the change up on its very
        next tick (no need to force a screen change here directly -- it's
        already showing that device's connect screen, and refresh()
        re-evaluates the setup gate every tick regardless while it's still
        pending).

        Also reachable mid-manual-reconnect (request_reconnect(kind), via
        info.InfoTile's device buttons or a *_disconnected screen's knob
        push) -- refresh()'s manual-reconnect handling only ever resolves
        by watching that client's state.connected, which skipping doesn't
        change at all (there may not even be a device_name to connect to),
        so it's cleared here directly instead of leaving that branch
        waiting on a connection that's never coming. If the mode currently
        selected/displayed on Home needed exactly the device just skipped,
        it's reset to "off" too -- otherwise refresh()'s steady-state check
        would immediately bounce right back to a Disconnected screen for a
        device that's now permanently (by this same choice) unavailable.
        """
        if kind == "aircon":
            panel_settings.set_aircon_skipped(True)
        else:
            panel_settings.set_heater_skipped(True)
        if self._manual_reconnect == kind:
            self._manual_reconnect = None
            if (
                self.home.current_mode()
                and self._mode_device.get(self.home.current_mode()) == kind
            ):
                self.home.apply_mode("off")

    def request_reconnect(self, kind):
        """info.InfoTile's device buttons' click callback -- `kind` is
        "aircon" or "heater". Also reused by poll_input() for a knob push
        on either *_disconnected screen once setup is done (see there).
        Manually reopens that device's Connect screen so the user can pick
        a different one, even though initial setup is long since done.
        Suspends the normal automatic screen-selection gate in refresh()
        until it resolves -- see there for the full sequencing, and
        aircon_ble.AirconClient.set_device_name()/heater_ble.HeaterClient.
        set_device_name() for how picking a new device actually
        disconnects whatever was live before, which this whole flow
        depends on.

        Clears panel_settings.get_aircon_skipped()/get_heater_skipped()
        (whichever applies) -- opening this screen is itself an explicit
        re-engagement with pairing that device, which should supersede an
        earlier "skip" decision (the button/screen is reachable, and makes
        sense to use, precisely *because* the user might want to reverse
        that decision -- see info.InfoTile's "Not configured" display for
        a skipped device).
        """
        client = self.client if kind == "aircon" else self.heater_client
        self._manual_reconnect = kind
        self._manual_reconnect_prev_name = client.device_name
        self._manual_reconnect_dropped = False
        self._manual_reconnect_password_wait_start_ms = None
        if kind == "aircon":
            panel_settings.set_aircon_skipped(False)
        else:
            panel_settings.set_heater_skipped(False)
        self._show("%s_connect" % kind)

    def _show(self, name):
        if self._screen == name:
            return
        prev = self._screen
        self._screen = name
        _set_visible(self.tileview, name == "home")
        _set_visible(self.aircon_connect_tile.screen, name == "aircon_connect")
        _set_visible(
            self.aircon_disconnected_tile.screen, name == "aircon_disconnected"
        )
        _set_visible(self.heater_connect_tile.screen, name == "heater_connect")
        _set_visible(
            self.heater_disconnected_tile.screen, name == "heater_disconnected"
        )
        _set_visible(self.heater_password_tile.screen, name == "heater_password")
        _set_visible(self.cooldown_tile.screen, name == "cooldown")
        if prev == "aircon_connect":
            # Stops ConnectTile's background scan loop rather than leaving
            # it running (and holding ble_shared.radio_lock) after
            # navigating away -- see ConnectTile.on_hide().
            self.aircon_connect_tile.on_hide()
        if prev == "heater_connect":
            self.heater_connect_tile.on_hide()
        if prev == "home":
            # Defensive backstop for the same reasoning as _wire_tile_swipe's
            # own on_leave=cancel_active/close_mode_menu wiring in __init__
            # (which handles the ordinary swipe-away case) -- this covers
            # leaving "home" entirely some other way instead, e.g. a BLE
            # disconnect while mid-edit on Settings or with the mode menu
            # open. A no-op if nothing needed cancelling/closing.
            self.settings_tile.cancel_active()
            self.home.close_mode_menu()
        if name == "aircon_connect":
            self.aircon_connect_tile.on_show()
        elif name == "aircon_disconnected":
            self.aircon_disconnected_tile.on_show(self._ever_connected)
        elif name == "heater_connect":
            self.heater_connect_tile.on_show()
        elif name == "heater_disconnected":
            self.heater_disconnected_tile.on_show(self._ever_connected)
        elif name == "heater_password":
            self.heater_password_tile.on_show()

    def _wire_tile_swipe(self, tile, col, row, allowed, on_leave=None):
        """Makes `tile` (one grid cell of self.tileview) respond to a swipe
        starting on its own background (not on a CLICKABLE child of its
        own, like Home's mode/recirc buttons -- see _wire_swipe()'s
        docstring for why those two never conflict) by jumping straight to
        the adjacent tile in that direction, provided the drag both clears
        _SWIPE_THRESHOLD_*/`_classify_swipe()` and the resulting direction
        is one of `allowed` for this particular tile -- now the *only*
        thing gating which directions navigate anywhere, since every tile
        is created with dir_=NONE (see App.__init__) rather than the
        DIR.TOP/BOTTOM/LEFT bitmask that used to serve this same purpose
        for tileview's own (now fully disabled) gesture engine.

        `on_leave`, if given, is called (with no arguments) right before a
        qualifying swipe actually navigates away from `tile` -- settings.
        SettingsTile.cancel_active() uses this to discard an in-progress
        edit rather than leaving it dangling once the tile's no longer
        visible; home.HomeTile.close_mode_menu() uses it the same way for
        an open-but-unconfirmed radial mode menu.
        """
        tile.add_flag(lv.obj.FLAG.CLICKABLE)

        def on_swipe(dx, dy):
            direction = self._classify_swipe(dx, dy)
            if direction is None or direction not in allowed:
                return
            # Literal: up means the target is one row up (row-1), etc. --
            # see App.__init__'s grid-layout comment for why History/
            # Settings/Temps ended up positioned where they did (chosen to
            # keep this arithmetic literal rather than needing its own
            # inversion layer on top of it).
            target_col, target_row = col, row
            if direction == "up":
                target_row -= 1
            elif direction == "down":
                target_row += 1
            elif direction == "left":
                target_col -= 1
            elif direction == "right":
                target_col += 1
            if on_leave is not None:
                on_leave()
            self.tileview.set_tile_by_index(target_col, target_row, False)

        _wire_swipe(tile, on_swipe)

    def _classify_swipe(self, dx, dy):
        """Returns "up"/"down"/"left"/"right" for a drag of (dx, dy) pixels
        past _SWIPE_THRESHOLD_* on whichever axis moved further, else None
        (too short, or too diagonal to call cleanly one way or the other --
        the larger axis wins).
        """
        if abs(dy) >= abs(dx):
            if abs(dy) < self._SWIPE_THRESHOLD_Y:
                return None
            return "up" if dy < 0 else "down"
        if abs(dx) < self._SWIPE_THRESHOLD_X:
            return None
        return "right" if dx > 0 else "left"

    def poll_input(self):
        """Called every main-loop tick (not just on the slower BLE-driven
        refresh cadence) so the knob feels responsive. Drains the encoder's
        delta every call regardless of which screen is active, so turning
        it on a screen that ignores the knob (Temps, Info) doesn't build up
        a jump that applies all at once after swiping back to the main
        screen.

        The knob's push-button is edge-detected here (fires once per
        physical press, not once per poll while held) for the Connect,
        Disconnected, and Settings tiles (both device kinds' Connect/
        Disconnected pairs alike), and for Home's radial mode menu while
        it's open -- unlike home.HomeTile's mode/recirc cells themselves,
        which need a touch point together with the button (see
        widgets._wire_button()), none of these share screen space with a
        swipe gesture in a way that'd make a bare button push ambiguous, so
        a bare push is enough for all of them.
        """
        delta = self.encoder.read_delta()
        pressed = self.encoder.button_pressed()
        btn_edge = pressed and not self._btn_prev
        self._btn_prev = pressed

        # Long-press-to-cooldown: see _COOLDOWN_HOLD_MS's comment. A plain
        # continuous read of `pressed` (not the edge-detected btn_edge
        # above), tracked independently of whatever else this same tick's
        # `pressed` value drives further down -- matches main.py's old
        # long-press-to-reboot tracking this replaced (see this module's
        # own docstring), just moved here since _enter_cooldown() needs
        # self.home/self._mode_cooldown_target, which main.py never had
        # direct access to.
        now = time.ticks_ms()
        if pressed:
            if self._btn_hold_start_ms is None:
                self._btn_hold_start_ms = now
            elif (
                self._cooldown_start_ms is None
                and time.ticks_diff(now, self._btn_hold_start_ms) >= self._COOLDOWN_HOLD_MS
            ):
                self._enter_cooldown()
        else:
            self._btn_hold_start_ms = None

        # self._screen == "home" only means the tileview (not Connect/
        # Disconnected, either device kind's) is the visible top-level
        # screen -- still need get_tile_active() to check *which* tile
        # within it is active, since the knob should do nothing on Temps/
        # Info (plain read-outs).
        active_tile = (
            self.tileview.get_tile_active() if self._screen == "home" else None
        )
        if active_tile is self.home.tile:
            if self.home.mode_menu_open:
                self.home.handle_mode_menu_knob(delta)
                if btn_edge:
                    self.home.confirm_mode_menu()
            else:
                self.home.handle_knob(delta)
        elif active_tile is self.settings_tile.tile:
            self.settings_tile.handle_knob(delta)
            if btn_edge:
                self.settings_tile.handle_button()
        elif active_tile is self.history_tile.tile:
            self.history_tile.handle_knob(delta)
            if btn_edge:
                self.history_tile.handle_button()
        elif self._screen == "aircon_connect":
            self.aircon_connect_tile.handle_knob(delta)
            if btn_edge:
                self.aircon_connect_tile.select_current()
                # Forces an immediate re-evaluation instead of waiting out
                # the rest of refresh()'s ~250ms cadence (or a dirty event
                # that a plain set_device_name()/skip never sets on its
                # own) -- without this, the roller/spinner stayed on screen
                # for a beat (or indefinitely, for a skip -- see
                # _skip_device(), which alone never advances anything) after
                # a pick was already made, easy to mistake for the picker
                # being stuck. See also the matching call below for
                # heater_connect_tile.
                self.refresh()
        elif self._screen == "aircon_disconnected":
            if btn_edge:
                # During initial setup, the plain automatic gate below
                # already re-shows the connect screen on its own -- a bare
                # _show() is enough. Once setup is done, this screen can
                # also appear for a later steady-state drop -- jump
                # straight to Info instead of forcing the one device's
                # picker: Info's own device buttons (self.request_reconnect,
                # see there) already cover "pick a different device", and
                # doing it this way means a red-X screen never traps the
                # user into re-pairing specifically the device that just
                # happened to be down, when what they actually wanted was
                # the *other* one, or neither. refresh()'s steady-state
                # check has a matching carve-out so it doesn't immediately
                # bounce back here while Info is being viewed this way --
                # see there.
                if self._setup_done:
                    self._show("home")
                    self.tileview.set_tile_by_index(2, 1, False)
                else:
                    self._show("aircon_connect")
        elif self._screen == "heater_connect":
            self.heater_connect_tile.handle_knob(delta)
            if btn_edge:
                self.heater_connect_tile.select_current()
                self.refresh()
        elif self._screen == "heater_disconnected":
            if btn_edge:
                if self._setup_done:
                    self._show("home")
                    self.tileview.set_tile_by_index(2, 1, False)
                else:
                    self._show("heater_connect")
        elif self._screen == "heater_password":
            self.heater_password_tile.handle_knob(delta)
            if btn_edge:
                self.heater_password_tile.select_current()

    def _enter_cooldown(self):
        """Triggered by poll_input() once the knob's push-button has been
        held continuously for _COOLDOWN_HOLD_MS. Not a real HVAC mode of
        its own -- see screens/cooldown.py's own module docstring --
        purely a full-screen takeover plus, per home.MODE_COOLDOWN_TARGET,
        a mode transition for whatever was selected going in (a mode
        absent from that mapping, e.g. "fan"/"off", is left alone via
        .get()'s fallback to itself). See refresh()'s own top-priority
        handling of self._cooldown_start_ms for how the display window
        this starts actually ends.
        """
        current = self.home.current_mode()
        target = self._mode_cooldown_target.get(current, current)
        if target != current:
            self.home.apply_mode(target)
        self._cooldown_start_ms = time.ticks_ms()
        self._show("cooldown")

    def _advance_device_setup(self, kind):
        """One-time pick-or-skip-or-timeout gate for `kind`'s ("aircon" or
        "heater") initial connection -- see this module's docstring.
        Returns True once resolved (skipped, or connected -- for the
        heater specifically, "connected" here also means its password
        handshake has resolved out of "unknown", so the password-required
        check in refresh() sees a real answer rather than racing it -- or
        gave up after _DEVICE_CONNECT_TIMEOUT_MS). False if still pending,
        in which case self._show() has already been called with whatever
        screen reflects that.
        """
        client = self.client if kind == "aircon" else self.heater_client
        skipped = (
            panel_settings.get_aircon_skipped()
            if kind == "aircon"
            else panel_settings.get_heater_skipped()
        )
        if skipped:
            return True
        if not client.device_name:
            self._show("%s_connect" % kind)
            return False

        s = client.state
        resolved = s.connected and (kind != "heater" or s.password_required is not None)
        if resolved:
            return True

        now = time.ticks_ms()
        if self._connect_wait_start_ms[kind] is None:
            self._connect_wait_start_ms[kind] = now
        if (
            time.ticks_diff(now, self._connect_wait_start_ms[kind])
            >= self._DEVICE_CONNECT_TIMEOUT_MS
        ):
            # Given up -- see _DEVICE_CONNECT_TIMEOUT_MS's comment. The
            # client's own run() loop is still retrying in the background
            # regardless; this only stops it from blocking setup.
            return True
        self._show("%s_disconnected" % kind)
        return False

    def refresh(self):
        if self._cooldown_start_ms is not None:
            # Highest priority of everything below -- a cooldown in
            # progress overrides even a manual-reconnect-in-progress or an
            # unresolved setup gate, same as the screen it shows is a full-
            # screen takeover regardless of what's normally on screen (see
            # _enter_cooldown()). Once _COOLDOWN_DISPLAY_MS elapses this
            # clears itself and falls through to the normal logic below on
            # this same tick, rather than needing a whole extra refresh()
            # call to notice.
            now = time.ticks_ms()
            if time.ticks_diff(now, self._cooldown_start_ms) < self._COOLDOWN_DISPLAY_MS:
                self._show("cooldown")
                return
            self._cooldown_start_ms = None

        if self._manual_reconnect is not None:
            # info.InfoTile's device buttons (or a *_disconnected screen's
            # knob push post-setup, see poll_input()) triggered this --
            # suspends the normal gate logic below entirely until it
            # resolves.
            kind = self._manual_reconnect
            client = self.client if kind == "aircon" else self.heater_client
            if client.device_name == self._manual_reconnect_prev_name:
                # Nothing picked yet -- stay on whatever's currently shown
                # (almost always the picker itself) regardless of
                # state.connected, which only reflects whatever was
                # already configured *before* this manual visit (possibly
                # nothing connected at all -- see
                # _manual_reconnect_prev_name's own comment in __init__ for
                # the bug this specifically avoids) and isn't relevant
                # until a new device_name actually shows up.
                return
            # A new device has been picked (ConnectTile.select_current() ->
            # *Client.set_device_name(), which also disconnects whatever
            # was live before, if anything) -- now wait for the switch to
            # actually complete.
            if not client.state.connected:
                self._manual_reconnect_dropped = True
                self._show("%s_disconnected" % kind)
                return
            if not self._manual_reconnect_dropped:
                # Still connected, but to the device that was live
                # *before* this pick -- the disconnect set_device_name()
                # triggered hasn't taken effect yet.
                return
            if kind == "heater":
                # A freshly-picked heater needs its password phase (if
                # any) resolved too, same as initial setup -- unlike
                # initial setup, this doesn't re-run the full shared gate
                # (see _advance_device_setup()'s own comment on why that
                # would risk the AirCon's own state hijacking this screen
                # if it happened to be down at the same moment); it's
                # handled inline here instead, with one combined timeout
                # covering both the handshake-resolve and PIN-entry
                # phases.
                hs = self.heater_client.state
                if hs.password_required is None or hs.password_required:
                    now = time.ticks_ms()
                    if self._manual_reconnect_password_wait_start_ms is None:
                        self._manual_reconnect_password_wait_start_ms = now
                    if (
                        time.ticks_diff(
                            now, self._manual_reconnect_password_wait_start_ms
                        )
                        < self._HEATER_PASSWORD_TIMEOUT_MS
                    ):
                        if hs.password_required:
                            self.heater_password_tile.refresh()
                            self._show("heater_password")
                        else:
                            self._show("heater_disconnected")
                        return
                    # else: gave up waiting on either phase, fall through.
            self._manual_reconnect = None
            self._manual_reconnect_password_wait_start_ms = None
            # Falls through to the steady-state logic below.

        if not self._setup_done:
            # One-time gate, evaluated only until it resolves -- see this
            # module's own docstring. AirCon first, then heater (its own
            # extra password phase handled right after) -- order is
            # arbitrary (neither blocks the other's own timeout) but fixed,
            # so setup always asks about the same device first.
            if not self._advance_device_setup("aircon"):
                return
            if not self._advance_device_setup("heater"):
                return
            hs = self.heater_client.state
            if hs.connected and hs.password_required:
                now = time.ticks_ms()
                if self._heater_password_wait_start_ms is None:
                    self._heater_password_wait_start_ms = now
                if (
                    time.ticks_diff(now, self._heater_password_wait_start_ms)
                    >= self._HEATER_PASSWORD_TIMEOUT_MS
                ):
                    # Given up -- see _HEATER_PASSWORD_TIMEOUT_MS's comment
                    # (deliberately NOT the same as skipping heater pairing
                    # outright -- offered again next boot).
                    pass
                else:
                    self.heater_password_tile.refresh()
                    self._show("heater_password")
                    return
            self._setup_done = True
            self._ever_connected = True

        # Steady state: Home is reachable as long as whatever the currently
        # selected mode needs (home.MODE_DEVICE) is connected -- "off"
        # needs neither and is always fine. If neither device is connected
        # at all, that's shown too even for a mode that needs neither (e.g.
        # "off" the moment setup finishes with both skipped/unreachable) --
        # see this module's own docstring.
        #
        # Exception: if the user is already looking at Info (whether via an
        # ordinary swipe, or via poll_input()'s aircon_disconnected/
        # heater_disconnected -> Info escape hatch), this gate is
        # deliberately NOT enforced -- Info's own device buttons
        # (request_reconnect()) are the whole point of sending them there,
        # and re-forcing a Disconnected screen on the very next tick would
        # undo that navigation before the user could ever use them.
        viewing_info = (
            self._screen == "home"
            and self.tileview.get_tile_active() is self.info_tile.tile
        )
        if not viewing_info:
            aircon_ok = self.client.state.connected
            heater_ok = self.heater_client.state.connected
            required = self._mode_device.get(self.home.current_mode())
            if required == "aircon" and not aircon_ok:
                self._show("aircon_disconnected")
                return
            if required == "heater" and not heater_ok:
                self._show("heater_disconnected")
                return
            if required == "heater" and heater_ok and self.heater_client.state.password_required:
                # Only reachable post-setup via heater_ble.HeaterClient.
                # _schedule_verify() -- the connection itself never drops
                # (see heater_ok above), so unlike a real disconnect this
                # can only ever be noticed once the user is actually trying
                # to use heat/heat_auto (required == "heater") and a
                # command silently didn't take -- gated the same way as the
                # disconnected check just above, for the same "don't nag
                # about the heater while the dial's on an AC-only mode"
                # reasoning as this module's docstring, point 2.
                self.heater_password_tile.refresh()
                self._show("heater_password")
                return
            if not aircon_ok and not heater_ok:
                self._show(
                    "aircon_disconnected"
                )  # generic fallback -- see module docstring
                return

        self._show("home")
        self.home.refresh()
        self.settings_tile.refresh()
        self.info_tile.refresh()
        self.history_tile.refresh()
        self.temps_tile.refresh()


def build(client, heater_client, encoder, scr, checkpoint=lambda label: None):
    """Returns the App. `encoder` is the raw encoder.Encoder object from
    hal.hal_init_input() -- polled directly by App.poll_input()/
    HomeTile.handle_knob(), not wired through an lv.indev/group (see this
    module's own docstring for the interaction-model reasoning). `scr` is
    the active screen (lv.screen_active()), fetched by main.py.
    `checkpoint`, if given, is called (with a label) after each tile module
    is imported inside App.__init__ -- main.py passes its own _checkpoint()
    so the watchdog gets fed between them instead of only once before/after
    this whole call.
    """
    return App(client, heater_client, encoder, scr, checkpoint=checkpoint)
