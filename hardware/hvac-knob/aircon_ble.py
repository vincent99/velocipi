"""BLE GATT central for the AirCon controller — a MicroPython/aioble port of
server/hardware/aircon/aircon.go's Client. Talks to the exact same 7
characteristics (see aircon_ble_config.py), same wire format: UTF-8 strings,
floats as "%.2f" decimal strings, JSON for the settings/status
characteristics.

AirCon-specific, as the name says -- see heater_ble.py for the second BLE
peripheral this panel talks to (a completely different wire protocol) and
ble_shared.py for the one thing genuinely shared between the two
(serializing aioble.scan() calls).

Requires `aioble` on the device (not part of stock MicroPython firmware —
install with `mpremote mip install aioble`, see ../README.md). Targets the
API documented in micropython-lib's aioble README/examples at the time of
writing; if a newer aioble release has renamed/reshaped something, this
central-role connect/subscribe flow is the most likely place to need
updating.

Unlike the original C++/NimBLE port (which needed a mutex because BLE
callbacks ran on a separate FreeRTOS task), everything here is a single
cooperative asyncio event loop, so plain attribute reads/writes on
AirconState are safe without locking — no two coroutines run truly
concurrently, only interleaved at `await` points.

AirconClient no longer connects to a hardcoded device name (see
aircon_ble_config.py) -- it's constructed with whatever panel_settings.py has
persisted (possibly ""), and set_device_name() (called by
screens.ConnectTile once the user picks one from scan_for_aircons()'s
results) both persists the new choice and wakes run() up to act on it.
"""

import asyncio
import json
import time

import aioble
import bluetooth

import ble_shared
import panel_settings
from aircon_ble_config import (
    AIRCON_SERVICE_UUID,
    UUID_MODE,
    UUID_FAN,
    UUID_SETPOINT,
    UUID_CIRC,
    UUID_PANEL,
    UUID_SETTINGS,
    UUID_STATUS,
)

# Sets this device's *preferred* MTU -- BLE's default ATT MTU is 23 bytes
# (22 usable bytes for a single GATT read response), which is why settings/
# status JSON reads were truncating at exactly 22 bytes (e.g.
# '{"delta": {"value": 2.') and failing json.loads. This alone is NOT
# sufficient, confirmed on real hardware and against MicroPython's own
# bluetooth module docs: config(mtu=...) only sets the value an exchange
# will use *if one happens*; something still has to actively request the
# exchange, which is _connect_and_run's gattc_exchange_mtu() call -- see
# the comment there for the full story (including two earlier wrong
# guesses: device.connect(mtu=...) doesn't exist on this aioble build, and
# config() alone silently does nothing on its own).
aioble.config(mtu=256)

_SVC = bluetooth.UUID(AIRCON_SERVICE_UUID)
_CHAR_UUIDS = {
    "mode": bluetooth.UUID(UUID_MODE),
    "fan": bluetooth.UUID(UUID_FAN),
    "setpoint": bluetooth.UUID(UUID_SETPOINT),
    "circ": bluetooth.UUID(UUID_CIRC),
    "panel": bluetooth.UUID(UUID_PANEL),
    "settings": bluetooth.UUID(UUID_SETTINGS),
    "status": bluetooth.UUID(UUID_STATUS),
}
_JSON_CHARS = ("settings", "status")
# Safety cap on _notify_loop's per-characteristic reassembly buffer -- both
# JSON characteristics' encoded payloads are comfortably under this in
# normal operation, so hitting it means the buffer has desynced (e.g. a
# stray fragment picked up mid-object after an earlier reset) and will
# never reach a valid _json_complete() on its own.
_JSON_BUF_MAX = 512

_SCAN_DURATION_MS = 5000
_PICKER_SCAN_DURATION_MS = 4000  # scan_for_aircons()'s default -- see screens.ConnectTile
_RECONNECT_DELAY_MS = 5000
# Quiet period after the last set_*() call before it's actually written over
# BLE -- see AirconClient._debounce(). Long enough to collapse a fast knob
# spin into one write, short enough that a deliberate single turn still
# feels responsive (the optimistic local update makes the UI itself feel
# instant either way -- this only delays when the real BLE round-trip
# happens). Bumped up from an initial 250ms -- too short a window let
# consecutive knob detents each start their own write+read round-trip
# before the next detent's debounce could cancel it, which is what the
# generation-check in set_*()/_commit_*() now guards against but this
# still reduces how often it's needed in the first place.
_DEBOUNCE_MS = 600

