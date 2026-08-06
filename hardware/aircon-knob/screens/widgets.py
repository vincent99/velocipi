"""Shared LVGL widget-construction helpers used by more than one screen.

Screen-specific widgets/constants live in their own screens/*.py module
instead (home.py, connect.py, disconnected.py) -- this module is only for
things genuinely reused across them.
"""

import lvgl as lv

import theme


def _cycle(options, current, delta):
    try:
        idx = options.index(current)
    except ValueError:
        idx = 0
    return options[(idx + delta) % len(options)]


def _fmt_temp(v):
    # \xb0 is the single Unicode codepoint for "°" (U+00B0) -- an earlier
    # version of this used "\xc2\xb0" (presumably meant as the UTF-8 *byte*
    # encoding of "°"), but \x escapes in a plain str literal are per-
    # codepoint, not per-byte, so that produced two real characters ("Â" +
    # "°") instead of one, rendering as a broken-glyph box before the degree
    # sign.
    #
    # No "F" suffix, 1 decimal place -- "72.9°", not "73°F". >=100 drops
    # the decimal instead ("101°", not "101.9°") -- three digits plus a
    # decimal point didn't fit the space this label has. Widest possible
    # rendering is therefore "99.9°" (5 glyphs, from the <100 branch, since
    # the >=100 branch is never wider than "999°"); home.HomeTile's
    # current_temp_label sizing/positioning accounts for that width -- see
    # theme.FONT_CURRENT_TEMP's comment.
    if not v:
        return "--"
    if v >= 100.0:
        return "%.0f\xb0" % v
    return "%.1f\xb0" % v


def _transparent(parent):
    o = lv.obj(parent)
    o.set_style_bg_opa(lv.OPA.TRANSP, 0)
    o.set_style_border_width(0, 0)
    # Plain lv.obj is scrollable by default, so any of these purely
    # decorative/layout containers (rows, the circular grid, button cells)
    # shows a scrollbar the moment its flex content is even a pixel taller
    # than the container -- none of them are meant to scroll at all, so
    # just turn scrolling off outright rather than chasing exact sizing.
    # Doesn't affect the tileview's own swipe-driven scrolling, which
    # operates on the tileview widget itself, not these descendants.
    o.remove_flag(lv.obj.FLAG.SCROLLABLE)
    return o


def _label(parent, text="", font=None, color=theme.COLOR_TEXT):
    l = lv.label(parent)
    l.set_text(text)
    l.set_style_text_font(font or theme.FONT_BODY, 0)
    l.set_style_text_color(color, 0)
    return l


def _column(parent):
    c = _transparent(parent)
    c.set_size(lv.pct(100), lv.SIZE_CONTENT)
    c.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    c.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    return c


def _set_visible(obj, visible):
    if visible:
        obj.remove_flag(lv.obj.FLAG.HIDDEN)
    else:
        obj.add_flag(lv.obj.FLAG.HIDDEN)


def _make_tile(tileview, col, row, dir_):
    """A tile with centered flex content -- used for the placeholder
    screens, which are just a single centered label.
    """
    tile = tileview.add_tile(col, row, dir_)
    tile.set_style_bg_color(theme.COLOR_BG, 0)
    tile.set_style_pad_all(theme.SPACE_LG, 0)
    tile.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    tile.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    # Confirmed on real hardware: removing SCROLLABLE from the parent
    # tileview (see screens/__init__.py's App.__init__) does NOT stop an
    # individual tile from independently rubber-banding/scrolling under a
    # touch-drag -- each tile returned by add_tile() is its own ordinary
    # lv_obj, scrollable by default same as any plain lv.obj() (this is
    # exactly why widgets._transparent() always removes it too), and that's
    # a wholly separate flag from the tileview container's own. Home's tile
    # in particular has manually-positioned content with negative offsets
    # (see home.py's _TEMP_Y etc.) that plausibly overflows its bounds
    # vertically but not horizontally, matching the reported symptom
    # exactly: right/Temps swiped clean, up/down still rubber-banded.
    tile.remove_flag(lv.obj.FLAG.SCROLLABLE)
    return tile


