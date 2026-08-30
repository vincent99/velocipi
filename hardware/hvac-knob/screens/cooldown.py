"""Cooldown: full-screen takeover shown for a few seconds after the knob's
push-button is held for App._COOLDOWN_HOLD_MS -- see screens/__init__.py's
App._enter_cooldown()/refresh() for the state machine (when this triggers,
how long it stays up, and what it does to the currently-selected mode). Not
a real HVAC mode of its own -- purely a UI screen -- so unlike home.py's
MODES this has nothing to plug into MODE_DEVICE/current_mode()/etc.

Replaces an earlier version of this same button-hold gesture, which
rebooted the panel outright (main.py's old _REBOOT_HOLD_MS) -- see
screens/__init__.py's module docstring for why that was dropped in favor of
this.
"""

import theme
from .widgets import _label, _make_screen


class CooldownTile:
    """Static, non-interactive full-screen message -- no knob/touch handling
    at all (screens/__init__.py's App doesn't route input here while it's
    showing, see poll_input()'s own cooldown carve-out).
    """

    def __init__(self, scr):
        self.screen = _make_screen(scr)
        _label(self.screen, "Cooldown", font=theme.FONT_TITLE, color=theme.COLOR_TEXT)
