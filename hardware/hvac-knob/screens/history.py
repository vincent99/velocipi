"""History: a knob-driven scrub graph of client.history (see aircon_ble.py's
AirconClient._sample_history()/_compact_history() -- an RRD-style buffer,
starting at 1 sample/second and halving+doubling its own interval every
time it fills to 180 points, so it never grows past that but gets
progressively coarser the further back it reaches). Reached by swiping up
from Home, swipe down to return -- see screens/__init__.py's App.__init__
for the grid layout.

Two overlaid lv.chart widgets, same size/position/point_count/axis_range,
one per series -- not one chart with two series -- because the two need
completely different rendering (current_temp filled, setpoint a plain
line) and this LVGL build's lv.chart has no per-series style override:

  - current_temp (_temp_chart): lv.chart.TYPE.BAR, not LINE. An earlier
    version tried LINE + PART.ITEMS' own background opacity for the "filled
    area" look (a technique that's real in upstream LVGL docs) -- confirmed
    by reading this build's own lv_chart.c draw_series_line() that this
    specific version's LINE renderer never reads PART.ITEMS' bg_opa at all
    (it only draws the line + optional point markers), so that call was a
    silent no-op the whole time. BAR, on the other hand, draws each point
    as a filled column from the chart's bottom (the axis *minimum*, not
    zero) up to its value -- with point_cnt == pixel width and PART.MAIN's
    pad_column forced to 0 (see block_gap in draw_series_bar()), columns
    end up exactly 1px wide with no gaps, i.e. a real filled area at this
    chart's full 1px/point resolution. Drawn first/underneath so the
    setpoint chart (below) draws on top of it.
  - setpoint (_setpoint_chart): lv.chart.TYPE.LINE, transparent background,
    on top -- also owns the cursor, so it renders above both. PART.ITEMS'
    line_width is forced down from the default theme's ~2-3px to 1px:
    point_cnt (180) >= this chart's pixel width triggers lv_chart's
    "crowded mode" (draw_series_line(), confirmed via the same source read),
    which already skips per-point marker circles in favor of one vertical
    segment per x-pixel -- but leaves line_width alone, and the default was
    visibly thick/blocky at 1px point spacing.

Y-axis value labels: this build's lv.chart has no set_axis_tick()/tick-label
support at all (absent from lvgl.pyi's exhaustive method listing, unlike
upstream LVGL's C API) -- see _axis_levels()/_draw_axis_labels() below,
which draw plain lv.label/lv.obj gridlines by hand instead, positioned via
already-hardware-verified obj.align(lv.ALIGN.LEFT_MID, x, y) (see home.py's
row3/mode_cell/recirc_cell, the first uses of .align() in this codebase)
rather than introducing new unverified positioning calls. Both charts'
own div lines are turned off (set_div_line_count(0, 0)) so only these
hand-drawn, value-aligned gridlines show. The axis range is scaled to the
actual data (min/max of every setpoint/current_temp value currently in
history, padded by _AXIS_PAD and rounded out to a nice step) -- not
client.setpoint_bounds(), which would drag the range out to whatever the
configured setpoint min/max happen to be even when the real data never
goes near them.
"""

import time

import lvgl as lv

import theme
from .widgets import _label, _make_tile, _transparent

_CHART_W = 180
_CHART_H = 150  # "as tall as fits inside the circle without clipping" -- a
# judgment call (not measured on real hardware, per the request that named
# this exact figure as an estimate); size down if it visibly clips against
# the round bezel, up if there's clearly room to spare.

# Matches aircon_ble.py's _HISTORY_MAX_POINTS -- 1 point per pixel, no
# interpolation needed.
_CHART_POINTS = 180

# Room to the right of the chart for its value labels -- also a judgment
# call, not hardware-measured. The tile's own left/right padding is trimmed
# down from _make_tile()'s default (theme.SPACE_LG) specifically for this
# tile (see HistoryTile.__init__) to make room for this without shrinking
# _CHART_W (which would break the 1px/point sizing above).
_AXIS_GAP = 6
_AXIS_LABEL_W = 34

