"""Home: the main screen. An outer knob-driven dial gauge rings a 3-row
grid -- current temp, mode/recirc buttons, setpoint/fan-speed -- inset in a
circle to match the round panel. See screens/__init__.py's module
docstring for the panel-wide interaction model.
"""

import asyncio

import lvgl as lv

import theme
from .widgets import _cycle, _fmt_temp, _label, _make_bare_tile, _make_button_cell, _row, _set_visible, _transparent, _wire_button

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

        # Circular inset holding the 3-row grid, sized to sit just inside
        # the gauge's track.
        inset = 236 - 2 * self._ARC_WIDTH - theme.SPACE_MD
        self.grid = _transparent(self.tile)
        self.grid.set_size(inset, inset)
        self.grid.center()
        self.grid.set_style_radius(inset // 2, 0)
        self.grid.set_style_clip_corner(True, 0)
        self.grid.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.grid.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        row1 = _transparent(self.grid)
        row1.set_size(lv.pct(100), lv.pct(33))
        self.current_temp_label = _label(row1, font=theme.FONT_DISPLAY, color=theme.COLOR_TEXT)
        self.current_temp_label.center()

        row2 = _row(self.grid)
        row2.set_height(lv.pct(33))
        self.mode_cell = _make_button_cell(row2)
        self.mode_label = _label(self.mode_cell)
        self.recirc_cell = _make_button_cell(row2)
        self.recirc_label = _label(self.recirc_cell)
        _wire_button(self.mode_cell, encoder, self._cycle_mode)
        _wire_button(self.recirc_cell, encoder, self._cycle_circ)

        self.row3 = _row(self.grid)
        self.row3.set_height(lv.pct(34))
        self.setpoint_label = _label(self.row3, font=theme.FONT_DISPLAY, color=theme.COLOR_TEXT)
        self.fan_label = _label(self.row3, font=theme.FONT_DISPLAY, color=theme.COLOR_TEXT)

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

        icon = _MODE_ICON.get(s.mode, "")
        name = _MODE_TEXT.get(s.mode, s.mode or "--")
        if s.mode in ("fan", "cool") and s.fan:
            self.mode_label.set_text("%s %s %s" % (icon, name, s.fan.capitalize()))
        else:
            self.mode_label.set_text("%s %s" % (icon, name))

        circ_icon = _CIRC_ICON.get(s.circulation, "")
        circ_name = _CIRC_TEXT.get(s.circulation, s.circulation or "--")
        self.recirc_label.set_text("%s %s" % (circ_icon, circ_name))

        _set_visible(self.setpoint_label, s.mode == "auto")
        if s.mode == "auto":
            self.setpoint_label.set_text("%.0f\xc2\xb0F" % s.setpoint if s.setpoint else "--")

        if s.mode == "off":
            self.fan_label.set_text("Off")
        else:
            self.fan_label.set_text(s.fan.capitalize() if s.fan else "--")

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
