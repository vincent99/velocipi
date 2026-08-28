"""BLE GATT central for the second peripheral this panel talks to: a
white-label parking-heater platform, completely unrelated to the AirCon
controller's own protocol (see aircon_ble.py) -- different service, one
binary framed protocol over a single characteristic instead of one
characteristic per field, no vendor documentation at all (reconstructed by
decompiling the Android app that ships with this class of heater -- see
../../scratch/airheater-ble-protocol.md and heater_ble_config.py's module
docstring for the full story and every "NOT hardware-verified" caveat that
implies).

Structurally mirrors aircon_ble.py's AirconClient on purpose (same run()
reconnect loop shape, same scan_for_*()/set_device_name() shape so
screens/connect.py's ConnectTile can drive either client generically, same
debounce-collapses-a-knob-spin-into-one-write pattern) but is NOT a byte-
for-byte port of anything -- there's no Go/C++ reference implementation for
this protocol anywhere in this repo, unlike the AirCon side.

Three real differences from AirconClient worth knowing before touching this:
  1. No read-back. AirconClient's set_*() methods write, then re-read the
     characteristic to reconcile self.state with whatever the controller
     actually accepted (e.g. a clamped setpoint). This protocol's single
     characteristic has no such request/response read semantics -- writes
     are fire-and-forget, and status only ever arrives as an unsolicited
     notification. So state.on/run_mode/run_param are purely optimistic
     (whatever this client itself last commanded), not reconciled against
     the device at all -- see HeaterState's own docstring. CMD_HANDSHAKE
     (see _attempt_handshake()) is the one exception -- it's the only
     command this client ever actually waits on a response for.
  2. Pairing is opt-in and non-blocking (see screens/__init__.py's App):
     unlike the AirCon controller, which gates the whole panel (Home is
     unreachable without one), a missing/disconnected heater just means
     "heat" mode and auto mode's heating branch quietly do nothing --
     see screens/home.py.
  3. Password detection is a best-effort heuristic, not a confirmed
     protocol feature. Some physical units apparently require a 4-digit
     PIN (`CMD_HANDSHAKE`/`SUB_HANDSHAKE`, byte offsets and encoding taken
     from the vendor app's `writeBufferData`/`uu()` functions -- see the
     scratch/ doc) before accepting control commands; this client sends
     that handshake on every fresh connection and waits briefly for an
     explicit accept/reject. If nothing answers at all within
     _HANDSHAKE_TIMEOUT_MS, the *first* time this device is ever probed
     this session, that's read as "this unit doesn't gate on a password"
     rather than "wrong password" -- deliberately optimistic, so units
     that simply don't implement/answer this command (plausibly most of
     them) aren't mistaken for password-protected ones and don't need a
     PIN nobody has. Once an explicit reject has been seen even once,
     though, later ambiguous timeouts stay conservative (password still
     treated as required) rather than being reinterpreted as "must not be
     needed after all" right after a failed attempt -- see
     _attempt_handshake().

NOT hardware-verified, in addition to everything heater_ble_config.py
already flags: whether this board's BLE stack (aioble/the underlying
`bluetooth` module in this lvgl_micropython build) can hold two independent
central connections open at once at all -- one to the AirCon controller,
one to this heater. ../README.md's "Still open" list already documents a
DIFFERENT single-central constraint (the AirCon controller itself accepting
only one central at a time, panel vs. the Pi) -- this is a separate
concern: whether the ESP32's *own* radio/stack can be central to two
different peripherals simultaneously. Most NimBLE-based ports support this
(configurable connection limit, commonly >1), but this specific custom
firmware build's config isn't confirmed. If pairing a heater makes the
AirCon connection itself flaky or vice versa, this is the first thing to
suspect -- check with `make repl` by watching both clients' connect/
disconnect logs together.
"""

import asyncio

import aioble
import bluetooth

import ble_shared
import heater_ble_config as cfg
import panel_settings

_SVC = bluetooth.UUID(cfg.SERVICE_UUID)
_CHAR = bluetooth.UUID(cfg.CHAR_UUID)

