"""Home: the main screen. An outer knob-driven dial gauge rings three
manually-positioned elements -- current temp, mode/recirc buttons,
setpoint/fan-speed -- against the round panel. See screens/__init__.py's
module docstring for the panel-wide interaction model.

"heat"/"auto"'s heating branch (see MODES and HomeTile._apply_mode()/
_update_auto_heat()) are this screen's only heater-aware pieces -- the
heater is otherwise invisible to it, matching screens/__init__.py's
"optional, non-blocking" design: heater_client.state.connected is only
ever consulted for cosmetic feedback (see refresh()'s row1 highlight), not
to gate anything.
"""

import asyncio

import lvgl as lv

import heater_ble_config as heater_cfg
import theme
from .widgets import _column, _cycle, _fmt_temp, _label, _make_bare_tile, _make_button_cell, _set_visible, _transparent, _wire_button

# "heat" -- new, panel-only. The AirCon controller's own BLE "mode"
# characteristic (aircon_ble.py's UUID_MODE) only ever understands these
# same 4 original values; it has no slot for "drive the heater instead", so
# HomeTile tracks the *displayed* mode locally instead of reading it
# straight off client.state.mode the way the other 4 always have -- see
# HomeTile._mode/_mode_is_local and _apply_mode().
MODES = ("off", "fan", "cool", "heat", "auto")
CIRCS = ("recirc", "fresh")

# The knob's fan-speed dial, used whenever mode is fan/cool (auto uses the
# setpoint instead, off isn't reachable via the knob at all -- turning it
# always implies "on"; the mode button is the only way to power off). See
# HomeTile.handle_knob().
POWER_STATES = ("low", "medium", "high")

# "heat" mode's dial -- manual heater output level (heater_ble.py's
# RUN_MODE_GEAR), the heater's equivalent of fan/cool's POWER_STATES. See
# heater_ble_config.py's HEAT_LEVEL_MIN/MAX docstring for how confident to
# be in this exact range.
HEAT_LEVELS = tuple(range(heater_cfg.HEAT_LEVEL_MIN, heater_cfg.HEAT_LEVEL_MAX + 1))

