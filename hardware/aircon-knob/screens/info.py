"""Info: static "about" screen -- app/controller identification plus
whatever error the controller last reported. Reached by swiping right from
Home, the mirror image of Temps (reached by swiping left) -- see
screens/__init__.py's App.__init__ for the grid layout.
"""

import lvgl as lv

import theme
from .widgets import _label, _make_bare_tile, _set_visible, _transparent

# "Just a constant somewhere" -- this screen is the only thing that reads
# it, so it lives here rather than in its own module. Bump by hand on
# release, independently of ../aircon/config.py's VERSION (that one's the
# AC controller's own firmware version, a separate piece of hardware this
# screen also reports -- see refresh()).
KNOB_VERSION = "1.0"


class InfoTile:
    def __init__(self, client, tileview):
        self.client = client
        # (2, 1): matches App.__init__'s grid layout -- Info sits to the
        # right of Home, the mirror of Temps at (0, 1).
        self.tile = _make_bare_tile(tileview, 2, 1, lv.DIR.NONE)

        col = _transparent(self.tile)
        col.set_size(lv.pct(100), lv.pct(100))
        col.set_style_pad_all(theme.SPACE_LG, 0)
        col.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        # main_place=START (not CENTER, used by widgets._make_tile's
        # placeholder screens): the error label below needs the title/
        # version lines packed at the top so its flex_grow(1) can actually
        # claim whatever's left of the tile underneath them, not share
        # space in a centered block with them. cross_place=CENTER is what
        # actually centers each line horizontally for a COLUMN flow --
        # confirmed on real hardware that leaving this at START (as an
        # earlier version of this file did) put every label flush against
        # the left edge of the round display instead.
        col.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        title = _label(col, "AirCon", font=theme.FONT_TITLE, color=theme.COLOR_TEXT)
        knob_version = _label(col, "Knob v%s" % KNOB_VERSION, font=theme.FONT_BUTTON_LABEL, color=theme.COLOR_TEXT_MUTED)
        self.controller_version_label = _label(col, font=theme.FONT_BUTTON_LABEL, color=theme.COLOR_TEXT_MUTED)

        # Hidden entirely while state.error is empty (see refresh()) --
        # flex_grow(1) only claims space while the label itself isn't
        # HIDDEN, so the title/version lines above just sit at the top with
        # nothing but blank tile below them when there's nothing to report.
        self.error_label = _label(col, font=theme.FONT_BODY, color=theme.COLOR_DANGER)
        self.error_label.set_width(lv.pct(100))
        # lv.label.LONG_MODE, not lv.LABEL_LONG_MODE -- this binding nests
        # the enum under the label widget class itself, confirmed via
        # lvgl.pyi (not guessed) after lv.LABEL_LONG_MODE crashed real
        # hardware.
        self.error_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.error_label.set_flex_grow(1)

        # Centered per line, not just as a block (the flex column's own
        # CENTER cross-align above only centers each label's bounding box) --
        # matters most for the error label, which wraps across several
        # lines at full tile width and would otherwise read ragged-left.
        for label in (title, knob_version, self.controller_version_label, self.error_label):
            label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    def refresh(self):
        s = self.client.state
        self.controller_version_label.set_text("Controller v%s" % (s.controller_version or "--"))

        _set_visible(self.error_label, bool(s.error))
        if s.error:
            # "Error" heading first, then the actual message -- the wire
            # value in state.error is just the bare message text, no label
            # of its own.
            self.error_label.set_text("Error\n%s" % s.error)
