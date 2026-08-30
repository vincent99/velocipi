"""Settings: a knob-driven grid of tunables -- 8 BLE-backed ones the
AirCon controller's "settings" characteristic reports (see ../hvac-sim/
ble_server.py's AC_SETTINGS_WIRE_KEYS for the full list and wire-key naming)
plus one purely local one, the panel's own neopixel status-LED brightness
(hal.get/set_led_brightness_pct(), persisted via panel_settings.get/
set_led_brightness_pct() -- independent of the LCD backlight's own
brightness, which the Pi drives instead, see hal.py's own
set_led_brightness_pct() comment).

Laid out as 5 rows of 1/2/3/2/1 fields (see _ROWS) rather than a uniform
grid -- chosen to roughly match the round panel's own available width at
each row's vertical position: the single-field rows sit at the top/bottom,
where the circle's chord is narrowest, and the widest (3-field) row sits in
the middle, where it's widest.

Entirely knob-driven, no touch needed at all -- see screens/__init__.py's
App.poll_input(), which dispatches the knob's delta/button-edge here the
same bare-button-press way it already does for Connect/Disconnected (this
tile isn't sharing screen space with anything that also wants a touch
point, unlike home.HomeTile's mode/recirc cells -- see
widgets._wire_button()'s docstring for why that one's different). Swiping
back to Home is a separate, touch-only mechanism (widgets._wire_swipe(),
wired up in App.__init__) that doesn't conflict with any of this.

Interaction model -- two states, toggled by the knob's push-button:
  - NAVIGATE (default): turning the knob moves which of the 9 cells is
    "selected" (theme.COLOR_HOVER background). A button press enters ACTIVE
    on that cell.
  - ACTIVE: turning the knob adjusts *that* cell's value locally, in
    _STEP increments (_LED_STEP for the LEDs field) -- not written/applied
    yet (theme.COLOR_ACTIVE background instead). A second button press
    commits it (over BLE for the 8 wire fields, or straight to hal.py +
    panel_settings.py for LEDs) and returns to NAVIGATE. Swiping away to
    Home mid-ACTIVE instead discards it -- see cancel_active(), wired up
    by App.__init__.
"""

import asyncio

import lvgl as lv

import hal
import panel_settings
import theme
from .widgets import _label, _make_bare_tile, _transparent

# (wire key, label, unit) triples, in on-screen order -- see _ROWS for how
# these are grouped into rows. wire_key is None for the one local field
# (LEDs), handled separately everywhere below (a local hal.py/
# panel_settings.py round trip instead of a BLE write, a different step
# size, an implicit 0-100 range rather than "no upper bound", and integer
# whole-percent formatting rather than one decimal place + unit suffix).
#
# unit is appended directly to the formatted number with no space (e.g.
# "72.0°", "5.0s") -- "°" for a temperature or a temperature *delta* alike
# (this dial only ever moves in Fahrenheit elsewhere in this app too, see
# home.py's _fmt_temp), "s" for anything that's a wire *_interval under the
# hood, i.e. a duration in seconds (confirmed against ../hvac-sim/
# ac_controller.py's use of each as an asyncio.sleep()/now-comparison bound,
# not just guessed from the "Rate" label).
_FIELDS = (
    ("delta", "Delta", "\xb0"),
    ("fan_med", "Med Delta", "\xb0"),
    ("fan_high", "High Delta", "\xb0"),
    ("temp_read", "Temp Rate", "s"),
    ("auto_loop", "Auto Rate", "s"),
    ("fan_change", "Fan Rate", "s"),
    ("set_min", "Min Temp", "\xb0"),
    ("set_max", "Max Temp", "\xb0"),
    (None, "LEDs", "%"),
)

# How many consecutive _FIELDS entries share each row, top to bottom --
# must sum to len(_FIELDS). See this module's own docstring for why this
# particular 1/2/3/2/1 shape (not a uniform grid) was chosen.
_ROWS = (1, 2, 3, 2, 1)

# Each row's cell width, keyed by how many fields are in it -- narrower
# per-cell for a more crowded row, same overall look (a handful of percent
# of the row's own width left over for flex's SPACE_EVENLY gaps) as the
# original fixed 2-per-row/48%-per-cell layout this replaced.
_ROW_CELL_WIDTH_PCT = {1: 60, 2: 46, 3: 30}

_STEP = 0.5  # value change per knob detent while ACTIVE, wire fields
_LED_STEP = 10  # value change per knob detent while ACTIVE, LEDs field only


