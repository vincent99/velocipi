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
  1. No read-back, mostly. AirconClient's set_*() methods write, then
     re-read the characteristic to reconcile self.state with whatever the
     controller actually accepted (e.g. a clamped setpoint). This
     protocol's single characteristic has no such request/response read
     semantics -- writes are fire-and-forget (ATT-acknowledged, see
     heater_ble_config.py's frame-format comment on Write Request vs.
     Write Command, but not reconciled at this protocol's own application
     layer), and status only arrives as an unsolicited notification
     instead (decoded -- see heater_ble_config.py's NOTIFY_XOR_KEY comment
     for the full field layout and how confident to be in each one).
     state.on is reconciled against that decode (see _apply_status());
     run_mode/run_param stay purely optimistic (whatever this client
     itself last commanded) since the status payload's mode/gear-or-temp
     fields aren't confidently decoded yet -- see HeaterState's own
     docstring.
  2. Pairing is opt-in and non-blocking (see screens/__init__.py's App):
     unlike the AirCon controller, which gates the whole panel (Home is
     unreachable without one), a missing/disconnected heater just means
     "heat" mode and auto mode's heating branch quietly do nothing --
     see screens/home.py.
  3. Password detection is a best-effort heuristic, not a confirmed
     protocol feature -- and a weaker one than an earlier version of this
     file assumed. This protocol version has no distinct handshake/login
     command at all (confirmed via a real BLE capture -- see
     heater_ble_config.py's frame-format comment): the password just rides
     along on every frame, checked (or not) per-frame device-side, with no
     ATT-level or application-level reject either way for this client to
     catch (see _schedule_verify()'s own docstring). Two independent,
     weaker-than-ideal signals feed state.password_required as a result:
     _attempt_handshake() sends a CMD_READ probe on every fresh connection
     and waits briefly to see if *anything* comes back at all -- since the
     real notify payload's structure isn't decoded yet and so can't be
     checked for an explicit accept/reject the way an earlier version of
     this assumed a dedicated handshake response could be, this alone can
     only ever resolve to False, never actually catching a wrong password
     at connect time (see that method's own comment). _schedule_verify()
     (called from _apply_run()/power_off(), and from _connect_and_run()
     itself whenever a fresh connection finds state.on already True -- see
     that reassert call's own comment) is the one path that can actually
     resolve this True: it catches a password that goes wrong after a
     successful connection -- most plausibly on this project's own
     ../hvac-sim/, which only takes a --heat-password change via a full
     process restart, forcing exactly that kind of reconnect -- by
     noticing a freshly (re)commanded on/off value the device's own status
     pushes never end up agreeing with.

Confirmed on real hardware: this board's BLE stack (aioble/the underlying
`bluetooth` module in this lvgl_micropython build) holds two independent
central connections open at once fine -- one to the AirCon controller, one
to this heater -- with neither connection making the other flaky. That's
the normal case (a real AirCon and a real heater are always two separate
physical devices with separate BLE addresses). If AirconClient and
HeaterClient ever resolve to the *same* address instead (only ever
expected against ../hvac-sim/'s combined single-peripheral simulator --
see that package's own README), BLE itself only supports one link-layer
connection per peer address at all, so a second independent
device.connect() to that address fails outright (confirmed on real
hardware: OSError 5 EIO) -- see ble_shared.canonical_device()'s own
docstring for how this module and aircon_ble.py cooperate to share one
underlying connection in that case instead, transparently to everything
else in this file.
../README.md's "Still open" list documents a DIFFERENT single-central
constraint (the AirCon controller itself accepting only one central at a
time, panel vs. the Pi); that one's unrelated and still applies.
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

# How long _attempt_handshake() waits for an explicit accept/reject before
# giving up on this attempt -- see this module's docstring, point 3, for
# what happens on that timeout. Generous relative to a single BLE
# round-trip (the notify path has already proven itself well under 1s in
# practice for status pushes), not tuned against a real password-protected
# unit -- shorten if a real one answers reliably faster, lengthen if it
# turns out slower than this.
_HANDSHAKE_TIMEOUT_MS = 3000

# How long _schedule_verify() waits after commanding on/off before checking
# whether the device's own reported state.on (reconciled by _apply_status()
# from a real notification) ever agreed -- see that method's own docstring.
# Longer than _HANDSHAKE_TIMEOUT_MS: this has to outlast not just one BLE
# round-trip but this protocol's own unprompted status cadence too (../
# hvac-sim/config.py's HEAT_NOTIFY_INTERVAL is 2s; a real unit's own
# unprompted push rate isn't confirmed, so this leaves extra margin above
# that sim's value rather than tuning tight against it).
_VERIFY_TIMEOUT_MS = 5000

# See scan_for_heaters()'s per-result diagnostic below -- disabled again
# now that it served its purpose confirming the real cause behind that
# method's own docstring's FALLBACK paragraph (a same-machine concurrent-
# BLE-peripheral-advertiser conflict on the *sim* side, not anything wrong
# with this scan itself -- see ../hvac-sim/'s README for the actual fix).
_DEBUG_SCAN_RESULTS = False


def _checksum(buf):
    """(sum(buf[0:7]) + 1) & 0xFF -- see heater_ble_config.py's
    frame-format comment. Confirmed against ~10 independently captured
    real frames, not a guess.
    """
    return (sum(buf[0:7]) + 1) & 0xFF


def _encode_frame(password, cmd, param1=0, param2=0):
    """Fixed 8 bytes always -- see heater_ble_config.py's frame-format
    comment. The password rides along on every frame (bytes 2-3, base-100
    split, high byte first: byte2=password//100, byte3=password%100 --
    confirmed exactly against the real capture for password 1234 ->
    bytes (12, 34)) -- there's no separate handshake/login frame in this
    protocol version.
    """
    buf = bytearray(8)
    buf[0] = cfg.HEAD_1
    buf[1] = cfg.HEAD_2
    buf[2] = password // 100
    buf[3] = password % 100
    buf[4] = cmd
    buf[5] = param1 & 0xFF
    buf[6] = param2 & 0xFF
    buf[7] = _checksum(buf)
    return bytes(buf)


class HeaterState:
    def __init__(self):
        self.connected = False
        # Starts at the safe "definitely off" default rather than
        # guessing. Optimistically set by this client's own set_*() calls,
        # same as run_mode/run_param below, but -- unlike those two -- also
        # reconciled against the device's own reported power state on every
        # status push (see HeaterClient._apply_status()): decoded, cheap,
        # and means a power change made some other way (the physical
        # remote, a fault shutdown) shows up here too, not just changes
        # this client itself made.
        self.on = False
        # NOT confirmed against real hardware -- see _apply_status()'s own
        # comment. Best-guess placeholder for the post-shutdown "purging
        # residual heat before it's fully off" state these heaters
        # commonly have -- unlike a typical interlock, this unit accepts a
        # fresh power-on command even while cooling off (confirmed), it
        # just takes it a few minutes to finish the cycle on its own if
        # left alone. screens/home.py shows an indicator on the main dial
        # while this is true, purely informational.
        self.cooling_off = False
        self.run_mode = None  # last-commanded cfg.RUN_MODE_* constant, or None before ever set
        self.run_param = None  # last-commanded gear level (RUN_MODE_GEAR) or target deg C (RUN_MODE_THERMOSTAT)
        # Informational only, decoded from the device's own status pushes
        # (see HeaterClient._apply_status()) -- NOT fed back into any
        # control decision (see run_mode/run_param above for the fields
        # that matter for control), only shown if screens/home.py wants to
        # display it.
        self.now_gear = None
        # 0 = no fault, decoded from NOTIFY_OFF_FAULT -- see that
        # constant's own comment in heater_ble_config.py for exactly how
        # confident to be in this (short version: the byte position is a
        # guess, "confirmed" only in the narrow sense that it was 0x00 in
        # every real sample captured so far -- no capture has ever caught
        # an actual fault to check the *nonzero* case against). Shown as
        # an error on the panel the same way the AirCon's own state.error
        # is -- see screens/home.py's refresh() and screens/info.py.
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
        # Set only on the subset of _mark_dirty() call sites that change a
        # field serial_link.py's send_state() actually reports (connected,
        # on, run_mode/run_param, now_gear, fault_code) -- separate from
        # self.dirty (which also covers password/handshake bookkeeping
        # that only screens/__init__.py's App needs to redraw for) so
        # main.py can push a fresh serial "state" packet promptly on a real
        # heater state change without also spamming one on every password-
        # flow event. Mirrors aircon_ble.AirconClient's own dirty/
        # state_dirty split exactly -- see that class's _mark_state_dirty().
        self.state_dirty = asyncio.Event()
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
        # Set while a handshake probe is being awaited (see
        # _attempt_handshake()); _notify_loop() sets it (and the matching
        # event) on any raw notification arriving, so the two coroutines
        # only ever hand off through instance state, no shared queue needed
        # for what's always at most one outstanding probe at a time.
        self._handshake_event = None
        self._handshake_success = None
        # The single outstanding _verify_run() task, if any -- see
        # _schedule_verify()'s own docstring. Cancel-and-replace, same
        # pattern as self._pending's per-key debounce tasks, so only the
        # most recently commanded on/off value ever gets checked.
        self._verify_task = None

    def _mark_dirty(self):
        self.dirty.set()

    def _mark_state_dirty(self):
        self.dirty.set()
        self.state_dirty.set()

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
                print("heater_ble: connection error:", e)
            self.state.connected = False
            self._char = None
            self._connection = None
            self._mark_state_dirty()
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
                        # Not result.device directly -- see ble_shared.
                        # canonical_device()'s own docstring: lets this
                        # resolve to the same aioble.Device AirconClient
                        # may already be connected on, when both happen to
                        # point at the same address (only ever expected
                        # against ../hvac-sim/'s combined peripheral).
                        return ble_shared.canonical_device(result.device)
        return None

    async def scan_for_heaters(self, duration_ms=_PICKER_SCAN_DURATION_MS):
        """Scans for any BLE peripheral whose advertised name matches
        cfg.NAME_PREFIX (and none of cfg.NAME_EXCLUDE_PREFIXES) -- not by
        service UUID as the primary filter, unlike AirconClient.
        scan_for_aircons(), since this heater's service UUID (cfg.
        SERVICE_UUID, 0xFFE0) is a generic one shared with unrelated
        devices in the wild (see heater_ble_config.py's module docstring).
        Same (found, other_count) return shape as scan_for_aircons() though,
        so screens.ConnectTile can drive either client identically.

        SIM NAME MATCH: also matches any device whose advertised name
        contains "sim" as its own word (case-insensitive), where a "word"
        is delimited by spaces, hyphens, or the start/end of the name --
        e.g. "HVAC-Sim", "hvac-sim", "HVAC Sim", or bare "Sim" all match,
        but "AirSim"/"Simulator" don't (no separator on both sides of the
        substring). A deliberate, permanent dev/testing convenience, not a
        workaround for anything in particular: it means ../hvac-sim/ (or
        any future desktop simulator) doesn't need to follow the real
        heater's own "BYD-" naming convention just to be discoverable
        here, one less thing to get right when standing up a test rig.
        Independent of NAME_PREFIX/NAME_EXCLUDE_PREFIXES entirely -- a
        real heater is never going to legitimately advertise a name
        shaped like this, so there's no real-world exclusion list to
        apply.

        FALLBACK: also matches any device advertising cfg.SERVICE_UUID
        whose name *doesn't* match the prefix (including no name at all) --
        originally added while chasing a report of the desktop heater
        simulator never reaching this scan at all. That turned out to be a
        same-Mac Bluetooth radio limitation, not a name/matching bug here:
        two separate simulator processes (the AC one and the heater one,
        each with their own bless/CoreBluetooth peripheral manager) don't
        reliably coexist advertising at once, each logging a clean local
        "did start advertising" while only one at a time actually reached
        the air -- fixed by merging both into one process/one peripheral
        (see ../hvac-sim/'s README, "Why one combined process, not two
        separate ones"), not by anything in this method. This fallback is
        kept anyway, on its own merits: a real heater unit's name is
        controlled by its own firmware, not this client, so falling back to
        matching its service UUID directly is a reasonable safety net
        regardless -- the only cost is possibly surfacing unrelated
        real-world 0xFFE0 peripherals (cheap "HM-10 style" BLE modules
        exist for all sorts of unrelated products) as extra, harmless
        entries in the picker's list; nothing here auto-selects any of
        them, the user still has to pick one off the roller.
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
                    try:
                        svcs = list(result.services())
                    except Exception as e:
                        svcs = []
                        svcs_err = e
                    else:
                        svcs_err = None
                    # Per-result diagnostic (name/addr/advertised services)
                    # confirmed scan_for_heaters() reliably finding a real
                    # heater on real hardware, and separately confirmed this
                    # method's own docstring's FALLBACK paragraph's actual
                    # root cause -- disabled again now that both have served
                    # their purpose, not deleted, in case a future scan
                    # issue needs the same visibility again. Flip
                    # _DEBUG_SCAN_RESULTS to re-enable over `make repl`
                    # without needing to reconstruct this from scratch.
                    if _DEBUG_SCAN_RESULTS:
                        addr_str = addr.hex() if addr is not None else "?"
                        print(
                            "heater_ble: scan result: name=%r addr=%s svcs=%s"
                            % (name, addr_str, svcs if svcs_err is None else "?(%s)" % svcs_err)
                        )
                    name_matches = name and name.startswith(cfg.NAME_PREFIX) and not any(
                        name.startswith(p) for p in cfg.NAME_EXCLUDE_PREFIXES
                    )
                    # "word" here means space/hyphen/string-edge delimited --
                    # lowercasing then swapping hyphens for spaces before
                    # split() turns both separators into the same plain
                    # whitespace-split check, no regex needed. See this
                    # method's own docstring's SIM NAME MATCH paragraph.
                    sim_matches = name and "sim" in name.lower().replace("-", " ").split()
                    svc_matches = not (name_matches or sim_matches) and _SVC in svcs
                    if name_matches or sim_matches or svc_matches:
                        # Falls back to the address for the roller's display
                        # text when svc_matches fired with no usable name --
                        # see this method's own docstring's FALLBACK
                        # paragraph. Never actually empty in practice (name
                        # is falsy in exactly the cases addr took over for),
                        # but "" would otherwise be indistinguishable from
                        # "no entry at all" on screens.ConnectTile's roller.
                        display_name = name or ("Heater (%s)" % (addr.hex() if addr else "?"))
                        if display_name not in seen:
                            seen.add(display_name)
                            found.append((display_name, result.device))
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
        # docstring for why that's deliberate. Separately: device.connect()
        # itself is safe even if AirconClient already holds a connection to
        # this exact address -- see ble_shared.canonical_device()'s own
        # docstring (device here is already routed through it, in
        # _find_device() above) for why that doesn't raise the OSError 5
        # EIO a naive second connect() would.
        async with ble_shared.radio_lock:
            connection = await device.connect(timeout_ms=5000)
        self._connection = connection
        async with connection:
            # Discovery (service()/characteristic() lookups) and
            # subscribe() serialized against AirconClient's own, in case
            # this connection is shared with it -- see ble_shared.
            # discovery_lock_for()'s own docstring; a no-op lock
            # (uncontended) whenever it isn't, which is every real-hardware
            # case.
            async with ble_shared.discovery_lock_for(device):
                # Confirmed via a real BLE capture of the vendor iOS app's
                # own connection: it negotiates MTU 247 (Client Rx MTU 527,
                # Server Rx MTU 247), while this connection otherwise sits
                # at the BLE default of 23 (20 usable bytes) -- and this
                # heater's status notification payload is ~50 bytes, well
                # over that. Without this exchange, the device never sends
                # a single notification at all (not truncated/garbled --
                # completely silent, confirmed against real hardware with a
                # standalone script identical in every other respect to
                # what's below), consistent with its firmware just
                # dropping a notification it can't fit in one packet
                # rather than fragmenting or truncating it. Requesting 247
                # to match the app exactly rather than guessing a smaller
                # value that "should" be enough -- connection.exchange_mtu()
                # (unlike aircon_ble.py's own MTU dance for its completely
                # separate connection) returns the negotiated value
                # directly, no manual IRQ-less sleep-and-hope needed on
                # this build.
                #
                # ble_shared.mtu_exchange_needed() guard: MTU is negotiated
                # once per *connection*, not once per client -- if
                # AirconClient already exchanged it on this connection
                # (see canonical_device()'s own docstring for when that
                # happens), attempting it again here isn't just redundant,
                # it's rejected outright (confirmed on real hardware:
                # OSError 120 EALREADY). See that function's own docstring.
                if ble_shared.mtu_exchange_needed(connection):
                    try:
                        mtu = await connection.exchange_mtu(247)
                        print("heater_ble: mtu=%r" % (mtu,))
                    except Exception as e:
                        print("heater_ble: exchange_mtu failed: %s" % e)

                # Earlier attempt here: pairing (bond=True,
                # io=NO_INPUT_OUTPUT), on the theory that this device only
                # exposes FFE0 to a bonded central. Confirmed WRONG on real
                # hardware -- see git history -- and reverted; the MTU
                # exchange above was the actual fix.
                #
                # ble_shared.discover_all(), not connection.service(_SVC)/
                # service.characteristic(_CHAR) directly -- confirmed on
                # real hardware that a second, differently-filtered
                # discovery call on an already-discovered shared connection
                # (AirconClient's own discovery having already run first on
                # it) comes back empty even though the service/
                # characteristic genuinely is there -- see that function's
                # own docstring for the full story, including why
                # subscribe() below also goes through ble_shared instead of
                # aioble's own char.subscribe().
                #
                # ble_shared.find_entry(), not discovered.get(_SVC)/
                # chars.get(_CHAR) directly -- confirmed on real hardware
                # that ../hvac-sim/ reports this service/characteristic in
                # expanded 128-bit UUID form over ATT, unlike a real
                # heater (which reports the same logical UUID in compact
                # 16-bit form, matching _SVC/_CHAR below directly) -- see
                # that function's own docstring.
                discovered = await ble_shared.discover_all(connection)
                entry = ble_shared.find_entry(discovered, cfg.SERVICE_UUID)
                if entry is None:
                    print("heater_ble: service not found")
                    return
                _service, chars = entry
                char_entry = ble_shared.find_entry(chars, cfg.CHAR_UUID)
                if char_entry is None:
                    print("heater_ble: characteristic not found")
                    return
                char, descs = char_entry
                self._char = char

                try:
                    await ble_shared.subscribe(char, descs, notify=True)
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
            self._mark_state_dirty()
            print("heater_ble: connected")

            # _notify_loop must already be running before
            # _attempt_handshake() sends anything -- it's what delivers
            # the handshake's own response back to it.
            task = asyncio.create_task(self._notify_loop())
            await self._attempt_handshake()
            if self.state.on and self.state.run_mode is not None:
                # Reassert the last known desired run state across this
                # fresh connection -- state.on/run_mode/run_param are
                # purely local memory (this module's docstring, point 1),
                # never automatically resent by aioble/BLE itself on a
                # reconnect, so a heater that's actually gone back to its
                # own power-on-default "off" while this client was briefly
                # disconnected (a real power cycle, or -- the case that
                # actually surfaced this -- ../hvac-sim/ restarted with a
                # new --heat-password, which forces exactly this reconnect
                # path) would otherwise leave the panel silently showing
                # "on" forever, with nothing to trigger a fresh
                # _apply_run()/power_off() call (and this its
                # _schedule_verify()) until the user happens to touch the
                # knob again. Also doubles as a stronger password probe
                # than _attempt_handshake()'s own bare CMD_READ above --
                # its "did anything at all come back" heuristic can't tell
                # a rejected probe apart from this sim's (and presumably
                # real hardware's) own unprompted periodic status pushes,
                # which arrive regardless of any password at all -- see
                # _schedule_verify()'s own docstring for why comparing
                # against state.on instead doesn't have that blind spot.
                self._debounce("run", self._commit_run(self.state.run_mode, self.state.run_param))
                self._schedule_verify(True)
            try:
                await connection.disconnected()
            finally:
                task.cancel()
        print("heater_ble: disconnected")

    async def _attempt_handshake(self):
        """Sends a CMD_READ probe (password embedded, like every frame this
        protocol version sends) and waits up to _HANDSHAKE_TIMEOUT_MS to see
        whether the device responds at all, resolving state.
        password_required -- see this module's docstring, point 3, for why
        that can currently only ever end up False (no confirmed way to
        observe an explicit reject yet). Also tracks
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
        # No distinct handshake/login command in this protocol version --
        # the password rides along on every frame instead (see
        # heater_ble_config.py's frame-format comment) -- so this sends a
        # CMD_READ query as a probe and treats "did anything at all come
        # back" as the accept signal. _handshake_success is set by
        # _notify_loop on any raw notification arriving while this event
        # is pending, not by parsing an explicit accept/reject field the
        # way the old (never actually spoken by this unit) v2.1 guess did
        # -- the real notify payload's structure isn't decoded yet (see
        # _notify_loop's own comment), so there's currently no way to
        # observe an explicit *reject* at all, only "responded" or
        # "didn't". That means state.password_required can only ever
        # resolve to False here, never True -- if this unit does reject
        # wrong passwords somehow, we can't see it until that payload
        # format is reverse-engineered.
        await self._write_frame(cfg.CMD_READ)
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

        if self._handshake_success is True or self.state.password_required is None:
            self.state.password_required = False
        self.state.password_check_pending = False
        # TEMPORARY diagnostic while getting this protocol working against
        # real hardware for the first time -- remove once handshake
        # behavior is confirmed reliable.
        print("heater_ble: handshake resolved: success=%r password_required=%r" % (
            self._handshake_success, self.state.password_required))
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
            # TEMPORARY diagnostic -- raw bytes as they arrive, before
            # _drain_frames()'s resync below. Kept even now that the format
            # is decoded: cheap, and still the fastest way to eyeball
            # what's coming in without waiting on _apply_status()'s own
            # (much narrower) prints.
            print("heater_ble: notify raw: %s" % (bytes(data).hex(),))
            # Signals _attempt_handshake()'s probe on ANY arrival, not on a
            # successfully-parsed frame -- simpler and just as reliable
            # given every real notification observed so far has been a
            # well-formed status push; no observed case yet where "arrived
            # but didn't parse" needs telling apart from "didn't arrive".
            if self._handshake_event is not None:
                self._handshake_success = True
                self._handshake_event.set()
            try:
                buf += data
                buf = self._drain_frames(buf)
            except Exception as e:
                print("heater_ble: notify handling failed: %s" % e)
                buf = bytearray()

    def _drain_frames(self, buf):
        """Looks for this protocol's status-push shape (NOTIFY_RAW_HEAD_1/2,
        fixed NOTIFY_LEN bytes, XOR-obfuscated -- see heater_ble_config.py's
        NOTIFY_XOR_KEY comment for the full field layout and how confident
        to be in each one) inside the notify stream. Resyncs on the raw
        (pre-XOR) header bytes rather than decoding incrementally -- cheap,
        and that header is fixed regardless of the rest of the payload (see
        NOTIFY_RAW_HEAD_1/2's own comment for why).

        Returns the remaining, not-yet-consumed tail of `buf` -- confirmed
        on real hardware that this build's bytearray has no __delitem__ at
        all (`del buf[0]`/`del buf[:n]` both raised "'bytearray' object
        doesn't support item deletion", caught by _notify_loop()'s own
        try/except and silently dropping the whole buffer, including
        already-received bytes, every single time any resync was actually
        needed), unlike CPython's. Slicing (buf[1:]/buf[n:], which builds
        and returns a new bytearray rather than mutating this one in place)
        works on every port and is what this returns for _notify_loop() to
        reassign over its own `buf` local instead.
        """
        while True:
            while len(buf) >= 2 and not (
                buf[0] == cfg.NOTIFY_RAW_HEAD_1 and buf[1] == cfg.NOTIFY_RAW_HEAD_2
            ):
                buf = buf[1:]
            if len(buf) < cfg.NOTIFY_LEN:
                return buf  # not enough yet for a full fixed-size frame
            frame = bytes(buf[: cfg.NOTIFY_LEN])
            buf = buf[cfg.NOTIFY_LEN :]
            self._handle_status_frame(frame)

    def _handle_status_frame(self, frame):
        decoded = bytes(
            b ^ cfg.NOTIFY_XOR_KEY[i % len(cfg.NOTIFY_XOR_KEY)] for i, b in enumerate(frame)
        )
        # TEMPORARY diagnostic -- remove once this decode's been live
        # against real hardware long enough to trust without watching it.
        print("heater_ble: status: %s" % (decoded.hex(),))
        self._apply_status(decoded)

    def _apply_status(self, decoded):
        """Reconciles state.on against the device's own reported power
        state (unlike run_mode/run_param, which stay purely optimistic --
        see this module's own docstring, point 1 -- on/off is cheap to
        reconcile now that it's decoded, and doing so means a manual power
        change made some other way -- the physical remote, a fault
        shutdown -- shows up here too, not just changes this client itself
        made). now_gear is informational only, never fed back into a
        control decision -- see HeaterState's own docstring.

        state.cooling_off: NOT confirmed against real hardware -- only 0
        (off) and 1 (on) have ever actually been observed in
        NOTIFY_OFF_ON's byte across every real capture so far, since none
        of them happened to catch a real cool-off period. Best-guess
        placeholder: treats any *other* value as "cooling off" rather than
        picking one specific number, on the theory that whatever it turns
        out to be, it's very unlikely to also be 0 or 1. Confirm (and
        replace with the real value) next time real hardware is on hand:
        power the unit on then off and watch heater_ble: status: ... 's
        NOTIFY_OFF_ON byte during the minutes afterward.

        state.fault_code: also NOT confirmed -- see heater_ble_config.py's
        NOTIFY_OFF_FAULT comment for exactly what the guess is based on
        (that byte's always been 0x00, i.e. no real fault has ever been
        captured to confirm the nonzero case against).
        """
        s = self.state
        on_byte = decoded[cfg.NOTIFY_OFF_ON]
        s.on = on_byte == 1
        s.cooling_off = on_byte not in (0, 1)
        s.fault_code = decoded[cfg.NOTIFY_OFF_FAULT]
        s.now_gear = decoded[cfg.NOTIFY_OFF_GEAR] + 1
        self._mark_state_dirty()

    # --- send ----------------------------------------------------------------

    async def _write_frame(self, cmd, param1=0, param2=0):
        if self._char is None:
            return False
        frame = _encode_frame(self.password, cmd, param1, param2)
        # TEMPORARY diagnostic, same reasoning as _handle_status_frame()'s
        # -- lets a "frame out" line be matched up against whatever comes
        # back as "notify raw"/"status", and against a real session's BLE
        # capture.
        print("heater_ble: frame out: %s" % (frame.hex(),))
        try:
            # response=True (ATT Write Request), not Write Command --
            # confirmed via a real BLE capture that the vendor app always
            # does this and gets a Write Response back for every write;
            # this client previously used response=False (Write Command)
            # and never got anything back from the real device at all --
            # see heater_ble_config.py's frame-format comment.
            await self._char.write(frame, response=True)
            return True
        except Exception as e:
            print("heater_ble: write failed: %s" % e)
            return False

    def _apply_run(self, run_mode, run_param):
        """Optimistic local update (picked up on the very next redraw, see
        aircon_ble.py's set_*() methods for the same pattern) + a debounced
        commit of mode+level/temp+power-on -- see _commit_run()'s own
        comment for why that's three separate writes, not one combined
        frame the way an earlier version of this (guessing at a different,
        wrong protocol version) assumed.

        power_on()/set_heat_level()/set_auto_target() all share the single
        "run" debounce key (not one key per field, unlike AirconClient) --
        they're all mutually exclusive commands to the exact same
        underlying run_mode/run_param, so whichever one the user did most
        recently should always win outright, not partially blend with an
        older pending one. power_off() also shares this key, for the same
        reason.

        Refuses outright (no optimistic update either) while
        state.password_required is True -- if the device is known to be
        rejecting unauthenticated commands, applying an optimistic "on"
        update anyway would show the panel lying about what the heater is
        actually doing. Reachable now via _schedule_verify() below (a
        password change mid-session, so every subsequent frame's embedded
        password stops matching -- see that method's own docstring), not
        just _attempt_handshake()'s own weaker connect-time heuristic
        (still can only ever resolve to False on its own -- see that
        method's own comment).
        """
        if self.state.password_required:
            print("heater_ble: password required, refusing to send run command")
            return
        self.state.on = True
        self.state.run_mode = run_mode
        self.state.run_param = run_param
        self._mark_state_dirty()
        self._debounce("run", self._commit_run(run_mode, run_param))
        self._schedule_verify(True)

    async def _commit_run(self, run_mode, run_param):
        """Three separate writes, not one combined frame -- see
        heater_ble_config.py's frame-format comment: this protocol's
        CMD_ON_OFF carries no mode/gear/temp payload of its own (unlike the
        single combined frame an earlier, wrong protocol-version guess
        assumed); mode and gear/temp are set via their own dedicated
        commands instead, confirmed as independent writes in the real
        capture. Mode/param sent before the power-on write -- an
        unverified but sensible ordering for a unit that's currently off,
        so it (hopefully) already knows what to do the moment it powers on
        rather than momentarily starting at some other last-remembered
        setting.
        """
        await self._write_frame(cfg.CMD_SET_MODE, run_mode)
        await self._write_frame(cfg.CMD_SET_GEAR_OR_TEMP, run_param)
        await self._write_frame(cfg.CMD_ON_OFF, 1)

    async def power_on(self, run_mode=None, run_param=None):
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
        self._apply_run(run_mode, run_param)

    async def power_off(self):
        if self.state.password_required:
            print("heater_ble: password required, refusing to send run command")
            return
        self.state.on = False
        self._mark_state_dirty()
        self._debounce("run", self._write_frame(cfg.CMD_ON_OFF, 0))
        self._schedule_verify(False)

    def _schedule_verify(self, expected_on):
        """Cancel-and-replace a background check of whether the device ever
        actually agrees with the on/off value just commanded -- the closest
        thing to a reject signal this protocol has (see this module's
        docstring, point 3, and _apply_run()'s own comment): every frame
        carries the password, a wrong one gets silently dropped rather than
        answered (confirmed as this project's own sim's behavior in
        ../hvac-sim/ble_server.py's _on_write_heat()), so a command that
        never takes effect looks identical to one that was never sent at
        all -- there's no ATT-level or application-level error to catch
        instead (_write_frame() already sends response=True and still gets
        a normal Write Response either way).

        state.on is the one field _apply_status() reconciles against the
        device's own real reports rather than leaving purely optimistic
        (see this module's docstring, point 1) -- including the unprompted
        periodic pushes this sim (and presumably real hardware) sends
        regardless of any password, so it's the one field that will
        eventually disagree with what was just commanded if that command
        was silently dropped, without needing this client to guess at
        whether any given notification was actually a response to it.

        Not proof of a wrong password specifically -- a real fault shutdown
        could produce the same "commanded on, device still reports off"
        symptom -- but it's the best signal this protocol version's
        silent-failure design leaves available, and wrong-password-mid-
        session is a far more likely cause of a *freshly* commanded change
        never taking effect than a fault landing in that exact window.
        """
        prev = self._verify_task
        if prev is not None:
            prev.cancel()
        self._verify_task = asyncio.create_task(self._verify_run(expected_on))

    async def _verify_run(self, expected_on):
        try:
            await asyncio.sleep_ms(_VERIFY_TIMEOUT_MS)
        except asyncio.CancelledError:
            return
        if self.state.connected and self.state.on != expected_on:
            print(
                "heater_ble: commanded on=%r but device still reports on=%r after %dms -- "
                "assuming the password is wrong" % (expected_on, self.state.on, _VERIFY_TIMEOUT_MS)
            )
            self.state.password_required = True
            self._mark_state_dirty()

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
