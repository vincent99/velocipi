"""Disconnected: full-screen "no connection" state. See
screens/__init__.py's module docstring for how this fits into the overall
screen flow and interaction model.
"""

import math

import lvgl as lv

import hal
import theme
from .widgets import _label

# LVGL's line style has no centered-vs-one-sided alignment property --
# line_width/line_color/line_opa/line_rounded/line_dash_* are the whole
# set. On real hardware, a plain corner-to-corner lv.line at this width
# rendered with the full stroke offset to one side of the mathematical
# diagonal instead of straddling it, so _center_stroke() below shifts each
# line's anchor points sideways (perpendicular to its own direction) by
# half the stroke width to compensate.
#
# NOT independently re-verified after adding this -- _STROKE_SIGN is a
# guess at *which* perpendicular direction to shift. If the X still looks
# off-center (or is now off-center the other way), flip this to -1; it
# should land exactly on the corners either way once the sign is right.
_STROKE_SIGN = 0


def _center_stroke(x1, y1, x2, y2, width):
    dx, dy = x2 - x1, y2 - y1
    length = math.sqrt(dx * dx + dy * dy)
    if length == 0:
        return x1, y1, x2, y2
    px, py = -dy / length, dx / length  # unit vector perpendicular to (dx, dy)
    offset = _STROKE_SIGN * (width / 2.0)
    return (x1 + px * offset, y1 + py * offset, x2 + px * offset, y2 + py * offset)


class DisconnectedTile:
    """Full-screen "no connection" state -- shown at startup (until the
    first successful connect, if a device is already picked) or any time
    the connection drops while Home was showing -- see
    screens/__init__.py's App.refresh(). Knob push here (edge-detected in
    App.poll_input()) goes to Connect, to pick a different device.

    Generalized from an AirCon-only screen (see screens/connect.py's same
    change) -- App now owns one instance per device kind
    (aircon_disconnected_tile/heater_disconnected_tile), told apart only by
    `label`, shown in the "Connecting…"/"Disconnected" text so a heater
    drop doesn't read as an (unrelated) AirCon one. `label=""` (the
    AirCon's) reproduces the original bare text exactly.
    """

    _LINE_WIDTH = 14

    def __init__(self, scr, label=""):
        self.kind_label = label
        # Deliberately not built with widgets._make_screen()/flex layout --
        # the two corner-to-corner diagonal lines below need absolute panel
        # coordinates, which a flex container would instead treat as just
        # another child to auto-position/size, breaking the X.
        self.screen = lv.obj(scr)
        self.screen.set_size(lv.pct(100), lv.pct(100))
        self.screen.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.screen.set_style_border_width(0, 0)
        # Zeroed defensively -- a raw lv.obj() shouldn't inherit any
        # default padding, but the two lines below are placed with
        # absolute panel coordinates that assume (0,0) is this object's
        # true top-left, not an inset content area.
        self.screen.set_style_pad_all(0, 0)
        self.screen.set_style_bg_opa(lv.OPA.COVER, 0)
        self.screen.set_style_bg_color(theme.COLOR_BG, 0)

        for (x1, y1, x2, y2) in (
            (0, 0, hal.WIDTH, hal.HEIGHT),
            (hal.WIDTH, 0, 0, hal.HEIGHT),
        ):
            x1, y1, x2, y2 = _center_stroke(x1, y1, x2, y2, self._LINE_WIDTH)
            line = lv.line(self.screen)
            points = [lv.point_precise_t({"x": x1, "y": y1}), lv.point_precise_t({"x": x2, "y": y2})]
            line.set_points(points, len(points))
            line.set_style_line_width(self._LINE_WIDTH, 0)
            line.set_style_line_color(theme.COLOR_DANGER, 0)
            line.set_style_line_rounded(False, 0)

        self.label = _label(self.screen, "", font=theme.FONT_TITLE, color=lv.color_hex(0xFFFFFF))
        # lv.label is a regular lv.obj under the hood, so it takes the same
        # bg_opa/bg_color/padding styling as any other widget directly --
        # no separate backing rectangle needed.
        self.label.set_style_bg_opa(lv.OPA.COVER, 0)
        self.label.set_style_bg_color(theme.COLOR_DANGER, 0)
        self.label.set_style_pad_hor(theme.SPACE_MD, 0)
        self.label.set_style_pad_ver(theme.SPACE_SM, 0)
        self.label.center()

    def on_show(self, ever_connected):
        base = "Disconnected" if ever_connected else "Connecting"
        text = ("%s %s" % (base, self.kind_label)) if self.kind_label else base
        self.label.set_text(text)
