"""Home: the main screen. An outer knob-driven dial gauge rings three
manually-positioned elements -- current temp, mode/recirc buttons,
setpoint/fan-speed -- against the round panel. See screens/__init__.py's
module docstring for the panel-wide interaction model.

Mode selection is a radial menu now, not a knob-cycle -- see MODES/
MODE_DEVICE/_open_mode_menu() and this class's own "Mode menu" section.
Both the AirCon and the heater are independent, optionally-connected
devices (see screens/__init__.py's module docstring): MODE_DEVICE records
which one (if either) each mode needs, used both to grey out/skip menu
slices for a currently-unavailable device and by screens/__init__.py's App
to decide whether Home is even reachable for whatever mode is currently
selected.
"""

import math

import asyncio

import lvgl as lv

import hal
import heater_ble_config as heater_cfg
import theme
from .widgets import _column, _fmt_temp, _label, _make_bare_tile, _make_button_cell, _set_visible, _transparent, _wire_button

# Display order matches the radial menu's clockwise layout below, starting
# from "off" at 6 o'clock: Off, Fan, Cool, '[ac] Auto', '[heat] Auto', Heat
# -- see HomeTile._MENU_START_ANGLE. "auto" keeps its original bare name
# (not "ac_auto") since that's also the literal wire value sent to the
# AirCon controller's own mode characteristic (aircon_ble.py's set_mode())
# -- only "heat"/"heat_auto" are panel-only pseudo-modes with no slot on the
# controller itself (see HomeTile._mode_is_local).
MODES = ("off", "fan", "cool", "auto", "heat_auto", "heat")

# Which physical device (if any) a mode needs -- None for "off", which
# needs nothing and is therefore always selectable/reachable regardless of
# what's connected. Used by _available_modes() (radial menu) and by
# screens/__init__.py's App (whether Home is reachable at all for whatever
# mode is currently selected, showing the Disconnected screen instead if
# not).
MODE_DEVICE = {
    "heat_auto": "heater",
    "heat": "heater",
    "off": None,
    "fan": "aircon",
    "cool": "aircon",
    "auto": "aircon",
}

# Where the dial lands after a cooldown (App._enter_cooldown(), triggered
# by holding the knob's push-button App._COOLDOWN_HOLD_MS -- see
# screens/__init__.py's module docstring) -- a mode absent here (fan, off)
# means "no change", matching .get(mode, mode)'s fallback at the one call
# site. Both AC-cooling modes drop to fan (keep circulating air, stop
# actively cooling) and both heat modes drop to off (a heater left running
# unattended is the higher-risk case of the two) -- deliberately asymmetric,
# not an oversight.
MODE_COOLDOWN_TARGET = {
    "auto": "fan",
    "cool": "fan",
    "heat": "off",
    "heat_auto": "off",
}

# Radial menu color category per mode -- "heat"/"ac"/"neutral", see
# theme.py's COLOR_MODE_*_SELECTED/AVAILABLE comment for the actual colors.
_MODE_CATEGORY = {
    "heat_auto": "heat",
    "heat": "heat",
    "off": "neutral",
    "fan": "ac",
    "cool": "ac",
    "auto": "ac",
}

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