# "auto" mode's heating branch (see HomeTile._update_auto_heat()): the
# heater only switches on once the setpoint sits at least this far above
# cabin temp, and back off once cabin temp reaches setpoint exactly -- a
# deadband on the "on" side only (not symmetric), so hovering right at the
# boundary doesn't chatter the heater on/off every refresh tick, while
# still turning off promptly and exactly at the target rather than
# overshooting by another margin's worth. Fahrenheit, matching the AirCon's
# own setpoint unit (see set_auto_target()'s F->C conversion in
# _update_auto_heat()).
_AUTO_HEAT_ON_MARGIN_F = 1.0

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
# the specific glyphs chosen here. "heat" in particular has no good match --
# LVGL's built-in symbol font has no flame/heat glyph at all -- UP (rising
# temperature) is a placeholder stand-in like the rest of this dict, not a
# considered final choice.
_MODE_ICON = {
    "off": lv.SYMBOL.POWER,
    "fan": lv.SYMBOL.REFRESH,
    "cool": lv.SYMBOL.CHARGE,
    "heat": lv.SYMBOL.UP,
    "auto": lv.SYMBOL.EYE_OPEN,
}
_MODE_TEXT = {"off": "Off", "fan": "Fan", "cool": "Cool", "heat": "Heat", "auto": "Auto"}
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

    def __init__(self, client, heater_client, encoder, tileview):
        self.client = client
        self.heater_client = heater_client
        self.encoder = encoder

        # Local "which mode is displayed/selected" state -- see MODES'
        # comment above for why this can't just be client.state.mode
        # anymore. _mode_is_local is False (defer to client.state.mode, the
        # original behavior, unchanged) until the user actually cycles into
        # "heat"; cycling to any of the other 4 sets it back to False, since
        # those all still have a real slot on the AirCon controller's own
        # mode characteristic and it's the source of truth for them (e.g.
        # if the AirCon's own mode gets changed some other way -- the Pi,
        # another client -- while this panel is showing something else, it
        # should still track that, exactly as it always has).
        self._mode = "off"
        self._mode_is_local = False
        # "auto" mode's own heater bookkeeping -- see _update_auto_heat().
        # Both reset on any transition away from "auto" (_apply_mode()), so
        # a later re-entry always re-sends fresh rather than trusting stale
        # "already sent" state from whatever happened to the heater in the
        # meantime.
        self._auto_heating = False
        self._last_auto_target_c = None
        # dir_=NONE, not DIR.TOP|BOTTOM|RIGHT -- tileview's *own* gesture
        # engine (a swipe past its built-in threshold scrolls+snaps to the
        # adjacent tile permitted by this bitmask) is fully disabled across
        # every tile in the app now, in favor of App._wire_tile_swipe()'s
        # own larger-threshold, no-animation navigation -- see
        # screens/__init__.py's App.__init__ for why (this tile's swipe-out
        # directions -- down-to-up to History, up-to-down to Settings,
        # right-to-left to Temps -- are declared there instead, alongside
        # the other tiles').
        self.tile = _make_bare_tile(tileview, 1, 1, lv.DIR.NONE)

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
        current = self._mode if self._mode_is_local else self.client.state.mode
        self._apply_mode(_cycle(MODES, current, 1))

    def _cycle_circ(self):
        s = self.client.state
        asyncio.create_task(self.client.set_circulation(_cycle(CIRCS, s.circulation, 1)))

    def _apply_mode(self, mode):
        """Central place every mode transition goes through -- both
        _cycle_mode() (the mode button) and _apply_mode() itself are the
        only callers; refresh()/handle_knob() only ever read self._mode/
        _mode_is_local, never write them, so this is the one spot that
        needs to reason about what leaving/entering each mode implies for
        the heater.
        """
        prev_mode = self._mode if self._mode_is_local else self.client.state.mode
        self._mode = mode
        self._mode_is_local = mode == "heat"

        if prev_mode == "auto" and mode != "auto":
            # Leaving auto -- see _auto_heating/_last_auto_target_c's own
            # comment in __init__ for why these reset here.
            self._auto_heating = False
            self._last_auto_target_c = None

        if mode == "heat":
            # Panel-only mode -- the AirCon controller's own mode
            # characteristic has no slot for it (see MODES' comment), so
            # tell the AirCon "off" instead (don't run its blower/
            # compressor against the heater) and drive the heater
            # directly. Resumes the heater's last-commanded gear level if
            # it was already in gear mode (e.g. re-entering "heat" after a
            # detour through another mode), else starts at the lowest
            # level -- never resumes a stale *thermostat* target left over
            # from a previous "auto" session, which would be a confusing
            # level to land on for a manual-level mode.
            asyncio.create_task(self.client.set_mode("off"))
            hs = self.heater_client.state
            if hs.run_mode == heater_cfg.RUN_MODE_GEAR and hs.run_param:
                level = hs.run_param
            else:
                level = HEAT_LEVELS[0]
            asyncio.create_task(self.heater_client.power_on(heater_cfg.RUN_MODE_GEAR, level))
        else:
            asyncio.create_task(self.client.set_mode(mode))
            if mode != "auto":
                # auto's own continuous refresh()-driven logic
                # (_update_auto_heat()) owns the heater for as long as
                # auto is active; every other mode (off/fan/cool) has no
                # business running it at all.
                asyncio.create_task(self.heater_client.power_off())

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
        mode = self._mode if self._mode_is_local else s.mode

        # Off is inert -- the knob does nothing at all (no mode change, no
        # fan change) while off, matching the arc being hidden entirely in
        # refresh() rather than showing some stale/meaningless dial value.
        # The mode button (see MODES/_cycle_mode) is the only way in or out
        # of off now.
        if mode == "off":
            return

        if mode == "auto":
            lo, hi = self._setpoint_min(), self._setpoint_max()
            target = min(max(s.setpoint + delta, lo), hi)
            asyncio.create_task(self.client.set_setpoint(target))
            return

        if mode == "heat":
            # Manual heat-level dial: HEAT_LEVELS, not wrapping at either
            # end -- same shape as fan/cool's POWER_STATES dial just below.
            hs = self.heater_client.state
            if hs.run_mode == heater_cfg.RUN_MODE_GEAR and hs.run_param in HEAT_LEVELS:
                idx = HEAT_LEVELS.index(hs.run_param)
            else:
                idx = 0
            idx = min(max(idx + delta, 0), len(HEAT_LEVELS) - 1)
            asyncio.create_task(self.heater_client.set_heat_level(HEAT_LEVELS[idx]))
            return

        # Only fan/cool reach here (heat/auto/off all returned above) --
        # fan-speed dial: low/medium/high, not wrapping at either end,
        # mode unchanged (no set_mode() call needed -- it's already
        # fan/cool).
        idx = POWER_STATES.index(s.fan) if s.fan in POWER_STATES else 0
        idx = min(max(idx + delta, 0), len(POWER_STATES) - 1)
        asyncio.create_task(self.client.set_fan(POWER_STATES[idx]))

    # ── Refresh ───────────────────────────────────────────────────────────

    def _current_heat_level(self):
        """The heat level to display/dial from -- the heater's own last-
        commanded run_param if it's actually in gear mode, else the lowest
        level (same fallback handle_knob()/_apply_mode() use when there's
        nothing meaningful to resume).
        """
        hs = self.heater_client.state
        if hs.run_mode == heater_cfg.RUN_MODE_GEAR and hs.run_param in HEAT_LEVELS:
            return hs.run_param
        return HEAT_LEVELS[0]

    def _update_auto_heat(self):
        """Called from refresh() only while mode == "auto" -- the knob-
        driven half of auto mode is unchanged (still just adjusts
        client.state.setpoint, see handle_knob()); this is the other half,
        continuously comparing that setpoint against current cabin temp
        every refresh tick and turning the heater on/off accordingly (see
        _AUTO_HEAT_ON_MARGIN_F's comment for the hysteresis), independent
        of the knob.

        Deliberately edge-triggered, not level-triggered: heater_client.
        set_auto_target()/power_off() are only ever called when the
        *desired* value actually changes, never unconditionally every tick
        -- HeaterClient's own debounce (600ms) is longer than this
        screen's refresh cadence (250ms, see main.py's _REFRESH_PERIOD_MS),
        so calling either one unconditionally on every tick while the
        situation is unchanged would perpetually cancel-and-reschedule that
        debounce's pending write and it would never actually fire.
        """
        s = self.client.state
        cabin = s.cabin_temp if s.cabin_temp is not None else s.current_temp
        if cabin is None or not s.setpoint:
            return

        diff = s.setpoint - cabin
        if not self._auto_heating and diff > _AUTO_HEAT_ON_MARGIN_F:
            self._auto_heating = True
        elif self._auto_heating and diff <= 0:
            self._auto_heating = False

        if self._auto_heating:
            target_c = round((s.setpoint - 32.0) * 5.0 / 9.0, 1)
            if target_c != self._last_auto_target_c:
                self._last_auto_target_c = target_c
                asyncio.create_task(self.heater_client.set_auto_target(target_c))
        elif self._last_auto_target_c is not None:
            self._last_auto_target_c = None
            asyncio.create_task(self.heater_client.power_off())

    def refresh(self):
        s = self.client.state
        mode = self._mode if self._mode_is_local else s.mode

        self.current_temp_label.set_text(_fmt_temp(s.current_temp))

        self.mode_icon_label.set_text(_MODE_ICON.get(mode, ""))
        # Just the mode name -- "Fan", not "Fan Low". Fan speed (or heat
        # level, in "heat" mode) shows on its own down in row3's fan_label
        # instead.
        self.mode_text_label.set_text(_MODE_TEXT.get(mode, mode or "--"))

        self.recirc_icon_label.set_text(_CIRC_ICON.get(s.circulation, ""))
        self.recirc_text_label.set_text(_CIRC_TEXT.get(s.circulation, s.circulation or "--"))

        _set_visible(self.setpoint_label, mode == "auto")
        if mode == "auto":
            # See widgets._fmt_temp for why this is "\xb0" and not
            # "\xc2\xb0". No "F" suffix here (unlike _fmt_temp) -- setpoint
            # is shown bare, e.g. "72°".
            self.setpoint_label.set_text("%.0f\xb0" % s.setpoint if s.setpoint else "--")

        # Hidden entirely while off, same reasoning as setpoint_label above
        # (and the arc itself, in the gauge block below) -- no fan speed/
        # heat level means anything then.
        _set_visible(self.fan_label, mode != "off")
        if mode == "heat":
            self.fan_label.set_text("Level %d" % self._current_heat_level())
        elif mode != "off":
            self.fan_label.set_text(_FAN_TEXT.get(s.fan, "--") if s.fan else "--")

        # Gauge: hidden entirely while off -- there's no dial value that
        # means anything then (handle_knob() ignores the knob in this
        # state too, see there), so showing some stale fan-speed/setpoint/
        # heat-level position would just be confusing. Shown otherwise:
        # fan/cool show the fan-speed dial, heat shows the heat-level dial,
        # auto reads its range from the controller's BLE settings (set_min/
        # set_max) instead.
        #
        # Every non-off/non-auto branch pads the arc's low end by one extra
        # "fake" unit that handle_knob() never actually lets the value
        # reach (it still clamps to the real 0..len(...)-1 range there,
        # unchanged) -- purely so the indicator always shows a visible
        # sliver of fill even at the lowest reachable setting, instead of
        # looking fully empty right at the true minimum.
        _set_visible(self.arc, mode != "off")
        if mode == "auto":
            lo, hi = self._setpoint_min(), self._setpoint_max()
            self.arc.set_range(int(lo) - 1, int(hi))
            self.arc.set_value(int(s.setpoint))
        elif mode == "heat":
            self.arc.set_range(-1, len(HEAT_LEVELS) - 1)
            self.arc.set_value(HEAT_LEVELS.index(self._current_heat_level()))
        elif mode != "off":
            self.arc.set_range(-1, len(POWER_STATES) - 1)
            idx = POWER_STATES.index(s.fan) if s.fan in POWER_STATES else 0
            self.arc.set_value(idx)

        if mode == "auto":
            self._update_auto_heat()

        # row1 (current-temp cell), not row3 -- row3 sits low enough to
        # overlap the arc's bottom gap (see its own comment above), and a
        # solid fill there visibly covered/blocked the arc. row1 is full
        # tile width now (see _TEMP_W), so this fill deliberately spans
        # edge-to-edge under the arc's ring rather than staying inside some
        # smaller inset. self.arc.move_foreground() (see __init__) keeps
        # those ring strokes rendering on top of this fill, not under it.
        # Priority, most to least urgent: a controller-reported error (the
        # full text is one swipe away on the Info screen, see
        # screens/info.py); the AC compressor running; the heater actively
        # commanded on and connected (whether from "heat" mode or auto
        # mode's heating branch -- either way it's the same "something is
        # actively conditioning the cabin" fact worth surfacing here, just
        # with a distinct warm color instead of the compressor's cool blue,
        # see theme.COLOR_HEATER_ON); otherwise no highlight at all.
        hs = self.heater_client.state
        if s.error:
            self.row1.set_style_bg_opa(lv.OPA.COVER, 0)
            self.row1.set_style_bg_color(theme.COLOR_DANGER, 0)
        elif s.compressor == "on":
            self.row1.set_style_bg_opa(lv.OPA.COVER, 0)
            self.row1.set_style_bg_color(theme.COLOR_COMPRESSOR_ON, 0)
        elif hs.connected and hs.on:
            self.row1.set_style_bg_opa(lv.OPA.COVER, 0)
            self.row1.set_style_bg_color(theme.COLOR_HEATER_ON, 0)
        else:
            self.row1.set_style_bg_opa(lv.OPA.TRANSP, 0)
