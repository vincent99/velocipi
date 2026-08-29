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
further static analysis). Still NOT independently confirmed: HEAT_LEVEL_MIN/
MAX (no real unit's gear count has been read back yet -- see that
constant's own comment) and the exact meaning of the status notification
payload (a still-undeciphered ~25-byte blob, doesn't start with HEAD_1/
HEAD_2 -- see heater_ble.py's _notify_loop for the raw-bytes logging
left in place to reverse-engineer that in a follow-up pass).
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

# The available range of gear levels
HEAT_LEVEL_MIN = 1
HEAT_LEVEL_MAX = 10

# Target-temperature clamp for RUN_MODE_THERMOSTAT's run_param, in Celsius --
# taken directly from the vendor app's status-frame parser, which clamps the
# equivalent field to this exact range (8-36 deg C, or the Fahrenheit
# equivalent 40-99 deg F in the app's alternate unit branch -- this client
# always works in Celsius internally, see heater_ble.py.set_auto_target()).
THERMOSTAT_TEMP_MIN_C = 8
THERMOSTAT_TEMP_MAX_C = 36