_SCAN_DURATION_MS = 5000
_PICKER_SCAN_DURATION_MS = 4000  # scan_for_heaters()'s default -- see screens.ConnectTile
_RECONNECT_DELAY_MS = 5000
# Same reasoning as aircon_ble.py's own _DEBOUNCE_MS: collapses a fast knob
# spin (heat mode's level dial, or auto mode's continuous target-temp
# updates -- see screens/home.py) into one write instead of one per detent/
# per refresh tick.
_DEBOUNCE_MS = 600

# Safety cap on _notify_loop's reassembly buffer, same purpose as
# aircon_ble.py's _JSON_BUF_MAX: every real frame this protocol ever sends
# or receives is well under this (see heater_ble_config.py's frame-format
# comment -- a run-family status push is under 20 bytes), so a buffer this
# large means a desync, not a legitimately large in-flight frame.
_MAX_FRAME_LEN = 64

# How long _attempt_handshake() waits for an explicit accept/reject before
# giving up on this attempt -- see this module's docstring, point 3, for
# what happens on that timeout. Generous relative to a single BLE
# round-trip (the notify path has already proven itself well under 1s in
# practice for status pushes), not tuned against a real password-protected
# unit -- shorten if a real one answers reliably faster, lengthen if it
# turns out slower than this.
_HANDSHAKE_TIMEOUT_MS = 3000


def _checksum(buf, length):
    """8-bit sum of buf[0:length-1], mod 256 -- see heater_ble_config.py's
    frame-format comment. `length` is the frame's own declared total
    length (bytes 4-5), i.e. the checksum covers everything through the
    byte immediately before itself.
    """
    total = 0
    for i in range(length - 1):
        total += buf[i]
    return total & 0xFF


def _encode_frame(cmd1, cmd2, payload=b""):
    length = 8 + len(payload) + 1  # header(8) + payload + checksum
    buf = bytearray(length)
    buf[0] = cfg.HEAD_1
    buf[1] = cfg.HEAD_2
    buf[2] = cfg.PROTOCOL_VERSION
    buf[3] = 0  # sequence number -- always 0, no multi-packet writes needed here
    buf[4] = length & 0xFF
    buf[5] = (length >> 8) & 0xFF
    buf[6] = cmd1
    buf[7] = cmd2
    buf[8 : 8 + len(payload)] = payload
    buf[length - 1] = _checksum(buf, length)
    return bytes(buf)


