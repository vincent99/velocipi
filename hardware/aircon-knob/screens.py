"""The 5 screens shown on the panel, built with real LVGL widgets (an
lv.tileview of tiles, sharing one lv.group for encoder navigation) -- a
close Python port of ../temp_knob/firmware/src/ui_app.cpp, now that we're
using the real lvgl_micropython bindings instead of hand-rolled framebuf
drawing.

CAVEAT: written against the LVGL Python binding's well-established naming
convention (widget constructors take `parent`, C function
`lv_foo_set_bar()` becomes Python `foo.set_bar()`, C enums like
`LV_EVENT_VALUE_CHANGED` become `lv.EVENT.VALUE_CHANGED`) but not run
against the actual generated binding. If a name doesn't resolve, check the
`lvgl.pyi` stub the firmware build / MicroPico's "Configure project" step
produces -- see ../README.md.
"""

import asyncio

import lvgl as lv

import theme

MODES = ("off", "fan", "auto", "cool")
FANS = ("low", "medium", "high")
CIRCS = ("recirc", "fresh")

SETPOINT_MIN = 60
SETPOINT_MAX = 90

# lv.ANIM and lv.ROLLER_MODE (as nested enum-group classes, the pattern that
# works for lv.DIR/lv.EVENT/lv.PART/etc. elsewhere in this file) don't exist
# in the actual binding -- confirmed by check_lvgl_api.py on real hardware.
# Using the plain numeric values instead: LV_ANIM_OFF and
# LV_ROLLER_MODE_NORMAL are both long-standing, stable 0 in upstream LVGL,
# so this is a safe substitute rather than another guess. If
# check_lvgl_api.py's search turns up the real symbolic names later, prefer
# those for readability.
_ANIM_OFF = 0
_ROLLER_MODE_NORMAL = 0


def _cycle(options, current, delta):
    try:
        idx = options.index(current)
    except ValueError:
        idx = 0
    return options[(idx + delta) % len(options)]


def _fmt_temp(v):
    return "%.1f\xc2\xb0F" % v if v is not None else "--"


def _transparent(parent):
    o = lv.obj(parent)
    o.set_style_bg_opa(lv.OPA.TRANSP, 0)
    o.set_style_border_width(0, 0)
    return o


def _label(parent, text="", font=None, color=theme.COLOR_TEXT):
    l = lv.label(parent)
    l.set_text(text)
    l.set_style_text_font(font or theme.FONT_BODY, 0)
    l.set_style_text_color(color, 0)
    return l


def _row(parent):
    r = _transparent(parent)
    r.set_size(lv.pct(100), lv.SIZE_CONTENT)
    r.set_flex_flow(lv.FLEX_FLOW.ROW)
    r.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    return r


def _make_tile(tileview, col, dir_):
    tile = tileview.add_tile(col, 0, dir_)
    tile.set_style_bg_color(theme.COLOR_BG, 0)
    tile.set_style_pad_all(theme.SPACE_LG, 0)
    tile.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    tile.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    tile.set_style_pad_row(theme.SPACE_MD, 0)
    return tile


def _make_roller(parent, options, group):
    r = lv.roller(parent)
    r.set_options(options, _ROLLER_MODE_NORMAL)
    r.set_visible_row_count(3)
    r.set_width(lv.pct(90))
    r.set_style_text_font(theme.FONT_BODY, 0)
    group.add_obj(r)
    return r


