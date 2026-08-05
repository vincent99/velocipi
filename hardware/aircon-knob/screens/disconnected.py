"""Disconnected: full-screen "no connection" state. See
screens/__init__.py's module docstring for how this fits into the overall
screen flow and interaction model.
"""

import lvgl as lv

import hal
import theme
from .widgets import _label


class DisconnectedTile:
    """Full-screen "no connection" state -- shown at startup (until the
    first successful connect, if a device is already picked) or any time
    the connection drops while Home was showing -- see
    screens/__init__.py's App.refresh(). Knob push here (edge-detected in
    App.poll_input()) goes to Connect, to pick a different device.
    """

    _LINE_WIDTH = 14

    def __init__(self, scr):
        # Deliberately not built with widgets._make_screen()/flex layout --
        # the two corner-to-corner diagonal lines below need absolute panel
        # coordinates, which a flex container would instead treat as just
        # another child to auto-position/size, breaking the X.
        self.screen = lv.obj(scr)
        self.screen.set_size(lv.pct(100), lv.pct(100))
        self.screen.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.screen.set_style_border_width(0, 0)
        self.screen.set_style_bg_opa(lv.OPA.COVER, 0)
        self.screen.set_style_bg_color(theme.COLOR_DANGER, 0)

        # hal.WIDTH/HEIGHT rather than a hardcoded 240, matching main.py's
        # own splash image sizing.
        for (x1, y1, x2, y2) in (
            (0, 0, hal.WIDTH, hal.HEIGHT),
            (hal.WIDTH, 0, 0, hal.HEIGHT),
        ):
            line = lv.line(self.screen)
            points = [lv.point_t({"x": x1, "y": y1}), lv.point_t({"x": x2, "y": y2})]
            line.set_points(points, len(points))
            line.set_style_line_width(self._LINE_WIDTH, 0)
            line.set_style_line_color(theme.COLOR_DANGER_DARK, 0)
            line.set_style_line_rounded(False, 0)

        self.label = _label(self.screen, "", font=theme.FONT_DISPLAY, color=lv.color_hex(0xFFFFFF))
        self.label.center()

        self._shown_before = False

    def on_show(self):
        """Called by App._show() every time this becomes the active
        screen. "Connecting..." only the very first time this is ever
        shown; every later showing (a drop after having been connected, or
        the attempt right after a new device is picked) says
        "Disconnected".
        """
        self.label.set_text("Disconnected" if self._shown_before else "Connecting...")
        self._shown_before = True
