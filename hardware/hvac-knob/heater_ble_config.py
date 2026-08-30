"""BLE identity and wire-protocol constants for the second BLE peripheral
this panel talks to: a Chinese white-label parking-heater platform (sold
under several brand names, including "AirHeaterBLE" -- see
../../scratch/airheater-ble-protocol.md for the full writeup this file and
heater_ble.py were reconstructed from, by decompiling that brand's Android
app since no vendor protocol documentation exists).

Unlike the AirCon controller (aircon_ble_config.py -- one GATT
characteristic per field, custom service UUID unique to that firmware),
this heater:
  - has no custom service UUID of its own -- it reuses a generic BLE-SIG
    UUID (0xFFE0/0xFFE1, the same "HM-10 style UART bridge" pattern a lot
    of unrelated cheap BLE peripherals also use), so it can't be found by
    service-UUID scan filtering the way AirconClient.scan_for_aircons()
    finds the AirCon. It's identified by advertised name prefix instead
    (NAME_PREFIX) -- see heater_ble.py's scan_for_heaters().
  - speaks one binary framed protocol over a single characteristic (both
    notify and write) instead of one characteristic per field.

Frame format below is now CONFIRMED against a real unit -- captured via
nRF Sniffer + Wireshark against the real vendor iOS app talking to this
exact heater (see git history for the pre-capture version of this file,
which had guessed the *other* frame format the app's JS actually builds --
see the scratch doc's "v1 protocol" section: that JS has no outgoing
builder for what the real unit turned out to actually speak, so it could
only ever have been reconstructed by capturing a live session, not by
further static analysis). The status NOTIFY_* format (see below) is
likewise now confirmed, decoded from two independent captures (a fresh
first-ever pairing, and a later reconnect) by diffing successive payloads
against the specific command that preceded each one and testing the
scratch doc's "optional password/XOR layer" theory -- see NOTIFY_XOR_KEY's
own comment. HEAT_LEVEL_MIN/MAX are confirmed against this real unit's
actual gear count. Still NOT independently confirmed: the
temperature-related notify fields (see NOTIFY_OFF_GEAR's own comment for
exactly what's confirmed vs. not).
"""

# Standard BLE-SIG "UART bridge" service, shared with a whole family of
# unrelated cheap BLE peripherals -- NOT a reliable scan filter on its own,
# unlike AIRCON_SERVICE_UUID. Only used to look up the characteristic once
# already connected to a device matched by name (see heater_ble.py).
# Short (16-bit) form, not the equivalent 128-bit
# "0000ffe0-0000-1000-8000-00805f9b34fb" string -- confirmed on real
# hardware that MicroPython's bluetooth.UUID doesn't expand a short-form
# UUID to its 128-bit canonical form for equality: a peripheral that
# registers/advertises this standard-range UUID in compact 16-bit form (as
# this heater does, and as virtually every real GATT stack does for
# standard-range UUIDs) never compares equal against a UUID built from the
# expanded string, even though they're the same UUID per the Bluetooth Base
# UUID spec -- aioble's service()/characteristic() lookups (both filter by
# `==`) silently returned nothing because of this, not because the service
# was actually missing (bluetooth.UUID(0xffe0) == bluetooth.UUID("0000ffe0-
# ...") is False on this build; bytes(bluetooth.UUID(0xffe0)) is 2 bytes,
# bytes(bluetooth.UUID("0000ffe0-...")) is 16 -- never going to match).
SERVICE_UUID = 0xFFE0
CHAR_UUID = 0xFFE1  # both notify and write

# The vendor app's own scan filter (`deviceNameFilter`/`filterNames` in the
# decompiled BluetoothManager.js -- see the scratch doc). NAME_EXCLUDE_PREFIXES
# are advertising names seen only while a unit is in bootloader/OTA mode
# (BYDOTA-/BACOTA-) or a different product line entirely (BYD-MD-) -- none of
# those speak the control protocol below, so scan_for_heaters() filters them
# out even though they'd otherwise match NAME_PREFIX.
NAME_PREFIX = "BYD-"
NAME_EXCLUDE_PREFIXES = ("BYD-MD-", "BYDOTA-", "BACOTA-")

