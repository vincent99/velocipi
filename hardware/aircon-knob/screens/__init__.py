"""The panel's screens package. `App` (this module) owns which full-screen
"screen" is currently showing and dispatches knob input to it; each
screen's own widgets/logic live in their own module -- home.py (the main
screen), connect.py, disconnected.py -- with LVGL widget-construction
helpers shared across them factored into widgets.py.

Interaction model (deliberately different from a typical LVGL encoder+group
setup -- see ../hal.py's _init_encoder() docstring for why):
  - Turning the knob adjusts whichever control is "current" on the active
    screen (fan speed/power on the main screen when mode is off/fan/cool,
    setpoint when mode is auto) -- see home.HomeTile.handle_knob(). It does
    nothing on the History/Settings/Temps placeholders, and moves the
    highlighted device on Connect -- see connect.ConnectTile.handle_knob().
  - A touch tap alone never triggers anything by itself.
  - A "click" on Home's mode/recirc cells requires a touch point on that
    cell *and* the knob's push-button, since on this hardware pressing down
    on the screen is what mechanically presses the encoder's button -- see
    widgets._wire_button(). Connect and Disconnected are simpler: a bare
    knob push (edge-detected in App.poll_input(), no touch needed) is
    enough, since neither shares panel space with a swipe gesture.
  - Swipes (no push needed) navigate between Home/History/Settings/Temps --
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
`lvgl.pyi` stub the firmware build / MicroPico's "Configure project" step
produces -- see ../README.md. ../check_lvgl_api.py exercises the LVGL API
surface these modules add (lv.SYMBOL.*, arc.set_bg_angles, obj
add/remove_flag, tileview.get_tile_active, lv.line/lv.point_t, etc.) -- run
that before main.py on a fresh setup.

Relative imports (`from .widgets import ...` etc.) are used throughout this
package -- already exercised in practice by aioble's own source (a
dependency of this project, structured the same way), so this isn't a new,
unverified assumption about this MicroPython build's import support.
"""

import lvgl as lv

import hal
import theme
from .connect import ConnectTile
from .disconnected import DisconnectedTile
from .home import HomeTile
from .widgets import _make_placeholder_tile, _set_visible, _wire_swipe