# "heat_auto" mode's target-temp dial bounds, Fahrenheit (this dial always
# works in Fahrenheit, matching the AirCon-auto setpoint dial and
# current_temp display elsewhere on this screen) -- converted from
# heater_ble_config.py's THERMOSTAT_TEMP_MIN_C/MAX_C, themselves the vendor
# app's own clamp range for this field. The heater's own firmware owns all
# on/off cycling and hysteresis around this target -- this client only ever
# sets the target itself (heater_ble.HeaterClient.set_auto_target()), same
# as "heat" mode only ever sets a gear level, never manages on/off timing.
_HEAT_AUTO_TARGET_MIN_F = heater_cfg.THERMOSTAT_TEMP_MIN_C * 9.0 / 5.0 + 32.0
_HEAT_AUTO_TARGET_MAX_F = heater_cfg.THERMOSTAT_TEMP_MAX_C * 9.0 / 5.0 + 32.0
_HEAT_AUTO_TARGET_DEFAULT_F = 72.0

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
# the specific glyphs chosen here. "heat"/"heat_auto" in particular have no
# good match -- LVGL's built-in symbol font has no flame/heat glyph at all;
# CHARGE (a lightning bolt, normally used for a "charging" battery
# indicator) stands in for heat instead, and heat_auto reuses "auto"'s own
# EYE_OPEN -- both are thermostat-style "hold a target" modes, just for a
# different device, so sharing an icon (distinguished by the red/blue wedge
# color, see theme.COLOR_MODE_*) reads better than an unrelated one. "cool"
# in turn moves off CHARGE (its own placeholder pick before heat needed the
# slot) onto TINT, a water-drop glyph -- still a placeholder, not a
# considered final choice, just no longer a duplicate of heat's icon.
_MODE_ICON = {
    "off": lv.SYMBOL.POWER,
    "fan": lv.SYMBOL.REFRESH,
    "cool": lv.SYMBOL.TINT,
    "heat": lv.SYMBOL.CHARGE,
    "heat_auto": lv.SYMBOL.EYE_OPEN,
    "auto": lv.SYMBOL.EYE_OPEN,
}
_MODE_TEXT = {"off": "Off", "fan": "Fan", "cool": "Cool", "heat": "Heat", "heat_auto": "Auto", "auto": "Auto"}
# Radial menu slice labels -- distinguish the two Autos (main dial doesn't
# need to: only one mode is ever the *active* one, shown via _MODE_TEXT
# above, so there's no ambiguity there) in the small space a slice label
# has to work with.
_MENU_TEXT = {
    "heat_auto": "Heat\nAuto",
    "heat": "Heat",
    "off": "Off",
    "fan": "Fan",
    "cool": "Cool",
    "auto": "AC\nAuto",
}
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

    # Radial mode menu -- see "Mode menu" section below. Ring (donut)
    # segments, NOT full-radius pie wedges -- an earlier version used
    # near-full-radius wedges (width 110 out of a 236 diameter) with no
    # set_style_arc_rounded(False, ...) call, which on real hardware
    # rendered as big overlapping rounded blobs rather than six distinct
    # slices (LVGL arcs default to rounded end-caps, same as the confirmed
    # line_rounded property on lv.line -- at that width/that many stacked
    # instances, the rounding swallowed the seams between slices). This
    # version draws a much narrower ring (_MENU_RING_WIDTH) inward from the
    # outer edge instead of nearly to center, explicitly disables end-cap
    # rounding, and leaves a real angular gap (_MENU_PAD_DEG) between
    # adjacent slices rather than relying on exactly-abutting bg_angles --
    # see _init_mode_menu().
    #
    # hal.WIDTH (240, the full round panel diameter), not self.arc's own
    # 236 -- the menu is meant to visually replace the whole dial while
    # open, all the way out to the physical bezel, not leave a ring of its
    # own inset from it (confirmed on real hardware: an earlier version at
    # 230 left a visible several-pixel gap between the wedges' outer edge
    # and the screen edge).
    _MENU_DIAMETER = hal.WIDTH
    _MENU_RING_DIAMETER = hal.WIDTH
    _MENU_RING_WIDTH = 50
    _MENU_PAD_DEG = 6
    # 90 = 6 o'clock in LVGL's angle convention (0 = 3 o'clock, clockwise) --
    # this is the *center* angle of MODES[0] ("off"), not a starting edge
    # the way an earlier version's _MENU_START_ANGLE was: "off" reading as
    # literally the lowest/gravity position on the dial is a deliberate,
    # not incidental, choice, and each subsequent mode in MODES continues
    # clockwise from there (fan at 150, cool at 210, auto at 270, heat_auto
    # at 330, heat at 30).
    _MENU_START_ANGLE = 90
    # Icons sit at each slice's angular midpoint, at the ring's own middle
    # radius: outer_radius - half the ring's width -- computed once here
    # rather than re-derived per-slice in _init_mode_menu(). With the
    # values above this is 95px out from center (outer radius 120, ring
    # spanning 70-120), leaving roughly the inner 58% of the diameter
    # clear for the center label -- see _init_mode_menu().
    _MENU_ICON_RADIUS = _MENU_RING_DIAMETER // 2 - _MENU_RING_WIDTH // 2

    def __init__(self, client, heater_client, encoder, tileview):
        self.client = client
        self.heater_client = heater_client
        self.encoder = encoder

        # Local "which mode is displayed/selected" state -- see MODES'
        # comment above for why this can't just be client.state.mode
        # anymore. _mode_is_local is False (defer to client.state.mode, the
        # original behavior, unchanged) until the user actually selects
        # "heat"/"heat_auto" from the radial menu; selecting any of the
        # other 4 sets it back to False, since those all still have a real
        # slot on the AirCon controller's own mode characteristic and it's
        # the source of truth for them (e.g. if the AirCon's own mode gets
        # changed some other way -- the Pi, another client -- while this
        # panel is showing something else, it should still track that,
        # exactly as it always has).
        self._mode = "off"
        self._mode_is_local = False
        # "heat_auto" mode's own target temp, Fahrenheit -- independent of
        # the AirCon's own client.state.setpoint (that's a real remote
        # characteristic tied specifically to the AirCon controller; this
        # is purely local UI state for a target this class itself sends to
        # the heater via set_auto_target(), see handle_knob()/apply_mode()).
        self._heat_auto_target_f = _HEAT_AUTO_TARGET_DEFAULT_F
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

        # Cooling-off indicator -- see heater_ble.HeaterState.cooling_off's
        # own comment for how confident to be in the byte this reflects.
        # Shown regardless of which mode is currently selected/displayed
        # (the heater's own state is independent of the dial's current
        # focus -- see apply_mode()'s docstring), so it lives outside the
        # per-mode row1/row3 content instead of being tied to mode=="heat".
        self.cooling_off_label = _label(self.tile, "Cooling Off", font=theme.FONT_TINY, color=theme.COLOR_TEXT_MUTED)
        self.cooling_off_label.align(lv.ALIGN.CENTER, 0, self._TEMP_Y + self._TEMP_H // 2 + theme.SPACE_SM)
        _set_visible(self.cooling_off_label, False)

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

        _wire_button(self.mode_cell, encoder, self._open_mode_menu)
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

        self._init_mode_menu()

    # ── Mode menu ────────────────────────────────────────────────────────

    def _init_mode_menu(self):
        """Builds the radial mode-select menu -- six lv.arc ring segments
        plus an icon each, all children of self._menu_container (hidden by
        default, same size/position as self.arc so it visually stands in
        for the whole dial while open -- see _open_mode_menu()), plus one
        center label (self._menu_center_label) showing the currently-
        highlighted mode's name in the clear middle the ring leaves open.
        Built last (after everything above), so its natural paint order is
        already topmost without needing its own move_foreground() call.
        """
        self._menu_open = False
        self._menu_selected = MODES[0]
        self._menu_container = _transparent(self.tile)
        self._menu_container.set_size(self._MENU_DIAMETER, self._MENU_DIAMETER)
        self._menu_container.center()
        _set_visible(self._menu_container, False)

        slice_span = 360 // len(MODES)
        self._menu_slices = {}
        self._menu_icons = {}
        for i, mode in enumerate(MODES):
            center_angle = (self._MENU_START_ANGLE + i * slice_span) % 360
            # int, not float -- set_bg_angles takes integer degrees (see
            # every other call site in this file, all plain ints); slice_span
            # (60) and _MENU_PAD_DEG (6) are both even so this division is
            # exact, but round()/int() defensively regardless.
            half_span = (slice_span - self._MENU_PAD_DEG) // 2
            start = (center_angle - half_span) % 360
            end = (center_angle + half_span) % 360
            wedge = lv.arc(self._menu_container)
            wedge.set_size(self._MENU_RING_DIAMETER, self._MENU_RING_DIAMETER)
            wedge.center()
            wedge.set_bg_angles(start, end)
            wedge.set_style_arc_width(self._MENU_RING_WIDTH, lv.PART.MAIN)
            wedge.set_style_arc_width(0, lv.PART.INDICATOR)
            # The actual fix for the "big overlapping blobs" bug -- see
            # _MENU_DIAMETER's comment above. NOT independently re-
            # confirmed on real hardware yet (only ever one arc at a time
            # elsewhere in this codebase besides this menu) -- if slices
            # still bleed into each other visually, this call not actually
            # suppressing the end-cap rounding (wrong method name/PART) is
            # the first thing to suspect.
            wedge.set_style_arc_rounded(False, lv.PART.MAIN)
            wedge.remove_flag(lv.obj.FLAG.CLICKABLE)
            wedge.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.KNOB)
            wedge.set_style_border_width(0, lv.PART.KNOB)
            self._menu_slices[mode] = wedge

            mid_angle = math.radians(center_angle)
            lx = int(round(math.cos(mid_angle) * self._MENU_ICON_RADIUS))
            ly = int(round(math.sin(mid_angle) * self._MENU_ICON_RADIUS))
            icon = _label(self._menu_container, text=_MODE_ICON.get(mode, ""), font=theme.FONT_BUTTON_ICON)
            icon.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
            icon.align(lv.ALIGN.CENTER, lx, ly)
            self._menu_icons[mode] = icon

        # Center label -- see this method's own docstring. Text set per-
        # frame by _refresh_menu_visuals(), not here (nothing selected to
        # show yet at construction time beyond MODES[0], not worth a
        # separate code path for).
        self._menu_center_label = _label(self._menu_container, font=theme.FONT_BUTTON_LABEL, color=theme.COLOR_TEXT)
        self._menu_center_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self._menu_center_label.center()

    def current_mode(self):
        """The mode actually in effect right now -- screens/__init__.py's
        App reads this (not self._mode/_mode_is_local directly) to decide
        whether Home is reachable at all, via MODE_DEVICE.
        """
        return self._mode if self._mode_is_local else self.client.state.mode

    def _available_modes(self):
        """Modes whose MODE_DEVICE (if any) is currently connected -- "off"
        (device None) is always included. Order follows MODES, not
        insertion/selection order.
        """
        aircon_ok = self.client.state.connected
        heater_ok = self.heater_client.state.connected
        avail = []
        for mode in MODES:
            device = MODE_DEVICE[mode]
            if device is None or (device == "aircon" and aircon_ok) or (device == "heater" and heater_ok):
                avail.append(mode)
        return avail

    def _open_mode_menu(self):
        """mode_cell's click callback (touch + knob-button, same gating as
        every other Home button -- see widgets._wire_button()) -- opens the
        radial picker instead of directly cycling the mode the way an
        earlier version of this did. Once open, further interaction is
        bare knob-turn + knob-button (no touch needed, same as Connect/
        Disconnected's picker) -- see screens/__init__.py's App.
        poll_input(), which routes to handle_mode_menu_knob()/
        confirm_mode_menu() instead of handle_knob() while self.
        mode_menu_open is true.

        No-op if already open -- mode_cell/recirc_cell sit *underneath*
        self._menu_container once it's showing (added earlier, see
        __init__), and it's not confirmed whether this LVGL binding's hit-
        testing lets a touch pass through a non-CLICKABLE object on top
        (the menu's wedges) to a CLICKABLE one further down (these two
        cells) or stops at the topmost object regardless -- guarding here
        (and in _cycle_circ()) means it doesn't matter which: a stray tap
        landing on either cell while the menu's already up can't do
        anything unexpected either way.
        """
        if self._menu_open:
            return
        avail = self._available_modes()
        current = self.current_mode()
        self._menu_selected = current if current in avail else (avail[0] if avail else "off")
        self._menu_open = True
        self._refresh_menu_visuals()
        _set_visible(self._menu_container, True)
        # Explicitly hidden, not just relied on to be covered by the ring
        # segments' own opaque fill -- there's a deliberate gap between
        # each segment now (_MENU_PAD_DEG, see _init_mode_menu()), and the
        # ring itself doesn't reach all the way to center, so there's
        # always tile background visible through/inside the menu regardless
        # of how the ring segments render.
        for obj in (self.arc, self.row1, self.row3, self.mode_cell, self.recirc_cell, self.cooling_off_label):
            _set_visible(obj, False)

    @property
    def mode_menu_open(self):
        return self._menu_open

    def handle_mode_menu_knob(self, delta):
        """Moves the highlighted slice by exactly `delta` positions among
        the currently *available* modes (wrapping) -- unavailable ones
        aren't stops at all, same as a disabled entry never being
        reachable on screens.connect.ConnectTile's roller.
        """
        if not delta:
            return
        avail = self._available_modes()
        if not avail:
            return
        try:
            idx = avail.index(self._menu_selected)
        except ValueError:
            idx = 0
        self._menu_selected = avail[(idx + delta) % len(avail)]
        self._refresh_menu_visuals()

    def confirm_mode_menu(self):
        """Knob-button press while the menu is open -- commits the
        highlighted mode and closes the menu. See close_mode_menu() for
        the "close without changing anything" counterpart, called directly
        (not through here) by cancel paths.
        """
        self.apply_mode(self._menu_selected)
        self.close_mode_menu()

    def close_mode_menu(self):
        """Closes the menu without applying self._menu_selected -- called
        both by cancel paths (swiping away from Home while it's open, see
        screens/__init__.py's App.__init__ on_leave wiring) and internally
        by confirm_mode_menu() after it's already applied the change.

        Restores everything _open_mode_menu() explicitly hid. row1/row3/
        mode_cell/recirc_cell are always visible outside the menu (refresh()
        never toggles those containers themselves, only their children's
        text/styling), so unconditionally showing them again is correct.
        self.arc/cooling_off_label are mode-dependent instead (refresh()
        already recomputes their visibility fresh every tick regardless of
        this) -- recomputed here too, rather than left for the next
        refresh() tick to fix, so there's no possible one-frame flash of
        the wrong state in between (confirm_mode_menu() closes the menu
        from inside poll_input(), which can run several ticks before
        refresh() runs again).
        """
        self._menu_open = False
        _set_visible(self._menu_container, False)
        for obj in (self.row1, self.row3, self.mode_cell, self.recirc_cell):
            _set_visible(obj, True)
        hs = self.heater_client.state
        _set_visible(self.arc, self.current_mode() != "off")
        _set_visible(self.cooling_off_label, hs.connected and hs.cooling_off)

    def _refresh_menu_visuals(self):
        avail = self._available_modes()
        for mode, wedge in self._menu_slices.items():
            category = _MODE_CATEGORY[mode]
            if mode not in avail:
                color = theme.COLOR_MODE_DISABLED
                icon_color = theme.COLOR_TEXT_MUTED
            elif mode == self._menu_selected:
                color = {
                    "heat": theme.COLOR_MODE_HEAT_SELECTED,
                    "ac": theme.COLOR_MODE_AC_SELECTED,
                    "neutral": theme.COLOR_MODE_NEUTRAL_SELECTED,
                }[category]
                icon_color = theme.COLOR_TEXT
            else:
                color = {
                    "heat": theme.COLOR_MODE_HEAT_AVAILABLE,
                    "ac": theme.COLOR_MODE_AC_AVAILABLE,
                    "neutral": theme.COLOR_MODE_NEUTRAL_AVAILABLE,
                }[category]
                icon_color = theme.COLOR_TEXT
            wedge.set_style_arc_color(color, lv.PART.MAIN)
            self._menu_icons[mode].set_style_text_color(icon_color, 0)
        # The highlighted mode's name, shown once in the ring's clear
        # center instead of a label per slice -- _MENU_TEXT (not
        # _MODE_TEXT) since it's the one that distinguishes the two Autos
        # ("AC Auto" vs. "Heat Auto"), which matters here precisely because
        # both are visible on the menu at once.
        self._menu_center_label.set_text(_MENU_TEXT[self._menu_selected])

    # ── Button-cell actions ──────────────────────────────────────────────

    def _cycle_circ(self):
        # See _open_mode_menu()'s docstring for why this guards against the
        # menu being open too.
        if self._menu_open:
            return
        s = self.client.state
        current = s.circulation
        idx = CIRCS.index(current) if current in CIRCS else 0
        asyncio.create_task(self.client.set_circulation(CIRCS[(idx + 1) % len(CIRCS)]))

    def apply_mode(self, mode):
        """Central place every mode transition goes through -- both
        confirm_mode_menu() (the radial menu) and apply_mode() itself are
        the only callers; refresh()/handle_knob() only ever read
        self._mode/_mode_is_local, never write them, so this is the one
        spot that needs to reason about what leaving/entering each mode
        implies for the heater.

        The heater's on/off bit is ONLY ever commanded from here, and only
        for three cases: entering heat/heat_auto (turns it on, with
        whatever mode/level-or-temp that entry implies), and entering
        "off" specifically (turns it off, as a universal safety/reset
        state). Switching between the three AC-only modes (fan/cool/auto)
        never touches the heater at all -- it keeps doing whatever it was
        last told, independent of what the dial is currently showing. This
        means the heater can legitimately keep running while the dial is
        parked on an AC mode; heater_ble.HeaterState.on/cooling_off (see
        refresh()) reflect that regardless of self._mode.
        """
        self._mode = mode
        self._mode_is_local = mode in ("heat", "heat_auto")

        if mode == "heat":
            # Panel-only mode -- the AirCon controller's own mode
            # characteristic has no slot for it (see MODES' comment), so
            # tell the AirCon "off" instead (don't run its blower/
            # compressor against the heater) and drive the heater
            # directly. Resumes the heater's last-commanded gear level if
            # it was already in gear mode (e.g. re-entering "heat" after a
            # detour through another mode), else starts at the lowest
            # level -- never resumes a stale *thermostat* target left over
            # from a previous "heat_auto" session, which would be a
            # confusing level to land on for a manual-level mode.
            asyncio.create_task(self.client.set_mode("off"))
            hs = self.heater_client.state
            if hs.run_mode == heater_cfg.RUN_MODE_GEAR and hs.run_param:
                level = hs.run_param
            else:
                level = HEAT_LEVELS[0]
            asyncio.create_task(self.heater_client.power_on(heater_cfg.RUN_MODE_GEAR, level))
        elif mode == "heat_auto":
            asyncio.create_task(self.client.set_mode("off"))
            hs = self.heater_client.state
            if hs.run_mode == heater_cfg.RUN_MODE_THERMOSTAT and hs.run_param:
                target_f = round(hs.run_param * 9.0 / 5.0 + 32.0)
                target_f = min(max(target_f, _HEAT_AUTO_TARGET_MIN_F), _HEAT_AUTO_TARGET_MAX_F)
            else:
                target_f = _HEAT_AUTO_TARGET_DEFAULT_F
            self._heat_auto_target_f = target_f
            target_c = round((target_f - 32.0) * 5.0 / 9.0, 1)
            asyncio.create_task(self.heater_client.power_on(heater_cfg.RUN_MODE_THERMOSTAT, target_c))
        elif mode == "off":
            asyncio.create_task(self.client.set_mode("off"))
            asyncio.create_task(self.heater_client.power_off())
        else:
            # fan/cool/auto -- AC-only; heater deliberately untouched, see
            # this method's own docstring.
            asyncio.create_task(self.client.set_mode(mode))

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
        last poll, only while this is the active tile AND the radial mode
        menu isn't open (see screens/__init__.py's App.poll_input(), which
        routes to handle_mode_menu_knob() instead while it is).
        """
        if not delta:
            return
        s = self.client.state
        mode = self.current_mode()

        # Off is inert -- the knob does nothing at all (no fan change)
        # while off, matching the arc being hidden entirely in refresh()
        # rather than showing some stale/meaningless dial value. The mode
        # button (see _open_mode_menu()) is the only way in or out of off
        # now.
        if mode == "off":
            return

        if mode == "auto":
            lo, hi = self._setpoint_min(), self._setpoint_max()
            target = min(max(s.setpoint + delta, lo), hi)
            asyncio.create_task(self.client.set_setpoint(target))
            return

        if mode == "heat_auto":
            target = min(max(self._heat_auto_target_f + delta, _HEAT_AUTO_TARGET_MIN_F), _HEAT_AUTO_TARGET_MAX_F)
            self._heat_auto_target_f = target
            target_c = round((target - 32.0) * 5.0 / 9.0, 1)
            asyncio.create_task(self.heater_client.set_auto_target(target_c))
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

        # Only fan/cool reach here (heat/heat_auto/auto/off all returned
        # above) -- fan-speed dial: low/medium/high, not wrapping at either
        # end, mode unchanged (no set_mode() call needed -- it's already
        # fan/cool).
        idx = POWER_STATES.index(s.fan) if s.fan in POWER_STATES else 0
        idx = min(max(idx + delta, 0), len(POWER_STATES) - 1)
        asyncio.create_task(self.client.set_fan(POWER_STATES[idx]))

    # ── Refresh ───────────────────────────────────────────────────────────

    def _current_heat_level(self):
        """The heat level to display/dial from -- the heater's own last-
        commanded run_param if it's actually in gear mode, else the lowest
        level (same fallback handle_knob()/apply_mode() use when there's
        nothing meaningful to resume).
        """
        hs = self.heater_client.state
        if hs.run_mode == heater_cfg.RUN_MODE_GEAR and hs.run_param in HEAT_LEVELS:
            return hs.run_param
        return HEAT_LEVELS[0]

    def refresh(self):
        # While the radial mode menu is open, its own visuals are kept
        # current by _refresh_menu_visuals() (called from _open_mode_menu()/
        # handle_mode_menu_knob()) instead of this periodic refresh() --
        # skip everything below entirely rather than just leaving it
        # harmless: _set_visible(self.arc, mode != "off") a few lines down
        # doesn't know the menu hid the arc on purpose (_open_mode_menu()),
        # so without this guard the very next refresh() tick (this runs
        # every ~250ms regardless of what's on screen, see
        # screens/__init__.py's App.refresh()) unconditionally re-showed it
        # behind the menu -- confirmed on real hardware as the gauge track
        # visibly peeking out from under the ring segments moments after
        # opening the menu.
        if self._menu_open:
            return

        s = self.client.state
        mode = self.current_mode()

        self.current_temp_label.set_text(_fmt_temp(s.current_temp))

        self.mode_icon_label.set_text(_MODE_ICON.get(mode, ""))
        # Just the mode name -- "Fan", not "Fan Low". Fan speed (or heat
        # level, in "heat" mode) shows on its own down in row3's fan_label
        # instead.
        self.mode_text_label.set_text(_MODE_TEXT.get(mode, mode or "--"))

        self.recirc_icon_label.set_text(_CIRC_ICON.get(s.circulation, ""))
        self.recirc_text_label.set_text(_CIRC_TEXT.get(s.circulation, s.circulation or "--"))

        _set_visible(self.setpoint_label, mode in ("auto", "heat_auto"))
        if mode == "auto":
            # See widgets._fmt_temp for why this is "\xb0" and not
            # "\xc2\xb0". No "F" suffix here (unlike _fmt_temp) -- setpoint
            # is shown bare, e.g. "72°".
            self.setpoint_label.set_text("%.0f\xb0" % s.setpoint if s.setpoint else "--")
        elif mode == "heat_auto":
            self.setpoint_label.set_text("%.0f\xb0" % self._heat_auto_target_f)

        # Hidden entirely while off/heat_auto, same reasoning as
        # setpoint_label above (and the arc itself, in the gauge block
        # below) -- no fan speed/heat level means anything then (heat_auto
        # shows its target via setpoint_label instead, same slot cool/auto
        # uses).
        _set_visible(self.fan_label, mode not in ("off", "heat_auto"))
        if mode == "heat":
            self.fan_label.set_text("Level %d" % self._current_heat_level())
        elif mode not in ("off", "heat_auto"):
            self.fan_label.set_text(_FAN_TEXT.get(s.fan, "--") if s.fan else "--")

        # Gauge: hidden entirely while off -- there's no dial value that
        # means anything then (handle_knob() ignores the knob in this
        # state too, see there), so showing some stale fan-speed/setpoint/
        # heat-level position would just be confusing. Shown otherwise:
        # fan/cool show the fan-speed dial, heat shows the heat-level dial,
        # auto/heat_auto read their own target ranges instead.
        #
        # Every non-off/non-auto/non-heat_auto branch pads the arc's low
        # end by one extra "fake" unit that handle_knob() never actually
        # lets the value reach (it still clamps to the real
        # 0..len(...)-1 range there, unchanged) -- purely so the indicator
        # always shows a visible sliver of fill even at the lowest
        # reachable setting, instead of looking fully empty right at the
        # true minimum.
        _set_visible(self.arc, mode != "off")
        if mode == "auto":
            lo, hi = self._setpoint_min(), self._setpoint_max()
            self.arc.set_range(int(lo) - 1, int(hi))
            self.arc.set_value(int(s.setpoint))
        elif mode == "heat_auto":
            self.arc.set_range(int(_HEAT_AUTO_TARGET_MIN_F) - 1, int(_HEAT_AUTO_TARGET_MAX_F))
            self.arc.set_value(int(self._heat_auto_target_f))
        elif mode == "heat":
            self.arc.set_range(-1, len(HEAT_LEVELS) - 1)
            self.arc.set_value(HEAT_LEVELS.index(self._current_heat_level()))
        elif mode != "off":
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
        # Priority, most to least urgent: an error -- either the AirCon
        # controller's own state.error, or the heater reporting a nonzero
        # fault_code (see heater_ble.HeaterState's own docstring for how
        # confident to be in that byte -- best-guess, not confirmed against
        # a real fault; wired up the same way state.error already is, not
        # a new category of behavior) -- the full text of either is one
        # swipe away on the Info screen, see screens/info.py; the AC
        # compressor running; the heater actively on and connected
        # (independent of which mode is currently selected/displayed here
        # -- see apply_mode()'s docstring -- just with a distinct warm
        # color instead of the compressor's cool blue, see
        # theme.COLOR_HEATER_ON); otherwise no highlight at all.
        hs = self.heater_client.state
        if s.error or (hs.connected and hs.fault_code):
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

        _set_visible(self.cooling_off_label, hs.connected and hs.cooling_off)
