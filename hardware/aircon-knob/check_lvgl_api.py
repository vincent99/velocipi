"""One-shot LVGL API sanity check -- run this BEFORE main.py to catch any
remaining `lv.*` name mismatches in one pass instead of one flash-cycle per
AttributeError. This project's code was written against the LVGL Python
binding's well-established naming convention, but not verified against the
actual generated binding (no hardware available while writing it) -- this
script builds one of everything main.py/hal.py/screens.py/theme.py touch
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
    "color_hex", "binfont_create", "obj", "label", "roller", "arc", "slider",
    "tileview", "pct", "SIZE_CONTENT", "screen_active", "group_create",
    "timer_handler", "indev_create", "display_create", "DIR", "EVENT",
    "PART", "OPA", "FLEX_FLOW", "FLEX_ALIGN",
    "INDEV_TYPE", "INDEV_STATE", "COLOR_FORMAT", "DISPLAY_RENDER_MODE",
):
    check("lv." + name, (lambda n=name: getattr(lv, n)), search_in=lv, search_term=name)

print("\n=== confirmed absent, already worked around in screens.py ===")
print("(lv.ANIM / lv.ROLLER_MODE don't exist as nested enum-group classes on")
print(" this binding; screens.py uses the plain numeric values instead --")
print(" see its _ANIM_OFF/_ROLLER_MODE_NORMAL. Not counted as failures below;")
print(" only worth re-checking if you're curious whether a real symbolic")
print(" name exists somewhere else in dir(lv).)")
for name in ("ANIM", "ROLLER_MODE"):
    hits = [n for n in dir(lv) if name in n.upper()]
    print("     dir(lv) containing %r: %s" % (name, hits))

print("\n=== enum members actually used in this project ===")
for path in (
    "DIR.RIGHT", "DIR.LEFT", "DIR.HOR", "DIR.VER",
    "EVENT.VALUE_CHANGED",
    "PART.MAIN", "PART.INDICATOR",
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
        check("tv.add_tile(0,0,DIR)", lambda: tv.add_tile(0, 0, lv.DIR.RIGHT), search_in=tv, search_term="tile")
        tile_parent = tv

    obj = check("lv.obj(parent)", lambda: lv.obj(tile_parent))
    if obj is not None:
        check("obj.set_size(pct,pct)", lambda: obj.set_size(lv.pct(50), lv.pct(50)), search_in=obj, search_term="set_size")
        check("obj.set_style_bg_opa", lambda: obj.set_style_bg_opa(lv.OPA.TRANSP, 0), search_in=obj)
        check("obj.set_style_border_width", lambda: obj.set_style_border_width(0, 0), search_in=obj)
        check("obj.set_style_bg_color", lambda: obj.set_style_bg_color(lv.color_hex(0), 0), search_in=obj)
        check("obj.set_style_pad_all", lambda: obj.set_style_pad_all(4, 0), search_in=obj)
        check("obj.set_style_pad_row", lambda: obj.set_style_pad_row(4, 0), search_in=obj)
        check("obj.set_flex_flow", lambda: obj.set_flex_flow(lv.FLEX_FLOW.COLUMN), search_in=obj)
        check(
            "obj.set_flex_align",
            lambda: obj.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER),
            search_in=obj,
        )
        check("obj.set_scroll_dir", lambda: obj.set_scroll_dir(lv.DIR.VER), search_in=obj)
        check("obj.clean()", obj.clean, search_in=obj)

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

    slider = check("lv.slider(parent)", lambda: lv.slider(tile_parent))
    if slider is not None:
        check("slider.set_width", lambda: slider.set_width(lv.pct(50)), search_in=slider)
        check("slider.set_range", lambda: slider.set_range(0, 10), search_in=slider)
        check("slider.set_value", lambda: slider.set_value(5, 0), search_in=slider)
        check("slider.get_value", slider.get_value, search_in=slider)

    print("\n=== lv.image (startup splash, main.py's _show_splash()) ===")
    img = check("lv.image(parent)", lambda: lv.image(tile_parent), search_in=lv, search_term="image")
    if img is not None:
        check("img.set_src(...)", lambda: img.set_src("images/splash.bin"), search_in=img, search_term="src")
        check("img.center()", img.center, search_in=img)
        check("img.delete()", img.delete, search_in=img, search_term="del")

print("\n=== summary ===")
print("(Not checked here: lv.event_t.get_target_obj()/get_user_data(), used")
print(" in screens.py's slider/roller/arc callbacks -- only reachable from a")
print(" real fired event, not worth synthesizing one just for this script.")
print(" If a callback raises AttributeError on `e.get_...`, print(dir(e))")
print(" inside the callback itself the same way.)")
if _fails:
    print("%d check(s) FAILED:" % len(_fails))
    for f in _fails:
        print("  -", f)
    print("Fix the corresponding call(s) in hal.py/screens.py/theme.py/main.py,")
    print("then re-run this script before trying main.py again.")
else:
    print("All checks passed.")
