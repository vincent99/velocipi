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
    return "%.0f\xc2\xb0F" % v if v else "--"


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


def _row(parent):
    r = _transparent(parent)
    r.set_size(lv.pct(100), lv.SIZE_CONTENT)
    r.set_flex_flow(lv.FLEX_FLOW.ROW)
    r.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    return r


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
    return tile


def _make_bare_tile(tileview, col, row, dir_):
    """A tile with no layout/padding of its own -- used for the main screen,
    which positions its gauge/grid manually to match the round panel.
    """
    tile = tileview.add_tile(col, row, dir_)
    tile.set_style_bg_color(theme.COLOR_BG, 0)
    tile.set_style_pad_all(0, 0)
    return tile


def _make_placeholder_tile(tileview, col, row, dir_, text):
    tile = _make_tile(tileview, col, row, dir_)
    _label(tile, text, font=theme.FONT_DISPLAY)
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


def _make_button_cell(parent):
    """Half-width flex cell that acts like a button (see _wire_button) --
    used for the mode/recirc cells in home.HomeTile's middle row.
    """
    cell = _transparent(parent)
    cell.set_size(lv.pct(50), lv.pct(100))
    cell.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    cell.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
    cell.add_flag(lv.obj.FLAG.CLICKABLE)
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
    """
    _seen = {"btn": False}

    def on_pressed(e):
        _seen["btn"] = encoder.button_pressed()

    def on_pressing(e):
        if encoder.button_pressed():
            _seen["btn"] = True

    def on_clicked(e):
        if _seen["btn"]:
            on_click()
        _seen["btn"] = False

    cell.add_event_cb(on_pressed, lv.EVENT.PRESSED, None)
    cell.add_event_cb(on_pressing, lv.EVENT.PRESSING, None)
    cell.add_event_cb(on_clicked, lv.EVENT.CLICKED, None)