# How far past the actual data's min/max the axis range extends on each
# side, before rounding out to a nice step -- so the lowest/highest points
# don't render flush against the chart's own top/bottom edge.
_AXIS_PAD = 2

# _axis_levels() rounds the data range out to whichever of these first
# keeps the label count at _AXIS_MAX_LEVELS or fewer -- degrades to sparser
# labels for a wide range instead of overlapping ones on this display's
# limited vertical room, rather than a single fixed step that could crowd.
_AXIS_STEPS = (5, 10, 20, 50)
_AXIS_MAX_LEVELS = 6

# Knob acceleration: two detents landing within this many ms of each other
# count as a "fast" turn and jump _FAST_STEP datapoints instead of
# _SLOW_STEP -- at 1-60s/point depending on how long the panel's been
# running (see aircon_ble.py's RRD-style history), a slow single-detent-at-
# a-time scrub took too many turns to reach anything more than a couple
# minutes back.
_FAST_TURN_MS = 150
_SLOW_STEP = 1
_FAST_STEP = 10

# Top (time label) and bottom (readout) rows are both pinned to this same
# height so the chart sits vertically centered between them -- previously
# both were SIZE_CONTENT, sized only by each row's own font, which differed
# (FONT_BODY vs FONT_TITLE) and threw the chart off-center. Sized to
# comfortably fit FONT_TITLE's line height with a little breathing room;
# not hardware-measured, same caveat as _CHART_H above.
_LABEL_ROW_H = 30


