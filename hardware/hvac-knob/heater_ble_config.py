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

NOT hardware-verified anywhere in this file -- reconstructed entirely from
static analysis of the vendor app's decompiled JS (see the scratch/ doc
above for exactly which app source paths each piece came from), never
tested against a live unit. Treat every value here as a documented best
guess, not a confirmed fact -- particularly HEAT_LEVEL_MIN/MAX (the app
reads a device's actual gear count from macData bit-flags before showing
its UI at all; this file just picks a plausible fixed range) and whether
your specific unit even speaks this exact frame shape (the vendor app can
still *parse*, but never builds, an older/simpler frame format for legacy
hardware -- see the scratch doc's "v1 protocol" section; if status
notifications never start with HEAD1/HEAD2 below, that's the likely
reason).
"""

# Standard BLE-SIG "UART bridge" service, shared with a whole family of
# unrelated cheap BLE peripherals -- NOT a reliable scan filter on its own,
# unlike AIRCON_SERVICE_UUID. Only used to look up the characteristic once
# already connected to a device matched by name (see heater_ble.py).
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"  # both notify and write

# The vendor app's own scan filter (`deviceNameFilter`/`filterNames` in the
# decompiled BluetoothManager.js -- see the scratch doc). NAME_EXCLUDE_PREFIXES
# are advertising names seen only while a unit is in bootloader/OTA mode
# (BYDOTA-/BACOTA-) or a different product line entirely (BYD-MD-) -- none of
# those speak the control protocol below, so scan_for_heaters() filters them
# out even though they'd otherwise match NAME_PREFIX.
NAME_PREFIX = "BYD-"
NAME_EXCLUDE_PREFIXES = ("BYD-MD-", "BYDOTA-", "BACOTA-")

# --- Frame format ---------------------------------------------------------
#
# byte 0    : HEAD_1
# byte 1    : HEAD_2
# byte 2    : PROTOCOL_VERSION (this file only speaks the non-AC/heat-pump
#             variant -- the vendor app uses version 10 for its heat-pump
#             product line, which this codebase has no use for)
# byte 3    : sequence number -- always 0 here, no multi-packet writes needed
#             for anything this client sends
# byte 4-5  : payload length, uint16 little-endian (of the header+payload
#             region -- i.e. everything through the byte before the
#             checksum)
# byte 6    : cmd_1 (command family) -- the device echoes back cmd_1 + 128
#             in its response/notification
# byte 7    : cmd_2 (sub-command)
# byte 8..N : payload, cmd-specific -- see heater_ble.py's frame builders
# byte N+1  : checksum -- 8-bit sum of bytes 0..N, mod 256
HEAD_1 = 0xFE
HEAD_2 = 0xAA
PROTOCOL_VERSION = 0

CMD_INFO = 0  # cmd_1: device identity
SUB_INFO_MAC = 3  # cmd_2: MAC/HW/SW version, part number, mode-capability bitmask

CMD_RUN = 1  # cmd_1: power + run parameters
SUB_RUN_OFF = 0  # cmd_2: power off, no payload
SUB_RUN_ON = 1  # cmd_2: power on / update run params, payload: run_mode, run_param, remain_run_time(u16 LE)

CMD_TIMER = 2  # cmd_1: scheduled timers -- unused by this client, listed for completeness

CMD_ATTR = 3  # cmd_1: general device attributes (temp unit, altitude unit, backlight, ...)
SUB_ATTR_QUERY = 0
SUB_ATTR_WRITE = 1
SUB_ATTR_RESET = 3  # factory reset
SUB_ATTR_ENTER_OTA = 4

CMD_HANDSHAKE = 6  # cmd_1: password handshake
SUB_HANDSHAKE = 0

# run_mode values (byte 8 of a CMD_RUN/SUB_RUN_ON payload) -- reconstructed
# from the vendor app's mode-capability bitmask parser (macData.js), which
# maps bit position to both a button name and this exact numeric "type"
# string: bit0->gMode->"1", bit1->hMode->"2", bit2->aMode->"3", bit3->
# stMode->"4". Not every physical unit necessarily supports all four (that
# bitmask, read via CMD_INFO/SUB_INFO_MAC, is what the vendor app uses to
# decide which mode buttons to even show) -- this client doesn't query it
# and just assumes GEAR + THERMOSTAT are both available, since those are the
# two this codebase's "heat" and "auto" modes need.
RUN_MODE_GEAR = 1  # "gMode": manual heat-level -- run_param = level (see HEAT_LEVEL_MIN/MAX)
RUN_MODE_THERMOSTAT = 2  # "hMode": constant-temperature -- run_param = target temp, deg C
RUN_MODE_VENT = 3  # "aMode": ventilation only (fan, no heat) -- unused by this codebase
RUN_MODE_HIGH = 4  # "stMode": high-heat boost -- unused by this codebase

# NOT hardware-verified (see module docstring): a plausible gear range for
# this style of diesel/parking heater, not read from any specific unit.
# HomeTile's heat-mode dial (screens/home.py) just needs *some* fixed range
# to drive with the knob; adjust to match your unit's actual gear count
# once you can see now_gear in a real status notification.
HEAT_LEVEL_MIN = 1
HEAT_LEVEL_MAX = 10

# Target-temperature clamp for RUN_MODE_THERMOSTAT's run_param, in Celsius --
# taken directly from the vendor app's status-frame parser, which clamps the
# equivalent field to this exact range (8-36 deg C, or the Fahrenheit
# equivalent 40-99 deg F in the app's alternate unit branch -- this client
# always works in Celsius internally, see heater_ble.py.set_auto_target()).
THERMOSTAT_TEMP_MIN_C = 8
THERMOSTAT_TEMP_MAX_C = 36