class SettingsTile:
    def __init__(self, client, encoder, tileview):
        self.client = client
        self.encoder = encoder
        # (1, 2): matches App.__init__'s grid layout -- Settings sits below
        # Home, reached by an up-to-down swipe gesture from there.
        self.tile = _make_bare_tile(tileview, 1, 2, lv.DIR.NONE)

        self._selected = 0  # index into _FIELDS -- which cell NAVIGATE is on
        self._active_idx = None  # index into _FIELDS, or None if not ACTIVE
        self._pending_value = 0.0  # local, uncommitted value while ACTIVE

        # Full tile size, not a smaller centered box inset from it (an
        # earlier version left a deliberate margin, sized/positioned per
        # specific feedback back when this was a 4-row grid -- with the
        # LEDs row added on top of that, 5 rows in that same shrunk box
        # read as too cramped; SPACE_EVENLY below still keeps every row
        # off the tile's own bare edges, so this doesn't run fields right
        # up against the round bezel, just reclaims the margin that used
        # to sit *outside* that spacing as more room to space rows out
        # with).
        grid = _transparent(self.tile)
        grid.set_size(lv.pct(100), lv.pct(100))
        grid.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        grid.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        # self._cells[i] = (cell_container, label_widget, value_widget)
        self._cells = []
        index = 0
        for count in _ROWS:
            row_box = _transparent(grid)
            row_box.set_size(lv.pct(100), lv.SIZE_CONTENT)
            row_box.set_flex_flow(lv.FLEX_FLOW.ROW)
            row_box.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
            width_pct = _ROW_CELL_WIDTH_PCT[count]
            for _ in range(count):
                self._cells.append(self._make_cell(row_box, index, width_pct))
                index += 1

    def _make_cell(self, parent, index, width_pct):
        """One (label, value) pair, value on top and label below it --
        side-by-side "label value"/"value label" rows got the label text
        cut off, not enough horizontal room in a narrow cell for both.
        Stacked vertically instead -- a small amount of padding, both
        around the cell and between the two labels, keeps adjacent cells
        from crowding together.
        """
        _wire_key, label_text, _unit = _FIELDS[index]
        cell = _transparent(parent)
        cell.set_size(lv.pct(width_pct), lv.SIZE_CONTENT)
        cell.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        cell.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        cell.set_style_pad_row(0, 0)
        cell.set_style_pad_all(0, 0)
        cell.set_style_radius(theme.RADIUS, 0)
        cell.set_style_clip_corner(False, 0)
        value = _label(cell, font=theme.FONT_TITLE, color=theme.COLOR_TEXT)
        label = _label(cell, text=label_text, font=theme.FONT_BODY, color=theme.COLOR_TEXT_MUTED)
        return cell, label, value

    # ── Knob ──────────────────────────────────────────────────────────────

    def handle_knob(self, delta):
        """Called with the encoder's accumulated detent delta since the
        last poll, only while this is the active tile (see
        screens/__init__.py's App.poll_input()).
        """
        if not delta:
            return
        if self._active_idx is not None:
            wire_key, _label_text, _unit = _FIELDS[self._active_idx]
            if wire_key is None:
                # LEDs: a real 0-100% range (both ends meaningful -- 0 is
                # "off", not just "as dim as this goes"), not the
                # floored-at-0-only/no-upper-bound shape the wire fields
                # below have.
                self._pending_value = min(max(self._pending_value + delta * _LED_STEP, 0), 100)
            else:
                # No upper bound (not asked for) -- floored at 0 since none
                # of these settings (deltas, thresholds, intervals-in-
                # seconds, setpoint bounds) make sense negative, matching
                # the controllers' own server-side validation (e.g.
                # ../hvac-sim/ac_controller.py's set_settings(), "delta"'s
                # `if v >= 0`).
                self._pending_value = max(0.0, self._pending_value + delta * _STEP)
        else:
            self._selected = (self._selected + delta) % len(_FIELDS)

    def handle_button(self):
        """Called on the knob push-button's rising edge (see
        screens/__init__.py's App.poll_input()) while this is the active
        tile -- toggles NAVIGATE/ACTIVE, per this module's own docstring.
        """
        if self._active_idx is None:
            self._active_idx = self._selected
            wire_key, _label_text, _unit = _FIELDS[self._active_idx]
            if wire_key is None:
                self._pending_value = float(hal.get_led_brightness_pct())
            else:
                sv = self.client.state.settings.get(wire_key)
                self._pending_value = sv["value"] if sv else 0.0
        else:
            wire_key, _label_text, _unit = _FIELDS[self._active_idx]
            if wire_key is None:
                pct = int(round(self._pending_value))
                hal.set_led_brightness_pct(pct)
                panel_settings.set_led_brightness_pct(pct)
            else:
                asyncio.create_task(self.client.set_setting(wire_key, self._pending_value))
            self._active_idx = None

    def cancel_active(self):
        """Discards any in-progress ACTIVE edit without writing anything --
        called by App when the user swipes away to Home mid-edit (see
        App.__init__'s _wire_tile_swipe(..., on_leave=...) for this tile)
        and defensively from App._show() if "home" is left entirely (e.g.
        a BLE disconnect mid-edit). A no-op if not currently ACTIVE. Safe
        for the LEDs field too -- unlike the wire fields, LEDs is applied
        to hal.py/panel_settings.py immediately on commit (handle_button()
        above), not queued as an async BLE write, so there's nothing
        in-flight to also cancel here.
        """
        self._active_idx = None

    # ── Refresh ───────────────────────────────────────────────────────────

    def refresh(self):
        s = self.client.state
        for i, (wire_key, _label_text, unit) in enumerate(_FIELDS):
            cell, _label_widget, value_widget = self._cells[i]

            if wire_key is None:
                v = self._pending_value if i == self._active_idx else float(hal.get_led_brightness_pct())
                value_widget.set_text("%.0f%%" % v)
                modified = v != 100.0
            else:
                sv = s.settings.get(wire_key)
                if i == self._active_idx:
                    v = self._pending_value
                elif sv:
                    v = sv["value"]
                else:
                    v = None
                value_widget.set_text(("%.1f" + unit) % v if v is not None else "--")
                default = sv["default"] if sv else None
                modified = v is not None and default is not None and v != default

            value_widget.set_style_text_color(theme.COLOR_MODIFIED if modified else theme.COLOR_TEXT, 0)

            if i == self._active_idx:
                cell.set_style_bg_opa(lv.OPA.COVER, 0)
                cell.set_style_bg_color(theme.COLOR_ACTIVE, 0)
            elif i == self._selected:
                cell.set_style_bg_opa(lv.OPA.COVER, 0)
                cell.set_style_bg_color(theme.COLOR_HOVER, 0)
            else:
                cell.set_style_bg_opa(lv.OPA.TRANSP, 0)
