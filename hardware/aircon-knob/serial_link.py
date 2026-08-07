"""Bidirectional JSON serial protocol with the Pi's server/hardware/knob Go
package, over the same USB-CDC connection mpremote's REPL uses.

Wire format: one JSON object per line (newline-delimited), each with an
"id". Pi -> knob requests get an `{"id": <same id>, "success": true/false}`
response (ping is the one exception: `{"id": ..., "cmd": "pong"}"`). Knob ->
Pi pushes ("state"/"settings") use their own knob-generated ids and expect
no response.

Commands implemented, pi -> knob:
  {"id": N, "cmd": "setBrightness", "val": 0-100}
  {"id": N, "cmd": "setClock", "val": "<ISO8601 UTC, e.g. 2026-08-06T14:51:00Z>"}
  {"id": N, "cmd": "ping"}                      -> {"id": N, "cmd": "pong"}
  {"id": N, "cmd": "setSettings", "settings": {...}}  -- same shape as the
    outbound "settings" push below (key -> {"value":.., "default":..}, or
    just key -> bare number)
  {"id": N, "cmd": "setMode", "val": "off"|"fan"|"auto"|"cool"}
  {"id": N, "cmd": "setFan", "val": "low"|"medium"|"high"}
  {"id": N, "cmd": "setSetpoint", "val": <fahrenheit float>}
  {"id": N, "cmd": "setCirculation", "val": "recirc"|"fresh"}
  {"id": N, "cmd": "setPanelTemp", "val": <fahrenheit float>}  -- no knob UI
    edits this; it exists for the Pi to push its own temperature reading
    down to the controller (planned, not yet wired up on the Pi side)

setMode/setFan/setSetpoint/setCirculation/setPanelTemp all relay straight
to the matching AirconClient.set_*() method (see aircon_ble.py), which
applies an optimistic local update and hands the real BLE write off to a
600ms debounce -- so `{"success": true}` here means "queued", not "the
controller confirmed it took", same as turning the knob itself already
behaves.

Pushed automatically, knob -> pi (no response expected):
  {"id": N, "cmd": "state", "state": {...}}      -- on client.state_dirty
  {"id": N, "cmd": "settings", "settings": {...}} -- on client.settings_dirty

SerialLink owns the stream but does none of its own scheduling: main.py's
loop calls poll() every tick (drains+dispatches whatever's buffered on
stdin, non-blocking) and calls send_state()/send_settings() whenever it
sees client.state_dirty/settings_dirty set, mirroring how it already
drives app.poll_input()/app.refresh() off similar per-tick checks.
"""

import asyncio
import json
import sys

try:
    import select
except ImportError:
    import uselect as select

import machine

import hal

# Deliberately does NOT call micropython.kbd_intr(-1) to disable Ctrl-C
# trapping on this stream (an earlier version of this file did): both ends
# of this wire only ever send JSON via json.dumps()/Go's json.Marshal,
# neither of which can emit a raw control byte (0x03 included) inside an
# encoded payload -- string values with control characters get escaped to
# "", not the literal byte -- so there's no legitimate way for a
# stray Ctrl-C to show up here in the first place. Disabling kbd_intr
# bought protection against a byte this protocol was never actually going
# to produce, at the real cost of permanently losing mpremote's Ctrl-C once
# main.py is flashed and auto-running on every boot, with no way back in
# short of racing the boot window or a full reflash -- see main.py's
# _safe_mode_requested()/boot-button check for the real recovery path now.

_poll = select.poll()
_poll.register(sys.stdin, select.POLLIN)

_MAX_LINE = 4096  # generous -- a full settings object is at most a few hundred bytes