# --- Frame format (v1 -- confirmed via BLE capture, see module docstring) -
#
# Fixed 8 bytes, always -- no variable-length payload/length field the way
# the (wrong, never-built-by-the-real-app) v2.1 guess had:
#
# byte 0    : HEAD_1
# byte 1    : HEAD_2
# byte 2    : password // 100
# byte 3    : password % 100  -- every single frame carries the password;
#             there's no separate handshake/login command in this protocol
#             version at all (unlike v2.1's CMD_HANDSHAKE) -- the device
#             presumably just checks it per-frame. Confirmed present
#             identically across every captured frame regardless of cmd.
# byte 4    : cmd
# byte 5-6  : cmd-specific params (2 bytes, meaning depends on cmd)
# byte 7    : checksum = (sum(bytes[0:7]) + 1) & 0xFF -- confirmed against
#             ~10 independently-captured real frames, not a guess.
#
# Writes MUST use ATT Write Request (response=True on this build's
# char.write()), not Write Command -- confirmed the real app does this via
# the same capture (opcode 0x12 "Write Request" + matching 0x13 "Write
# Response" on every outgoing frame, never opcode 0x52 "Write Command").
# Sending as a Write Command (this file's previous assumption) is a
# plausible reason the real device never responded to anything at all: if
# it silently drops unacknowledged writes, framing correctness wouldn't
# have mattered either way.
HEAD_1 = 0xAA
HEAD_2 = 0x55

# Confirmed against the real capture: 1, 2, 3, 4, 10 were all observed in
# genuine app-originated writes and match this cmd table exactly. 5, 6, 23
# were never captured (this client never sends them) -- kept from the
# vendor app's documented command table (see the scratch doc) for
# reference/completeness, not independently confirmed.
CMD_READ = 1  # "readData" -- query/poll; every observed one was followed shortly by a status notification
CMD_SET_MODE = 2  # "setMode" -- param1: RUN_MODE_* below
CMD_ON_OFF = 3  # "onOff" -- param1: 1=on, 0=off (no mode/gear/temp payload -- those persist device-side, set separately via CMD_SET_MODE/CMD_SET_GEAR_OR_TEMP)
CMD_SET_GEAR_OR_TEMP = 4  # "setGearOrTemp" -- param1: gear level (RUN_MODE_GEAR) or target temp (RUN_MODE_THERMOSTAT), depending on whatever mode is currently set
CMD_SET_MODE_DATA = 5  # not sent by this client -- listed for completeness only
CMD_PUMP_OIL = 6  # not sent by this client -- listed for completeness only
CMD_SET_TIME = 10  # param1-2 seen as (0x36, 0x02) in one capture -- exact encoding not reverse-engineered, not sent by this client
CMD_ENTER_OTA = 23  # not sent by this client -- listed for completeness only

# run_mode values (CMD_SET_MODE's param1) -- reconstructed from the vendor
# app's mode-capability bitmask parser (macData.js), which maps bit
# position to both a button name and this exact numeric "type" string:
# bit0->gMode->"1", bit1->hMode->"2", bit2->aMode->"3", bit3->stMode->"4".
# GEAR(1)/THERMOSTAT(2) match the real capture: a CMD_SET_MODE(2) write was
# followed by CMD_SET_GEAR_OR_TEMP writes carrying temp-range values
# (0x4e/0x4f = 78/79), consistent with mode 2 meaning constant-temperature.
# Not every physical unit necessarily supports all four (that bitmask,
# read via a CMD_INFO query this client doesn't send) -- this client just
# assumes GEAR + THERMOSTAT are both available, since those are the two
# this codebase's "heat" and "auto" modes need.
RUN_MODE_GEAR = (
    1  # "gMode": manual heat-level -- run_param = level (see HEAT_LEVEL_MIN/MAX)
)
RUN_MODE_THERMOSTAT = (
    2  # "hMode": constant-temperature -- run_param = target temp, deg C
)
RUN_MODE_VENT = 3  # "aMode": ventilation only (fan, no heat) -- unused by this codebase
RUN_MODE_HIGH = 4  # "stMode": high-heat boost -- unused by this codebase

# Confirmed against real hardware -- this unit's actual gear range is 1-10.
HEAT_LEVEL_MIN = 1
HEAT_LEVEL_MAX = 10

