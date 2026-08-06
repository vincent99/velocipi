"""Home: the main screen. An outer knob-driven dial gauge rings a 3-row
grid -- current temp, mode/recirc buttons, setpoint/fan-speed -- inset in a
circle to match the round panel. See screens/__init__.py's module
docstring for the panel-wide interaction model.
"""

import asyncio

import lvgl as lv

import theme
from .widgets import _column, _cycle, _fmt_temp, _label, _make_bare_tile, _make_button_cell, _row, _set_visible, _transparent, _wire_button

MODES = ("off", "fan", "auto", "cool")
CIRCS = ("recirc", "fresh")

# The knob's combined power/fan-speed dial when mode is off/fan/cool -- one
# ordered scale from fully counterclockwise (off) to fully clockwise (high).
# See HomeTile.handle_knob().
POWER_STATES = ("off", "low", "medium", "high")

# Fallback setpoint bounds, used only until the controller's BLE settings
# characteristic (which now reports setpoint_min/setpoint_max -- see
# ../../aircon/config.py's DEFAULT_SETPOINT_MIN/MAX) has been read at least
# once. Matches those same compiled-in defaults.
_DEFAULT_SETPOINT_MIN = 60.0
_DEFAULT_SETPOINT_MAX = 80.0

# Placeholder icon+text pairings -- lv.SYMBOL.* are LVGL's built-in glyphs
# (baked into its default font, usable directly inside any label's text), so
# these don't need any new binary asset. Swap for real icons whenever
# they're available; nothing else about the mode/recirc cells depends on
# the specific glyphs chosen here.
_MODE_ICON = {
    "off": lv.SYMBOL.POWER,
    "fan": lv.SYMBOL.REFRESH,
    "auto": lv.SYMBOL.LOOP,
    "cool": lv.SYMBOL.TINT,
}
_MODE_TEXT = {"off": "Off", "fan": "Fan", "auto": "Auto", "cool": "Cool"}
_CIRC_ICON = {"recirc": lv.SYMBOL.LOOP, "fresh": lv.SYMBOL.REFRESH}
_CIRC_TEXT = {"recirc": "Recirc", "fresh": "Fresh"}
# str.capitalize() isn't in MicroPython's built-in str type, so fan names
# (POWER_STATES, minus "off" which has its own label above) get their own
# display-text lookup rather than title-casing at render time.
_FAN_TEXT = {"low": "Low", "medium": "Medium", "high": "High"}


