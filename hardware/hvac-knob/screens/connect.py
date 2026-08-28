"""Connect: lets the user pick which physical device (AirCon controller or
heater) to connect to. See screens/__init__.py's module docstring for how
this fits into the overall screen flow and interaction model.

Generalized from an AirCon-only screen to work for either device kind --
screens/__init__.py's App now owns two independent instances of this class
(aircon_connect_tile/heater_connect_tile), differing only in which client
they drive, what label they show, and whether skipping is offered (the
heater is optional and non-blocking, see App's module docstring; the
AirCon is not, and keeps its exact original mandatory-picker behavior).
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
    """Lets the user pick which physical device to connect to -- shown
    full-screen in place of the tileview (see screens/__init__.py's
    App._show()).

    Purely knob-driven, unlike home.HomeTile's mode/recirc cells: turning
    the knob moves the highlighted device in the list, pressing the button
    selects it (edge-detected in App.poll_input(), not through LVGL touch
    events) -- this screen isn't sharing space with any swipe gesture, so
    there's no touch/swipe ambiguity here to resolve the way
    widgets._wire_button() does for Home.

    Until a real match turns up, this shows a spinner + "N other devices
    found" instead of a roller with an unselectable "(none found)" entry --
    see _apply_results(). Exception: when allow_skip is set, the roller
    (with just its skip entry) shows immediately instead of waiting on the
    spinner -- an optional device shouldn't force the user to sit through a
    scan just to say "I don't have one".
    """

    _SCAN_MS = 4000
    _SCAN_GAP_MS = 300  # brief pause between back-to-back scan passes

    def __init__(self, client, scr, *, label, scan_fn, allow_skip=False, on_skip=None):
        """`client` is whichever *Client this drives (AirconClient or
        HeaterClient) -- only used for its set_device_name(), everything
        else goes through the explicitly-passed `scan_fn` (client.
        scan_for_aircons or client.scan_for_heaters) so this class never
        has to know which kind of client it has. `label` is the device
        kind shown in the title/status text ("AirCon"/"Heater").
        `allow_skip`, if set, prepends a "Skip -- No <label>" entry to the
        roller that calls `on_skip()` instead of client.set_device_name()
        when selected -- used for the heater (optional) but not the AirCon
        (mandatory, unchanged from this screen's original behavior).
        """
        self.client = client
        self.label = label
        self._scan_fn = scan_fn
        self._allow_skip = allow_skip
        self._on_skip = on_skip
        self.screen = _make_screen(scr)

        _label(self.screen, "Connect %s" % label, font=theme.FONT_TITLE)

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

        self._results = []  # [(name, aioble.Device), ...], see *Client.scan_for_*()
        self._active = False  # True while this is the shown screen -- see on_show()/on_hide()

    def _option_labels(self):
        options = []
        if self._allow_skip:
            options.append("Skip -- No %s" % self.label)
        options += [name for name, _dev in self._results]
        return options

    def _option_count(self):
        return len(self._results) + (1 if self._allow_skip else 0)

    def on_show(self):
        """Called by App._show() every time this becomes the active
        screen -- starts (or restarts) a repeating scan that keeps running
        for as long as this screen stays up, so devices that power on or
        wander into range after this screen was shown still turn up
        without the user having to back out and back in again.
        """
        self._active = True
        self._results = []
        _set_visible(self.spinner, not self._allow_skip)
        _set_visible(self.roller, self._allow_skip)
        if self._allow_skip:
            self.roller.set_options("\n".join(self._option_labels()), _ROLLER_MODE_NORMAL)
            self.roller.set_selected(0, _ANIM_OFF)
        self.status_label.set_text("Scanning for %s..." % self.label)
        asyncio.create_task(self._scan_loop())

    def on_hide(self):
        """Called by App._show() when navigating away from this screen --
        stops _scan_loop() rather than leaving it running (and holding
        ble_shared.radio_lock) in the background indefinitely.
        """
        self._active = False

    async def _scan_loop(self):
        while self._active:
            try:
                new_results, other_count = await self._scan_fn(self._SCAN_MS)
            except Exception as e:
                print("screens.connect: scan failed:", e)
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
        if self._results or self._allow_skip:
            _set_visible(self.spinner, False)
            _set_visible(self.roller, True)
            # Keep whatever's currently highlighted in range rather than
            # resetting to the top of the list every pass.
            idx = min(self.roller.get_selected(), self._option_count() - 1)
            self.roller.set_options("\n".join(self._option_labels()), _ROLLER_MODE_NORMAL)
            self.roller.set_selected(max(idx, 0), _ANIM_OFF)
            if self._results:
                self.status_label.set_text("")
            elif other_count:
                self.status_label.set_text(
                    "%d other device%s found" % (other_count, "" if other_count == 1 else "s")
                )
            else:
                self.status_label.set_text("Scanning for %s..." % self.label)
        else:
            _set_visible(self.spinner, True)
            _set_visible(self.roller, False)
            if other_count:
                self.status_label.set_text(
                    "%d other device%s found" % (other_count, "" if other_count == 1 else "s")
                )
            else:
                self.status_label.set_text("Scanning for %s..." % self.label)

    def handle_knob(self, delta):
        if not delta:
            return
        count = self._option_count()
        if not count:
            return
        idx = min(max(self.roller.get_selected() + delta, 0), count - 1)
        self.roller.set_selected(idx, _ANIM_OFF)

    def select_current(self):
        count = self._option_count()
        if not count:
            return
        idx = self.roller.get_selected()
        if self._allow_skip:
            if idx == 0:
                if self._on_skip:
                    self._on_skip()
                return
            idx -= 1
        if idx >= len(self._results):
            return
        name, _dev = self._results[idx]
        self.client.set_device_name(name)