class HomeTile:
    def __init__(self, client, group, tileview):
        self.client = client
        self.group = group
        tile = _make_tile(tileview, 0, lv.DIR.RIGHT)

        self.conn_label = _label(tile, "Searching...", color=theme.COLOR_TEXT_MUTED)

        self.arc = lv.arc(tile)
        self.arc.set_size(180, 180)
        self.arc.set_range(SETPOINT_MIN, SETPOINT_MAX)
        self.arc.set_value(72)
        self.arc.set_style_arc_color(theme.COLOR_ACCENT, lv.PART.INDICATOR)
        self.arc.set_style_arc_color(theme.COLOR_TRACK, lv.PART.MAIN)
        self.arc.add_event_cb(self._on_arc_changed, lv.EVENT.VALUE_CHANGED, None)
        group.add_obj(self.arc)

        self.setpoint_label = lv.label(self.arc)
        self.setpoint_label.set_style_text_font(theme.FONT_DISPLAY, 0)
        self.setpoint_label.set_style_text_color(theme.COLOR_ACCENT, 0)
        self.setpoint_label.center()
        self.setpoint_label.set_text("--")

        summary = _row(tile)
        self.mode_label = _label(summary)
        self.fan_label = _label(summary)
        self.compressor_label = _label(summary)

        self.current_temp_label = _label(tile, color=theme.COLOR_TEXT_MUTED)

    def _on_arc_changed(self, e):
        asyncio.create_task(self.client.set_setpoint(float(self.arc.get_value())))

    def refresh(self):
        s = self.client.state
        self.conn_label.set_text("AirCon connected" if s.connected else "Searching for AirCon...")

        if self.group.get_focused() != self.arc:
            self.arc.set_value(int(s.setpoint))
        self.setpoint_label.set_text("%.0f\xc2\xb0F" % s.setpoint if s.setpoint else "--")

        self.mode_label.set_text("Mode: %s" % (s.mode or "--"))
        self.fan_label.set_text("Fan: %s" % (s.fan or "--"))
        self.compressor_label.set_text("Compressor: %s" % (s.compressor or "--"))
        self.current_temp_label.set_text("Cabin now: %s" % _fmt_temp(s.current_temp))


class ModeFanTile:
    def __init__(self, client, group, tileview):
        self.client = client
        self.group = group
        tile = _make_tile(tileview, 1, lv.DIR.HOR)

        row = _row(tile)
        row.set_size(lv.pct(100), lv.pct(85))

        mode_col = _transparent(row)
        mode_col.set_size(lv.pct(45), lv.pct(100))
        mode_col.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        mode_col.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        _label(mode_col, "Mode")
        self.mode_roller = _make_roller(mode_col, "Off\nFan\nAuto\nCool", group)
        self.mode_roller.add_event_cb(self._on_mode_changed, lv.EVENT.VALUE_CHANGED, None)

        fan_col = _transparent(row)
        fan_col.set_size(lv.pct(45), lv.pct(100))
        fan_col.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        fan_col.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        _label(fan_col, "Fan")
        self.fan_roller = _make_roller(fan_col, "Low\nMedium\nHigh", group)
        self.fan_roller.add_event_cb(self._on_fan_changed, lv.EVENT.VALUE_CHANGED, None)

    def _on_mode_changed(self, e):
        sel = self.mode_roller.get_selected()
        if sel < len(MODES):
            asyncio.create_task(self.client.set_mode(MODES[sel]))

    def _on_fan_changed(self, e):
        sel = self.fan_roller.get_selected()
        if sel < len(FANS):
            asyncio.create_task(self.client.set_fan(FANS[sel]))

    def refresh(self):
        s = self.client.state
        if self.group.get_focused() != self.mode_roller and s.mode in MODES:
            self.mode_roller.set_selected(MODES.index(s.mode), _ANIM_OFF)
        if self.group.get_focused() != self.fan_roller and s.fan in FANS:
            self.fan_roller.set_selected(FANS.index(s.fan), _ANIM_OFF)


class CirculationTile:
    def __init__(self, client, group, tileview):
        self.client = client
        self.group = group
        tile = _make_tile(tileview, 2, lv.DIR.HOR)

        _label(tile, "Circulation")
        self.circ_roller = _make_roller(tile, "Recirculate\nFresh air", group)
        self.circ_roller.add_event_cb(self._on_changed, lv.EVENT.VALUE_CHANGED, None)

    def _on_changed(self, e):
        sel = self.circ_roller.get_selected()
        if sel < len(CIRCS):
            asyncio.create_task(self.client.set_circulation(CIRCS[sel]))

    def refresh(self):
        s = self.client.state
        if self.group.get_focused() != self.circ_roller and s.circulation in CIRCS:
            self.circ_roller.set_selected(CIRCS.index(s.circulation), _ANIM_OFF)