def _make_bare_tile(tileview, col, row, dir_):
    """A tile with no layout/padding of its own -- used for the main screen,
    which positions its gauge/grid manually to match the round panel.
    """
    tile = tileview.add_tile(col, row, dir_)
    tile.set_style_bg_color(theme.COLOR_BG, 0)
    tile.set_style_pad_all(0, 0)
    # See _make_tile()'s comment above -- same reasoning applies here.
    tile.remove_flag(lv.obj.FLAG.SCROLLABLE)
    return tile


def _make_placeholder_tile(tileview, col, row, dir_, text):
    tile = _make_tile(tileview, col, row, dir_)
    _label(tile, text, font=theme.FONT_TITLE)
    return tile


def _make_screen(scr):
    """A full-screen container for a top-level (non-tile) screen -- Connect
    and Disconnected aren't part of the swipeable + grid, just shown/hidden
    in place of the tileview (see screens/__init__.py's App._show()).
    """
    o = lv.obj(scr)
    o.set_size(lv.pct(100), lv.pct(100))
    o.remove_flag(lv.obj.FLAG.SCROLLABLE)
    o.set_style_border_width(0, 0)
    o.set_style_bg_color(theme.COLOR_BG, 0)
    o.set_style_pad_all(theme.SPACE_LG, 0)
    o.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    o.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    return o


def _make_button_cell(parent, width, height):
    """Fixed-size flex cell (icon line over label line, see home.py's
    mode_icon_label/mode_text_label) that acts like a button (see
    _wire_button) -- used for the mode/recirc cells in home.HomeTile.
    Explicit pixel width/height, not a percentage of some parent row: those
    cells are manually positioned directly on home.py's self.tile (no flex
    grid), so there's no flex parent to size a percentage against.
    set_style_pad_all gives the two-line icon+label content some breathing
    room instead of shrink-wrapping tight to the text.

    Border + radius are always visible (not just on touch) so the touch
    target itself is legible; the fill color is left to _wire_button's
    hover/active feedback. BUTTON_RADIUS is a uniform corner radius on all
    four corners as the practical stand-in for "curve to match the round
    panel" -- LVGL styles don't support rounding only the outer two corners
    of a cell sitting flush against its neighbor. COLOR_BUTTON_OUTLINE
    (not COLOR_TRACK, used for the gauge's own track) is a duller gray so
    the outline doesn't compete with the icon/label content inside it.
    """
    cell = _transparent(parent)
    cell.set_size(width, height)
    cell.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    cell.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    cell.add_flag(lv.obj.FLAG.CLICKABLE)
    cell.set_style_radius(theme.BUTTON_RADIUS, 0)
    cell.set_style_clip_corner(True, 0)
    cell.set_style_border_width(2, 0)
    cell.set_style_border_color(theme.COLOR_BUTTON_OUTLINE, 0)
    cell.set_style_border_opa(lv.OPA.COVER, 0)
    cell.set_style_pad_all(theme.SPACE_MD, 0)
    return cell