# Target-temperature clamp for RUN_MODE_THERMOSTAT's run_param, in Celsius --
# taken directly from the vendor app's status-frame parser, which clamps the
# equivalent field to this exact range (8-36 deg C, or the Fahrenheit
# equivalent 40-99 deg F in the app's alternate unit branch -- this client
# always works in Celsius internally, see heater_ble.py.set_auto_target()).
THERMOSTAT_TEMP_MIN_C = 8
THERMOSTAT_TEMP_MAX_C = 36

# --- Status notification format ------------------------------------------
#
# Confirmed via BLE capture: NOT the same shape as this file's own outgoing
# frames above -- fixed 48 bytes, XOR-obfuscated with a repeating 15-byte
# keystream. This matches the scratch doc's "Optional password/XOR layer"
# note ("default all-frames key 'passwordA2409PW'") almost exactly, except
# this key is applied to every byte of the *notify* direction specifically
# (not outgoing writes, which this client's own captures confirm travel in
# the clear -- see the frame-format comment above) and this analysis found
# no evidence of the per-device password being combined into it at all
# (decoding worked cleanly with the bare key against two different units'
# worth of captures... well, the same unit, but two independently-captured
# sessions with different connections/central identities).
#
# Decoded (raw bytes XOR NOTIFY_XOR_KEY, repeating from index 0):
#   byte 0-1  : 0xAA 0x66 -- fixed header, distinct from this protocol's
#               own app->device frames (0xAA 0x55) -- matches the scratch
#               doc's "0xAA, 0x55|0x66" note exactly once you realize it's
#               describing two different directions, not two alternate
#               unit variants.
#   byte 2    : echoes whichever cmd (CMD_* above) most recently
#               triggered/preceded this push. Not read by this client.
#   byte 3    : power state, 1=on 0=off -- CONFIRMED against real hardware
#               across two independently-captured on->off transitions,
#               exactly matching this client's own CMD_ON_OFF writes.
#   byte 4    : NOT confirmed -- best-guess fault/error code slot, 0=no
#               fault. Real basis for the guess: this byte was 0x00 in
#               *every* sample across both real captures, with zero
#               exceptions -- consistent with "no fault occurred during
#               either capture" (true) rather than telling us what a real
#               nonzero value would look like. Position is a guess too
#               (grouped right after the cmd echo and right before power
#               state, both confirmed fields) -- there's no capture of an
#               actual fault condition to confirm this against. Treat any
#               nonzero value read here with real skepticism until that
#               happens.
#   byte 5    : current gear level, 0-indexed (add 1 to compare against
#               this file's 1-indexed HEAT_LEVEL_MIN/MAX) -- CONFIRMED
#               against two independent CMD_SET_GEAR_OR_TEMP(gear) writes
#               while in RUN_MODE_GEAR, in two different captures.
#   byte 8    : moves when RUN_MODE changes (0x30 in RUN_MODE_GEAR, 0x33 in
#               RUN_MODE_THERMOSTAT in testing) but NOT decoded -- only two
#               data points, no confirmed formula.
#   byte 9    : moves in the expected direction after a
#               CMD_SET_GEAR_OR_TEMP(temp_f) write while in
#               RUN_MODE_THERMOSTAT, but NOT decoded -- doesn't match a
#               plain Fahrenheit->Celsius conversion of the commanded
#               value in one capture, and drifted gradually one step per
#               poll rather than jumping straight to a fixed value in the
#               other (possibly a slowly-converging measured value, not a
#               direct echo of the target). Needs more real samples --
#               ideally one where a target is set once and then polled
#               repeatedly for a while with nothing else changing -- before
#               trusting any formula here.
#   remainder : constant across every sample captured in both sessions
#               (best guess: device identity/version/reserved fields) --
#               not decoded.
NOTIFY_XOR_KEY = b"passwordA2409PW"
NOTIFY_LEN = 48
# The raw (pre-XOR) bytes actually on the wire for byte 0-1 above -- fixed,
# since XOR-ing a constant header with the start of a constant key is
# itself constant. Used to resync the notify stream without needing to
# XOR-decode incrementally byte-by-byte first.
NOTIFY_RAW_HEAD_1 = 0xAA ^ NOTIFY_XOR_KEY[0]
NOTIFY_RAW_HEAD_2 = 0x66 ^ NOTIFY_XOR_KEY[1]
NOTIFY_OFF_ON = 3
NOTIFY_OFF_FAULT = 4
NOTIFY_OFF_GEAR = 5
