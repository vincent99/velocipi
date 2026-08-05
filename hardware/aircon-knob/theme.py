"""Visual constants -- colors mirror ../temp_knob/ui/globals.xml's design
tokens (same palette as the other two prototypes in this repo).

Fonts: the ../fonts/*.bin Nasalization binfonts (see ../fonts/README.md)
turned out to be unreliable to load on real hardware -- lv.binfont_create()
hung intermittently, sometimes succeeding and sometimes not with no code
change in between, regardless of call depth or whether the .bin files were
read from a `mount .` remote mount or the device's own flash. Using LVGL's
built-in font instead for now, which has been solid throughout. Revisit the
custom font separately, later -- see ../README.md.
"""

import lvgl as lv

COLOR_BG = lv.color_hex(0x12151C)  # color_dark_bg
COLOR_PANEL = lv.color_hex(0x1E232E)  # color_dark_panel
COLOR_TEXT = lv.color_hex(0xE6E9F0)  # color_dark_text
COLOR_TEXT_MUTED = lv.color_hex(0x7A8090)
COLOR_ACCENT = lv.color_hex(0x9429FF)  # color_accent
COLOR_ACCENT_TEXT = lv.color_hex(0xFFFFFF)
COLOR_DANGER = lv.color_hex(0xE5484D)
COLOR_TRACK = lv.color_hex(0x9AA3B2)

SPACE_XS = 2
SPACE_SM = 4
SPACE_MD = 8
SPACE_LG = 16
SPACE_XL = 32
RADIUS = 12

# Populated by load_fonts(), which main.py calls right after lv.init() --
# NOT at import time (unlike the plain lv.color_hex() constants above,
# which are cheap value-type constructors safe to call anytime), since
# widget/font construction in general needs lv_init() to have already set up
# LVGL's global state first.
FONT_BODY = None
FONT_DISPLAY = None


def load_fonts():
    global FONT_BODY, FONT_DISPLAY
    # Both sizes point at the same built-in font for now (LVGL's compiled-in
    # Montserrat, confirmed available via check_lvgl_api.py) -- the custom
    # Nasalization binfonts are unreliable to load, see this module's
    # docstring. FONT_DISPLAY (the big setpoint readout) will look
    # undersized until that's revisited.
    FONT_BODY = lv.font_montserrat_14
    FONT_DISPLAY = lv.font_montserrat_14
