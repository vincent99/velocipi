"""Info: "about" screen -- app/controller identification, whatever error
the controller last reported, and (see the two device buttons below) which
AirCon controller and heater are configured and whether each is currently
connected. Reached by swiping right from Home, the mirror image of Temps
(reached by swiping left) -- see screens/__init__.py's App.__init__ for
the grid layout.
"""

import lvgl as lv

import theme
from .widgets import _label, _make_bare_tile, _make_button_cell, _set_visible, _transparent, _wire_button

# "Just a constant somewhere" -- this screen is the only thing that reads
# it, so it lives here rather than in its own module. Bump by hand on
# release, independently of ../aircon/config.py's VERSION (that one's the
# AC controller's own firmware version, a separate piece of hardware this
# screen also reports -- see refresh()).
KNOB_VERSION = "1.0"

_DEVICE_BUTTON_W = 200
_DEVICE_BUTTON_H = 64


class InfoTile:
    def __init__(self, client, heater_client, encoder, tileview, on_reconnect):
        self.client = client
        self.heater_client = heater_client
        # Called with "aircon" or "heater" when one of the device buttons
        # below is clicked -- screens/__init__.py's App.request_reconnect(),
        # threaded through as a plain callback rather than this tile
        # holding a reference to the whole App, matching how screens.
        # ConnectTile's on_skip already does the same thing for a
        # different button.
        self.on_reconnect = on_reconnect
        # (2, 1): matches App.__init__'s grid layout -- Info sits to the
        # right of Home, the mirror of Temps at (0, 1).
        self.tile = _make_bare_tile(tileview, 2, 1, lv.DIR.NONE)

        col = _transparent(self.tile)
        col.set_size(lv.pct(100), lv.pct(100))
        col.set_style_pad_all(theme.SPACE_LG, 0)
        col.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        # main_place=START (not CENTER, used by widgets._make_tile's other
        # caller, History): the error label below needs the title/
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

        # Two device buttons, AirCon then Heater -- see refresh() for what
        # each line shows; click handling is the same widgets._wire_button()
        # home.HomeTile's mode/recirc cells use (touch + knob-button, see
        # this screen's swipe-back-to-Home gesture -- a bare tap alone
        # would be ambiguous with that the same way it is on Home).
        # _make_button_cell() (also used by those same Home cells) already
        # gives these the same border/radius/touch-feedback styling, just
        # sized for 3 lines of text instead of an icon+label pair.
        self.aircon_cell = _make_button_cell(col, _DEVICE_BUTTON_W, _DEVICE_BUTTON_H)
        self.aircon_kind_label = _label(self.aircon_cell, "AirCon", font=theme.FONT_TINY, color=theme.COLOR_TEXT_MUTED)
        self.aircon_name_label = _label(self.aircon_cell, font=theme.FONT_BODY, color=theme.COLOR_TEXT)
        self.aircon_status_label = _label(self.aircon_cell, font=theme.FONT_TINY)
        _wire_button(self.aircon_cell, encoder, lambda: self.on_reconnect("aircon"))

        self.heater_cell = _make_button_cell(col, _DEVICE_BUTTON_W, _DEVICE_BUTTON_H)
        self.heater_kind_label = _label(self.heater_cell, "Heater", font=theme.FONT_TINY, color=theme.COLOR_TEXT_MUTED)
        self.heater_name_label = _label(self.heater_cell, font=theme.FONT_BODY, color=theme.COLOR_TEXT)
        self.heater_status_label = _label(self.heater_cell, font=theme.FONT_TINY)
        _wire_button(self.heater_cell, encoder, lambda: self.on_reconnect("heater"))

        # Hidden entirely while state.error is empty (see refresh()) --
        # flex_grow(1) only claims space while the label itself isn't
        # HIDDEN, so everything above just sits at the top with nothing
        # but blank tile below it when there's nothing to report.
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
        for label in (
            title,
            knob_version,
            self.controller_version_label,
            self.aircon_kind_label,
            self.aircon_name_label,
            self.aircon_status_label,
            self.heater_kind_label,
            self.heater_name_label,
            self.heater_status_label,
            self.error_label,
        ):
            label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

    def refresh(self):
        s = self.client.state
        self.controller_version_label.set_text("Controller v%s" % (s.controller_version or "--"))

        # AirCon is always configured by the time Home (and therefore
        # Info) is reachable at all -- screens/__init__.py's App gates
        # Home entirely on it -- so this is really only ever showing the
        # device's name and (in practice, almost always) "Connected"; see
        # that module's own docstring for why the heater's equivalent
        # varies far more in practice.
        self.aircon_name_label.set_text(self.client.device_name or "Not configured")
        if s.connected:
            self.aircon_status_label.set_text("Connected")
            self.aircon_status_label.set_style_text_color(theme.COLOR_TEXT, 0)
        else:
            self.aircon_status_label.set_text("Disconnected")
            self.aircon_status_label.set_style_text_color(theme.COLOR_DANGER, 0)

        hs = self.heater_client.state
        if self.heater_client.device_name:
            self.heater_name_label.set_text(self.heater_client.device_name)
            if hs.connected:
                self.heater_status_label.set_text("Connected")
                self.heater_status_label.set_style_text_color(theme.COLOR_TEXT, 0)
            else:
                self.heater_status_label.set_text("Disconnected")
                self.heater_status_label.set_style_text_color(theme.COLOR_DANGER, 0)
        else:
            # Either explicitly skipped (panel_settings.get_heater_skipped())
            # or App gave up waiting on it (screens/__init__.py's
            # _HEATER_CONNECT_TIMEOUT_MS/_HEATER_PASSWORD_TIMEOUT_MS) --
            # either way there's no device name to show, and neither
            # "Connected" nor "Disconnected" would be accurate.
            self.heater_name_label.set_text("Not configured")
            self.heater_status_label.set_text("")

        _set_visible(self.error_label, bool(s.error))
        if s.error:
            # "Error" heading first, then the actual message -- the wire
            # value in state.error is just the bare message text, no label
            # of its own.
            self.error_label.set_text("Error\n%s" % s.error)