class HistoryTile:
    def __init__(self, client, encoder, tileview):
        self.client = client
        self.encoder = encoder
        # (1, 0): matches App.__init__'s grid layout -- History sits above
        # Home. _make_tile (flex_flow/flex_align live directly on the tile
        # itself), not _make_bare_tile plus a separate SIZE_CONTENT wrapper
        # centered via .center() -- confirmed on real hardware that
        # centering a SIZE_CONTENT-height wrapper *before* any children
        # were added froze its centering math against an effectively-empty
        # box: everything ended up pushed against the top of the tile
        # instead, shoving the first child (the time label) off the
        # visible area entirely. The tile itself has a full, definite size
        # from the moment it's created (no SIZE_CONTENT timing to get
        # wrong), so putting CENTER main-align directly on it reliably
        # centers the whole title/graph/readout stack as a group.
        self.tile = _make_tile(tileview, 1, 0, lv.DIR.NONE)
        self.tile.set_style_pad_row(theme.SPACE_SM, 0)
        # Trimmed from _make_tile()'s default SPACE_LG (16px/side) -- this
        # tile needs the extra room more than it needs generous padding:
        # horizontally for the chart's y-axis labels (see _AXIS_LABEL_W),
        # vertically to fit _LABEL_ROW_H on both ends without shrinking
        # _CHART_H.
        self.tile.set_style_pad_left(theme.SPACE_XS, 0)
        self.tile.set_style_pad_right(theme.SPACE_XS, 0)
        self.tile.set_style_pad_top(theme.SPACE_SM, 0)
        self.tile.set_style_pad_bottom(theme.SPACE_SM, 0)

        time_row = _transparent(self.tile)
        time_row.set_size(lv.pct(100), _LABEL_ROW_H)
        time_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        time_row.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        self.time_label = _label(time_row, font=theme.FONT_TITLE, color=theme.COLOR_TEXT)

        self._graph_area = _transparent(self.tile)
        self._graph_area.set_size(_CHART_W + _AXIS_GAP + _AXIS_LABEL_W, _CHART_H)
        # Found on real hardware, via a one-shot geometry dump: this obj's
        # own content height was 124px against a declared 150 -- some
        # nonzero default padding neither _transparent() nor this file ever
        # zeroed, and (see the two charts below) a *different* nonzero
        # amount than theirs, so the two coordinate spaces this file
        # otherwise assumes are identical (graph_area's, for the hand-drawn
        # axis labels/gridlines, and each chart's own, for its actual data)
        # quietly weren't -- the root cause of a value-dependent y-axis
        # scale mismatch that pure formula review couldn't explain. Forcing
        # pad_all to 0 everywhere in this tree removes the discrepancy at
        # the source instead of chasing where each default came from.
        self._graph_area.set_style_pad_all(0, 0)

        # Underneath: current_temp, filled blue area (see module docstring
        # for why this is TYPE.BAR, not TYPE.LINE). Drawn first so the fade
        # overlay and the setpoint chart (both below) draw on top of it.
        self._temp_chart = lv.chart(self._graph_area)
        self._temp_chart.set_size(_CHART_W, _CHART_H)
        self._temp_chart.set_style_bg_opa(lv.OPA.TRANSP, 0)
        self._temp_chart.set_style_border_width(0, 0)
        self._temp_chart.set_style_pad_all(0, 0)  # see graph_area's comment above
        # Charts are lv.obj-derived and scrollable by default, same as any
        # other plain container (see widgets._transparent()'s own comment) --
        # unlike the rest of this codebase's containers, these two were
        # never given remove_flag(SCROLLABLE), which can leave a nonzero
        # internal scroll offset shifting rendered content without it being
        # reflected anywhere these hand-computed axis positions account for.
        self._temp_chart.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self._temp_chart.set_type(lv.chart.TYPE.BAR)
        self._temp_chart.set_point_count(_CHART_POINTS)
        self._temp_chart.set_div_line_count(0, 0)
        # block_gap (draw_series_bar()'s gap between adjacent columns) reads
        # PART.MAIN's pad_column, which the default theme sets to a nonzero
        # DPI-scaled value -- left alone, that overflows chart width at 180
        # columns and produces garbage bar positions. Forcing it to 0 is
        # required, not cosmetic, for 1px/point columns with no gaps.
        self._temp_chart.set_style_pad_column(0, 0)
        self._temp_chart.set_style_radius(0, lv.PART.ITEMS)
        self._temp_series = self._temp_chart.add_series(theme.COLOR_MODIFIED, lv.chart.AXIS.PRIMARY_Y)

        # Fade overlay: draw_series_bar() (lv_chart.c) unconditionally
        # forces PART.ITEMS' bg_opa to LV_OPA_COVER and bg_grad.dir to NONE
        # right after reading the rest of the style, discarding *both*
        # set_style_bg_opa and any gradient set on the chart's own bars --
        # confirmed by reading that function, and consistent with the bars
        # rendering fully opaque regardless of what's set there. A real
        # per-bar fade isn't achievable on this chart type in this LVGL
        # version, so this fakes the same look with a separate, plain
        # lv.obj sized/positioned exactly over the bars, transparent at its
        # own top and fading to a translucent black toward the bottom --
        # against this screen's pure black background, "more opaque black"
        # and "more transparent" read as the same thing, so this darkens the
        # opaque blue underneath it without needing the blue itself to
        # support per-pixel opacity. NOT hardware-verified: GRAD_DIR.VER's
        # main stop (bg_color/bg_opa) is assumed to land at the *top* and
        # the grad stop (bg_grad_color/bg_grad_opa) at the *bottom* (matches
        # every other UI toolkit's top-to-bottom gradient convention, and
        # lv_draw_sw_grad.c's row-indexed gradient cache is consistent with
        # it) -- if it visibly renders upside down, swap opa/grad_opa below.
        fade = _transparent(self._graph_area)
        fade.set_size(_CHART_W, _CHART_H)
        fade.set_style_pad_all(0, 0)  # see graph_area's comment above
        fade.set_style_bg_color(theme.COLOR_BG, 0)
        fade.set_style_bg_grad_color(theme.COLOR_BG, 0)
        fade.set_style_bg_grad_dir(lv.GRAD_DIR.VER, 0)
        fade.set_style_bg_opa(lv.OPA.TRANSP, 0)
        fade.set_style_bg_grad_opa(lv.OPA._60, 0)

        # On top: setpoint, plain line, no fill -- transparent chart
        # background so the temp chart's bars/fade show through underneath.
        # Also owns the cursor, so it renders above both.
        self._setpoint_chart = lv.chart(self._graph_area)
        self._setpoint_chart.set_size(_CHART_W, _CHART_H)
        self._setpoint_chart.set_style_bg_opa(lv.OPA.TRANSP, 0)
        self._setpoint_chart.set_style_border_width(0, 0)
        self._setpoint_chart.set_style_pad_all(0, 0)  # see graph_area's comment above
        self._setpoint_chart.remove_flag(lv.obj.FLAG.SCROLLABLE)  # see _temp_chart's comment above
        self._setpoint_chart.set_type(lv.chart.TYPE.LINE)
        self._setpoint_chart.set_point_count(_CHART_POINTS)
        self._setpoint_chart.set_div_line_count(0, 0)
        self._setpoint_chart.set_style_line_width(1, lv.PART.ITEMS)
        self._setpoint_series = self._setpoint_chart.add_series(theme.COLOR_DANGER, lv.chart.AXIS.PRIMARY_Y)
        self._cursor = self._setpoint_chart.add_cursor(lv.color_hex(0xFFFFFF), lv.DIR.VER)

        # Hand-drawn y-axis gridlines/labels -- see _draw_axis_labels().
        # Rebuilt only when the rounded (y_lo, y_hi, levels) actually
        # changes (cheap to compare, and avoids deleting/recreating these
        # widgets on every ~250ms refresh for no reason).
        self._axis_widgets = []
        self._axis_levels_drawn = None

        readout_row = _transparent(self.tile)
        readout_row.set_size(lv.pct(100), _LABEL_ROW_H)
        readout_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        readout_row.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        readout_row.set_style_pad_column(theme.SPACE_MD, 0)
        self.setpoint_readout = _label(readout_row, font=theme.FONT_TITLE, color=theme.COLOR_DANGER)
        self.current_temp_readout = _label(readout_row, font=theme.FONT_TITLE, color=theme.COLOR_MODIFIED)

        # None == tracking the latest point ("Now") -- see handle_knob()/
        # _cursor_index(). Otherwise a ticks_ms-comparable "virtual
        # timestamp" for the pinned point (see handle_knob()'s comment) --
        # client.history itself no longer stores one (RRD-style compaction,
        # see aircon_ble.py), so this is reconstructed once at pin time from
        # client.history_age_ms() instead of copied from the point directly.
        self._cursor_ts = None
        self._last_turn_ms = None  # for the knob-acceleration check in handle_knob()

    # ── Knob ──────────────────────────────────────────────────────────────

    def handle_knob(self, delta):
        """Called with the encoder's accumulated detent delta since the
        last poll, only while this is the active tile (see
        screens/__init__.py's App.poll_input()).
        """
        if not delta:
            return
        history = self.client.history
        n = len(history)
        if n == 0:
            return
        idx = self._cursor_index()
        if idx is None:
            return

        now = time.ticks_ms()
        fast = self._last_turn_ms is not None and time.ticks_diff(now, self._last_turn_ms) < _FAST_TURN_MS
        self._last_turn_ms = now
        step = _FAST_STEP if fast else _SLOW_STEP

        new_idx = min(max(idx + delta * step, 0), n - 1)
        if new_idx == n - 1:
            self._cursor_ts = None
        else:
            # Anchor the pin to a real point in time (ticks_ms() minus that
            # point's current age), not to new_idx itself -- new_idx is only
            # meaningful against *this* refresh's history; a future
            # compaction can coarsen the interval and shift exactly which
            # index this same real instant falls on (see _cursor_index()).
            self._cursor_ts = time.ticks_add(now, -self.client.history_age_ms(new_idx))

    def handle_button(self):
        """Called on the knob's push-button edge while History is the
        active tile (see screens/__init__.py's App.poll_input()) -- always
        jumps the cursor straight back to the latest point ("Now"),
        regardless of where it was, since a button push reads as a
        deliberate "take me back" gesture.
        """
        self._cursor_ts = None

    def _cursor_index(self):
        """Resolves self._cursor_ts against the *current* client.history,
        returning None if there's no history at all yet. Deliberately a
        pure query (no side effects on self._cursor_ts) -- refresh() and
        handle_knob() each call it independently and don't rely on the
        other having run first, since poll_input() (-> handle_knob())
        runs every main-loop tick but refresh() only every ~250ms/on
        client.dirty.

        Resolves by closest age, not exact match -- client.history no
        longer carries a per-point identity to match exactly (RRD-style
        compaction, see aircon_ble.py), and a compaction between pinning
        and now may have coarsened the interval, shifting which index the
        pinned instant now falls closest to. This also naturally covers the
        old "pinned point rolled off the front entirely" case: the closest
        match is then just whatever's now the oldest available point, with
        no separate fallback needed.
        """
        history = self.client.history
        n = len(history)
        if n == 0:
            return None
        if self._cursor_ts is None:
            return n - 1
        target_age = time.ticks_diff(time.ticks_ms(), self._cursor_ts)
        best_i, best_diff = 0, None
        for i in range(n):
            diff = abs(self.client.history_age_ms(i) - target_age)
            if best_diff is None or diff < best_diff:
                best_i, best_diff = i, diff
        return best_i

    # ── Refresh ───────────────────────────────────────────────────────────

    def refresh(self):
        history = self.client.history
        idx = self._cursor_index()

        if idx is None:
            self.time_label.set_text("--")
            self.setpoint_readout.set_text("--")
            self.current_temp_readout.set_text("--")
            self._refresh_charts(history, None, False)
            return

        is_latest = idx == len(history) - 1
        setpoint, current_temp = history[idx]
        self.time_label.set_text(_format_ago(self.client.history_age_ms(idx), is_latest))
        self.setpoint_readout.set_text(_fmt_temp_bare(setpoint))
        self.current_temp_readout.set_text(_fmt_temp_bare(current_temp))

        self._refresh_charts(history, idx, is_latest)

    def _refresh_charts(self, history, cursor_idx, is_latest):
        n = len(history)
        offset = _CHART_POINTS - n  # leading points with no data yet are blank (CHART_POINT_NONE)

        if history:
            values = []
            for setpoint, current_temp in history:
                values.append(setpoint)
                values.append(current_temp)
            y_lo, y_hi, levels = _axis_levels(min(values) - _AXIS_PAD, max(values) + _AXIS_PAD)
        else:
            lo, hi = self.client.setpoint_bounds()
            y_lo, y_hi, levels = _axis_levels(lo, hi)

        self._temp_chart.set_axis_range(lv.chart.AXIS.PRIMARY_Y, y_lo, y_hi)
        self._setpoint_chart.set_axis_range(lv.chart.AXIS.PRIMARY_Y, y_lo, y_hi)

        if levels != self._axis_levels_drawn:
            self._draw_axis_labels(y_lo, y_hi, levels)
            self._axis_levels_drawn = levels

        for i in range(_CHART_POINTS):
            if i < offset:
                self._temp_chart.set_series_value_by_id(self._temp_series, i, lv.CHART_POINT_NONE)
                self._setpoint_chart.set_series_value_by_id(self._setpoint_series, i, lv.CHART_POINT_NONE)
            else:
                setpoint, current_temp = history[i - offset]
                self._temp_chart.set_series_value_by_id(self._temp_series, i, round(current_temp))
                self._setpoint_chart.set_series_value_by_id(self._setpoint_series, i, round(setpoint))

        # Hidden while tracking "Now", shown only once actually scrubbed
        # back in time (it has nothing meaningful to point at otherwise --
        # the latest point is already the chart's own rightmost edge).
        # Toggling PART.CURSOR's own opacity, not point_id = CHART_POINT_NONE
        # (lv_chart.c's draw_cursors() does special-case that, in theory --
        # confirmed on real hardware that it doesn't actually suppress the
        # cursor on this build; opa is a plain, independent style property
        # read straight into the draw descriptor, with no extra branch to
        # go wrong).
        if cursor_idx is not None and not is_latest:
            self._setpoint_chart.set_style_opa(lv.OPA.COVER, lv.PART.CURSOR)
            self._setpoint_chart.set_cursor_point(self._cursor, self._setpoint_series, offset + cursor_idx)
        else:
            self._setpoint_chart.set_style_opa(lv.OPA.TRANSP, lv.PART.CURSOR)

    def _draw_axis_labels(self, y_lo, y_hi, levels):
        for w in self._axis_widgets:
            w.delete()
        self._axis_widgets = []

        span = y_hi - y_lo
        for v in levels:
            # y_ofs is relative to the graph area's own vertical center
            # (ALIGN.LEFT_MID's reference point), matching how the chart
            # widgets inside it map axis values to pixels -- both charts
            # and this graph_area share the same _CHART_H.
            y_ofs = int(_CHART_H * (y_hi - v) / span - _CHART_H / 2)

            line = _transparent(self._graph_area)
            line.set_size(_CHART_W, 1)
            line.set_style_bg_opa(lv.OPA.COVER, 0)
            # Darker than the label text (COLOR_TEXT_MUTED) -- these lines
            # sit underneath the data and only need to read as faint
            # structure, not compete with it. Reusing COLOR_BUTTON_OUTLINE
            # (theme.py's existing "duller/darker than COLOR_TRACK" gray)
            # rather than inventing a new gray constant.
            line.set_style_bg_color(theme.COLOR_BUTTON_OUTLINE, 0)
            line.align(lv.ALIGN.LEFT_MID, 0, y_ofs)
            self._axis_widgets.append(line)

            label = _label(self._graph_area, text=str(v), font=theme.FONT_TINY, color=theme.COLOR_TEXT_MUTED)
            label.align(lv.ALIGN.LEFT_MID, _CHART_W + _AXIS_GAP, y_ofs)
            self._axis_widgets.append(label)