# RRD-style: starts fine-grained (1 sample/second) and, every time the
# buffer fills to _HISTORY_MAX_POINTS, halves itself (keeping every other
# point -- see _compact_history()) and doubles the recording interval for
# future samples, then keeps recording new points at that coarser interval
# until it fills again. Total stored points never exceeds _HISTORY_MAX_POINTS
# (also screens/history.py's graph width in pixels, so the graph is always
# 1 point/pixel with no interpolation needed) no matter how long the panel's
# been running -- older data just gets progressively less granular, trading
# resolution for reach instead of ever growing the buffer.
_HISTORY_INITIAL_INTERVAL_MS = 1_000
_HISTORY_MAX_POINTS = 180

# Fallback setpoint bounds used only until the controller's BLE settings
# characteristic (set_min/set_max) has been read at least once -- same
# values as home.HomeTile's own _DEFAULT_SETPOINT_MIN/MAX, duplicated
# rather than imported (this module is the model layer, home.py the view
# layer built on top of it -- importing the other way around would be
# backwards, and home.py touches theme/lv at import time, which this
# module has no business depending on).
_DEFAULT_SETPOINT_MIN = 0.0
_DEFAULT_SETPOINT_MAX = 100.0

class AirconState:
    def __init__(self):
        self.connected = False
        self.mode = ""
        self.fan = ""
        self.setpoint = 0.0
        self.circulation = ""
        self.panel_temp = 0.0
        # key -> {"value": float, "default": float} -- this local shape is
        # unchanged even though the wire format uses terser "v"/"d" keys
        # (see _apply_settings_json()); only the BLE JSON encoding is
        # compact, not this decoded representation.
        self.settings = {}

        self.current_temp = None
        self.compressor = ""
        self.cabin_temp = None
        self.blower_temp = None
        self.exhaust_temp = None
        self.compressor_temp = None
        self.baggage_temp = None
        self.tail_temp = None
        self.error = ""
        self.controller_version = ""  # from the status characteristic's "ver" -- see _apply_status_json()


def _json_complete(buf):
    """Same balanced-braces heuristic as aircon.go's jsonComplete(): detects
    when a JSON payload split across multiple BLE notifications is done.
    """
    if not buf:
        return False
    depth = 0
    in_str = False
    escape = False
    for b in buf:
        c = chr(b)
        if escape:
            escape = False
            continue
        if in_str:
            if c == "\\":
                escape = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
    return depth == 0


