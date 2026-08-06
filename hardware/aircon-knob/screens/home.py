"""Home: the main screen. An outer knob-driven dial gauge rings three
manually-positioned elements -- current temp, mode/recirc buttons,
setpoint/fan-speed -- against the round panel. See screens/__init__.py's
module docstring for the panel-wide interaction model.
"""

import asyncio

import lvgl as lv

import theme
from .widgets import _column, _cycle, _fmt_temp, _label, _make_bare_tile, _make_button_cell, _set_visible, _transparent, _wire_button

MODES = ("off", "fan", "cool", "auto")
CIRCS = ("recirc", "fresh")

# The knob's fan-speed dial, used whenever mode is fan/cool (auto uses the
# setpoint instead, off isn't reachable via the knob at all -- turning it
# always implies "on"; the mode button is the only way to power off). See
# HomeTile.handle_knob().
POWER_STATES = ("low", "medium", "high")

# Fallback setpoint bounds, used only until the controller's BLE settings
# characteristic (which reports set_min/set_max -- see
# ../../aircon/config.py's DEFAULT_SETPOINT_MIN/MAX, currently 60/80) has
# been read at least once. Deliberately wide open (not those same compiled
# defaults) so an unread bound doesn't quietly clamp a real setpoint that
# turns out to sit outside 60-80.
_DEFAULT_SETPOINT_MIN = 0.0
_DEFAULT_SETPOINT_MAX = 100.0

# Placeholder icon+text pairings -- lv.SYMBOL.* are LVGL's built-in glyphs
# (baked into its default font, usable directly inside any label's text), so
# these don't need any new binary asset. Swap for real icons whenever
# they're available; nothing else about the mode/recirc cells depends on
# the specific glyphs chosen here.
_MODE_ICON = {
    "off": lv.SYMBOL.POWER,
    "fan": lv.SYMBOL.REFRESH,
    "cool": lv.SYMBOL.CHARGE,
    "auto": lv.SYMBOL.EYE_OPEN,
}
_MODE_TEXT = {"off": "Off", "fan": "Fan", "auto": "Auto", "cool": "Cool"}
_CIRC_ICON = {"recirc": lv.SYMBOL.REFRESH, "fresh": lv.SYMBOL.SHUFFLE}
_CIRC_TEXT = {"recirc": "Recirc", "fresh": "Fresh"}
# str.capitalize() isn't in MicroPython's built-in str type, so fan names
# (POWER_STATES) get their own display-text lookup rather than title-casing
# at render time.
_FAN_TEXT = {"low": "Low", "medium": "Medium", "high": "High"}


