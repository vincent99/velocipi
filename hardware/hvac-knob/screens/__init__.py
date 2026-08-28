"""The panel's screens package. `App` (this module) owns which full-screen
"screen" is currently showing and dispatches knob input to it; each
screen's own widgets/logic live in their own module -- home.py (the main
screen), connect.py, disconnected.py -- with LVGL widget-construction
helpers shared across them factored into widgets.py.

Two BLE devices, two different gates: `client` (AirconClient) is mandatory
-- exactly the original single-device behavior, Home is unreachable without
one connected, full stop. `heater_client` (HeaterClient) is optional and
asked about exactly once: the first time Home would otherwise become
reachable (i.e. right after the AirCon connects), App shows
heater_connect_tile so the user can either pick a heater or explicitly skip
("Skip -- No Heater", see screens.ConnectTile's allow_skip) -- once that
one-time decision is made (persisted via panel_settings.get/
set_heater_skipped()), it's never asked again, and Home becomes reachable
regardless of whether the heater stays connected afterward (a heater
dropping later just means "heat" mode / auto mode's heating branch quietly
do nothing -- see home.HomeTile -- not a full-screen blocker the way an
AirCon drop is). See App.refresh()'s _heater_setup_done handling for
exactly how this sequences, including the give-up timeout for a picked-but-
now-permanently-absent heater.

A picked heater can additionally require a password (see heater_ble.py's
module docstring, point 3, for how that's detected -- it's a heuristic, not
a certainty) -- if so, App shows heater_password_tile
(screens.heater_password.HeaterPasswordTile) in the same one-time setup
sequence, right after the heater connects and before Home. Unlike the
Connect screen's explicit "Skip -- No Heater" entry, giving up here is a
timeout (App._HEATER_PASSWORD_TIMEOUT_MS) rather than a dedicated control
on the screen itself, and deliberately does NOT persist via
panel_settings.set_heater_skipped() -- see that function's own docstring
for why "don't have the PIN handy this boot" is treated as temporary
rather than a permanent opt-out.

Interaction model (deliberately different from a typical LVGL encoder+group
setup, which moves focus between widgets -- there's no "focused widget"
concept here at all, just a single fixed "current" control per screen):
  - Turning the knob adjusts whichever control is "current" on the active
    screen (fan speed/power on the main screen when mode is off/fan/cool,
    setpoint when mode is auto) -- see home.HomeTile.handle_knob(). It cycles
    which tunable is selected (or adjusts it, mid-edit) on the Settings tile
    -- see settings.SettingsTile -- scrubs the graph's cursor on History --
    see history.HistoryTile.handle_knob() -- does nothing on Temps or Info
    (both are plain read-outs), and moves the highlighted device on
    Connect -- see connect.ConnectTile.handle_knob().
  - A touch tap alone never triggers anything by itself.
  - A "click" on Home's mode/recirc cells requires a touch point on that
    cell *and* the knob's push-button, since on this hardware pressing down
    on the screen is what mechanically presses the encoder's button -- see
    widgets._wire_button(). Connect and Disconnected are simpler: a bare
    knob push (edge-detected in App.poll_input(), no touch needed) is
    enough, since neither shares panel space with a swipe gesture.
  - Swipes (no push needed) navigate between Home/History/Settings/Temps/Info --
    not the tileview's own built-in scrolling/gesture engine (disabled
    entirely by removing its SCROLLABLE flag, see App.__init__: it was
    stealing drags away from Home's mode/recirc buttons, its sliding-snap
    animation felt laggy, and even with per-tile dir_=NONE it still
    rubber-banded under a touch-drag), but App._wire_tile_swipe()'s own
    press/release distance tracking -- a drag has to clear
    App._SWIPE_THRESHOLD_* (half the screen height/width) before it jumps
    straight to the target tile, with no transition animation at all.

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

import lvgl as lv

import hal
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

    # How long to wait for a *previously-picked* heater's first connection
    # of this boot (including its handshake resolving out of "unknown" --
    # see heater_ble.py's HeaterState.password_required -- which normally
    # takes a few seconds at most, well inside this) before giving up and
    # showing Home anyway -- see refresh()'s _heater_setup_done handling.
    # Without this, a heater that was paired once but is now permanently
    # gone (removed, dead battery) would wedge the panel on
    # heater_disconnected forever, exactly the "heater must never be a
    # hard blocker" property this whole two-gate design is supposed to
    # guarantee. HeaterClient.run() keeps retrying in the background
    # regardless of this timeout -- if it does eventually reconnect,
    # state.connected flips true and heat/auto mode start working live,
    # same as any other later drop-and-reconnect.
    _HEATER_CONNECT_TIMEOUT_MS = 15000

    # Separate, much longer timeout for the password screen specifically
    # (see heater_password_tile) -- entering a 4-digit PIN one knob-turn-
    # and-tap at a time is an active, deliberate user task, not a passive
    # wait for hardware, so it gets a generous allowance instead of
    # _HEATER_CONNECT_TIMEOUT_MS's 15s. Same "never a hard blocker"
    # guarantee either way: past this, Home becomes reachable regardless,
    # and the password screen will be offered again next boot (this
    # give-up is deliberately NOT persisted via panel_settings.
    # set_heater_skipped() -- see that function's own docstring).
    _HEATER_PASSWORD_TIMEOUT_MS = 90000

    def __init__(self, client, heater_client, encoder, scr, checkpoint=lambda label: None):
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
        from .home import HomeTile

        checkpoint("screens: imported home")
        self.home = HomeTile(client, heater_client, encoder, self.tileview)

        from .settings import SettingsTile

        checkpoint("screens: imported settings")
        self.settings_tile = SettingsTile(client, encoder, self.tileview)

        from .info import InfoTile

        checkpoint("screens: imported info")
        self.info_tile = InfoTile(client, heater_client, encoder, self.tileview, self.request_reconnect)

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
        # SettingsTile.cancel_active()'s docstring.
        self._wire_tile_swipe(self.home.tile, 1, 1, ("up", "down", "left", "right"))
        self._wire_tile_swipe(self.history_tile.tile, 1, 0, ("down",))
        self._wire_tile_swipe(
            self.settings_tile.tile, 1, 2, ("up",), on_leave=self.settings_tile.cancel_active
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
        # swipeable grid at all. One pair per device kind -- see this
        # module's own docstring for why the heater's pair behaves
        # differently (optional, skippable, asked once) from the AirCon's
        # (mandatory, unchanged from this screen's original single-device
        # behavior).
        from .connect import ConnectTile

        checkpoint("screens: imported connect")
        self.aircon_connect_tile = ConnectTile(
            client, scr, label="AirCon", scan_fn=client.scan_for_aircons
        )
        self.heater_connect_tile = ConnectTile(
            heater_client,
            scr,
            label="Heater",
            scan_fn=heater_client.scan_for_heaters,
            allow_skip=True,
            on_skip=self._skip_heater,
        )

        from .disconnected import DisconnectedTile

        checkpoint("screens: imported disconnected")
        self.aircon_disconnected_tile = DisconnectedTile(scr)
        self.heater_disconnected_tile = DisconnectedTile(scr, label="Heater")

        from .heater_password import HeaterPasswordTile

        checkpoint("screens: imported heater_password")
        self.heater_password_tile = HeaterPasswordTile(heater_client, scr)

        # "home" | "aircon_connect" | "aircon_disconnected" |
        # "heater_connect" | "heater_disconnected" | "heater_password" --
        # see _show().
        self._screen = None
        self._btn_prev = False  # for edge-detecting the knob's push-button in poll_input()
        self._ever_connected = False  # set True the first time refresh() sees client.state.connected
        self._heater_setup_done = False  # set True once the heater's been picked-and-connected(-and-authenticated), skipped, or timed out -- see refresh()
        self._heater_connect_wait_start_ms = None  # ticks_ms() of when _HEATER_CONNECT_TIMEOUT_MS's wait started, or None -- see refresh()
        self._heater_password_wait_start_ms = None  # ticks_ms() of when _HEATER_PASSWORD_TIMEOUT_MS's wait started, or None -- see refresh()
        # "aircon" | "heater" | None -- set by request_reconnect() (called
        # from info.InfoTile's device buttons), see that method and
        # refresh()'s own handling of it for the full flow.
        self._manual_reconnect = None
        # device_name the relevant client had at the moment
        # request_reconnect() was called -- refresh() compares against
        # this (not state.connected) to tell "nothing picked yet, stay on
        # the picker" apart from "a new device_name showed up, now watch
        # for it to connect". Deliberately NOT keyed off state.connected
        # alone: a heater that's never been paired at all has
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

        if client.device_name:
            # A device is already picked -- show Disconnected ("Connecting…")
            # until the client's own reconnect loop
            # (aircon_ble.AirconClient.run()) gets it hooked up; refresh()
            # flips to Home once client.state.connected is True.
            self._show("aircon_disconnected")
        else:
            self._show("aircon_connect")

    def _skip_heater(self):
        """heater_connect_tile's on_skip callback -- the user explicitly
        chose "no heater" rather than picking one. Persisted so this is
        never asked again; refresh() picks the change up on its very next
        tick (no need to force a screen change here directly -- it's
        already showing heater_connect, and refresh() re-evaluates
        _heater_setup_done every tick regardless).

        Also reachable mid-manual-reconnect (request_reconnect("heater"),
        via info.InfoTile's Heater button) -- refresh()'s manual-reconnect
        handling only ever resolves by watching heater_client.state.
        connected, which skipping doesn't change at all (there may not
        even be a device_name to connect to), so it's cleared here
        directly instead of leaving that branch waiting on a connection
        that's never coming.
        """
        panel_settings.set_heater_skipped(True)
        if self._manual_reconnect == "heater":
            self._manual_reconnect = None
            self._heater_setup_done = True

    def request_reconnect(self, kind):
        """info.InfoTile's device buttons' click callback -- `kind` is
        "aircon" or "heater". Manually reopens that device's Connect
        screen so the user can pick a different one, even though initial
        setup is long since done. Suspends the normal automatic screen-
        selection gate in refresh() until it resolves -- see there for the
        full sequencing, and aircon_ble.AirconClient.set_device_name()/
        heater_ble.HeaterClient.set_device_name() for how picking a new
        device actually disconnects whatever was live before, which this
        whole flow depends on.

        For "heater", also clears panel_settings.get_heater_skipped() --
        opening this screen from Info is itself an explicit re-engagement
        with heater pairing, which should supersede an earlier "no
        heater" decision (the button is reachable, and makes sense to
        press, precisely *because* the user might want to reverse that
        decision -- see info.InfoTile's "Not configured" display for a
        skipped heater).
        """
        client = self.client if kind == "aircon" else self.heater_client
        self._manual_reconnect = kind
        self._manual_reconnect_prev_name = client.device_name
        self._manual_reconnect_dropped = False
        if kind == "heater":
            panel_settings.set_heater_skipped(False)
        self._show("%s_connect" % kind)

    def _show(self, name):
        if self._screen == name:
            return
        prev = self._screen
        self._screen = name
        _set_visible(self.tileview, name == "home")
        _set_visible(self.aircon_connect_tile.screen, name == "aircon_connect")
        _set_visible(self.aircon_disconnected_tile.screen, name == "aircon_disconnected")
        _set_visible(self.heater_connect_tile.screen, name == "heater_connect")
        _set_visible(self.heater_disconnected_tile.screen, name == "heater_disconnected")
        _set_visible(self.heater_password_tile.screen, name == "heater_password")
        if prev == "aircon_connect":
            # Stops ConnectTile's background scan loop rather than leaving
            # it running (and holding ble_shared.radio_lock) after
            # navigating away -- see ConnectTile.on_hide().
            self.aircon_connect_tile.on_hide()
        if prev == "heater_connect":
            self.heater_connect_tile.on_hide()
        if prev == "home":
            # Defensive backstop for the same reasoning as _wire_tile_swipe's
            # own on_leave=cancel_active wiring in __init__ (which handles
            # the ordinary swipe-away case) -- this covers leaving "home"
            # entirely some other way instead, e.g. a BLE disconnect while
            # mid-edit on Settings. A no-op if nothing was ACTIVE.
            self.settings_tile.cancel_active()
        if name == "aircon_connect":
            self.aircon_connect_tile.on_show()
        elif name == "aircon_disconnected":
            self.aircon_disconnected_tile.on_show(self._ever_connected)
        elif name == "heater_connect":
            self.heater_connect_tile.on_show()
        elif name == "heater_disconnected":
            # Always "Connecting…", never "Disconnected" -- this screen
            # only ever shows during the heater's first-ever connection
            # attempt of this boot (see refresh()'s _heater_setup_done
            # handling); once it's connected once, _heater_setup_done goes
            # True permanently and this screen is never shown again for any
            # later drop.
            self.heater_disconnected_tile.on_show(False)
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
        visible.
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
        Disconnected pairs alike) -- unlike home.HomeTile's mode/recirc
        cells, which need a touch point together with the button (see
        widgets._wire_button()), none of these share screen space with a
        swipe gesture in a way that'd make a bare button push ambiguous, so
        a bare push is enough for all of them.
        """
        delta = self.encoder.read_delta()
        pressed = self.encoder.button_pressed()
        btn_edge = pressed and not self._btn_prev
        self._btn_prev = pressed

        # self._screen == "home" only means the tileview (not Connect/
        # Disconnected, either device kind's) is the visible top-level
        # screen -- still need get_tile_active() to check *which* tile
        # within it is active, since the knob should do nothing on Temps/
        # Info (plain read-outs).
        active_tile = self.tileview.get_tile_active() if self._screen == "home" else None
        if active_tile is self.home.tile:
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
        elif self._screen == "aircon_disconnected":
            if btn_edge:
                self._show("aircon_connect")
        elif self._screen == "heater_connect":
            self.heater_connect_tile.handle_knob(delta)
            if btn_edge:
                self.heater_connect_tile.select_current()
        elif self._screen == "heater_disconnected":
            if btn_edge:
                self._show("heater_connect")
        elif self._screen == "heater_password":
            self.heater_password_tile.handle_knob(delta)
            if btn_edge:
                self.heater_password_tile.select_current()

    def refresh(self):
        if self._manual_reconnect is not None:
            # info.InfoTile's device buttons triggered this (see
            # request_reconnect()) -- suspends the normal gate logic below
            # entirely until it resolves.
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
            self._manual_reconnect = None
            if kind == "heater":
                # A freshly-picked heater needs to go through the same
                # setup gate (below) a first-ever pick does, including its
                # own password check -- _heater_setup_done being True
                # already reflects the *previous* heater, not this one.
                self._heater_setup_done = False
                self._heater_connect_wait_start_ms = None
                self._heater_password_wait_start_ms = None
            # Falls through to the normal logic below, unconditionally --
            # for "aircon" that's immediately screens.App._show("home")
            # (nothing else gates on it); for "heater" it re-enters the
            # setup gate just reset above.

        s = self.client.state
        if not s.connected:
            if self._screen == "home":
                # Connection dropped while Home was showing.
                self._show("aircon_disconnected")
            return
        self._ever_connected = True

        if not self._heater_setup_done:
            # One-time gate, evaluated only until it resolves one way or
            # another -- see this module's own docstring. Structured as an
            # explicit if/elif/else chain (not a single "decided" boolean
            # the way an earlier version of this worked) now that there
            # are three sequential phases instead of two: pick a device,
            # wait for it to connect and its password handshake to resolve
            # (heater_ble.HeaterState.password_required going out of
            # None), then -- only if that came back True -- wait for a
            # correct password. Each phase has its own give-up timeout so
            # none of them can block Home forever.
            if panel_settings.get_heater_skipped():
                self._heater_setup_done = True
            elif not self.heater_client.device_name:
                self._show("heater_connect")
                return
            else:
                hs = self.heater_client.state
                now = time.ticks_ms()
                if not hs.connected or hs.password_required is None:
                    if self._heater_connect_wait_start_ms is None:
                        self._heater_connect_wait_start_ms = now
                    if time.ticks_diff(now, self._heater_connect_wait_start_ms) >= self._HEATER_CONNECT_TIMEOUT_MS:
                        # Given up -- see _HEATER_CONNECT_TIMEOUT_MS's
                        # comment. HeaterClient.run() is still retrying in
                        # the background regardless; this only stops it
                        # from blocking Home.
                        self._heater_setup_done = True
                    else:
                        self._show("heater_disconnected")
                        return
                elif hs.password_required:
                    if self._heater_password_wait_start_ms is None:
                        self._heater_password_wait_start_ms = now
                    if time.ticks_diff(now, self._heater_password_wait_start_ms) >= self._HEATER_PASSWORD_TIMEOUT_MS:
                        # Given up -- see _HEATER_PASSWORD_TIMEOUT_MS's
                        # comment (deliberately NOT the same as skipping
                        # heater pairing outright -- offered again next
                        # boot).
                        self._heater_setup_done = True
                    else:
                        self.heater_password_tile.refresh()
                        self._show("heater_password")
                        return
                else:
                    self._heater_setup_done = True

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