def _encode_password(password):
    """CMD_HANDSHAKE's payload -- matches the vendor app's own encoding
    exactly (writeBufferData in the decompiled JS, see the scratch/ doc):
    NOT a 2-byte little-endian integer, a base-100 split -- byte0 =
    password % 100, byte1 = password // 100 (e.g. 1234 -> (34, 12)).
    """
    return bytes((password % 100, password // 100))


class HeaterState:
    def __init__(self):
        self.connected = False
        # Optimistic only -- whatever this client itself last commanded,
        # not reconciled against the device (see this module's own
        # docstring, point 1). Starts at the safe "definitely off" default
        # rather than guessing.
        self.on = False
        self.run_mode = None  # last-commanded cfg.RUN_MODE_* constant, or None before ever set
        self.run_param = None  # last-commanded gear level (RUN_MODE_GEAR) or target deg C (RUN_MODE_THERMOSTAT)
        # Best-effort telemetry decoded from the device's own status
        # notifications (see HeaterClient._apply_notification()) -- unlike
        # on/run_mode/run_param above, these two are NOT fed back into any
        # control decision, only shown if screens/home.py wants to display
        # them, precisely because this protocol's run_state/fault encoding
        # isn't confidently understood yet (see heater_ble_config.py).
        self.now_gear = None
        self.fault_code = None
        # Tri-state, set by HeaterClient._attempt_handshake() -- see this
        # module's docstring, point 3, for the detection heuristic:
        #   None  -- not yet probed on this BLE connection at all (still
        #            connecting, or the very first handshake attempt of
        #            this connection is in flight). screens/__init__.py's
        #            App treats this the same as "not connected yet" --
        #            keeps showing heater_disconnected.
        #   True  -- a password is required and hasn't been satisfied yet.
        #            App shows screens.heater_password.HeaterPasswordTile;
        #            _apply_run()/power_off() below refuse to send control
        #            commands while this is true.
        #   False -- no password needed, or the stored one was accepted.
        #
        # Deliberately reset to None only once, right when a fresh BLE
        # connection is established (_connect_and_run) -- NOT on every
        # individual handshake attempt after that (e.g. a retry from
        # set_password()). A retry's *previous* True stays in place for
        # the whole time that retry is in flight, so App's screen-
        # selection gate has no reason to flicker away from the password
        # screen mid-retry. password_check_pending below exists
        # specifically so screens.heater_password.HeaterPasswordTile can
        # still tell "my retry's answer isn't back yet" apart from "that
        # True you're looking at already reflects my retry" without this
        # field needing to go ambiguous (None) for that.
        self.password_required = None
        # True for the duration of any single _attempt_handshake() call,
        # regardless of what triggered it -- set synchronously (not just
        # inside the coroutine itself) by both call sites before the
        # coroutine actually starts running, so a caller can never observe
        # a stale "not pending" in the gap between kicking off a new
        # attempt and that attempt's first await -- see set_password()'s
        # own comment.
        self.password_check_pending = False


class HeaterClient:
    def __init__(self, device_name="", password=None):
        self.device_name = device_name  # "" until picked on the Connect screen, or explicitly skipped -- see panel_settings.py
        # None (never entered, see panel_settings.get_heater_password())
        # collapses to 0 here -- _attempt_handshake() always needs a
        # concrete byte value to send, and most units don't check this
        # command at all (see this module's docstring, point 3) so a
        # never-entered "password" of 0000 is a harmless default, not a
        # real guess at anything.
        self.password = password if password is not None else 0
        self.state = HeaterState()
        self.dirty = asyncio.Event()
        self._char = None
        # The live aioble connection object, or None whenever not connected
        # -- same purpose as aircon_ble.AirconClient._connection: lets
        # set_device_name() force-disconnect a still-live *different*
        # connection when the user picks a new heater from screens.
        # InfoTile's "change device" buttons (screens/__init__.py's App.
        # request_reconnect()), which run()'s reconnect loop otherwise has
        # no reason to ever notice until that old connection ends on its
        # own.
        self._connection = None
        self._name_event = asyncio.Event()
        # key -> pending debounce asyncio.Task -- same single shared "run"
        # key for power_on/power_off/set_heat_level/set_auto_target (see
        # _apply_run()'s docstring for why they all collapse together
        # rather than each having their own key the way AirconClient's
        # mode/fan/setpoint/circ/panel each do independently).
        self._pending = {}
        # Set while a handshake response is being awaited (see
        # _attempt_handshake()); _apply_notification() sets it (and the
        # matching event) when a CMD_HANDSHAKE frame arrives, so the two
        # coroutines only ever hand off through instance state, no shared
        # queue needed for what's always at most one outstanding handshake
        # at a time.
        self._handshake_event = None
        self._handshake_success = None

    def _mark_dirty(self):
        self.dirty.set()

    def _debounce(self, key, coro):
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
            print("heater_ble: debounced write failed: %s" % e)

    def set_device_name(self, name):
        """Called by screens.ConnectTile when the user picks a heater from
        the scan list. Persists it and wakes run() if it was idling with
        nothing picked yet. Same shape as AirconClient.set_device_name()
        (see aircon_ble.py) -- deliberately, so screens/__init__.py's App
        can drive both clients through the same Connect-screen code path.

        If a connection is already live (screens.InfoTile's "change
        device" flow, unlike the original first-time-pairing flow, always
        hits this case), also force-disconnects it -- see
        aircon_ble.AirconClient.set_device_name()'s identical comment for
        why that's necessary, not optional.
        """
        self.device_name = name
        panel_settings.set_heater_device_name(name)
        self._name_event.set()
        if self._connection is not None:
            asyncio.create_task(self._disconnect_current())

    async def _disconnect_current(self):
        # NOT hardware-verified -- see aircon_ble.AirconClient.
        # _disconnect_current()'s identical comment.
        try:
            await self._connection.disconnect()
        except Exception as e:
            print("heater_ble: disconnect (for device change) failed: %s" % e)

    def set_password(self, password):
        """Called by screens.heater_password.HeaterPasswordTile when the
        user submits a 4-digit PIN (0-9999). Persists it and, if already
        connected, immediately retries the handshake rather than waiting
        for the next reconnect cycle -- the whole point of a dedicated
        entry screen is fast feedback on whether it was accepted.

        Sets state.password_check_pending here, synchronously, rather than
        leaving it to _attempt_handshake() itself -- asyncio.create_task()
        only *schedules* that coroutine, it doesn't start running it
        immediately, so a refresh() landing in the gap between this call
        returning and the task's first actual execution could otherwise
        observe a stale "not pending" left over from the previous attempt
        and misread its old result as this new attempt's answer. Setting
        it True here closes that gap; _attempt_handshake() setting it True
        again as its own first step is only needed for its other call site
        (_connect_and_run's direct `await`, which has no such gap).
        """
        self.password = password
        panel_settings.set_heater_password(password)
        if self.state.connected:
            self.state.password_check_pending = True
            self._mark_dirty()
            asyncio.create_task(self._attempt_handshake())

    # --- connection lifecycle -------------------------------------------

    async def run(self):
        """Runs forever: scan, connect, subscribe, reconnect on drop. Waits
        (without scanning) whenever no device has been picked yet --
        set_device_name() wakes this back up. Same shape as
        AirconClient.run(), one notify loop instead of seven since this
        protocol has just the one characteristic.
        """
        while True:
            if not self.device_name:
                self.state.connected = False
                self._mark_dirty()
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
                print("heater_ble: connection error:", e)
            self.state.connected = False
            self._char = None
            self._connection = None
            self._mark_dirty()
            await asyncio.sleep_ms(_RECONNECT_DELAY_MS)

    async def _find_device(self):
        print("heater_ble: scanning for %r..." % (self.device_name,))
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

    async def scan_for_heaters(self, duration_ms=_PICKER_SCAN_DURATION_MS):
        """Scans for any BLE peripheral whose advertised name matches
        cfg.NAME_PREFIX (and none of cfg.NAME_EXCLUDE_PREFIXES) -- not by
        service UUID, unlike AirconClient.scan_for_aircons(), since this
        heater's service UUID is a generic one shared with unrelated
        devices (see heater_ble_config.py's module docstring). Same
        (found, other_count) return shape as scan_for_aircons() though, so
        screens.ConnectTile can drive either client identically.
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
                        addr = bytes(result.device.addr)
                    except Exception:
                        addr = None
                    addr_str = addr.hex() if addr is not None else "?"
                    # TEMPORARY diagnostic -- not gated behind a debug flag
                    # on purpose, so this shows up over `make repl` without
                    # needing a rebuild: prints every advertisement this
                    # scan sees, matched or not, so a "picker never finds
                    # the sim, but does report N other devices" report can
                    # be read directly off this instead of guessed at.
                    # svcs added after an initial round of this only
                    # logging name/addr wasn't conclusive on its own (every
                    # nearby device with a real name showed up fine, but
                    # neither sim's short name did, and this Mac can't
                    # scan its own advertisements to cross-check directly
                    # -- see ../heater-sim/README.md's macOS platform note)
                    # -- cfg.SERVICE_UUID showing up on an entry with
                    # name=None would confirm the name specifically is
                    # being dropped from the packet (not the whole
                    # advertisement); if cfg.SERVICE_UUID never appears on
                    # *any* entry at all, that's a different, bigger
                    # problem than a dropped name. Remove once
                    # scan_for_heaters() is confirmed reliably finding a
                    # real/sim heater on real hardware.
                    try:
                        svcs = list(result.services())
                    except Exception as e:
                        svcs = "?(%s)" % e
                    print("heater_ble: scan result: name=%r addr=%s svcs=%s" % (name, addr_str, svcs))
                    matches = name and name.startswith(cfg.NAME_PREFIX) and not any(
                        name.startswith(p) for p in cfg.NAME_EXCLUDE_PREFIXES
                    )
                    if matches:
                        if name not in seen:
                            seen.add(name)
                            found.append((name, result.device))
                        continue
                    if addr is None or addr not in other_addrs:
                        if addr is not None:
                            other_addrs.add(addr)
                        other_count += 1
        found.sort(key=lambda pair: pair[0])
        return found, other_count

    async def _connect_and_run(self, device):
        print("heater_ble: connecting...")
        # ble_shared.radio_lock, not just held for scanning -- see that
        # module's own docstring: confirmed on real hardware that a
        # connect() here racing the *other* client's scan() raises
        # OSError 16, presumably the same "radio already busy with a GAP
        # procedure" constraint scan-vs-scan already needed this lock for.
        # Only held through connection establishment, not this
        # connection's whole subsequent lifetime -- see that module's
        # docstring for why that's deliberate.
        async with ble_shared.radio_lock:
            connection = await device.connect(timeout_ms=5000)
        self._connection = connection
        async with connection:
            service = await connection.service(_SVC)
            if service is None:
                print("heater_ble: service not found")
                return
            try:
                char = await service.characteristic(_CHAR)
            except Exception as e:
                print("heater_ble: characteristic not found:", e)
                return
            self._char = char

            try:
                await char.subscribe(notify=True)
            except Exception as e:
                print("heater_ble: subscribe failed:", e)
                return

            self.state.connected = True
            # Reset, not carried over from a previous connection this same
            # process -- e.g. a drop-and-reconnect after a wrong PIN was
            # fixed via set_password() should re-derive True/False fresh
            # from this new attempt, not keep showing a stale result from
            # before the connection dropped.
            self.state.password_required = None
            self._mark_dirty()
            print("heater_ble: connected")

            # _notify_loop must already be running before
            # _attempt_handshake() sends anything -- it's what delivers
            # the handshake's own response back to it.
            task = asyncio.create_task(self._notify_loop())
            await self._attempt_handshake()
            try:
                await connection.disconnected()
            finally:
                task.cancel()
        print("heater_ble: disconnected")

    async def _attempt_handshake(self):
        """Sends CMD_HANDSHAKE with the current password and waits up to
        _HANDSHAKE_TIMEOUT_MS for the device's own accept/reject, resolving
        state.password_required -- see this module's docstring, point 3,
        for exactly what each outcome (accept / reject / no response at
        all) means and why "no response" is read differently the first
        time a device is probed than on a later retry. Also tracks
        state.password_check_pending for the duration of the attempt (see
        HeaterState's own docstring for why that's a separate field from
        password_required itself). Called once right after every fresh
        connection (_connect_and_run) and again whenever set_password() is
        called while already connected.
        """
        event = asyncio.Event()
        self._handshake_event = event
        self._handshake_success = None
        # Also set synchronously by set_password() before it schedules
        # this coroutine as a task -- see that method's own comment for
        # why both places matter. Harmless to set again here either way.
        self.state.password_check_pending = True
        await self._write_frame(cfg.CMD_HANDSHAKE, cfg.SUB_HANDSHAKE, _encode_password(self.password))
        try:
            # asyncio.wait_for() (seconds, not wait_for_ms()) -- NOT
            # hardware-verified which of the two this aioble-adjacent
            # MicroPython build actually has; wait_for() is the more
            # universally documented core-uasyncio API of the two, so it's
            # the safer bet despite every other timeout in this codebase
            # being expressed in milliseconds (see _HANDSHAKE_TIMEOUT_MS's
            # own naming, kept as-is for consistency with those -- only
            # converted to seconds right here, at this one call site).
            await asyncio.wait_for(event.wait(), _HANDSHAKE_TIMEOUT_MS / 1000)
        except asyncio.TimeoutError:
            pass
        self._handshake_event = None

        if self._handshake_success is True:
            self.state.password_required = False
        elif self._handshake_success is False:
            self.state.password_required = True
        elif self.state.password_required is None:
            # No response at all, and nothing has ever explicitly
            # rejected a handshake on this device before -- assume it
            # simply doesn't gate on a password rather than demanding a
            # PIN nobody has. If a later attempt *does* get an explicit
            # reject, this branch stops applying (state.password_required
            # is no longer None) and a subsequent timeout stays
            # conservative instead -- see this module's docstring, point 3.
            self.state.password_required = False
        self.state.password_check_pending = False
        self._mark_dirty()

    # --- receive -----------------------------------------------------------

    async def _notify_loop(self):
        """Reassembles the single characteristic's notify stream into
        whole frames (a BLE notification can split one frame across
        several packets, or coalesce more than one small frame into a
        single packet -- same reassembly problem aircon_ble.py's
        _notify_loop solves for JSON, solved here for this binary framing
        instead: resync on HEAD_1/HEAD_2, wait for the declared total
        length, drop and resync on anything that doesn't check out).
        """
        buf = bytearray()
        while True:
            try:
                data = await self._char.notified()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print("heater_ble: notify loop ending: %s" % e)
                return
            try:
                buf += data
                self._drain_frames(buf)
            except Exception as e:
                print("heater_ble: notify handling failed: %s" % e)
                buf = bytearray()

    def _drain_frames(self, buf):
        while True:
            # Resync: drop leading bytes until buf starts with HEAD_1/
            # HEAD_2 or is too short to tell yet. A stray fragment left
            # over from a desync (or this notify stream simply starting
            # mid-frame, right after subscribing) both look the same from
            # here -- neither is recoverable byte-by-byte, only by finding
            # the next real header.
            while len(buf) >= 2 and not (buf[0] == cfg.HEAD_1 and buf[1] == cfg.HEAD_2):
                del buf[0]
            if len(buf) < 6:
                return  # not enough yet to even read the declared length
            total_len = buf[4] | (buf[5] << 8)
            if total_len < 9 or total_len > _MAX_FRAME_LEN:
                # Not a real frame length for this protocol (see
                # heater_ble_config.py -- every real frame is small) --
                # drop just the bogus header byte and keep resyncing,
                # rather than waiting forever for a length that will never
                # arrive.
                del buf[0]
                continue
            if len(buf) < total_len:
                return  # wait for the rest of this frame
            frame = bytes(buf[:total_len])
            del buf[:total_len]
            self._handle_frame(frame, total_len)

    def _handle_frame(self, frame, total_len):
        if _checksum(frame, total_len) != frame[total_len - 1]:
            print("heater_ble: checksum mismatch, dropping frame")
            return
        raw_cmd1, cmd2 = frame[6], frame[7]
        # The device always echoes cmd1+128 on the way back, whether this
        # is a direct ack of something this client sent or an unprompted
        # periodic status push -- see heater_ble_config.py's frame-format
        # comment.
        cmd1 = raw_cmd1 - 128 if raw_cmd1 >= 128 else raw_cmd1
        self._apply_notification(cmd1, cmd2, frame)

    def _apply_notification(self, cmd1, cmd2, frame):
        if cmd1 == cfg.CMD_HANDSHAKE:
            # Only meaningful while _attempt_handshake() is actually
            # awaiting one -- a stray/duplicate handshake response arriving
            # outside that window (nothing currently listening) is just
            # ignored, same as any other notification this client doesn't
            # have an active use for right now.
            if self._handshake_event is not None:
                # Absolute frame-byte offset 8 -- matches the vendor app's
                # own success check (uu(): `1==e[8+o]`, o=0 in the
                # unencrypted case this client always uses).
                self._handshake_success = len(frame) > 8 and frame[8] == 1
                self._handshake_event.set()
            return
        if cmd1 != cfg.CMD_RUN:
            return
        # Absolute frame-byte offsets (not offsets into the payload) --
        # see heater_ble_config.py's module docstring for exactly how
        # confident to be in these two fields specifically. Deliberately
        # NOT touching self.state.on/run_mode/run_param here -- see this
        # module's own docstring, point 1, for why those stay purely
        # optimistic instead of trusting this decode.
        if len(frame) > 16:
            self.state.now_gear = frame[13]
            self.state.fault_code = frame[16]
            self._mark_dirty()

    # --- send ----------------------------------------------------------------

    async def _write_frame(self, cmd1, cmd2, payload=b""):
        if self._char is None:
            return False
        try:
            await self._char.write(_encode_frame(cmd1, cmd2, payload), response=False)
            return True
        except Exception as e:
            print("heater_ble: write failed: %s" % e)
            return False

    def _apply_run(self, run_mode, run_param, remain_run_time=0):
        """Optimistic local update (picked up on the very next redraw, see
        aircon_ble.py's set_*() methods for the same pattern) + a
        debounced write of the full {run_mode, run_param, remain_run_time}
        triple -- this protocol has no delta/partial update, so every
        change (a heat-level bump, a new auto target, a plain power-on)
        resends the complete state, same as the vendor app itself always
        does (see the scratch/ doc's "Adjust while running" note).

        power_on()/power_off()/set_heat_level()/set_auto_target() all
        share the single "run" debounce key (not one key per field, unlike
        AirconClient) -- they're all mutually exclusive commands to the
        exact same underlying run_mode/run_param/remain_run_time triple,
        so whichever one the user did most recently should always win
        outright, not partially blend with an older pending one.

        Refuses outright (no optimistic update either) while
        state.password_required is True -- if the device is known to be
        rejecting unauthenticated commands, applying an optimistic "on"
        update anyway would show the panel lying about what the heater is
        actually doing.
        """
        if self.state.password_required:
            print("heater_ble: password required, refusing to send run command")
            return
        self.state.on = True
        self.state.run_mode = run_mode
        self.state.run_param = run_param
        self._mark_dirty()
        remain_lo = remain_run_time & 0xFF
        remain_hi = (remain_run_time >> 8) & 0xFF
        payload = bytes((run_mode & 0xFF, run_param & 0xFF, remain_lo, remain_hi))
        self._debounce("run", self._write_frame(cfg.CMD_RUN, cfg.SUB_RUN_ON, payload))

    async def power_on(self, run_mode=None, run_param=None, remain_run_time=0):
        """Powers on with an explicit run_mode/run_param, or -- if either is
        omitted -- resumes whatever this client last commanded (falling
        back to RUN_MODE_GEAR at HEAT_LEVEL_MIN if nothing ever has been,
        the safest possible starting point: lowest manual heat, not an
        unbounded thermostat target). screens/home.py's mode-cycling into
        "heat" uses this bare form ("just turn on, resume the last
        level"); set_heat_level()/set_auto_target() below are for changing
        an already-on heater's target.
        """
        if run_mode is None:
            run_mode = self.state.run_mode or cfg.RUN_MODE_GEAR
        if run_param is None:
            run_param = self.state.run_param or cfg.HEAT_LEVEL_MIN
        self._apply_run(run_mode, run_param, remain_run_time)

    async def power_off(self):
        if self.state.password_required:
            print("heater_ble: password required, refusing to send run command")
            return
        self.state.on = False
        self._mark_dirty()
        self._debounce("run", self._write_frame(cfg.CMD_RUN, cfg.SUB_RUN_OFF))

    async def set_heat_level(self, level):
        """"heat" mode's knob dial -- manual heat output level (RUN_MODE_GEAR),
        not a target temperature. See heater_ble_config.py's
        HEAT_LEVEL_MIN/MAX.
        """
        level = min(max(int(level), cfg.HEAT_LEVEL_MIN), cfg.HEAT_LEVEL_MAX)
        self._apply_run(cfg.RUN_MODE_GEAR, level)

    async def set_auto_target(self, celsius):
        """"auto" mode's heating branch (see screens/home.py) -- a target
        cabin temperature (RUN_MODE_THERMOSTAT), not a manual level. Always
        Celsius at this layer (see heater_ble_config.py's
        THERMOSTAT_TEMP_MIN_C/MAX_C comment for why) -- callers working in
        Fahrenheit convert before calling this.
        """
        temp_c = min(max(int(round(celsius)), cfg.THERMOSTAT_TEMP_MIN_C), cfg.THERMOSTAT_TEMP_MAX_C)
        self._apply_run(cfg.RUN_MODE_THERMOSTAT, temp_c)
