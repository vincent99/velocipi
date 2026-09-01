"""One-shot LVGL API sanity check -- run this BEFORE main.py to catch any
remaining `lv.*` name mismatches in one pass instead of one flash-cycle per
AttributeError. This project's code was written against the LVGL Python
binding's well-established naming convention, but not verified against the
actual generated binding (no hardware available while writing it) -- this
script builds one of everything main.py/hal.py/screens/*.py/theme.py touch
and reports exactly what's missing, without needing the BLE/display/touch
hardware to be working first (a no-op dummy display stands in for the real
GC9A01 -- see build_dummy_display() -- since widgets need *some* registered
display to exist safely, even off real hardware).

Usage:
    mpremote run check_lvgl_api.py

Every check is wrapped individually so one missing name doesn't stop the
rest from being checked -- read the whole output, don't stop at the first
FAIL. On an AttributeError, it also searches dir(lv) (or dir() of the
relevant object) for likely candidates, so a wrong guess is actionable
immediately instead of needing another round trip.
"""

import lvgl as lv

_fails = []


def check(label, fn, search_in=None, search_term=None):
    try:
        result = fn()
        print("OK   ", label, "->", result)
        return result
    except AttributeError as e:
        print("FAIL ", label, "->", e)
        _fails.append(label)
        if search_in is not None:
            term = (search_term or label.split(".")[-1].split("(")[0]).upper()
            hits = [n for n in dir(search_in) if term in n.upper()]
            print("      candidates:", hits)
        return None
    except Exception as e:
        print("ERR  ", label, "-> unexpected:", type(e).__name__, e)
        _fails.append(label)
        return None


print("=== lv.init() ===")
lv.init()

print("\n=== module-level lv.* names ===")
for name in (
    "color_hex", "obj", "label", "roller", "arc", "slider",
    "tileview", "pct", "SIZE_CONTENT", "screen_active", "group_create",
    "timer_handler", "indev_create", "display_create", "DIR", "EVENT",
    "PART", "OPA", "FLEX_FLOW", "FLEX_ALIGN", "SYMBOL", "SCROLLBAR_MODE",
    "INDEV_TYPE", "INDEV_STATE", "COLOR_FORMAT", "DISPLAY_RENDER_MODE", "ALIGN",
):
    check("lv." + name, (lambda n=name: getattr(lv, n)), search_in=lv, search_term=name)

print("\n=== confirmed absent, worked around with plain 0 (screens/connect.py's roller) ===")
print("(lv.ANIM / lv.ROLLER_MODE don't exist as nested enum-group classes on")
print(" this binding -- screens/connect.py's roller (the Connect screen's")
print(" device picker) uses plain numeric values (_ANIM_OFF/_ROLLER_MODE_NORMAL)")
print(" instead. Not counted as failures below; only worth re-checking if")
print(" you're curious whether a real symbolic name exists somewhere else in")
print(" dir(lv).)")
for name in ("ANIM", "ROLLER_MODE"):
    hits = [n for n in dir(lv) if name in n.upper()]
    print("     dir(lv) containing %r: %s" % (name, hits))

print("\n=== lv.SYMBOL.* used for mode/recirc cell icons (screens/home.py) ===")
for name in ("POWER", "REFRESH", "LOOP", "TINT"):
    check("lv.SYMBOL." + name, (lambda n=name: getattr(lv.SYMBOL, n)), search_in=lv.SYMBOL, search_term=name)

print("\n=== lv.SYMBOL.BATTERY_* used for the fuel-level icon (screens/home.py's _fuel_icon()) ===")
for name in ("BATTERY_FULL", "BATTERY_3", "BATTERY_2", "BATTERY_1", "BATTERY_EMPTY"):
    check("lv.SYMBOL." + name, (lambda n=name: getattr(lv.SYMBOL, n)), search_in=lv.SYMBOL, search_term="BATTERY")

print("\n=== confirmed: obj flags are lv.obj.FLAG.*, not a top-level lv.OBJ_FLAG ===")
print("(found on real hardware: AttributeError: 'module' object has no")
print(" attribute 'OBJ_FLAG' -- unlike DIR/EVENT/PART/etc., which *are*")
print(" flat lv.* groups, this binding nests the obj-flag enum under the")
print(" lv.obj widget class itself, matching lv_binding_micropython's own")
print(" documented obj.add_flag(obj.FLAG.CLICKABLE) usage. screens/widgets.py's")
print(" add_flag/remove_flag calls use lv.obj.FLAG.* accordingly.)")
for name in ("CLICKABLE", "HIDDEN", "SCROLLABLE"):
    check(
        "lv.obj.FLAG." + name,
        (lambda n=name: getattr(lv.obj.FLAG, n)),
        search_in=lv.obj.FLAG,
        search_term=name,
    )