class SettingsTile:
    """Rebuilds its rows whenever the set of keys the controller reports
    changes -- the settings map is dynamic (see aircon.go's SettingValue).
    """

    def __init__(self, client, group, tileview):
        self.client = client
        self.group = group
        self.tile = _make_tile(tileview, 3, lv.DIR.HOR)
        _label(self.tile, "Settings")

        self.list = _transparent(self.tile)
        self.list.set_size(lv.pct(100), lv.pct(80))
        self.list.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.list.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        self.list.set_scroll_dir(lv.DIR.VER)

        self._built_keys = []
        self._sliders = {}
        self._value_labels = {}

    def sync(self):
        keys = sorted(self.client.state.settings.keys())
        if keys == self._built_keys:
            return
        self._built_keys = keys
        self.list.clean()
        self._sliders = {}
        self._value_labels = {}

        for key in keys:
            row = _transparent(self.list)
            row.set_size(lv.pct(100), lv.SIZE_CONTENT)
            row.set_flex_flow(lv.FLEX_FLOW.COLUMN)
            row.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

            _label(row, key)

            sv = self.client.state.settings[key]
            slider = lv.slider(row)
            slider.set_width(lv.pct(90))
            slider.set_range(int(sv["default"] - 10), int(sv["default"] + 10))
            slider.set_value(int(sv["value"]), _ANIM_OFF)
            slider.set_style_bg_color(theme.COLOR_ACCENT, lv.PART.INDICATOR)
            self.group.add_obj(slider)

            def make_handler(k=key):
                def handler(e):
                    slider = e.get_target_obj()
                    asyncio.create_task(self.client.set_setting(k, float(slider.get_value())))
                return handler

            slider.add_event_cb(make_handler(), lv.EVENT.VALUE_CHANGED, None)

            value_label = _label(row, color=theme.COLOR_TEXT_MUTED)

            self._sliders[key] = slider
            self._value_labels[key] = value_label

    def refresh(self):
        self.sync()
        for key, sv in self.client.state.settings.items():
            slider = self._sliders.get(key)
            label = self._value_labels.get(key)
            if slider is None:
                continue
            if self.group.get_focused() != slider:
                slider.set_value(int(sv["value"]), _ANIM_OFF)
            label.set_text("%.1f (default %.1f)" % (sv["value"], sv["default"]))


class StatusTile:
    def __init__(self, client, group, tileview):
        self.client = client
        tile = _make_tile(tileview, 4, lv.DIR.LEFT)
        _label(tile, "Status")

        self.cabin = _label(tile)
        self.blower = _label(tile)
        self.exhaust = _label(tile)
        self.baggage = _label(tile)
        self.tail = _label(tile)
        self.error = _label(tile, color=theme.COLOR_DANGER)

    def refresh(self):
        s = self.client.state
        self.cabin.set_text("Cabin: %s" % _fmt_temp(s.cabin_temp))
        self.blower.set_text("Blower: %s" % _fmt_temp(s.blower_temp))
        self.exhaust.set_text("Exhaust: %s" % _fmt_temp(s.exhaust_temp))
        self.baggage.set_text("Baggage: %s" % _fmt_temp(s.baggage_temp))
        self.tail.set_text("Tail: %s" % _fmt_temp(s.tail_temp))
        self.error.set_text(s.error or "")


class App:
    def __init__(self, client, group, scr):
        # `scr` (the active screen) is passed in from main.py rather than
        # fetched here via lv.screen_active() -- see main.py's call site for
        # why (a red herring from when the real culprit, theme.py's custom
        # font loading, was still misattributed to this constructor). Kept
        # as-is since it's a harmless, reasonable way to avoid a redundant
        # getter call either way.
        self.client = client
        self.group = group

        self.tileview = lv.tileview(scr)
        self.tileview.set_size(lv.pct(100), lv.pct(100))
        self.tileview.set_style_bg_color(theme.COLOR_BG, 0)

        # Printed per-tile (not per-widget) so a failure inside any one
        # tile's construction is still easy to localize, without the
        # earlier per-line verbosity now that the real cause (theme.py's
        # font loading, not tileview/widget construction) is understood.
        self.tiles = []
        for cls in (HomeTile, ModeFanTile, CirculationTile, SettingsTile, StatusTile):
            print("screens: creating", cls.__name__)
            self.tiles.append(cls(client, self.group, self.tileview))
            print("screens: created", cls.__name__)

    def refresh(self):
        for tile in self.tiles:
            tile.refresh()


def build(client, group, scr):
    """Returns the App. `group` is the lv.group_t hal.py's encoder indev
    drives -- created by main.py so it can be wired to the encoder before
    any widgets exist. `scr` is the active screen (lv.screen_active()),
    fetched by main.py -- see App.__init__'s comment for why.
    """
    return App(client, group, scr)
