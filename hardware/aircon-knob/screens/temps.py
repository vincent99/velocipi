"""Temps: a static grid of every temperature reading in client.state --
current/panel/cabin/blower/exhaust/baggage/tail. Reached by swiping right
from Home, swipe left to return -- see screens/__init__.py's App.__init__
for the grid layout.

No knob or touch interaction at all (see App.poll_input(), which does
nothing while this tile is active, same as the Info tile) -- purely a
read-out, styled like screens/settings.py's cells (value above label) minus
all the NAVIGATE/ACTIVE selection state that page needs and this one
doesn't.
"""

import lvgl as lv

import theme
from .widgets import _fmt_temp, _label, _make_bare_tile, _transparent

# (AirconState attribute name, label) pairs, in on-screen order -- 2/row,
# Current left alone on its own final row (see __init__'s loop below) since
# it's the one overall summary reading, the other six are individual sensor
# placements (matches aircon_ble.py's AirconState fields and Go's
# aircon.TempSample, minus OAT -- server-injected from Axis on the Pi side,
# never reaches the knob at all, so there's nothing to show here for it).
_FIELDS = (
    ("cabin_temp", "Cabin"),
    ("panel_temp", "Panel"),
    ("blower_temp", "Blower"),
    ("exhaust_temp", "Exhaust"),
    ("baggage_temp", "Baggage"),
    ("tail_temp", "Tail"),
    ("current_temp", "Current"),
)

# Same sizing rationale as settings.py's _GRID_W/_GRID_H -- clear of the
# round bezel's narrower top/bottom band. Taller than Settings' (180) since
# 7 fields at 2/row need 4 rows, not Settings' 4.
_GRID_W = 240
_GRID_H = 220


class TempsTile:
    def __init__(self, client, tileview):
        self.client = client
        # (0, 1): matches App.__init__'s grid layout -- Temps sits to the
        # left of Home, reached by a right-to-left swipe from there.
        self.tile = _make_bare_tile(tileview, 0, 1, lv.DIR.NONE)

        grid = _transparent(self.tile)
        grid.set_size(_GRID_W, _GRID_H)
        grid.center()
        grid.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        grid.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        # self._values[i] = (AirconState attribute name, value label widget)
        self._values = []
        for i in range(0, len(_FIELDS), 2):
            row_box = _transparent(grid)
            row_box.set_size(lv.pct(100), lv.SIZE_CONTENT)
            row_box.set_flex_flow(lv.FLEX_FLOW.ROW)
            row_box.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
            for attr, label_text in _FIELDS[i : i + 2]:
                self._values.append((attr, self._make_cell(row_box, label_text)))

    def _make_cell(self, parent, label_text):
        """One (value, label) pair, value on top -- see settings.py's
        _make_cell(), which this mirrors minus the selection styling
        (nothing here is ever selected/active).
        """
        cell = _transparent(parent)
        cell.set_size(lv.pct(48), lv.SIZE_CONTENT)
        cell.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        cell.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        cell.set_style_pad_row(0, 0)
        cell.set_style_pad_all(0, 0)
        value = _label(cell, font=theme.FONT_TITLE, color=theme.COLOR_TEXT)
        _label(cell, text=label_text, font=theme.FONT_BODY, color=theme.COLOR_TEXT_MUTED)
        return value

    def refresh(self):
        s = self.client.state
        for attr, value_widget in self._values:
            value_widget.set_text(_fmt_temp(getattr(s, attr)))
