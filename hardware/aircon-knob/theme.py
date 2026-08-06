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

COLOR_BG = lv.color_hex(0x000000)
COLOR_TEXT = lv.color_hex(0xE6E9F0)
COLOR_TEXT_MUTED = lv.color_hex(0x7A8090)
COLOR_ACCENT = lv.color_hex(0x9429FF)
COLOR_ACCENT_TEXT = lv.color_hex(0xFFFFFF)
COLOR_DANGER = lv.color_hex(0xFF0000)
COLOR_TRACK = lv.color_hex(0x9AA3B2)
COLOR_COMPRESSOR_ON = lv.color_hex(0x0B1F4D)  # dark blue fill behind the bottom row while the compressor is running
# Mode/recirc button-cell touch feedback (see screens/widgets.py's
# _wire_button): COLOR_HOVER fills the cell while it's touched but the
# knob's push-button isn't down yet, COLOR_ACTIVE (reusing the existing
# accent) once the button is also down -- i.e. right before a tap commits.
COLOR_HOVER = lv.color_hex(0x1E2230)
COLOR_ACTIVE = COLOR_ACCENT

SPACE_XS = 2
SPACE_SM = 4
SPACE_MD = 8
SPACE_LG = 16
SPACE_XL = 32
RADIUS = 12
BUTTON_RADIUS = 24  # mode/recirc cells -- rounder, to echo the round panel's own curve

# Populated by load_fonts(), which main.py calls right after lv.init() --
# NOT at import time (unlike the plain lv.color_hex() constants above,
# which are cheap value-type constructors safe to call anytime), since
# widget/font construction in general needs lv_init() to have already set up
# LVGL's global state first.
FONT_BODY = None
FONT_TITLE = None
FONT_BUTTON_ICON = None
FONT_BUTTON_LABEL = None


def load_fonts():
    global FONT_BODY, FONT_TITLE, FONT_BUTTON_ICON, FONT_BUTTON_LABEL

    FONT_BODY = lv.font_montserrat_14
    FONT_TITLE = lv.font_montserrat_20
    # Mode/recirc button cells: bigger now that montserrat 12-48 are loaded
    # (previously only 14/20 were available) -- icon line noticeably larger
    # than the text line below it.
    FONT_BUTTON_ICON = lv.font_montserrat_32
    FONT_BUTTON_LABEL = lv.font_montserrat_18
