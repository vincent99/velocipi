"""Settings: a knob-driven grid of BLE-backed tunables.

8 of the 9 settings the "settings" characteristic reports (see aircon-sim/
ble_server.py's SETTINGS_WIRE_KEYS for the full list and wire-key naming --
"brightness" is the one left out, since that's applied automatically
elsewhere instead of shown here, see screens/__init__.py's App.
_apply_brightness()), laid out as 4 rows of 2 settings each.

Entirely knob-driven, no touch needed at all -- see screens/__init__.py's
App.poll_input(), which dispatches the knob's delta/button-edge here the
same bare-button-press way it already does for Connect/Disconnected (this
tile isn't sharing screen space with anything that also wants a touch
point, unlike home.HomeTile's mode/recirc cells -- see
widgets._wire_button()'s docstring for why that one's different). Swiping
back to Home is a separate, touch-only mechanism (widgets._wire_swipe(),
wired up in App.__init__) that doesn't conflict with any of this.

Interaction model -- two states, toggled by the knob's push-button:
  - NAVIGATE (default): turning the knob moves which of the 8 cells is
    "selected" (theme.COLOR_HOVER background). A button press enters ACTIVE
    on that cell.
  - ACTIVE: turning the knob adjusts *that* cell's value locally, in
    _STEP increments -- not written over BLE yet (theme.COLOR_ACTIVE
    background instead). A second button press commits the write and
    returns to NAVIGATE. Swiping away to Home mid-ACTIVE instead discards
    it -- see cancel_active(), wired up by App.__init__.
"""

import asyncio

import lvgl as lv

import theme
from .widgets import _label, _make_bare_tile, _transparent

# (wire key, label) pairs, in on-screen order -- consecutive pairs share a
# row, left cell first: (0,1) row0, (2,3) row1, (4,5) row2, (6,7) row3.
_FIELDS = (
    ("delta", "Delta"),
    ("temp_read", "Temp Rate"),
    ("auto_loop", "Auto Rate"),
    ("fan_change", "Fan Rate"),
    ("fan_med", "Med Delta"),
    ("fan_high", "High Delta"),
    ("set_min", "Min Temp"),
    ("set_max", "Max Temp"),
)

_STEP = 0.5  # value change per knob detent while ACTIVE

# Sized/positioned per specific feedback: not the full 240px of tile height,
# and vertically centered -- the round display's usable chord width narrows
# fast near the very top/bottom, so this deliberately stays clear of that
# and only uses the wider middle band instead.
_GRID_W = 240
_GRID_H = 180


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

        grid = _transparent(self.tile)
        grid.set_size(_GRID_W, _GRID_H)
        grid.center()
        grid.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        grid.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        # self._cells[i] = (cell_container, label_widget, value_widget)
        self._cells = []
        for row in range(4):
            row_box = _transparent(grid)
            row_box.set_size(lv.pct(100), lv.SIZE_CONTENT)
            row_box.set_flex_flow(lv.FLEX_FLOW.ROW)
            row_box.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
            self._cells.append(self._make_cell(row_box, row * 2, is_left=True))
            self._cells.append(self._make_cell(row_box, row * 2 + 1, is_left=False))

    def _make_cell(self, parent, index, is_left):
        """One (label, value) pair, value on top and label below it --
        side-by-side "label value"/"value label" rows got the label text
        cut off, not enough horizontal room in a 48%-wide cell for both.
        Stacked vertically instead, both columns identical (is_left no
        longer changes anything here, kept only so callers don't need to
        care) -- a small amount of padding, both around the cell and
        between the two labels, keeps adjacent cells from crowding
        together.
        """
        _, label_text = _FIELDS[index]
        cell = _transparent(parent)
        cell.set_size(lv.pct(48), lv.SIZE_CONTENT)
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
            # No upper bound (not asked for) -- floored at 0 since none of
            # these settings (deltas, thresholds, intervals-in-seconds,
            # setpoint bounds) make sense negative, matching the
            # controllers' own server-side validation (e.g.
            # ../aircon-sim/controller.py's set_settings(), "delta"'s
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
            wire_key, _ = _FIELDS[self._active_idx]
            sv = self.client.state.settings.get(wire_key)
            self._pending_value = sv["value"] if sv else 0.0
        else:
            wire_key, _ = _FIELDS[self._active_idx]
            asyncio.create_task(self.client.set_setting(wire_key, self._pending_value))
            self._active_idx = None

    def cancel_active(self):
        """Discards any in-progress ACTIVE edit without writing anything --
        called by App when the user swipes away to Home mid-edit (see
        App.__init__'s _wire_tile_swipe(..., on_leave=...) for this tile)
        and defensively from App._show() if "home" is left entirely (e.g.
        a BLE disconnect mid-edit). A no-op if not currently ACTIVE.
        """
        self._active_idx = None

    # ── Refresh ───────────────────────────────────────────────────────────

    def refresh(self):
        s = self.client.state
        for i, (wire_key, _label_text) in enumerate(_FIELDS):
            cell, _label_widget, value_widget = self._cells[i]
            sv = s.settings.get(wire_key)

            if i == self._active_idx:
                v = self._pending_value
            elif sv:
                v = sv["value"]
            else:
                v = None
            value_widget.set_text("%.1f" % v if v is not None else "--")

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