class HomeTile:
    """The main screen: an outer dial gauge (knob-driven) ringing a 3-row
    grid -- current temp, mode/recirc buttons, setpoint/fan-speed -- inset
    in a circle to match the round panel. See screens/__init__.py's module
    docstring for the interaction model.
    """

    # bg_angles(120, 60): LVGL angles run clockwise from 3 o'clock, so this
    # draws the gauge from 120 degrees clockwise all the way around to 60
    # degrees (the long way -- a 300 degree sweep), leaving a 60 degree gap
    # centered at the bottom (90 degrees) of the circle -- "most of the way
    # around", like a round speedometer's flat bottom gap.
    _GAUGE_START_ANGLE = 120
    _GAUGE_END_ANGLE = 60
    _ARC_WIDTH = 20  # thicker than an unstyled default arc

    def __init__(self, client, encoder, tileview):
        self.client = client
        self.encoder = encoder
        # Enabled swipe-out directions: down to History, up to Settings,
        # right to Temps (see screens/__init__.py's App.__init__() grid
        # layout for where those tiles sit relative to this one).
        self.tile = _make_bare_tile(tileview, 1, 1, lv.DIR.TOP | lv.DIR.BOTTOM | lv.DIR.RIGHT)

        self.arc = lv.arc(self.tile)
        self.arc.set_size(236, 236)
        self.arc.center()
        self.arc.set_bg_angles(self._GAUGE_START_ANGLE, self._GAUGE_END_ANGLE)
        self.arc.set_style_arc_width(self._ARC_WIDTH, lv.PART.MAIN)
        self.arc.set_style_arc_width(self._ARC_WIDTH, lv.PART.INDICATOR)
        self.arc.set_style_arc_color(theme.COLOR_TRACK, lv.PART.MAIN)
        self.arc.set_style_arc_color(theme.COLOR_ACCENT, lv.PART.INDICATOR)
        # Display-only gauge -- value comes from the knob (handle_knob),
        # not from touch-dragging the arc's default draggable knob, and the
        # arc shouldn't intercept the swipe gestures that navigate tiles.
        self.arc.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.arc.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.KNOB)
        self.arc.set_style_border_width(0, lv.PART.KNOB)

        # Circular inset holding current-temp + the mode/recirc buttons,
        # sized to sit just inside the gauge's track. Only 2 rows now --
        # row3 (fan/setpoint) moved out to be positioned against self.tile
        # directly, below.
        inset = 236 - 2 * self._ARC_WIDTH - theme.SPACE_MD
        self.grid = _transparent(self.tile)
        self.grid.set_size(inset, inset)
        self.grid.center()
        self.grid.set_style_radius(inset // 2, 0)
        self.grid.set_style_clip_corner(True, 0)
        self.grid.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.grid.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        self.grid.set_style_pad_row(theme.SPACE_MD, 0)

        # SIZE_CONTENT, not a fixed lv.pct() height, for both this and row2
        # below -- the button restyle's two-line (icon + label) cells need
        # more room than an even 3-way split of the inset gave them, so
        # rows now size to fit their actual content instead.
        row1 = _transparent(self.grid)
        row1.set_size(lv.pct(100), lv.SIZE_CONTENT)
        self.current_temp_label = _label(row1, font=theme.FONT_TITLE, color=theme.COLOR_TEXT)
        self.current_temp_label.center()

        row2 = _row(self.grid)
        self.mode_cell = _make_button_cell(row2)
        self.mode_icon_label = _label(self.mode_cell, font=theme.FONT_BUTTON_ICON)
        self.mode_text_label = _label(self.mode_cell, font=theme.FONT_BUTTON_LABEL)
        self.recirc_cell = _make_button_cell(row2)
        self.recirc_icon_label = _label(self.recirc_cell, font=theme.FONT_BUTTON_ICON)
        self.recirc_text_label = _label(self.recirc_cell, font=theme.FONT_BUTTON_LABEL)
        _wire_button(self.mode_cell, encoder, self._cycle_mode)
        _wire_button(self.recirc_cell, encoder, self._cycle_circ)

        # Fan speed above setpoint (setpoint only shown in auto mode -- see
        # refresh()'s _set_visible call below), anchored to the very bottom
        # of the tile rather than living inside the circular `grid` above --
        # deliberately outside/independent of that inset's own height
        # budget so it can sit lower on the screen. Fine for it to overlap
        # the gauge arc down there: HomeTile's bg_angles leaves a 60-degree
        # gap centered at the bottom (see _GAUGE_START_ANGLE/_GAUGE_END_
        # ANGLE above) where the arc draws nothing at all.
        self.row3 = _column(self.tile)
        self.fan_label = _label(self.row3, font=theme.FONT_TITLE, color=theme.COLOR_TEXT)
        self.setpoint_label = _label(self.row3, font=theme.FONT_TITLE, color=theme.COLOR_TEXT)
        # NOT hardware-verified: obj.align()/lv.ALIGN.BOTTOM_MID follow this
        # binding's usual naming convention and lv_obj_center() (used
        # elsewhere in this file, confirmed working) is itself just a thin
        # wrapper around lv_obj_align() in upstream LVGL, but this is the
        # first direct use of .align() in this codebase -- see
        # check_lvgl_api.py.
        self.row3.align(lv.ALIGN.BOTTOM_MID, 0, -theme.SPACE_SM)

    # ── Button-cell actions ──────────────────────────────────────────────

    def _cycle_mode(self):
        s = self.client.state
        asyncio.create_task(self.client.set_mode(_cycle(MODES, s.mode, 1)))

    def _cycle_circ(self):
        s = self.client.state
        asyncio.create_task(self.client.set_circulation(_cycle(CIRCS, s.circulation, 1)))

    # ── Knob ──────────────────────────────────────────────────────────────

    def _setpoint_min(self):
        sv = self.client.state.settings.get("setpoint_min")
        return sv["value"] if sv else _DEFAULT_SETPOINT_MIN

    def _setpoint_max(self):
        sv = self.client.state.settings.get("setpoint_max")
        return sv["value"] if sv else _DEFAULT_SETPOINT_MAX

    def handle_knob(self, delta):
        """Called with the encoder's accumulated detent delta since the
        last poll, only while this is the active tile (see
        screens/__init__.py's App.poll_input()).
        """
        if not delta:
            return
        s = self.client.state

        if s.mode == "auto":
            lo, hi = self._setpoint_min(), self._setpoint_max()
            target = min(max(s.setpoint + delta, lo), hi)
            asyncio.create_task(self.client.set_setpoint(target))
            return

        # off/fan/cool share one combined dial: off (fully counterclockwise)
        # through low/medium/high (clockwise), not wrapping at either end.
        if s.mode == "off":
            idx = 0
        elif s.fan in POWER_STATES:
            idx = POWER_STATES.index(s.fan)
        else:
            idx = 1  # unknown/unset fan value -- default into "low"
        idx = min(max(idx + delta, 0), len(POWER_STATES) - 1)

        if idx == 0:
            asyncio.create_task(self.client.set_mode("off"))
        else:
            # Turning up from "off" needs *some* mode to land in; keep the
            # current one if it's already fan/cool, else default to fan.
            target_mode = s.mode if s.mode in ("fan", "cool") else "fan"
            asyncio.create_task(self.client.set_mode(target_mode))
            asyncio.create_task(self.client.set_fan(POWER_STATES[idx]))

    # ── Refresh ───────────────────────────────────────────────────────────

    def refresh(self):
        s = self.client.state

        self.current_temp_label.set_text(_fmt_temp(s.current_temp))

        self.mode_icon_label.set_text(_MODE_ICON.get(s.mode, ""))
        name = _MODE_TEXT.get(s.mode, s.mode or "--")
        if s.mode in ("fan", "cool") and s.fan:
            self.mode_text_label.set_text("%s %s" % (name, _FAN_TEXT.get(s.fan, s.fan)))
        else:
            self.mode_text_label.set_text(name)

        self.recirc_icon_label.set_text(_CIRC_ICON.get(s.circulation, ""))
        self.recirc_text_label.set_text(_CIRC_TEXT.get(s.circulation, s.circulation or "--"))

        _set_visible(self.setpoint_label, s.mode == "auto")
        if s.mode == "auto":
            # See widgets._fmt_temp for why this is "\xb0" and not
            # "\xc2\xb0". No "F" suffix here (unlike _fmt_temp) -- setpoint
            # is shown bare, e.g. "72°".
            self.setpoint_label.set_text("%.0f\xb0" % s.setpoint if s.setpoint else "--")

        if s.mode == "off":
            self.fan_label.set_text("Off")
        else:
            self.fan_label.set_text(_FAN_TEXT.get(s.fan, "--") if s.fan else "--")

        # Gauge range/value: fan/cool/off share the 0..len(POWER_STATES)-1
        # power dial; auto reads its range from the controller's BLE
        # settings (setpoint_min/setpoint_max).
        if s.mode == "auto":
            lo, hi = self._setpoint_min(), self._setpoint_max()
            self.arc.set_range(int(lo), int(hi))
            self.arc.set_value(int(s.setpoint))
        else:
            self.arc.set_range(0, len(POWER_STATES) - 1)
            if s.mode == "off":
                idx = 0
            elif s.fan in POWER_STATES:
                idx = POWER_STATES.index(s.fan)
            else:
                idx = 0
            self.arc.set_value(idx)

        if s.compressor == "on":
            self.row3.set_style_bg_opa(lv.OPA.COVER, 0)
            self.row3.set_style_bg_color(theme.COLOR_COMPRESSOR_ON, 0)
        else:
            self.row3.set_style_bg_opa(lv.OPA.TRANSP, 0)
