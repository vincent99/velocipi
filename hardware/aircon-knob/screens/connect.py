"""Connect: lets the user pick which physical AirCon controller to connect
to. See screens/__init__.py's module docstring for how this fits into the
overall screen flow and interaction model.
"""

import asyncio

import lvgl as lv

import theme
from .widgets import _label, _make_screen, _set_visible

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

    Until a real AirCon match turns up, this shows a spinner + "N other
    devices found" instead of a roller with an unselectable "(none found)"
    entry -- see _apply_results().
    """

    _SCAN_MS = 4000
    _SCAN_GAP_MS = 300  # brief pause between back-to-back scan passes

    def __init__(self, client, scr):
        self.client = client
        self.screen = _make_screen(scr)

        _label(self.screen, "Connect", font=theme.FONT_TITLE)

        self.spinner = lv.spinner(self.screen)
        self.spinner.set_size(48, 48)
        self.spinner.set_style_arc_color(theme.COLOR_ACCENT, lv.PART.INDICATOR)

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
        self._active = False  # True while this is the shown screen -- see on_show()/on_hide()

    def on_show(self):
        """Called by App._show() every time this becomes the active
        screen -- starts (or restarts) a repeating scan that keeps running
        for as long as this screen stays up, so devices that power on or
        wander into range after this screen was shown still turn up
        without the user having to back out and back in again.
        """
        self._active = True
        self._results = []
        _set_visible(self.spinner, True)
        _set_visible(self.roller, False)
        self.status_label.set_text("Scanning for AirCon...")
        asyncio.create_task(self._scan_loop())

    def on_hide(self):
        """Called by App._show() when navigating away from this screen --
        stops _scan_loop() rather than leaving it running (and holding
        aircon_ble._scan_lock) in the background indefinitely.
        """
        self._active = False

    async def _scan_loop(self):
        while self._active:
            try:
                new_results, other_count = await self.client.scan_for_aircons(self._SCAN_MS)
            except Exception as e:
                print("screens.connect: scan_for_aircons failed:", e)
                new_results, other_count = [], 0
            if not self._active:
                return  # navigated away mid-scan
            self._merge_results(new_results)
            self._apply_results(other_count)
            await asyncio.sleep_ms(self._SCAN_GAP_MS)

    def _merge_results(self, new_results):
        """Folds a fresh scan pass into the running list -- previously seen
        devices stay put (by name) rather than the list flashing empty and
        rebuilding every pass, so the highlighted selection doesn't jump
        around while the user is looking at it.
        """
        by_name = dict(self._results)
        by_name.update(new_results)
        self._results = sorted(by_name.items())

    def _apply_results(self, other_count):
        if self._results:
            _set_visible(self.spinner, False)
            _set_visible(self.roller, True)
            # Keep whatever's currently highlighted in range rather than
            # resetting to the top of the list every pass.
            idx = min(self.roller.get_selected(), len(self._results) - 1)
            self.roller.set_options("\n".join(name for name, _dev in self._results), _ROLLER_MODE_NORMAL)
            self.roller.set_selected(idx, _ANIM_OFF)
            self.status_label.set_text("")
        else:
            _set_visible(self.spinner, True)
            _set_visible(self.roller, False)
            if other_count:
                self.status_label.set_text(
                    "%d other device%s found" % (other_count, "" if other_count == 1 else "s")
                )
            else:
                self.status_label.set_text("Scanning for AirCon...")

    def handle_knob(self, delta):
        if not delta or not self._results:
            return
        idx = min(max(self.roller.get_selected() + delta, 0), len(self._results) - 1)
        self.roller.set_selected(idx, _ANIM_OFF)

    def select_current(self):
        if not self._results:
            return
        name, _dev = self._results[self.roller.get_selected()]
        self.client.set_device_name(name)