class App:
    # Minimum drag distance (pixels) for a swipe to register -- "half the
    # screen height/width", not LVGL's own much smaller built-in gesture
    # limit (irrelevant now regardless, since tileview's touch-scrolling is
    # disabled below in favor of this project's own _wire_swipe()).
    _SWIPE_THRESHOLD_Y = hal.HEIGHT // 2
    _SWIPE_THRESHOLD_X = hal.WIDTH // 2

    def __init__(self, client, encoder, scr, display):
        self.client = client
        self.encoder = encoder
        self.display = display
        # Tracks the last brightness percentage actually applied, so
        # refresh() (called every ~250ms regardless of whether anything
        # changed) only calls hal.set_brightness() when the BLE settings
        # value itself changes, not every single cycle.
        self._last_brightness = None

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
        # Settings below, Temps to the left. Only placeholders for
        # History/Settings/Temps for now. dir_=NONE on every tile (not
        # DIR.TOP/BOTTOM/LEFT) -- on its own (see comment above) this
        # doesn't stop drag-scrolling, but it's still correct to leave in
        # place: it stops a completed swipe gesture from ever being treated
        # as a valid snap-to-adjacent-tile target, belt-and-suspenders
        # alongside removing SCROLLABLE. Each tile's *actual* swipe-out
        # directions are declared via _wire_tile_swipe()'s `allowed`
        # argument below instead.
        #
        # Grid position (not gesture direction) is what's inverted from an
        # earlier version of this layout: History used to sit *below* Home
        # with an up-to-down gesture reaching it, which read backwards on
        # real hardware -- swiping down-to-up felt like it should reveal
        # whatever's below, the way dragging a page down reveals content
        # further down it (same convention as this file's on_swipe()
        # comment describes). Moving History above/Settings below/Temps
        # left keeps on_swipe()'s dx/dy-to-row/col arithmetic completely
        # literal (up really does mean row-1, no separate inversion layer
        # to keep track of) while still landing on the gesture feel that
        # was actually wanted.
        self.home = HomeTile(client, encoder, self.tileview)
        history_tile = _make_placeholder_tile(self.tileview, 1, 0, lv.DIR.NONE, "History")
        settings_tile = _make_placeholder_tile(self.tileview, 1, 2, lv.DIR.NONE, "Settings")
        temps_tile = _make_placeholder_tile(self.tileview, 0, 1, lv.DIR.NONE, "Temps")

        # Directions here are the finger's actual motion (see
        # _classify_swipe()) and on_swipe() below applies them completely
        # literally (up subtracts from row, left subtracts from col, etc.)
        # -- from Home: down-to-up reaches History (now above), up-to-down
        # reaches Settings (now below), right-to-left reaches Temps (now to
        # the left). Each placeholder's own entry is simply the reverse
        # gesture, back to Home.
        self._wire_tile_swipe(self.home.tile, 1, 1, ("up", "down", "left"))
        self._wire_tile_swipe(history_tile, 1, 0, ("down",))
        self._wire_tile_swipe(settings_tile, 1, 2, ("up",))
        self._wire_tile_swipe(temps_tile, 0, 1, ("right",))

        # A tileview's initial scroll position is grid cell (0,0) regardless
        # of whether any tile was actually added there -- our + shaped grid
        # has nothing at (0,0) (Home is at (1,1)), so without this it opens
        # on an empty cell with no tile to swipe *from* (no dir_ bitmask
        # applies to a nonexistent tile), which is exactly the "have to
        # swipe around to find the main screen" bug this fixes.
        self.tileview.set_tile_by_index(1, 1, False)

        # Connect/Disconnected are full-screen siblings of the tileview,
        # shown/hidden in its place -- see _show(). Not part of the
        # swipeable grid at all.
        self.connect_tile = ConnectTile(client, scr)
        self.disconnected_tile = DisconnectedTile(scr)

        self._screen = None  # "home" | "connect" | "disconnected" -- see _show()
        self._btn_prev = False  # for edge-detecting the knob's push-button in poll_input()
        self._ever_connected = False  # set True the first time refresh() sees client.state.connected

        if client.device_name:
            # A device is already picked -- show Disconnected ("Connecting…")
            # until the client's own reconnect loop
            # (aircon_ble.AirconClient.run()) gets it hooked up; refresh()
            # flips to Home once client.state.connected is True.
            self._show("disconnected")
        else:
            self._show("connect")

    def _show(self, name):
        if self._screen == name:
            return
        prev = self._screen
        self._screen = name
        _set_visible(self.tileview, name == "home")
        _set_visible(self.connect_tile.screen, name == "connect")
        _set_visible(self.disconnected_tile.screen, name == "disconnected")
        if prev == "connect":
            # Stops ConnectTile's background scan loop rather than leaving
            # it running (and holding aircon_ble._scan_lock) after
            # navigating away -- see ConnectTile.on_hide().
            self.connect_tile.on_hide()
        if name == "connect":
            self.connect_tile.on_show()
        elif name == "disconnected":
            self.disconnected_tile.on_show(self._ever_connected)

    def _wire_tile_swipe(self, tile, col, row, allowed):
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
        it on a placeholder screen doesn't build up a jump that applies all
        at once after swiping back to the main screen.

        The knob's push-button is edge-detected here (fires once per
        physical press, not once per poll while held) for the Connect and
        Disconnected screens -- unlike home.HomeTile's mode/recirc cells,
        which need a touch point together with the button (see
        widgets._wire_button()), these two screens aren't sharing space
        with a swipe gesture, so a bare button push is enough.
        """
        delta = self.encoder.read_delta()
        pressed = self.encoder.button_pressed()
        btn_edge = pressed and not self._btn_prev
        self._btn_prev = pressed

        if self._screen == "home" and self.tileview.get_tile_active() is self.home.tile:
            # self._screen == "home" only means the tileview (not Connect/
            # Disconnected) is the visible top-level screen -- still need
            # this to check *which* tile within it is active, since the
            # knob should do nothing on History/Settings/Temps.
            self.home.handle_knob(delta)
        elif self._screen == "connect":
            self.connect_tile.handle_knob(delta)
            if btn_edge:
                self.connect_tile.select_current()
        elif self._screen == "disconnected":
            if btn_edge:
                self._show("connect")

    def refresh(self):
        s = self.client.state
        self._apply_brightness(s)
        if s.connected:
            self._ever_connected = True
            self._show("home")
            self.home.refresh()
        elif self._screen == "home":
            # Connection dropped while Home was showing.
            self._show("disconnected")

    def _apply_brightness(self, s):
        """Follows the AC controller's BLE "brightness" setting (0-100,
        see hardware/aircon-sim/ble_server.py's SETTINGS_WIRE_KEYS) live --
        no-ops until that characteristic's been read at least once (state
        .settings starts empty), and persists across a brief disconnect
        since state.settings isn't cleared on disconnect, only a full
        reconnect re-reads it.
        """
        sv = s.settings.get("brightness")
        if not sv:
            return
        pct = sv["value"]
        if pct == self._last_brightness:
            return
        self._last_brightness = pct
        hal.set_brightness(self.display, pct)


def build(client, encoder, scr, display):
    """Returns the App. `encoder` is the raw encoder.Encoder object from
    hal.hal_init_input() -- polled directly by App.poll_input()/
    HomeTile.handle_knob(), not wired through an lv.indev/group (see
    ../hal.py's _init_encoder() docstring for why). `scr` is the active
    screen (lv.screen_active()), and `display` the object hal.hal_init_
    display() returned (used to follow the BLE "brightness" setting --
    see App._apply_brightness()), both fetched by main.py.
    """
    return App(client, encoder, scr, display)