class AirconClient:
    def __init__(self, device_name=""):
        self.device_name = device_name  # "" until the user picks one on the Connect screen
        self.state = AirconState()
        self.dirty = asyncio.Event()
        # Separate from `dirty` (which screens/ uses for "redraw something"
        # and fires on every change below, state or settings alike): these
        # two let serial_link.py tell apart "push a state message" from
        # "push a settings message" to the Pi, without it having to
        # re-derive that distinction itself. Only set from paths that
        # actually reflect something *received from BLE* (a notify, an
        # initial read, or a debounced write's read-back) -- not from the
        # optimistic local updates set_mode()/set_setting()/etc. apply
        # before the BLE round-trip completes, so the Pi doesn't see a
        # "state changed" push for a change it may have itself requested
        # (via the knob's setSettings) before BLE has actually confirmed it.
        self.state_dirty = asyncio.Event()
        self.settings_dirty = asyncio.Event()
        self._chars = {}
        # The live aioble connection object, or None whenever not
        # connected -- set/cleared by _connect_and_run(), read by
        # set_device_name() to force-disconnect a *different* device's
        # still-live connection when the user picks a new one from
        # screens.InfoTile's "change device" buttons (screens/__init__.py's
        # App.request_reconnect()) rather than only from a fresh, nothing-
        # picked-yet state. Without this, run()'s reconnect loop has no
        # reason to ever revisit self.device_name while the *old*
        # connection is still healthy -- it only re-reads device_name after
        # a connection actually ends.
        self._connection = None
        # Wakes run() immediately when set_device_name() gives it something
        # to connect to, instead of leaving it idling until whatever poll
        # interval it happened to be sleeping on.
        self._name_event = asyncio.Event()
        # field name -> pending debounce asyncio.Task, see _debounce().
        self._pending = {}
        # field name -> generation counter, see the set_*()/_commit_*()
        # methods' comment near the bottom of this class.
        self._gen = {}
        # (setpoint, current_temp) tuples, oldest first, capped at
        # _HISTORY_MAX_POINTS -- see _history_loop()/_sample_history(). Not
        # part of AirconState: this is derived/local bookkeeping, not a raw
        # mirror of anything BLE reports directly.
        #
        # Deliberately no per-point timestamp (unlike an earlier version):
        # RRD-style compaction (_compact_history()) always keeps whatever
        # survives evenly spaced at exactly history_interval_ms, for any
        # point currently in the buffer regardless of how many compactions
        # it's lived through -- an invariant of repeated "keep every other
        # point" decimation applied to an evenly-spaced series -- so a
        # point's age is fully recoverable from its position alone (see
        # history_age_ms()) without spending a field on it.
        self.history = []
        # Current recording interval -- starts at _HISTORY_INITIAL_INTERVAL_MS,
        # doubles on each compaction. Public (not a leading-underscore
        # field): screens/history.py's HistoryTile reads this indirectly via
        # history_age_ms() to compute each point's "X ago" label.
        self.history_interval_ms = _HISTORY_INITIAL_INTERVAL_MS
        # ticks_ms() of the most recent sample, or None before the first one
        # -- lets history_age_ms() account for however much of the current
        # interval has elapsed since that sample, so the latest point's age
        # ticks up smoothly in the UI instead of jumping once per interval.
        self._history_last_ms = None

    def _mark_dirty(self):
        self.dirty.set()

    def _mark_state_dirty(self):
        self.dirty.set()
        self.state_dirty.set()

    def _mark_settings_dirty(self):
        self.dirty.set()
        self.settings_dirty.set()

    def _debounce(self, key, coro):
        """Cancels any not-yet-fired debounce task for `key` and replaces it
        with one that runs `coro` (an already-constructed coroutine, e.g.
        from calling an `async def` method) after _DEBOUNCE_MS of quiet.

        Used by the set_*() methods below so a burst of rapid changes to
        the same field -- e.g. spinning the knob several detents in a row,
        which calls set_fan()/set_setpoint() once per detent -- collapses
        into a single BLE write + re-read of whatever the final value ended
        up being, instead of one write+read round-trip per detent.
        """
        prev = self._pending.get(key)
        if prev is not None:
            prev.cancel()
        self._pending[key] = asyncio.create_task(self._debounce_run(coro))

    async def _debounce_run(self, coro):
        try:
            await asyncio.sleep_ms(_DEBOUNCE_MS)
        except asyncio.CancelledError:
            return
        try:
            await coro
        except Exception as e:
            # Same reasoning as _notify_loop's try/except: this runs as an
            # orphaned task with nothing else awaiting it, so an unhandled
            # exception here would vanish silently instead of just failing
            # this one write.
            print("aircon_ble: debounced write failed: %s" % e)

    def set_device_name(self, name):
        """Called by screens.ConnectTile when the user picks a device from
        the scan list. Persists it (so it's still picked after a reboot)
        and wakes run() if it was idling with no device chosen yet.

        If a connection is already live (screens.InfoTile's "change
        device" flow, unlike the original first-time-pairing flow, always
        hits this case), also force-disconnects it -- run()'s loop only
        re-reads self.device_name once its current connection ends, so
        without this a change here would otherwise sit ignored for as long
        as the old connection happens to stay healthy, which could be
        indefinitely.
        """
        self.device_name = name
        panel_settings.set_aircon_device_name(name)
        self._name_event.set()
        if self._connection is not None:
            asyncio.create_task(self._disconnect_current())

    async def _disconnect_current(self):
        # NOT hardware-verified: aioble.DeviceConnection.disconnect() is
        # this project's best guess at the method name/shape (matches
        # aioble's own documented central-role API) -- every other aioble
        # call site in this file was confirmed against real hardware
        # first; this is the one exception, added for screens.InfoTile's
        # "change device" buttons without a real device on hand to verify
        # against. If picking a new device from that screen doesn't
        # actually drop the old connection, check here first.
        try:
            await self._connection.disconnect()
        except Exception as e:
            print("aircon_ble: disconnect (for device change) failed: %s" % e)

    def setpoint_bounds(self):
        """Public (not a leading-underscore helper, unlike most of this
        class's internals): both _sample_history() below and
        screens/history.py's HistoryTile (Y-axis scaling) need this exact
        same lookup.

        "set_min"/"set_max", not "setpoint_min"/"setpoint_max" -- see
        _apply_settings_json() for the terse wire key names. Same lookup
        home.HomeTile._setpoint_min()/_setpoint_max() do independently
        (duplicated, not shared -- see _DEFAULT_SETPOINT_MIN/MAX's
        comment above for why).
        """
        sv_min = self.state.settings.get("set_min")
        sv_max = self.state.settings.get("set_max")
        lo = sv_min["value"] if sv_min else _DEFAULT_SETPOINT_MIN
        hi = sv_max["value"] if sv_max else _DEFAULT_SETPOINT_MAX
        return lo, hi

    def _sample_history(self):
        """Appends one history point, if there's a real current_temp to
        record yet (skipped otherwise -- e.g. before the first BLE read
        ever completes). mode=off/fan/cool don't have a real controller-
        driven setpoint (the knob's dial controls fan speed in those modes
        instead -- see home.HomeTile.handle_knob()), so the logged
        setpoint there is a synthetic stand-in instead of the stale/
        meaningless real one: setpoint_max for off (nothing is trying to
        cool at all, so "no limit" reads most honestly as the ceiling) and
        setpoint_min for fan/cool (cool mode runs the compressor
        continuously already, i.e. always trying to reach the coldest
        allowed point). auto logs the real setpoint unchanged.
        """
        s = self.state
        if s.current_temp is None:
            return
        lo, hi = self.setpoint_bounds()
        if s.mode == "off":
            setpoint = hi
        elif s.mode in ("fan", "cool"):
            setpoint = lo
        else:
            setpoint = s.setpoint
        if len(self.history) >= _HISTORY_MAX_POINTS:
            self._compact_history()
        self.history.append((setpoint, s.current_temp))
        self._history_last_ms = time.ticks_ms()

    def _compact_history(self):
        """RRD-style: halves the buffer by keeping every other point (oldest
        first, so which parity survives is stable across repeated
        compactions) and doubles history_interval_ms so future samples
        continue at the new, coarser spacing -- keeps total stored points
        bounded at _HISTORY_MAX_POINTS forever instead of ever growing the
        buffer, at the cost of resolution on older data.
        """
        self.history = self.history[0::2]
        self.history_interval_ms *= 2

    def history_age_ms(self, index):
        """Milliseconds "ago" for self.history[index] (0 == oldest) --
        derived purely from position * history_interval_ms rather than a
        stored per-point timestamp (see self.history's own comment for why
        that's exact, not approximate, under RRD-style compaction). The
        trailing term accounts for whatever fraction of the current
        interval has elapsed since the last real sample, so the latest
        point's age ticks up smoothly rather than jumping only once per
        interval.
        """
        steps_from_latest = len(self.history) - 1 - index
        age = steps_from_latest * self.history_interval_ms
        if self._history_last_ms is None:
            return age
        return age + max(time.ticks_diff(time.ticks_ms(), self._history_last_ms), 0)

    async def _history_loop(self):
        while True:
            await asyncio.sleep_ms(self.history_interval_ms)
            self._sample_history()

    async def run(self):
        """Runs forever: scan, connect, subscribe, reconnect on drop. Waits
        (without scanning) whenever no device has been picked yet --
        set_device_name() wakes this back up as soon as one is.
        """
        asyncio.create_task(self._history_loop())
        while True:
            if not self.device_name:
                self.state.connected = False
                self._mark_state_dirty()
                await self._name_event.wait()
                self._name_event.clear()
                continue

            # try/except wraps _find_device() too, not just
            # _connect_and_run() -- confirmed on real hardware that
            # _find_device()'s aioble.scan() can itself raise (OSError 16,
            # a radio-busy collision with the *other* client's connect();
            # see ble_shared.py -- this run() loop is now the backstop for
            # whatever radio_lock doesn't manage to prevent). An earlier
            # version only caught exceptions from _connect_and_run(),
            # which let a scan failure escape run() entirely and silently
            # kill this client's reconnect loop for the rest of the boot
            # (surfaced as an unretrieved-task-exception traceback with no
            # further reconnect attempts ever, not just one failed one).
            try:
                device = await self._find_device()
                if device is not None:
                    await self._connect_and_run(device)
            except Exception as e:
                print("aircon_ble: connection error:", e)
            self.state.connected = False
            self._chars = {}
            self._connection = None
            self._mark_state_dirty()
            await asyncio.sleep_ms(_RECONNECT_DELAY_MS)

    async def _find_device(self):
        print("aircon_ble: scanning for %r..." % (self.device_name,))
        async with ble_shared.radio_lock:
            async with aioble.scan(
                _SCAN_DURATION_MS,
                interval_us=ble_shared.SCAN_INTERVAL_US,
                window_us=ble_shared.SCAN_WINDOW_US,
                active=True,
            ) as scanner:
                async for result in scanner:
                    if result.name() == self.device_name:
                        return result.device
        return None

    async def scan_for_aircons(self, duration_ms=_PICKER_SCAN_DURATION_MS):
        """Scans for any BLE peripheral advertising AIRCON_SERVICE_UUID --
        not by name, since each physical controller can have its own custom
        BLE_DEVICE_NAME (see aircon_ble_config.py's docstring) -- for
        screens.ConnectTile's device picker. Returns (found, other_count):
        `found` is a list of (name, aioble.Device) pairs, deduplicated and
        sorted by name (devices with no advertised name are skipped, since
        there'd be nothing sensible to show/select for those); other_count
        is the number of distinct non-matching BLE devices also seen in
        this pass, deduplicated by address where possible -- so
        screens.ConnectTile can show "scanning... N other devices found"
        while no AirCon has turned up yet, as reassurance that the radio
        itself is working rather than just silently sitting at zero.

        NOT hardware-verified: result.services() is this project's best
        guess at how aioble exposes a scan result's advertised service
        UUIDs (matching the shape used in aioble's own examples) -- see
        ../README.md's "Still open" list for the rest of this project's
        unverified aioble surface. Confirmed working against a live radio.
        result.device.addr (for other_count's dedup) is a separate, still
        untested guess -- falls back to counting every non-matching
        advertisement if that attribute isn't there.
        """
        seen = set()
        found = []
        other_addrs = set()
        other_count = 0
        async with ble_shared.radio_lock:
            async with aioble.scan(
                duration_ms,
                interval_us=ble_shared.SCAN_INTERVAL_US,
                window_us=ble_shared.SCAN_WINDOW_US,
                active=True,
            ) as scanner:
                async for result in scanner:
                    name = result.name()
                    try:
                        svcs = list(result.services())
                    except Exception as e:
                        print("aircon_ble: scan: result.services() failed for %r: %s" % (name, e))
                        svcs = []
                    if _SVC in svcs and name:
                        if name not in seen:
                            seen.add(name)
                            found.append((name, result.device))
                        continue
                    try:
                        addr = bytes(result.device.addr)
                    except Exception:
                        addr = None
                    if addr is None or addr not in other_addrs:
                        if addr is not None:
                            other_addrs.add(addr)
                        other_count += 1
        found.sort(key=lambda pair: pair[0])
        return found, other_count

    async def _connect_and_run(self, device):
        print("aircon_ble: connecting...")
        # ble_shared.radio_lock, not just held for scanning -- see that
        # module's own docstring: confirmed on real hardware that a
        # connect() here racing the *other* client's scan() raises
        # OSError 16, presumably the same "radio already busy with a GAP
        # procedure" constraint scan-vs-scan already needed this lock for.
        # Only held through connection establishment, not this
        # connection's whole subsequent lifetime -- see that module's
        # docstring for why that's deliberate.
        async with ble_shared.radio_lock:
            # NOT device.connect(..., mtu=256): confirmed on real hardware
            # that this installed aioble build's connect() doesn't accept
            # an mtu kwarg at all ("unexpected keyword argument 'mtu'").
            connection = await device.connect(timeout_ms=5000)
        self._connection = connection
        async with connection:
            # The fix for the settings/status JSON truncation (see
            # aioble.config(mtu=256) above): that call alone only sets the
            # *preferred* MTU, per MicroPython's bluetooth module docs --
            # the exchange itself must be actively triggered, and aioble
            # never does that on its own (central.py/client.py have no
            # gattc_exchange_mtu call anywhere), so it's done manually here.
            # bluetooth.BLE() is a singleton, so constructing it again just
            # returns aioble's own radio object. connection._conn_handle is
            # private (no public accessor), used because aioble's own
            # central.py._connect() relies on that same attribute name
            # internally.
            #
            # No IRQ handler awaits the _IRQ_MTU_EXCHANGED completion event
            # -- bluetooth.BLE.irq() only supports one global callback, and
            # aioble already owns that slot for its own dispatch, so a
            # fixed sleep stands in for it instead (the exchange is one
            # fast round-trip, and service/characteristic discovery right
            # after this adds further real time before the first read).
            try:
                bluetooth.BLE().gattc_exchange_mtu(connection._conn_handle)
                await asyncio.sleep_ms(200)
            except Exception as e:
                print("aircon_ble: MTU exchange request failed: %s" % e)

            service = await connection.service(_SVC)
            if service is None:
                print("aircon_ble: service not found")
                return

            chars = {}
            for name, uuid in _CHAR_UUIDS.items():
                try:
                    chars[name] = await service.characteristic(uuid)
                except Exception:
                    chars[name] = None
            self._chars = chars

            # Sequential, not one asyncio.create_task() per characteristic --
            # ch.subscribe() does CCCD descriptor discovery under the hood,
            # and aioble only allows one discovery in flight per connection
            # at a time. Firing all of them at once (as _notify_loop used to
            # do internally, all scheduled together right below) raced for
            # that single-discovery guard and most of them lost with
            # "ValueError: Discovery in progress".
            for name, ch in chars.items():
                if ch is None:
                    continue
                try:
                    await ch.subscribe(notify=True)
                except Exception as e:
                    print("aircon_ble: subscribe %s failed: %s" % (name, e))

            await self._read_initial()

            self.state.connected = True
            self._mark_state_dirty()
            print("aircon_ble: connected")

            tasks = [
                asyncio.create_task(self._notify_loop(name, ch))
                for name, ch in chars.items()
                if ch is not None
            ]
            try:
                await connection.disconnected()
            finally:
                for t in tasks:
                    t.cancel()
        print("aircon_ble: disconnected")

    async def _read_str(self, name):
        ch = self._chars.get(name)
        if ch is None:
            return ""
        try:
            data = await ch.read()
        except Exception:
            return ""
        return data.decode().rstrip("\x00")

    async def _read_initial(self):
        s = self.state
        s.mode = await self._read_str("mode") or s.mode
        s.fan = await self._read_str("fan") or s.fan
        sp = await self._read_str("setpoint")
        if sp:
            s.setpoint = float(sp)
        s.circulation = await self._read_str("circ") or s.circulation
        pt = await self._read_str("panel")
        if pt:
            s.panel_temp = float(pt)

        settings_raw = await self._read_str("settings")
        if settings_raw:
            self._apply_settings_json(settings_raw)
        status_raw = await self._read_str("status")
        if status_raw:
            self._apply_status_json(status_raw)

    async def _notify_loop(self, name, ch):
        # Subscription itself now happens up front in _connect_and_run,
        # sequentially across all characteristics -- see the comment there.
        buf = b""
        while True:
            try:
                data = await ch.notified()
            except asyncio.CancelledError:
                # Let cancellation (from _connect_and_run's `finally:
                # t.cancel()`, once its own await connection.disconnected()
                # wakes up) propagate normally rather than being absorbed
                # here -- swallowing it would make this task finish
                # "successfully" from asyncio's point of view instead of
                # actually cancelled, which isn't what the caller asked for.
                raise
            except Exception as e:
                # Anything else -- chiefly aioble.DeviceDisconnectedError,
                # raised straight out of ch.notified() when the peripheral
                # drops (confirmed: happens when the sim/real controller is
                # turned off) -- means this characteristic's notify stream
                # is over; there's nothing left to loop on. Ending the task
                # cleanly here avoids the "Task exception wasn't retrieved"
                # traceback this used to produce on every disconnect, and
                # doesn't need to wait on _connect_and_run's own
                # connection.disconnected() + cancel() to get there.
                print("aircon_ble: %s notify loop ending: %s" % (name, e))
                return
            # Everything below is wrapped in try/except: this loop runs as
            # an orphaned asyncio.create_task (see _connect_and_run) with
            # nothing awaiting or catching it, so any unhandled exception
            # here -- a stray decode error, a JSON value shaped differently
            # than expected, a mid-stream reassembly glitch in buf -- would
            # silently kill this characteristic's notify loop *forever*,
            # leaving its state frozen (e.g. current_temp stuck at "--")
            # while every other characteristic's independent notify loop
            # keeps working fine. Reset buf on any failure so a garbled
            # in-flight reassembly self-heals on the next notification
            # instead of wedging permanently.
            try:
                if name in _JSON_CHARS:
                    # If this is the start of a new message, require it to
                    # actually look like the start of one -- both JSON
                    # characteristics always encode a top-level object, so a
                    # fresh buffer that doesn't open with "{" is a stray
                    # fragment left over from a desync (see _JSON_BUF_MAX)
                    # rather than a real message, and accumulating it would
                    # just carry the desync forward instead of dropping it.
                    if buf or data[:1] == b"{":
                        buf += data
                    if len(buf) > _JSON_BUF_MAX:
                        print("aircon_ble: %s reassembly buffer desynced, resetting" % name)
                        buf = b""
                    elif _json_complete(buf):
                        text = buf.decode()
                        buf = b""
                        if name == "settings":
                            self._apply_settings_json(text)
                        else:
                            self._apply_status_json(text)
                else:
                    value = data.decode().rstrip("\x00")
                    s = self.state
                    if name == "mode":
                        s.mode = value
                    elif name == "fan":
                        s.fan = value
                    elif name == "setpoint":
                        s.setpoint = float(value)
                    elif name == "circ":
                        s.circulation = value
                    elif name == "panel":
                        s.panel_temp = float(value)
                    self._mark_state_dirty()
            except Exception as e:
                print("aircon_ble: notify %s failed: %s" % (name, e))
                buf = b""

    def _apply_settings_json(self, text):
        try:
            raw = json.loads(text)
        except ValueError:
            print("aircon_ble: settings JSON parse error:", text)
            return
        # Each entry is a bare [value, default] 2-element array (not a
        # {"v":.., "d":..} object) to keep this characteristic's JSON
        # payload compact -- see aircon-sim/ble_server.py's
        # _unwrap_settings() docstring for the full reasoning. Keys
        # themselves are also terse wire names now (e.g. "set_min", not
        # "setpoint_min" -- see that same file's SETTINGS_WIRE_KEYS): this
        # class has no need for a separate verbose internal name the way
        # the controllers do, so self.state.settings is keyed by whatever
        # comes over the wire directly. Decoded into the same
        # {"value":.., "default":..} local shape as before regardless (see
        # AirconState.settings above).
        settings = {}
        for key, v in raw.items():
            if isinstance(v, (int, float)):
                settings[key] = {"value": float(v), "default": float(v)}
            elif isinstance(v, (list, tuple)):
                val = float(v[0]) if len(v) > 0 and v[0] is not None else 0.0
                default = float(v[1]) if len(v) > 1 and v[1] is not None else val
                settings[key] = {"value": val, "default": default}
        self.state.settings = settings
        self._mark_settings_dirty()

    def _apply_status_json(self, text):
        try:
            raw = json.loads(text)
        except ValueError:
            print("aircon_ble: status JSON parse error:", text)
            return
        s = self.state
        s.current_temp = raw.get("curr")
        s.compressor = raw.get("comp") or ""
        s.cabin_temp = raw.get("cabin")
        s.blower_temp = raw.get("blower")
        s.exhaust_temp = raw.get("exhaust")
        s.compressor_temp = raw.get("comptemp")
        s.baggage_temp = raw.get("baggage")
        s.tail_temp = raw.get("tail")
        s.error = raw.get("err") or ""
        s.controller_version = raw.get("ver") or ""
        self._mark_state_dirty()

    # --- writes -------------------------------------------------------

    async def _write_str(self, name, value):
        ch = self._chars.get(name)
        if ch is None:
            return False
        try:
            await ch.write(value.encode(), response=False)
            return True
        except Exception as e:
            print("aircon_ble: write %s failed: %s" % (name, e))
            return False

    # Each set_*() below applies the change to self.state immediately
    # (optimistic update -- refresh() picks it up on the very next redraw,
    # before any BLE round-trip has happened) and hands the actual write off
    # to _debounce(), which coalesces a burst of rapid calls (e.g. spinning
    # the knob) into one write. Once that debounced write lands, the
    # corresponding _commit_*() re-reads the characteristic and reconciles
    # self.state with whatever the controller actually accepted -- e.g. a
    # setpoint clamped to its min/max, or a write that silently didn't take.
    #
    # Each set_*() also bumps a per-field entry in self._gen and hands the
    # value it captured to its _commit_*(), which only applies its re-read
    # result if that generation is still current when it finishes. Without
    # this, a commit's write+read round-trip (real BLE latency, not
    # instant) can still be in flight when a *newer* set_*() call lands --
    # e.g. the knob turning again before the previous debounce fired -- and
    # the stale re-read would otherwise overwrite the newer optimistic
    # value with an outdated one, right before that older value gets
    # reverted anyway. Relying on _debounce()'s Task.cancel() alone isn't
    # enough to prevent this: cancellation only takes effect at the
    # commit's next await point, and (unconfirmed, but plausible on
    # MicroPython's asyncio) a CancelledError raised inside _write_str/
    # _read_str's own `except Exception` blocks may simply get swallowed
    # there instead of propagating, letting the stale commit run to
    # completion regardless.

    def _bump_gen(self, key):
        gen = self._gen.get(key, 0) + 1
        self._gen[key] = gen
        return gen

    async def set_mode(self, mode):
        self.state.mode = mode
        self._mark_dirty()
        self._debounce("mode", self._commit_mode(mode, self._bump_gen("mode")))

    async def _commit_mode(self, mode, gen):
        await self._write_str("mode", mode)
        val = await self._read_str("mode")
        if val and self._gen.get("mode") == gen:
            self.state.mode = val
            self._mark_state_dirty()

    async def set_fan(self, fan):
        self.state.fan = fan
        self._mark_dirty()
        self._debounce("fan", self._commit_fan(fan, self._bump_gen("fan")))

    async def _commit_fan(self, fan, gen):
        await self._write_str("fan", fan)
        val = await self._read_str("fan")
        if val and self._gen.get("fan") == gen:
            self.state.fan = val
            self._mark_state_dirty()

    async def set_circulation(self, circ):
        self.state.circulation = circ
        self._mark_dirty()
        self._debounce("circ", self._commit_circ(circ, self._bump_gen("circ")))

    async def _commit_circ(self, circ, gen):
        await self._write_str("circ", circ)
        val = await self._read_str("circ")
        if val and self._gen.get("circ") == gen:
            self.state.circulation = val
            self._mark_state_dirty()

    async def set_setpoint(self, fahrenheit):
        self.state.setpoint = fahrenheit
        self._mark_dirty()
        self._debounce("setpoint", self._commit_setpoint(fahrenheit, self._bump_gen("setpoint")))

    async def _commit_setpoint(self, fahrenheit, gen):
        await self._write_str("setpoint", "%.2f" % fahrenheit)
        val = await self._read_str("setpoint")
        if val and self._gen.get("setpoint") == gen:
            self.state.setpoint = float(val)
            self._mark_state_dirty()

    async def set_panel_temp(self, fahrenheit):
        # No knob-side UI edits this today -- it exists so serial_link.py
        # can relay a setPanelTemp command from the Pi (planned: the Pi
        # pushing its own front-of-plane temperature reading down to the
        # controller). Same debounce+commit+reread shape as set_setpoint
        # regardless, since it's still just another characteristic write.
        self.state.panel_temp = fahrenheit
        self._mark_dirty()
        self._debounce("panel", self._commit_panel_temp(fahrenheit, self._bump_gen("panel")))

    async def _commit_panel_temp(self, fahrenheit, gen):
        await self._write_str("panel", "%.2f" % fahrenheit)
        val = await self._read_str("panel")
        if val and self._gen.get("panel") == gen:
            self.state.panel_temp = float(val)
            self._mark_state_dirty()

    async def set_setting(self, key, value):
        # Optimistic update, like the other set_*() methods above -- but no
        # debounce/commit-and-reread needed here (unlike those), since this
        # only ever fires once per explicit user commit (see
        # screens/settings.py's SettingsTile), not once per knob detent
        # during a continuous drag. The settings characteristic's own
        # push-on-change (see aircon-sim/ble_server.py's push()) reconciles
        # this the same way it already does for every other settings write.
        sv = self.state.settings.get(key)
        if sv is not None:
            sv["value"] = value
            self._mark_dirty()
        return await self._write_str("settings", json.dumps({key: value}))
