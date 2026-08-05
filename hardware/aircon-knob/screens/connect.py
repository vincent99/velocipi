"""Connect: lets the user pick which physical AirCon controller to connect
to. See screens/__init__.py's module docstring for how this fits into the
overall screen flow and interaction model.
"""

import asyncio

import lvgl as lv

import theme
from .widgets import _label, _make_screen

# lv.ANIM/lv.ROLLER_MODE don't exist as nested enum-group classes on this
# binding (see ../check_lvgl_api.py) -- both LV_ANIM_OFF and
# LV_ROLLER_MODE_NORMAL are long-standing 0 upstream, used directly here for
# the roller below.
_ANIM_OFF = 0
_ROLLER_MODE_NORMAL = 0


class ConnectTile:
    """Lets the user pick which physical AirCon controller to connect to --
    shown full-screen in place of the tileview (see
    screens/__init__.py's App._show()) on first boot (no device saved yet)
    or from the Disconnected screen's knob push.

    Purely knob-driven, unlike home.HomeTile's mode/recirc cells: turning
    the knob moves the highlighted device in the list, pressing the button
    selects it (edge-detected in App.poll_input(), not through LVGL touch
    events) -- this screen isn't sharing space with any swipe gesture, so
    there's no touch/swipe ambiguity here to resolve the way
    widgets._wire_button() does for Home.
    """

    _SCAN_MS = 4000

    def __init__(self, client, scr):
        self.client = client
        self.screen = _make_screen(scr)

        _label(self.screen, "Connect", font=theme.FONT_DISPLAY)
        self.status_label = _label(self.screen, "", color=theme.COLOR_TEXT_MUTED)

        self.roller = lv.roller(self.screen)
        self.roller.set_width(lv.pct(90))
        self.roller.set_visible_row_count(3)
        self.roller.set_style_text_font(theme.FONT_BODY, 0)
        # Driven directly by handle_knob()/select_current() below, not
        # LVGL's own touch-drag-to-scroll -- a stray tap could otherwise
        # move the roller out of step with what this class thinks is
        # selected.
        self.roller.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.roller.set_options("", _ROLLER_MODE_NORMAL)

        self._results = []  # [(name, aioble.Device), ...], see aircon_ble.AirconClient.scan_for_aircons
        self._scanning = False

    def on_show(self):
        """Called by App._show() every time this becomes the active
        screen -- (re)starts a scan so the list reflects what's actually in
        range right now, not whatever was found last time this was shown.
        """
        asyncio.create_task(self._scan())

    async def _scan(self):
        self._scanning = True
        self._results = []
        self.roller.set_options("Scanning...", _ROLLER_MODE_NORMAL)
        self.status_label.set_text("")
        try:
            self._results = await self.client.scan_for_aircons(self._SCAN_MS)
        except Exception as e:
            print("screens.connect: scan_for_aircons failed:", e)
        self._scanning = False
        if self._results:
            self.roller.set_options("\n".join(name for name, _dev in self._results), _ROLLER_MODE_NORMAL)
            self.roller.set_selected(0, _ANIM_OFF)
        else:
            self.roller.set_options("(none found)", _ROLLER_MODE_NORMAL)
            self.status_label.set_text("No AirCon devices found -- move closer and try again")

    def handle_knob(self, delta):
        if not delta or not self._results:
            return
        idx = min(max(self.roller.get_selected() + delta, 0), len(self._results) - 1)
        self.roller.set_selected(idx, _ANIM_OFF)

    def select_current(self):
        if self._scanning or not self._results:
            return
        name, _dev = self._results[self.roller.get_selected()]
        self.client.set_device_name(name)