print("\n=== enum members actually used in this project ===")
for path in (
    "DIR.RIGHT", "DIR.LEFT", "DIR.HOR", "DIR.VER", "DIR.TOP", "DIR.BOTTOM", "DIR.NONE",
    "EVENT.VALUE_CHANGED", "EVENT.PRESSED", "EVENT.PRESSING", "EVENT.CLICKED",
    "EVENT.RELEASED", "EVENT.PRESS_LOST",
    "ALIGN.BOTTOM_MID",
    "PART.MAIN", "PART.INDICATOR", "PART.KNOB",
    "OPA.TRANSP", "OPA.COVER",
    "FLEX_FLOW.COLUMN", "FLEX_FLOW.ROW",
    "FLEX_ALIGN.START", "FLEX_ALIGN.CENTER", "FLEX_ALIGN.SPACE_EVENLY",
    "INDEV_TYPE.ENCODER", "INDEV_TYPE.POINTER",
    "INDEV_STATE.PRESSED", "INDEV_STATE.RELEASED",
    "COLOR_FORMAT.RGB565",
):
    group_name, member = path.split(".")

    def get(g=group_name, m=member):
        return getattr(getattr(lv, g), m)

    # If lv.<group_name> itself doesn't exist this'll AttributeError on the
    # outer getattr -- searches dir(lv) for the group name, which is more
    # useful here than searching for the member name.
    check("lv." + path, get, search_in=lv, search_term=group_name)

print("\n=== lv.group_t ===")
group = check("lv.group_create()", lv.group_create)
if group is not None:
    check("group.set_default()", group.set_default, search_in=group)
    check("group.get_focused()", group.get_focused, search_in=group)

print("\n=== lv.indev_t ===")
indev = check("lv.indev_create()", lv.indev_create)
if indev is not None:
    check("indev.set_type(...)", lambda: indev.set_type(lv.INDEV_TYPE.ENCODER), search_in=indev)
    check("indev.set_read_cb(...)", lambda: indev.set_read_cb(lambda i, d: None), search_in=indev)
    if group is not None:
        check("indev.set_group(group)", lambda: indev.set_group(group), search_in=indev)

    # Used by screens/widgets.py's _wire_swipe() to read a touch point for
    # swipe-distance tracking. lv.point_t (distinct from lv.point_precise_t,
    # used by screens/disconnected.py's line -- see further down) and
    # indev.get_point() are checkable here directly; e.get_indev() (getting
    # *this* indev back out from inside a live event callback, which is
    # what _wire_swipe() actually does) is NOT checkable by this script at
    # all -- it needs a real event to have actually fired, which requires
    # live touch input, not just object construction/method lookup. If
    # swipe navigation doesn't work on real hardware, that's the first
    # thing to check by hand (e.g. print(dir(e)) inside a PRESSED handler).
    point = check("lv.point_t({...})", lambda: lv.point_t({"x": 0, "y": 0}), search_in=lv, search_term="point")
    if point is not None:
        check("indev.get_point(point)", lambda: indev.get_point(point), search_in=indev, search_term="point")


def build_dummy_display():
    """A no-op display: widgets need *a* registered display to exist safely
    (lv.screen_active() returns None with none registered, and creating
    widgets with a None parent before any display exists is the likely
    cause of a hang seen in testing) -- this stands in for hal.py's real
    GC9A01 setup so the widget checks below don't depend on real hardware.
    """
    def _flush_cb(disp, area, px_map):
        disp.flush_ready()

    disp = lv.display_create(240, 240)
    disp.set_color_format(lv.COLOR_FORMAT.RGB565)
    buf = bytearray(240 * 10 * 2)
    disp.set_buffers(buf, None, len(buf), lv.DISPLAY_RENDER_MODE.PARTIAL)
    disp.set_flush_cb(_flush_cb)
    return disp


print("\n=== dummy display (stand-in for hal.py's real GC9A01 setup) ===")
disp = check("build_dummy_display()", build_dummy_display)

print("\n=== widgets (parented to lv.screen_active()) ===")
scr = check("lv.screen_active()", lv.screen_active)
if scr is None:
    print("      lv.screen_active() is None -- dummy display setup above must")
    print("      have failed; skipping widget checks (would likely hang, per")
    print("      the last run, rather than raise a catchable error).")
