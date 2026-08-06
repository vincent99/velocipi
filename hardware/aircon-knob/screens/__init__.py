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
  - Swipes (no push needed) navigate between Home/History/Settings/Temps
    via the tileview's built-in gesture handling.

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

import theme
from .connect import ConnectTile
from .disconnected import DisconnectedTile
from .home import HomeTile
from .widgets import _make_placeholder_tile, _set_visible


class App:
    def __init__(self, client, encoder, scr):
        self.client = client
        self.encoder = encoder

        self.tileview = lv.tileview(scr)
        self.tileview.set_size(lv.pct(100), lv.pct(100))
        self.tileview.set_style_bg_color(theme.COLOR_BG, 0)
        # Unlike widgets._transparent()'s containers, the tileview can't
        # just have its SCROLLABLE flag removed -- scrolling *is* the
        # swipe-between-tiles mechanism. set_scrollbar_mode(OFF) hides the
        # scrollbar indicator it draws during that scrolling without
        # touching the scrolling itself.
        self.tileview.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        # A + shaped grid around the main tile at (1,1): History below
        # (swipe down from main, swipe up from history to return), Settings
        # above (swipe up from main, swipe down from settings to return),
        # Temps to the right (swipe right from main, swipe left from temps
        # to return). Only placeholders for History/Settings/Temps for now.
        self.home = HomeTile(client, encoder, self.tileview)
        _make_placeholder_tile(self.tileview, 1, 2, lv.DIR.TOP, "History")
        _make_placeholder_tile(self.tileview, 1, 0, lv.DIR.BOTTOM, "Settings")
        _make_placeholder_tile(self.tileview, 2, 1, lv.DIR.LEFT, "Temps")

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
        if s.connected:
            self._ever_connected = True
            self._show("home")
            self.home.refresh()
        elif self._screen == "home":
            # Connection dropped while Home was showing.
            self._show("disconnected")


def build(client, encoder, scr):
    """Returns the App. `encoder` is the raw encoder.Encoder object from
    hal.hal_init_input() -- polled directly by App.poll_input()/
    HomeTile.handle_knob(), not wired through an lv.indev/group (see
    ../hal.py's _init_encoder() docstring for why). `scr` is the active
    screen (lv.screen_active()), fetched by main.py.
    """
    return App(client, encoder, scr)
