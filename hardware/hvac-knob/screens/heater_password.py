"""HeaterPassword: 4-digit PIN entry for a password-protected heater. See
screens/__init__.py's module docstring for how this fits into the overall
screen flow, and heater_ble.py's module docstring (point 3) for how the
panel decides a heater needs this in the first place -- shown in place of
Home whenever heater_client.state.password_required is True (see
App.refresh()'s heater setup gate), which only ever happens after the
heater has explicitly rejected a handshake at least once.

Purely knob-driven, no touch, same bare-push pattern as Connect/
Disconnected (a knob push is edge-detected in App.poll_input(), not gated
on a touch point the way Home's mode/recirc cells are -- this screen
doesn't share panel space with any swipe gesture either).

Interaction, matching the actual request this was built for: turning the
knob edits the *value* of whichever of the 4 digits is currently focused
(0-9, wrapping); a push advances focus to the next digit, or -- once focus
reaches the 5th, terminal "Done" position -- submits the 4 digits as a
password (heater_ble.HeaterClient.set_password()). There's no dedicated
Skip control on this screen itself (a 6th cycle position didn't compose
cleanly with "push submits when already on Done" -- it'd need a different
gesture to ever reach past Done to it) -- screens/__init__.py's App instead
gives this screen its own generous give-up timeout
(App._HEATER_PASSWORD_TIMEOUT_MS), the same "must never be a hard
blocker" escape hatch already used for a heater that simply never connects
at all.
"""

import lvgl as lv

import theme
from .widgets import _label, _make_screen, _transparent

_DIGIT_COUNT = 4
_FOCUS_DONE = _DIGIT_COUNT  # 4 -- the 5th, terminal cycle position (indices 0-3 are the digits)

_DIGIT_CELL_W = 48
_DIGIT_CELL_H = 56


class HeaterPasswordTile:
    def __init__(self, heater_client, scr):
        self.heater_client = heater_client
        self.screen = _make_screen(scr)

        _label(self.screen, "Heater Password", font=theme.FONT_TITLE)
        self.status_label = _label(self.screen, "Enter the 4-digit PIN", color=theme.COLOR_TEXT_MUTED)

        row = _transparent(self.screen)
        row.set_size(lv.SIZE_CONTENT, lv.SIZE_CONTENT)
        row.set_flex_flow(lv.FLEX_FLOW.ROW)
        row.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        row.set_style_pad_column(theme.SPACE_MD, 0)

        # self._digit_cells[i]/self._digit_labels[i], not a list of (cell,
        # label) pairs -- _refresh_display() indexes both in lockstep with
        # self._digits by plain integer index, matching this codebase's
        # usual style elsewhere (e.g. settings.SettingsTile._cells) over
        # zip().
        self._digit_cells = []
        self._digit_labels = []
        for _ in range(_DIGIT_COUNT):
            cell = _transparent(row)
            cell.set_size(_DIGIT_CELL_W, _DIGIT_CELL_H)
            cell.set_style_radius(theme.RADIUS, 0)
            cell.set_style_border_width(2, 0)
            cell.set_style_border_color(theme.COLOR_BUTTON_OUTLINE, 0)
            cell.set_style_border_opa(lv.OPA.COVER, 0)
            label = _label(cell, "0", font=theme.FONT_TITLE, color=theme.COLOR_TEXT)
            label.center()
            self._digit_cells.append(cell)
            self._digit_labels.append(label)

        self.done_cell = _transparent(self.screen)
        self.done_cell.set_size(100, 40)
        self.done_cell.set_style_radius(theme.RADIUS, 0)
        self.done_cell.set_style_border_width(2, 0)
        self.done_cell.set_style_border_color(theme.COLOR_BUTTON_OUTLINE, 0)
        self.done_cell.set_style_border_opa(lv.OPA.COVER, 0)
        done_label = _label(self.done_cell, "Done", font=theme.FONT_BUTTON_LABEL, color=theme.COLOR_TEXT)
        done_label.center()

        self._digits = [0, 0, 0, 0]
        self._focus = 0
        # True from the moment a submit fires (select_current(), focus ==
        # _FOCUS_DONE) until refresh() sees heater_ble.HeaterClient's
        # resulting handshake attempt resolve one way or the other -- see
        # refresh()'s own docstring.
        self._awaiting_result = False

    def on_show(self):
        """Called by App._show() the first time this becomes the active
        screen this boot -- resets to a clean slate. Deliberately NOT
        called again on a failed retry (the screen name doesn't actually
        change away and back for that -- App.refresh() just keeps
        re-selecting "heater_password" every tick while password_required
        stays True); refresh() below is what resets the digits after a
        wrong attempt instead.
        """
        self._digits = [0, 0, 0, 0]
        self._focus = 0
        self._awaiting_result = False
        self.status_label.set_text("Enter the 4-digit PIN")
        self._refresh_display()

    def handle_knob(self, delta):
        if not delta or self._focus == _FOCUS_DONE or self._awaiting_result:
            return
        self._digits[self._focus] = (self._digits[self._focus] + delta) % 10
        self._refresh_display()

    def select_current(self):
        """Bare knob push, edge-detected in App.poll_input() -- see this
        module's own docstring for the advance-then-submit-on-Done shape.
        Ignored entirely while a previous submission is still being
        checked (_awaiting_result), so a fast double-press can't fire a
        second handshake attempt before the first one's even resolved.
        """
        if self._awaiting_result:
            return
        if self._focus == _FOCUS_DONE:
            password = 0
            for d in self._digits:
                password = password * 10 + d
            self.heater_client.set_password(password)
            self._awaiting_result = True
            self.status_label.set_text("Checking...")
            return
        self._focus += 1
        self._refresh_display()

    def refresh(self):
        """Called every App.refresh() tick while this is the active screen
        -- picks up the handshake's result once heater_ble.HeaterClient.
        set_password() (triggered by select_current()'s submit above)
        resolves it. A no-op unless _awaiting_result is set, so this is
        cheap to call unconditionally every tick.

        Checks state.password_check_pending, NOT state.password_required
        directly, to know whether an answer has actually landed yet --
        password_required alone can't tell "still reflects the attempt
        this screen just submitted" apart from "still holds a stale True
        from an earlier attempt, the new one hasn't resolved yet" (both
        look identical: True). See heater_ble.HeaterState's own docstring
        for why password_check_pending exists specifically to disambiguate
        that.
        """
        if not self._awaiting_result:
            return
        if self.heater_client.state.password_check_pending:
            return  # this submission's answer isn't back yet
        self._awaiting_result = False
        if self.heater_client.state.password_required:
            self._digits = [0, 0, 0, 0]
            self._focus = 0
            self.status_label.set_text("Incorrect, try again")
            self._refresh_display()
        else:
            # Accepted -- App.refresh()'s own gate logic is what actually
            # navigates away from this screen (it re-evaluates
            # password_required itself right after calling this), nothing
            # further to do here.
            self.status_label.set_text("")

    def _refresh_display(self):
        for i in range(_DIGIT_COUNT):
            self._digit_labels[i].set_text(str(self._digits[i]))
            focused = i == self._focus
            cell = self._digit_cells[i]
            cell.set_style_bg_opa(lv.OPA.COVER if focused else lv.OPA.TRANSP, 0)
            if focused:
                cell.set_style_bg_color(theme.COLOR_ACTIVE, 0)
        done_focused = self._focus == _FOCUS_DONE
        self.done_cell.set_style_bg_opa(lv.OPA.COVER if done_focused else lv.OPA.TRANSP, 0)
        if done_focused:
            self.done_cell.set_style_bg_color(theme.COLOR_ACTIVE, 0)