class HomeTile:
    """The main screen: an outer dial gauge (knob-driven) ringing three
    manually-positioned elements -- current temp, mode/recirc buttons,
    setpoint/fan-speed -- against the round panel. See
    screens/__init__.py's module docstring for the interaction model.
    """

    # bg_angles(120, 60): LVGL angles run clockwise from 3 o'clock, so this
    # draws the gauge from 120 degrees clockwise all the way around to 60
    # degrees (the long way -- a 300 degree sweep), leaving a 60 degree gap
    # centered at the bottom (90 degrees) of the circle -- "most of the way
    # around", like a round speedometer's flat bottom gap.
    _GAUGE_START_ANGLE = 120
    _GAUGE_END_ANGLE = 60
    _ARC_WIDTH = 20  # thicker than an unstyled default arc

    # Manual layout constants for everything except row3 (fan/setpoint,
    # left alone -- see __init__). No flex grid anymore: each element below
    # is sized/positioned directly with .align(CENTER, x, y) against
    # self.tile. Values are pixel deltas applied on top of an estimate of
    # this screen's earlier flex-computed layout, per specific feedback
    # after seeing it rendered on real hardware ("~20px higher", "~30px
    # higher/10px taller/20px wider") -- not independently re-derived, so
    # nudge these directly if they're off; there's no layout engine
    # computing them anymore.
    _TEMP_W = 240
    _TEMP_H = 56
    _TEMP_Y = -70
    _BUTTON_W = 100
    _BUTTON_H = 80
    _BUTTON_GAP = 10
    _BUTTON_Y = 5

    def __init__(self, client, encoder, tileview):
        self.client = client
        self.encoder = encoder
        # Enabled swipe-out directions: down to History, up to Settings,
        # right to Temps (see screens/__init__.py's App.__init__() grid
        # layout for where those tiles sit relative to this one).
        self.tile = _make_bare_tile(tileview, 1, 1, lv.DIR.TOP | lv.DIR.BOTTOM | lv.DIR.RIGHT)

        self.arc = lv.arc(self.tile)
        self.arc.set_size(236,236)
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

        # Current-temp cell: full tile width (see _TEMP_W's comment above),
        # manually centered on the tile with a fixed vertical offset. No
        # radius/clip styling needed -- it's a plain rectangle now, not
        # inset inside a circular mask, and the physical round bezel
        # already hides whatever corners fall outside the visible circle
        # regardless of what's drawn there (same assumption the arc/tile
        # already make elsewhere in this file). self.row1 (not a local var)
        # since refresh() also uses it as the compressor-on highlight
        # target -- see there.
        self.row1 = _transparent(self.tile)
        self.row1.set_size(self._TEMP_W, self._TEMP_H)
        self.row1.set_style_radius(0, 0)
        self.current_temp_label = _label(self.row1, font=theme.FONT_CURRENT_TEMP, color=theme.COLOR_TEXT)
        self.current_temp_label.center()
        self.row1.align(lv.ALIGN.CENTER, 0, self._TEMP_Y)

        # Mode/recirc buttons, side by side, symmetric about tile-center.
        button_x = self._BUTTON_W // 2 + self._BUTTON_GAP // 2
        self.mode_cell = _make_button_cell(self.tile, self._BUTTON_W, self._BUTTON_H)
        self.mode_icon_label = _label(self.mode_cell, font=theme.FONT_BUTTON_ICON)
        self.mode_text_label = _label(self.mode_cell, font=theme.FONT_BUTTON_LABEL)
        self.mode_cell.align(lv.ALIGN.CENTER, -button_x, self._BUTTON_Y)

        self.recirc_cell = _make_button_cell(self.tile, self._BUTTON_W, self._BUTTON_H)
        self.recirc_icon_label = _label(self.recirc_cell, font=theme.FONT_BUTTON_ICON)
        self.recirc_text_label = _label(self.recirc_cell, font=theme.FONT_BUTTON_LABEL)
        self.recirc_cell.align(lv.ALIGN.CENTER, button_x, self._BUTTON_Y)

        _wire_button(self.mode_cell, encoder, self._cycle_mode)
        _wire_button(self.recirc_cell, encoder, self._cycle_circ)

        # Fan speed above setpoint (setpoint only shown in auto mode -- see
        # refresh()'s _set_visible call below), anchored to the very bottom
        # of the tile. Left alone here -- good where it is, per feedback,
        # even after everything above it went from a flex grid to manual
        # positioning. Fine for it to overlap the gauge arc down there:
        # HomeTile's bg_angles leaves a 60-degree gap centered at the
        # bottom (see _GAUGE_START_ANGLE/_GAUGE_END_ANGLE above) where the
        # arc draws nothing at all.
        self.row3 = _column(self.tile)
        self.fan_label = _label(self.row3, font=theme.FONT_TITLE, color=theme.COLOR_TEXT)
        self.setpoint_label = _label(self.row3, font=theme.FONT_TITLE, color=theme.COLOR_TEXT)
        # NOT hardware-verified: obj.align()/lv.ALIGN.BOTTOM_MID follow this
        # binding's usual naming convention and lv_obj_center() (used
        # elsewhere in this file, confirmed working) is itself just a thin
        # wrapper around lv_obj_align() in upstream LVGL, but this is the
        # first direct use of .align() in this codebase -- see
        # check_lvgl_api.py.
        self.row3.align(lv.ALIGN.BOTTOM_MID, 0, 5)

        # Pushes the arc to the top of self.tile's paint order regardless of
        # creation order, so refresh()'s compressor-on fill on self.row1
        # renders underneath the arc's ring strokes instead of covering
        # them -- row1, added after the arc and now spanning the full tile
        # width, would otherwise paint right over it (the same problem
        # row3's fill used to have sitting over the arc's bottom gap,
        # before it got its own dedicated bottom position). The arc has no
        # CLICKABLE flag (see above), so this is purely visual -- doesn't
        # change touch hit-testing at all.
        # NOT hardware-verified: first use of move_foreground() in this
        # codebase -- see check_lvgl_api.py.
        self.arc.move_foreground()

    # ── Button-cell actions ──────────────────────────────────────────────

    def _cycle_mode(self):
        s = self.client.state
        asyncio.create_task(self.client.set_mode(_cycle(MODES, s.mode, 1)))

    def _cycle_circ(self):
        s = self.client.state
        asyncio.create_task(self.client.set_circulation(_cycle(CIRCS, s.circulation, 1)))

    # ── Knob ──────────────────────────────────────────────────────────────

    def _setpoint_min(self):
        # "set_min", not "setpoint_min" -- see aircon_ble.py's
        # _apply_settings_json() for the terse wire key names.
        sv = self.client.state.settings.get("set_min")
        return sv["value"] if sv else _DEFAULT_SETPOINT_MIN

    def _setpoint_max(self):
        sv = self.client.state.settings.get("set_max")
        return sv["value"] if sv else _DEFAULT_SETPOINT_MAX

    def handle_knob(self, delta):
        """Called with the encoder's accumulated detent delta since the
        last poll, only while this is the active tile (see
        screens/__init__.py's App.poll_input()).
        """
        if not delta:
            return
        s = self.client.state

        # Off is inert -- the knob does nothing at all (no mode change, no
        # fan change) while off, matching the arc being hidden entirely in
        # refresh() rather than showing some stale/meaningless dial value.
        # The mode button (see MODES/_cycle_mode) is the only way in or out
        # of off now.
        if s.mode == "off":
            return

        if s.mode == "auto":
            lo, hi = self._setpoint_min(), self._setpoint_max()
            target = min(max(s.setpoint + delta, lo), hi)
            asyncio.create_task(self.client.set_setpoint(target))
            return

        # Only fan/cool reach here (auto and off both returned above) --
        # fan-speed dial: low/medium/high, not wrapping at either end,
        # mode unchanged (no set_mode() call needed -- it's already
        # fan/cool).
        idx = POWER_STATES.index(s.fan) if s.fan in POWER_STATES else 0
        idx = min(max(idx + delta, 0), len(POWER_STATES) - 1)
        asyncio.create_task(self.client.set_fan(POWER_STATES[idx]))

    # ── Refresh ───────────────────────────────────────────────────────────

    def refresh(self):
        s = self.client.state

        self.current_temp_label.set_text(_fmt_temp(s.current_temp))

        self.mode_icon_label.set_text(_MODE_ICON.get(s.mode, ""))
        # Just the mode name -- "Fan", not "Fan Low". Fan speed shows on
        # its own down in row3's fan_label instead.
        self.mode_text_label.set_text(_MODE_TEXT.get(s.mode, s.mode or "--"))

        self.recirc_icon_label.set_text(_CIRC_ICON.get(s.circulation, ""))
        self.recirc_text_label.set_text(_CIRC_TEXT.get(s.circulation, s.circulation or "--"))

        _set_visible(self.setpoint_label, s.mode == "auto")
        if s.mode == "auto":
            # See widgets._fmt_temp for why this is "\xb0" and not
            # "\xc2\xb0". No "F" suffix here (unlike _fmt_temp) -- setpoint
            # is shown bare, e.g. "72°".
            self.setpoint_label.set_text("%.0f\xb0" % s.setpoint if s.setpoint else "--")

        # Hidden entirely while off, same reasoning as setpoint_label above
        # (and the arc itself, in the gauge block below) -- no fan speed
        # means anything then.
        _set_visible(self.fan_label, s.mode != "off")
        if s.mode != "off":
            self.fan_label.set_text(_FAN_TEXT.get(s.fan, "--") if s.fan else "--")

        # Gauge: hidden entirely while off -- there's no dial value that
        # means anything then (handle_knob() ignores the knob in this
        # state too, see there), so showing some stale fan-speed/setpoint
        # position would just be confusing. Shown otherwise: fan/cool show
        # the fan-speed dial, auto reads its range from the controller's
        # BLE settings (set_min/set_max) instead.
        #
        # Both non-off branches pad the arc's low end by one extra "fake"
        # unit that handle_knob() never actually lets the value reach (it
        # still clamps to the real lo/hi and real 0..len(POWER_STATES)-1
        # there, unchanged) -- purely so the indicator always shows a
        # visible sliver of fill even at the coldest/lowest reachable
        # setting, instead of looking fully empty right at the true
        # minimum.
        _set_visible(self.arc, s.mode != "off")
        if s.mode == "auto":
            lo, hi = self._setpoint_min(), self._setpoint_max()
            self.arc.set_range(int(lo) - 1, int(hi))
            self.arc.set_value(int(s.setpoint))
        elif s.mode != "off":
            self.arc.set_range(-1, len(POWER_STATES) - 1)
            idx = POWER_STATES.index(s.fan) if s.fan in POWER_STATES else 0
            self.arc.set_value(idx)

        # row1 (current-temp cell), not row3 -- row3 sits low enough to
        # overlap the arc's bottom gap (see its own comment above), and a
        # solid fill there visibly covered/blocked the arc. row1 is full
        # tile width now (see _TEMP_W), so this fill deliberately spans
        # edge-to-edge under the arc's ring rather than staying inside some
        # smaller inset. self.arc.move_foreground() (see __init__) keeps
        # those ring strokes rendering on top of this fill, not under it.
        if s.compressor == "on":
            self.row1.set_style_bg_opa(lv.OPA.COVER, 0)
            self.row1.set_style_bg_color(theme.COLOR_COMPRESSOR_ON, 0)
        else:
            self.row1.set_style_bg_opa(lv.OPA.TRANSP, 0)