def _wire_button(cell, encoder, on_click):
    """Wires a cell so `on_click()` fires only for a touch tap that
    coincides with the knob's push-button -- a bare tap (no button) or a
    bare button push (no touch, which LVGL never even sees an event for)
    both do nothing, per the interaction model described in
    screens/__init__.py's module docstring.

    `_seen["btn"]` latches True if the button was down at any point during
    the press (checked on PRESSED and again on every PRESSING tick, not
    just once) rather than only at the exact release instant, since the
    real ordering of "finger lifts" vs. "button switch releases" for this
    mechanically-coupled hardware isn't verified.

    Also drives visual touch feedback, independent of that click-gating
    latch: the cell fills with COLOR_HOVER as soon as it's touched, and
    upgrades to COLOR_ACTIVE for as long as the knob button is down too
    (falling back to hover, not clearing outright, if the button is
    released while still touching) -- cleared back to transparent once the
    touch itself lifts. NOT hardware-verified: this assumes LVGL's PRESSING
    event keeps firing periodically while a touch is held stationary (not
    just on movement), which is what lets the active-state upgrade react to
    a button press that happens mid-touch rather than only at touch-down.
    """
    _seen = {"btn": False, "touching": False}

    def _restyle():
        if not _seen["touching"]:
            cell.set_style_bg_opa(lv.OPA.TRANSP, 0)
            return
        cell.set_style_bg_opa(lv.OPA.COVER, 0)
        if encoder.button_pressed():
            cell.set_style_bg_color(theme.COLOR_ACTIVE, 0)
        else:
            cell.set_style_bg_color(theme.COLOR_HOVER, 0)

    def on_pressed(e):
        _seen["touching"] = True
        _seen["btn"] = encoder.button_pressed()
        _restyle()

    def on_pressing(e):
        if encoder.button_pressed():
            _seen["btn"] = True
        _restyle()

    def on_released(e):
        _seen["touching"] = False
        _restyle()

    def on_clicked(e):
        if _seen["btn"]:
            on_click()
        _seen["btn"] = False

    cell.add_event_cb(on_pressed, lv.EVENT.PRESSED, None)
    cell.add_event_cb(on_pressing, lv.EVENT.PRESSING, None)
    cell.add_event_cb(on_released, lv.EVENT.RELEASED, None)
    cell.add_event_cb(on_released, lv.EVENT.PRESS_LOST, None)
    cell.add_event_cb(on_clicked, lv.EVENT.CLICKED, None)


def _wire_swipe(obj, on_swipe):
    """Wires `obj` (must be CLICKABLE) to call `on_swipe(dx, dy)` with the
    total touch displacement (release point minus press point, in pixels)
    once a press-drag-release completes on it.

    Deliberately NOT LVGL's own gesture system (LV_EVENT_GESTURE) or a
    tileview's built-in scroll-to-snap -- screens/__init__.py's App
    disables tileview's touch-scrolling entirely (set_scroll_dir(NONE))
    since a press that started on a CLICKABLE child (e.g. home.HomeTile's
    mode/recirc buttons) but drifted a few pixels was getting stolen by
    the tileview's scroll-chain, turning an intended tap into an
    accidental page-drag. Measuring the raw drag distance ourselves here
    instead means navigation only triggers past a deliberately large,
    tunable threshold (see screens/__init__.py's App._SWIPE_THRESHOLD_*)
    rather than LVGL's own much smaller built-in gesture limit -- and
    since a press starting on a button fires PRESSED on that button, not
    on its parent tile (LVGL hit-tests the most specific/topmost object,
    events don't bubble to ancestors unless explicitly told to), this
    never interferes with _wire_button's own click handling above.

    NOT hardware-verified: e.get_indev() + a caller-owned lv.point_t()
    passed to indev.get_point() is this project's best guess at how to
    read a touch point from inside an LVGL Python event callback (a
    standard pattern in upstream LVGL's own C examples), but this is the
    first place anything in this codebase calls a method on the event
    object itself -- see check_lvgl_api.py. Wrapped in try/except so a
    wrong guess here just disables swipe navigation (logged once) instead
    of crashing the whole panel.
    """
    _state = {"x": 0, "y": 0, "ok": True}

    def _point(e):
        indev = e.get_indev()
        p = lv.point_t()
        indev.get_point(p)
        return p.x, p.y

    def on_pressed(e):
        if not _state["ok"]:
            return
        try:
            _state["x"], _state["y"] = _point(e)
        except Exception as ex:
            _state["ok"] = False
            print("widgets: swipe tracking disabled, point read failed:", type(ex), ex.args)

    def on_released(e):
        if not _state["ok"]:
            return
        try:
            x, y = _point(e)
        except Exception as ex:
            _state["ok"] = False
            print("widgets: swipe tracking disabled, point read failed:", type(ex), ex.args)
            return
        on_swipe(x - _state["x"], y - _state["y"])

    obj.add_event_cb(on_pressed, lv.EVENT.PRESSED, None)
    obj.add_event_cb(on_released, lv.EVENT.RELEASED, None)