def _axis_levels(data_lo, data_hi):
    """Rounds (data_lo, data_hi) out to whichever of _AXIS_STEPS first
    produces _AXIS_MAX_LEVELS or fewer evenly-spaced levels, returning
    (rounded_lo, rounded_hi, levels) -- rounded_lo/rounded_hi become the
    chart's own axis_range (so the drawn data lines up with the labels
    exactly), levels is what _draw_axis_labels() draws a gridline+label
    for.
    """
    lo = int(data_lo // 1)
    hi = int(-(-data_hi // 1))  # ceil, without needing the math module
    if hi <= lo:
        hi = lo + 1
    for step in _AXIS_STEPS:
        rlo = (lo // step) * step
        rhi = -(-hi // step) * step
        if rhi == rlo:
            rhi += step
        levels = list(range(rlo, rhi + 1, step))
        if len(levels) <= _AXIS_MAX_LEVELS:
            return rlo, rhi, levels
    return rlo, rhi, levels  # widest step still too many -- use it anyway


def _format_ago(age_ms, is_latest):
    if is_latest:
        return "Now"
    secs = max(age_ms, 0) // 1000
    minutes, secs = divmod(secs, 60)
    if minutes:
        return "%dm%ds ago" % (minutes, secs)
    return "%ds ago" % secs


def _fmt_temp_bare(v):
    # Same \xb0 reasoning as widgets._fmt_temp -- these are always real
    # floats (client.history never stores a None current_temp/setpoint,
    # see aircon_ble.py's _sample_history()), so no "--" fallback needed.
    return "%.1f\xb0" % v