else:
    tile_parent = scr
    tv = check("lv.tileview(scr)", lambda: lv.tileview(scr))
    if tv is not None:
        # App.__init__ removes SCROLLABLE from the tileview itself (unlike
        # widgets._transparent()'s containers, which do the same thing but
        # for unrelated decorative reasons) to kill its built-in touch-
        # scroll/gesture-navigate entirely -- two lesser attempts before
        # this (set_scroll_dir(NONE), then creating every tile with
        # dir_=NONE) both turned out insufficient on real hardware: the
        # tileview still rubber-banded under a touch-drag and still showed
        # its scrollbar either way. Removing SCROLLABLE outright is the
        # unambiguous fix -- no scroll capability at all means no drag
        # response, no rubber-band, no scrollbar. Done immediately after
        # construction, before add_tile()/set_tile_by_index() below, to
        # mirror App.__init__'s actual ordering and specifically verify
        # those two calls still work on a tile *after* this rather than
        # just in isolation.
        check("tv.remove_flag(SCROLLABLE)", lambda: tv.remove_flag(lv.obj.FLAG.SCROLLABLE), search_in=tv)
        check(
            "tv.add_tile(0,0,DIR.NONE)",
            lambda: tv.add_tile(0, 0, lv.DIR.NONE),
            search_in=tv,
            search_term="tile",
        )
        # screens/__init__.py's App.poll_input() uses this to tell which tile in the
        # +-shaped grid is currently active, to gate the knob to the main
        # screen only. Confirmed on real hardware: it's get_tile_active(),
        # not get_tile_act() (lv_tileview_get_tile_act() in upstream LVGL C
        # -- this binding renamed it). Wrapped in a lambda so a wrong guess
        # is caught by check()'s own try/except instead of raising while
        # this argument list is being built, before check() is even
        # entered -- an earlier unwrapped `tv.get_tile_act` reference here
        # crashed the whole script instead of reporting FAIL + candidates
        # like every other check.
        check("tv.get_tile_active()", lambda: tv.get_tile_active(), search_in=tv, search_term="tile")
        # App.__init__ uses this to force the initially-visible tile to
        # Home (1,1) -- a tileview otherwise opens on grid cell (0,0), which
        # is empty in the app's + shaped layout. Also App._wire_tile_swipe()'s
        # own means of jumping tiles on a qualifying swipe, now that
        # SCROLLABLE's gone -- if this still works with SCROLLABLE removed
        # above, so does that.
        check(
            "tv.set_tile_by_index(0,0,False)",
            lambda: tv.set_tile_by_index(0, 0, False),
            search_in=tv,
            search_term="tile",
        )
        # App.__init__ also calls this, though it's likely a no-op now that
        # SCROLLABLE (and therefore any scrollbar) is gone -- kept in case
        # it isn't.
        check(
            "tv.set_scrollbar_mode(OFF)",
            lambda: tv.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF),
            search_in=tv,
            search_term="scrollbar",
        )
        tile_parent = tv

    obj = check("lv.obj(parent)", lambda: lv.obj(tile_parent))
    if obj is not None:
        check("obj.set_size(pct,pct)", lambda: obj.set_size(lv.pct(50), lv.pct(50)), search_in=obj, search_term="set_size")
        check("obj.set_style_bg_opa", lambda: obj.set_style_bg_opa(lv.OPA.TRANSP, 0), search_in=obj)
        check("obj.set_style_border_width", lambda: obj.set_style_border_width(0, 0), search_in=obj)
        check("obj.set_style_bg_color", lambda: obj.set_style_bg_color(lv.color_hex(0), 0), search_in=obj)
        # Used by screens/widgets.py's _make_button_cell for the mode/recirc
        # buttons' always-visible outline.
        check(
            "obj.set_style_border_color",
            lambda: obj.set_style_border_color(lv.color_hex(0), 0),
            search_in=obj,
            search_term="border",
        )
        check(
            "obj.set_style_border_opa",
            lambda: obj.set_style_border_opa(lv.OPA.COVER, 0),
            search_in=obj,
            search_term="border",
        )
        check("obj.set_style_pad_all", lambda: obj.set_style_pad_all(4, 0), search_in=obj)
        # Used by screens/settings.py's SettingsTile for the gap between a
        # cell's value and label (value on top, label below).
        check("obj.set_style_pad_row", lambda: obj.set_style_pad_row(4, 0), search_in=obj)
        # Used by screens/history.py's HistoryTile for the gap between the
        # setpoint/current_temp readout labels -- confirmed present in
        # lvgl.pyi right next to set_style_pad_row above, same signature,
        # but never actually run until this check does.
        check("obj.set_style_pad_column", lambda: obj.set_style_pad_column(4, 0), search_in=obj, search_term="pad")
        # Used by screens/disconnected.py's label background padding.
        check("obj.set_style_pad_hor", lambda: obj.set_style_pad_hor(4, 0), search_in=obj, search_term="pad")
        check("obj.set_style_pad_ver", lambda: obj.set_style_pad_ver(4, 0), search_in=obj, search_term="pad")
        check("obj.set_flex_flow", lambda: obj.set_flex_flow(lv.FLEX_FLOW.COLUMN), search_in=obj)
        check(
            "obj.set_flex_align",
            lambda: obj.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER),
            search_in=obj,
        )
        check("obj.set_scroll_dir", lambda: obj.set_scroll_dir(lv.DIR.VER), search_in=obj)
        check("obj.clean()", obj.clean, search_in=obj)
        # Used by screens/home.py's HomeTile to keep the gauge arc's ring
        # strokes painting on top of the current-temp cell's compressor-on
        # background fill, regardless of the two objects' creation order.
        check("obj.move_foreground()", obj.move_foreground, search_in=obj, search_term="move_foreground")
        # Used by screens/home.py's HomeTile to anchor the fan/setpoint
        # stack to the bottom of the tile -- first use of .align() anywhere
        # in this codebase (everything else so far has used .center(),
        # confirmed working below).
        check(
            "obj.align(BOTTOM_MID)",
            lambda: obj.align(lv.ALIGN.BOTTOM_MID, 0, 0),
            search_in=obj,
            search_term="align",
        )
        # Used by screens/home.py's HomeTile (circular grid inset) and
        # screens/widgets.py's _make_button_cell()/_set_visible()
        # (mode/recirc click targets, setpoint label show/hide).
        check("obj.set_style_radius", lambda: obj.set_style_radius(4, 0), search_in=obj, search_term="radius")
        # Used by screens/history.py's HistoryTile for a one-shot geometry
        # diagnostic (real content height/y-position vs. the hand-computed
        # axis math's assumptions) while chasing a value-dependent y-axis
        # scale mismatch that isn't explained by the formula itself.
        check("obj.get_height", obj.get_height, search_in=obj, search_term="height")
        check("obj.get_content_height", obj.get_content_height, search_in=obj, search_term="height")
        check("obj.get_y", obj.get_y, search_in=obj, search_term="get_y")
        # Used by screens/history.py's HistoryTile for the current_temp
        # fade-to-transparent overlay (a plain lv.obj, not chart-specific --
        # draw_series_bar() in lv_chart.c forces PART.ITEMS' own bg_grad off
        # unconditionally, so a real gradient isn't achievable on the chart's
        # bars themselves; this workaround needs the generic style props on
        # an ordinary obj instead).
        check("lv.GRAD_DIR.VER", lambda: lv.GRAD_DIR.VER, search_in=lv, search_term="grad_dir")
        check(
            "obj.set_style_bg_grad_color",
            lambda: obj.set_style_bg_grad_color(lv.color_hex(0), 0),
            search_in=obj,
            search_term="grad",
        )
        check(
            "obj.set_style_bg_grad_dir",
            lambda: obj.set_style_bg_grad_dir(lv.GRAD_DIR.VER, 0),
            search_in=obj,
            search_term="grad",
        )
        check(
            "obj.set_style_bg_grad_opa",
            lambda: obj.set_style_bg_grad_opa(lv.OPA._60, 0),
            search_in=obj,
            search_term="grad",
        )
        check(
            "obj.set_style_clip_corner",
            lambda: obj.set_style_clip_corner(True, 0),
            search_in=obj,
            search_term="clip",
        )
        check(
            "obj.add_flag(CLICKABLE)",
            lambda: obj.add_flag(lv.obj.FLAG.CLICKABLE),
            search_in=obj,
            search_term="flag",
        )
        check(
            "obj.remove_flag(HIDDEN)",
            lambda: obj.remove_flag(lv.obj.FLAG.HIDDEN),
            search_in=obj,
            search_term="flag",
        )
        # Used by screens/widgets.py's _transparent() so a press/release
        # starting on any ordinary layout container/button cell still
        # reaches App._wire_tile_swipe()'s tile-level handler.
        check(
            "obj.add_flag(EVENT_BUBBLE)",
            lambda: obj.add_flag(lv.obj.FLAG.EVENT_BUBBLE),
            search_in=obj,
            search_term="flag",
        )
        check(
            "obj.add_event_cb(PRESSED)",
            lambda: obj.add_event_cb(lambda e: None, lv.EVENT.PRESSED, None),
            search_in=obj,
            search_term="event",
        )
        # Used by screens/widgets.py's _wire_button for hover/active touch
        # feedback on the mode/recirc button cells -- reverting the fill
        # back to transparent on either a normal release or the touch
        # sliding off the widget mid-press.
        check(
            "obj.add_event_cb(RELEASED)",
            lambda: obj.add_event_cb(lambda e: None, lv.EVENT.RELEASED, None),
            search_in=obj,
            search_term="event",
        )
        check(
            "obj.add_event_cb(PRESS_LOST)",
            lambda: obj.add_event_cb(lambda e: None, lv.EVENT.PRESS_LOST, None),
            search_in=obj,
            search_term="event",
        )

    label = check("lv.label(parent)", lambda: lv.label(tile_parent))
    if label is not None:
        check("label.set_text", lambda: label.set_text("hi"), search_in=label)
        check(
            "label.set_style_text_font",
            lambda: label.set_style_text_font(lv.font_montserrat_14, 0),
            search_in=label,
            search_term="font",
        )
        check("label.set_style_text_color", lambda: label.set_style_text_color(lv.color_hex(0), 0), search_in=label)
        check("label.center()", label.center, search_in=label)
        check("label.set_style_text_opa", lambda: label.set_style_text_opa(128, 0), search_in=label)
        # Used by screens/info.py's InfoTile for the wrapped error text --
        # fixed width so wrapping has something to wrap against, WRAP mode
        # (LVGL's own default for a label, but set explicitly here so it
        # doesn't silently depend on that default), and flex_grow(1) so it
        # claims whatever vertical space is left under the title/version
        # lines instead of shrink-wrapping to its own content height.
        check("label.set_width(pct)", lambda: label.set_width(lv.pct(100)), search_in=label)
        check(
            "label.set_long_mode(WRAP)",
            lambda: label.set_long_mode(lv.label.LONG_MODE.WRAP),
            search_in=label,
            search_term="long_mode",
        )
        check("label.set_flex_grow", lambda: label.set_flex_grow(1), search_in=label, search_term="flex")
        # Used by screens/info.py's InfoTile to center every line of text
        # (title/version lines and the wrapped error text alike) -- lv.TEXT_ALIGN
        # is a top-level class (unlike LONG_MODE above, which is nested under
        # lv.label), confirmed via lvgl.pyi.
        check(
            "label.set_style_text_align",
            lambda: label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0),
            search_in=label,
            search_term="align",
        )
        # theme.py's FONT_TITLE/FONT_BUTTON_LABEL/FONT_BUTTON_ICON -- montserrat
        # 12-48 are only in this project's LVGL image as of the mode/recirc
        # button restyle, so confirm the specific sizes theme.py now loads
        # actually resolve (lv.font_montserrat_14 above predates that build).
        for size in (12, 18, 20, 32, 36):
            check(
                "lv.font_montserrat_%d" % size,
                (lambda s=size: getattr(lv, "font_montserrat_%d" % s)),
                search_in=lv,
                search_term="font_montserrat",
            )

        # screens/home.py's fuel-level icon rotates 90 degrees left via
        # these three -- set_style_transform_rotation is this project's
        # best guess at LVGL v9's name for what v8 called
        # set_style_transform_angle (lvgl_micropython, this project's
        # firmware fork, tracks v9). home.py wraps its own actual use of
        # these in try/except (a wrong guess here just leaves that icon
        # unrotated, not crashing), but check here too so a wrong guess is
        # visible before ever flashing, not just silently swallowed at
        # runtime.
        check(
            "label.set_style_transform_pivot_x",
            lambda: label.set_style_transform_pivot_x(lv.pct(50), 0),
            search_in=label,
            search_term="transform",
        )
        check(
            "label.set_style_transform_pivot_y",
            lambda: label.set_style_transform_pivot_y(lv.pct(50), 0),
            search_in=label,
            search_term="transform",
        )
        check(
            "label.set_style_transform_rotation",
            lambda: label.set_style_transform_rotation(-900, 0),
            search_in=label,
            search_term="transform",
        )
        # screens/home.py's fuel icon also nudges itself up a few px this
        # way, to align with the larger percent label next to it inside a
        # flex ROW container (whose own CENTER cross-align only centers
        # bounding boxes, not text baselines) -- translate_x/y is long-
        # standing, unrenamed-since-v8 LVGL style API, so this is a much
        # safer bet than the transform_rotation guess above, but still not
        # independently confirmed against this specific binding.
        check(
            "label.set_style_translate_y",
            lambda: label.set_style_translate_y(-4, 0),
            search_in=label,
            search_term="translate",
        )

    arc = check("lv.arc(parent)", lambda: lv.arc(tile_parent))
    if arc is not None:
        check("arc.set_size", lambda: arc.set_size(100, 100), search_in=arc)
        check("arc.set_range", lambda: arc.set_range(0, 100), search_in=arc)
        check("arc.set_value", lambda: arc.set_value(50), search_in=arc)
        check("arc.get_value", arc.get_value, search_in=arc)
        check("arc.set_style_arc_color", lambda: arc.set_style_arc_color(lv.color_hex(0), lv.PART.MAIN), search_in=arc)
        check(
            "arc.add_event_cb",
            lambda: arc.add_event_cb(lambda e: None, lv.EVENT.VALUE_CHANGED, None),
            search_in=arc,
            search_term="event",
        )
        # New in HomeTile's outer dial gauge: a wide sweep (not a full
        # circle) via set_bg_angles, a thicker track/indicator, and a
        # display-only arc (no draggable knob, doesn't intercept swipes).
        check("arc.set_bg_angles", lambda: arc.set_bg_angles(120, 60), search_in=arc, search_term="angle")
        check(
            "arc.set_style_arc_width",
            lambda: arc.set_style_arc_width(20, lv.PART.MAIN),
            search_in=arc,
            search_term="width",
        )
        check(
            "arc.set_style_bg_opa(KNOB)",
            lambda: arc.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.KNOB),
            search_in=arc,
            search_term="opa",
        )
        check("arc.remove_flag(CLICKABLE)", lambda: arc.remove_flag(lv.obj.FLAG.CLICKABLE), search_in=arc, search_term="flag")

    print("\n=== six ring-segment arcs, padded gaps (HomeTile's radial mode menu) ===")
    print("(API-existence only -- this can't verify the *visual* result, i.e.")
    print(" whether six of these actually render as six distinct ring segments")
    print(" with a visible gap between each and no rounded-cap bleed between")
    print(" neighbors. An earlier near-full-radius version of this menu (width")
    print(" 110 out of a 236 diameter, no arc_rounded call) rendered on real")
    print(" hardware as big overlapping blobs instead -- see screens/home.py's")
    print(" _init_mode_menu() for the fix this now exercises; check on-device")
    print(" once real hardware is available.)")
    menu_parent = check("lv.obj(parent) (menu container)", lambda: lv.obj(tile_parent))
    if menu_parent is not None:
        wedge = check("lv.arc(menu_parent) (wedge)", lambda: lv.arc(menu_parent))
        if wedge is not None:
            check("wedge.set_bg_angles(0,54)", lambda: wedge.set_bg_angles(0, 54), search_in=wedge, search_term="angle")
            # A narrow ring (not near-full-radius) drawn inward from the
            # wedge's own outer edge -- see _MENU_RING_WIDTH's comment in
            # screens/home.py for why this (plus the padding above and
            # arc_rounded below) replaced the earlier full-radius-wedge
            # design.
            check(
                "wedge.set_style_arc_width(50, MAIN)",
                lambda: wedge.set_style_arc_width(50, lv.PART.MAIN),
                search_in=wedge,
                search_term="width",
            )
            # Suppresses the separate INDICATOR layer an arc draws by
            # default (this menu only wants each wedge's MAIN track
            # visible) -- 0 width, not a color/opa trick.
            check(
                "wedge.set_style_arc_width(0, INDICATOR)",
                lambda: wedge.set_style_arc_width(0, lv.PART.INDICATOR),
                search_in=wedge,
                search_term="width",
            )
            # Disables the arc's default rounded end-caps -- the actual fix
            # for the "big overlapping blobs" bug (see this section's own
            # print() above), by analogy with the already-confirmed-working
            # line.set_style_line_rounded(False, 0) in screens/disconnected.py.
            # NOT independently confirmed to exist on this binding until this
            # runs on real hardware.
            check(
                "wedge.set_style_arc_rounded(False, MAIN)",
                lambda: wedge.set_style_arc_rounded(False, lv.PART.MAIN),
                search_in=wedge,
                search_term="round",
            )

    print("\n=== lv.chart (screens/history.py's HistoryTile graph) ===")
    chart = check("lv.chart(parent)", lambda: lv.chart(tile_parent), search_in=lv, search_term="chart")
    if chart is not None:
        check("chart.set_size", lambda: chart.set_size(180, 150), search_in=chart)
        check(
            "chart.remove_flag(SCROLLABLE)",
            lambda: chart.remove_flag(lv.obj.FLAG.SCROLLABLE),
            search_in=chart,
            search_term="flag",
        )
        # lv.chart.TYPE, not a module-level lv.CHART_TYPE -- same nested-
        # under-the-widget-class pattern as lv.label.LONG_MODE, confirmed
        # via lvgl.pyi this time instead of guessed after a crash.
        check("chart.set_type(LINE)", lambda: chart.set_type(lv.chart.TYPE.LINE), search_in=chart, search_term="type")
        # BAR -- screens/history.py's current_temp fill (see its module
        # docstring for why: this build's LINE-type draw path never reads
        # PART.ITEMS' bg_opa at all, confirmed by reading lv_chart.c, so
        # the "area fill via bg_opa" check below doesn't actually produce
        # a filled area -- kept only because the call itself is harmless
        # and BAR needs its own type-switch verified).
        check("chart.set_type(BAR)", lambda: chart.set_type(lv.chart.TYPE.BAR), search_in=chart, search_term="type")
        check("chart.set_type(LINE) (restore)", lambda: chart.set_type(lv.chart.TYPE.LINE), search_in=chart)
        check(
            "chart.set_div_line_count",
            lambda: chart.set_div_line_count(0, 0),
            search_in=chart,
            search_term="div_line",
        )
        # Point count == the graph's pixel width (1 point/pixel, see
        # aircon_ble.py's _HISTORY_MAX_POINTS) -- despite the stub's own
        # parameter name ("delay_ms"), which is a stub-generation artifact,
        # not the real meaning (same kind of mislabeling set_point_count's
        # neighboring set_hor/ver_div_line_count(delay_ms) methods show for
        # an unrelated function -- the generator clearly reused one
        # parameter name template across several C signatures it didn't
        # individually describe).
        check("chart.set_point_count", lambda: chart.set_point_count(180), search_in=chart, search_term="point_count")
        check(
            "chart.set_axis_range(PRIMARY_Y)",
            lambda: chart.set_axis_range(lv.chart.AXIS.PRIMARY_Y, 0, 100),
            search_in=chart,
            search_term="axis_range",
        )
        temp_series = check(
            "chart.add_series (current_temp)",
            lambda: chart.add_series(lv.color_hex(0x0000FF), lv.chart.AXIS.PRIMARY_Y),
            search_in=chart,
            search_term="series",
        )
        if temp_series is not None:
            check(
                "chart.set_series_value_by_id",
                lambda: chart.set_series_value_by_id(temp_series, 0, 50),
                search_in=chart,
                search_term="series_value",
            )
            check(
                "lv.CHART_POINT_NONE",
                lambda: chart.set_series_value_by_id(temp_series, 1, lv.CHART_POINT_NONE),
                search_in=lv,
                search_term="chart_point",
            )
            # NOT an area fill (see the BAR-type comment above) -- kept as a
            # plain style-call smoke test, not a claim that this renders
            # anything visible for a LINE-type series.
            check(
                "chart.set_style_bg_opa(ITEMS)",
                lambda: chart.set_style_bg_opa(lv.OPA._30, lv.PART.ITEMS),
                search_in=chart,
                search_term="opa",
            )
            # screens/history.py's BAR-type fill needs block_gap (PART.MAIN's
            # pad_column) forced to 0, and its LINE-type setpoint series
            # needs a thinner-than-default PART.ITEMS line_width.
            check(
                "chart.set_style_pad_column(MAIN)",
                lambda: chart.set_style_pad_column(0, lv.PART.MAIN),
                search_in=chart,
                search_term="pad",
            )
            check(
                "chart.set_style_line_width(ITEMS)",
                lambda: chart.set_style_line_width(1, lv.PART.ITEMS),
                search_in=chart,
                search_term="line_width",
            )
            check(
                "chart.set_style_radius(ITEMS)",
                lambda: chart.set_style_radius(0, lv.PART.ITEMS),
                search_in=chart,
                search_term="radius",
            )
        setpoint_series = check(
            "chart.add_series (setpoint, 2nd series)",
            lambda: chart.add_series(lv.color_hex(0xFF0000), lv.chart.AXIS.PRIMARY_Y),
            search_in=chart,
            search_term="series",
        )
        cursor = check(
            "chart.add_cursor",
            lambda: chart.add_cursor(lv.color_hex(0xFFFFFF), lv.DIR.VER),
            search_in=chart,
            search_term="cursor",
        )
        # screens/history.py hides the cursor by toggling PART.CURSOR's own
        # opacity (found on real hardware to be more reliable than
        # set_cursor_point(..., CHART_POINT_NONE), which lv_chart.c's
        # draw_cursors() is supposed to special-case but didn't in practice).
        check(
            "chart.set_style_opa(CURSOR)",
            lambda: chart.set_style_opa(lv.OPA.TRANSP, lv.PART.CURSOR),
            search_in=chart,
            search_term="opa",
        )
        if cursor is not None and temp_series is not None:
            check(
                "chart.set_cursor_point",
                lambda: chart.set_cursor_point(cursor, temp_series, 0),
                search_in=chart,
                search_term="cursor",
            )
            check(
                "chart.get_cursor_point",
                lambda: chart.get_cursor_point(cursor),
                search_in=chart,
                search_term="cursor",
            )
        check("chart.refresh", chart.refresh, search_in=chart, search_term="refresh")

    roller = check("lv.roller(parent)", lambda: lv.roller(tile_parent))
    if roller is not None:
        # 0 == LV_ROLLER_MODE_NORMAL's known numeric value -- lv.ROLLER_MODE
        # itself already failed above, sidestepping it here rather than
        # guessing a second wrong symbolic path.
        check(
            "roller.set_options",
            lambda: roller.set_options("A\nB", 0),
            search_in=roller,
            search_term="option",
        )
        check("roller.set_visible_row_count", lambda: roller.set_visible_row_count(3), search_in=roller)
        check("roller.get_selected", roller.get_selected, search_in=roller)
        check("roller.set_selected", lambda: roller.set_selected(0, 0), search_in=roller)

    print("\n=== lv.spinner (screens/connect.py's ConnectTile loading indicator) ===")
    spinner = check("lv.spinner(parent)", lambda: lv.spinner(tile_parent), search_in=lv, search_term="spinner")
    if spinner is not None:
        check("spinner.set_size", lambda: spinner.set_size(48, 48), search_in=spinner, search_term="size")
        check(
            "spinner.set_style_arc_color",
            lambda: spinner.set_style_arc_color(lv.color_hex(0), lv.PART.INDICATOR),
            search_in=spinner,
            search_term="arc",
        )

    slider = check("lv.slider(parent)", lambda: lv.slider(tile_parent))
    if slider is not None:
        check("slider.set_width", lambda: slider.set_width(lv.pct(50)), search_in=slider)
        check("slider.set_range", lambda: slider.set_range(0, 10), search_in=slider)
        check("slider.set_value", lambda: slider.set_value(5, 0), search_in=slider)
        check("slider.get_value", slider.get_value, search_in=slider)

    print("\n=== lv.line / lv.point_precise_t (screens/disconnected.py's DisconnectedTile X) ===")
    # Confirmed on real hardware: line.set_points() wants lv_point_precise_t,
    # not lv_point_t -- passing lv.point_t raised "SyntaxError: Can't convert
    # lv_point_t to lv_point_precise_t!" (an LVGL-level type-check failure,
    # not a missing-attribute one, hence the except Exception branch below
    # rather than AttributeError).
    point_t = check(
        "lv.point_precise_t({...})",
        lambda: lv.point_precise_t({"x": 0, "y": 0}),
        search_in=lv,
        search_term="point",
    )
    line = check("lv.line(parent)", lambda: lv.line(tile_parent), search_in=lv, search_term="line")
    if line is not None and point_t is not None:
        check(
            "line.set_points",
            lambda: line.set_points(
                [lv.point_precise_t({"x": 0, "y": 0}), lv.point_precise_t({"x": 100, "y": 100})], 2
            ),
            search_in=line,
            search_term="point",
        )
        check(
            "line.set_style_line_width",
            lambda: line.set_style_line_width(14, 0),
            search_in=line,
            search_term="line",
        )
        check(
            "line.set_style_line_color",
            lambda: line.set_style_line_color(lv.color_hex(0), 0),
            search_in=line,
            search_term="line",
        )
        check(
            "line.set_style_line_rounded",
            lambda: line.set_style_line_rounded(False, 0),
            search_in=line,
            search_term="line",
        )

    print("\n=== lv.image (startup splash, main.py's _show_splash()) ===")
    img = check("lv.image(parent)", lambda: lv.image(tile_parent), search_in=lv, search_term="image")
    if img is not None:
        check("img.set_src(...)", lambda: img.set_src("images/splash.bin"), search_in=img, search_term="src")
        check("img.center()", img.center, search_in=img)
        check("img.delete()", img.delete, search_in=img, search_term="del")

print("\n=== summary ===")
print("(Not checked here: lv.event_t.get_target_obj()/get_user_data(), used")
print(" in screens/*.py's slider/roller/arc callbacks -- only reachable from a")
print(" real fired event, not worth synthesizing one just for this script.")
print(" If a callback raises AttributeError on `e.get_...`, print(dir(e))")
print(" inside the callback itself the same way.)")
if _fails:
    print("%d check(s) FAILED:" % len(_fails))
    for f in _fails:
        print("  -", f)
    print("Fix the corresponding call(s) in hal.py/screens/*.py/theme.py/main.py,")
    print("then re-run this script before trying main.py again.")
else:
    print("All checks passed.")