def _write(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")


def _parse_iso8601_utc(s):
    date_part, time_part = s.split("T")
    year, month, day = (int(x) for x in date_part.split("-"))
    time_part = time_part.rstrip("Zz")
    hms = time_part.split(".")[0]  # drop fractional seconds, if present
    hour, minute, second = (int(x) for x in hms.split(":"))
    return year, month, day, hour, minute, second


def _set_rtc(iso_str):
    year, month, day, hour, minute, second = _parse_iso8601_utc(iso_str)
    # weekday (index 3) and subseconds (index 7) are left at 0 -- nothing in
    # this codebase reads either back off the RTC, and MicroPython ports
    # disagree on weekday's exact convention (Monday=0 vs Monday=1 vs
    # Sunday=0 all appear across ports), not worth guessing without
    # hardware to confirm against.
    machine.RTC().datetime((year, month, day, 0, hour, minute, second, 0))


class SerialLink:
    def __init__(self, display, client):
        self._display = display
        self._client = client
        self._buf = ""
        self._next_out_id = 0

    # --- outbound ---------------------------------------------------------

    def _next_id(self):
        self._next_out_id += 1
        return self._next_out_id

    def send_state(self):
        # Explicit field-by-field, not vars(s)/s.__dict__: confirmed on real
        # hardware that this build's vars() doesn't work the way a desktop
        # CPython's does here (crashed main.py's whole asyncio loop, caught
        # only by main.py's top-level handler, which then hard-reset the
        # board) -- not worth re-attempting without a way to test it in
        # isolation first. Snake_case, matching AirconState's own attribute
        # names, since nothing on the Pi side parses individual field names
        # yet (hardware/knob.go stores this payload as opaque JSON).
        s = self._client.state
        _write({
            "id": self._next_id(),
            "cmd": "state",
            "state": {
                "connected": s.connected,
                "mode": s.mode,
                "fan": s.fan,
                "setpoint": s.setpoint,
                "circulation": s.circulation,
                "panel_temp": s.panel_temp,
                "current_temp": s.current_temp,
                "compressor": s.compressor,
                "cabin_temp": s.cabin_temp,
                "blower_temp": s.blower_temp,
                "exhaust_temp": s.exhaust_temp,
                "baggage_temp": s.baggage_temp,
                "tail_temp": s.tail_temp,
                "error": s.error,
                "controller_version": s.controller_version,
            },
        })

    def send_settings(self):
        _write({
            "id": self._next_id(),
            "cmd": "settings",
            "settings": self._client.state.settings,
        })

    # --- inbound ------------------------------------------------------------

    def poll(self):
        """Non-blocking: drains and dispatches whatever's currently buffered
        on stdin, one JSON object per newline-delimited line. Call every
        main-loop tick.
        """
        while _poll.poll(0):
            ch = sys.stdin.read(1)
            if not ch:
                break
            if ch == "\n":
                line = self._buf
                self._buf = ""
                if line.strip():
                    self._handle_line(line)
            else:
                self._buf += ch
                if len(self._buf) > _MAX_LINE:
                    print("serial_link: line too long, dropping")
                    self._buf = ""

    def _handle_line(self, line):
        try:
            msg = json.loads(line)
        except ValueError as e:
            print("serial_link: bad JSON:", line, e)
            return

        msg_id = msg.get("id")
        cmd = msg.get("cmd")

        if cmd == "setBrightness":
            self._cmd_set_brightness(msg_id, msg.get("val"))
        elif cmd == "setClock":
            self._cmd_set_clock(msg_id, msg.get("val"))
        elif cmd == "ping":
            _write({"id": msg_id, "cmd": "pong"})
        elif cmd == "setSettings":
            asyncio.create_task(self._apply_settings(msg_id, msg.get("settings") or {}))
        elif cmd == "setMode":
            asyncio.create_task(self._cmd_aircon(msg_id, self._client.set_mode(msg.get("val"))))
        elif cmd == "setFan":
            asyncio.create_task(self._cmd_aircon(msg_id, self._client.set_fan(msg.get("val"))))
        elif cmd == "setSetpoint":
            asyncio.create_task(self._cmd_aircon(msg_id, self._client.set_setpoint(msg.get("val"))))
        elif cmd == "setCirculation":
            asyncio.create_task(self._cmd_aircon(msg_id, self._client.set_circulation(msg.get("val"))))
        elif cmd == "setPanelTemp":
            asyncio.create_task(self._cmd_aircon(msg_id, self._client.set_panel_temp(msg.get("val"))))
        else:
            print("serial_link: unknown cmd:", cmd)
            _write({"id": msg_id, "success": False, "error": "unknown cmd"})

    def _cmd_set_brightness(self, msg_id, val):
        try:
            if val is None:
                raise ValueError("val required")
            hal.set_brightness(self._display, val)
            _write({"id": msg_id, "success": True})
        except Exception as e:
            print("serial_link: setBrightness failed:", e)
            _write({"id": msg_id, "success": False, "error": str(e)})

    def _cmd_set_clock(self, msg_id, val):
        try:
            if not val:
                raise ValueError("val required")
            _set_rtc(val)
            _write({"id": msg_id, "success": True})
        except Exception as e:
            print("serial_link: setClock failed:", e)
            _write({"id": msg_id, "success": False, "error": str(e)})

    async def _cmd_aircon(self, msg_id, coro):
        """Shared body for setMode/setFan/setSetpoint/setCirculation/
        setPanelTemp -- each just hands its own AirconClient.set_*() call
        (already-constructed coroutine) through here. Runs as an orphaned
        task like _apply_settings() below, same reasoning: an unhandled
        exception would otherwise vanish silently and leave the Pi waiting
        forever for a response that's never coming.
        """
        try:
            await coro
            _write({"id": msg_id, "success": True})
        except Exception as e:
            print("serial_link: aircon command failed:", e)
            _write({"id": msg_id, "success": False, "error": str(e)})

    async def _apply_settings(self, msg_id, settings):
        # Runs as an orphaned task (nothing awaits it) -- same reasoning as
        # aircon_ble.py's own _debounce_run/_notify_loop: an unhandled
        # exception here would vanish silently instead of failing the
        # request, and the Pi would be left waiting forever for a response
        # that's never coming.
        try:
            for key, v in settings.items():
                value = v.get("value") if isinstance(v, dict) else v
                await self._client.set_setting(key, value)
            _write({"id": msg_id, "success": True})
        except Exception as e:
            print("serial_link: setSettings failed:", e)
            _write({"id": msg_id, "success": False, "error": str(e)})
