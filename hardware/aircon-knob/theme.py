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
COLOR_COMPRESSOR_ON = lv.color_hex(0x0B1F4D)  # dark blue fill behind the current-temp cell while the compressor is running
# Mode/recirc button-cell touch feedback (see screens/widgets.py's
# _wire_button): COLOR_HOVER fills the cell while it's touched but the
# knob's push-button isn't down yet, COLOR_ACTIVE (reusing the existing
# accent) once the button is also down -- i.e. right before a tap commits.
COLOR_HOVER = lv.color_hex(0x1E2230)
COLOR_ACTIVE = COLOR_ACCENT
# Mode/recirc button outline -- deliberately duller/darker than COLOR_TRACK
# (used for the gauge's own inactive arc track, which wants to read clearly
# against the black background) so the outline recedes and doesn't compete
# with the icon/label content inside it.
COLOR_BUTTON_OUTLINE = lv.color_hex(0x3A3F4A)
# screens/settings.py: a setting's value renders in this (not COLOR_ACCENT/
# COLOR_ACTIVE, which already mean "purple = actively engaged" elsewhere)
# when it differs from its compiled-in default. Same blue as the web UI's
# own modified-value affordance (ui/src/routes/remote/settings.vue's
# .save-btn, #3b82f6) for a consistent "blue means changed" vocabulary
# across both UIs.
COLOR_MODIFIED = lv.color_hex(0x3B82F6)

SPACE_XS = 2
SPACE_SM = 4
SPACE_MD = 8
SPACE_LG = 16
SPACE_XL = 32
RADIUS = 12
BUTTON_RADIUS = 12  # mode/recirc cells -- halved from an earlier, too-round 24 per feedback

# Populated by load_fonts(), which main.py calls right after lv.init() --
# NOT at import time (unlike the plain lv.color_hex() constants above,
# which are cheap value-type constructors safe to call anytime), since
# widget/font construction in general needs lv_init() to have already set up
# LVGL's global state first.
FONT_TINY = None
FONT_BODY = None
FONT_TITLE = None
FONT_BUTTON_ICON = None
FONT_BUTTON_LABEL = None
FONT_CURRENT_TEMP = None


def load_fonts():
    global FONT_TINY, FONT_BODY, FONT_TITLE, FONT_BUTTON_ICON, FONT_BUTTON_LABEL, FONT_CURRENT_TEMP

    # screens/history.py's y-axis value labels -- the smallest size this
    # build's LVGL image has (see check_lvgl_api.py's font_montserrat_%d
    # loop, which now includes 12), used only where theme.FONT_BODY (14px)
    # doesn't leave enough room.
    FONT_TINY = lv.font_montserrat_12
    FONT_BODY = lv.font_montserrat_14
    FONT_TITLE = lv.font_montserrat_20
    # Mode/recirc button cells: bigger now that montserrat 12-48 are loaded
    # (previously only 14/20 were available) -- icon line noticeably larger
    # than the text line below it.
    FONT_BUTTON_ICON = lv.font_montserrat_32
    FONT_BUTTON_LABEL = lv.font_montserrat_18
    # home.HomeTile's current-temp label, sized as a judgment call (not
    # rendered/measured on real hardware): big enough to read as the
    # screen's headline number, but conservative enough that the widest
    # string it ever shows ("99.9°", 5 glyphs -- see widgets._fmt_temp)
    # still clears the circular inset's chord width up near the top of the
    # gauge, where that inset is narrower than at its vertical center. If
    # it visibly clips against the arc, size this down; if there's clear
    # room to spare, it can go bigger.
    FONT_CURRENT_TEMP = lv.font_montserrat_36
