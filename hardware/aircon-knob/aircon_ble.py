"""BLE GATT central for the AirCon controller — a MicroPython/aioble port of
server/hardware/aircon/aircon.go's Client. Talks to the exact same 7
characteristics (see ble_config.py), same wire format: UTF-8 strings, floats
as "%.2f" decimal strings, JSON for the settings/status characteristics.

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
"""

import asyncio
import json

import aioble
import bluetooth

from ble_config import (
    AIRCON_DEVICE_NAME,
    AIRCON_SERVICE_UUID,
    UUID_MODE,
    UUID_FAN,
    UUID_SETPOINT,
    UUID_CIRC,
    UUID_PANEL,
    UUID_SETTINGS,
    UUID_STATUS,
)

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

_SCAN_DURATION_MS = 5000
_RECONNECT_DELAY_MS = 5000


class AirconState:
    def __init__(self):
        self.connected = False
        self.mode = ""
        self.fan = ""
        self.setpoint = 0.0
        self.circulation = ""
        self.panel_temp = 0.0
        self.settings = {}  # key -> {"value": float, "default": float}

        self.current_temp = None
        self.compressor = ""
        self.cabin_temp = None
        self.blower_temp = None
        self.exhaust_temp = None
        self.baggage_temp = None
        self.tail_temp = None
        self.error = ""


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
    def __init__(self):
        self.state = AirconState()
        self.dirty = asyncio.Event()
        self._chars = {}

    def _mark_dirty(self):
        self.dirty.set()

    async def run(self):
        """Runs forever: scan, connect, subscribe, reconnect on drop."""
        while True:
            device = await self._find_device()
            if device is not None:
                try:
                    await self._connect_and_run(device)
                except Exception as e:
                    print("aircon_ble: connection error:", e)
            self.state.connected = False
            self._chars = {}
            self._mark_dirty()
            await asyncio.sleep_ms(_RECONNECT_DELAY_MS)

    async def _find_device(self):
        print("aircon_ble: scanning for %r..." % (AIRCON_DEVICE_NAME,))
        async with aioble.scan(
            _SCAN_DURATION_MS, interval_us=30000, window_us=30000, active=True
        ) as scanner:
            async for result in scanner:
                if result.name() == AIRCON_DEVICE_NAME:
                    return result.device
        return None

    async def _connect_and_run(self, device):
        print("aircon_ble: connecting...")
        connection = await device.connect(timeout_ms=5000)
        async with connection:
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

            await self._read_initial()

            self.state.connected = True
            self._mark_dirty()
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
        await ch.subscribe(notify=True)
        buf = b""
        while True:
            data = await ch.notified()
            if name in _JSON_CHARS:
                buf += data
                if _json_complete(buf):
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
                self._mark_dirty()

    def _apply_settings_json(self, text):
        try:
            raw = json.loads(text)
        except ValueError:
            print("aircon_ble: settings JSON parse error:", text)
            return
        settings = {}
        for key, v in raw.items():
            if isinstance(v, (int, float)):
                settings[key] = {"value": float(v), "default": float(v)}
            elif isinstance(v, dict):
                val = float(v.get("value", 0.0))
                settings[key] = {"value": val, "default": float(v.get("default", val))}
        self.state.settings = settings
        self._mark_dirty()

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
        s.baggage_temp = raw.get("baggage")
        s.tail_temp = raw.get("tail")
        s.error = raw.get("err") or ""
        self._mark_dirty()

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

    async def set_mode(self, mode):
        return await self._write_str("mode", mode)

    async def set_fan(self, fan):
        return await self._write_str("fan", fan)

    async def set_circulation(self, circ):
        return await self._write_str("circ", circ)

    async def set_setpoint(self, fahrenheit):
        return await self._write_str("setpoint", "%.2f" % fahrenheit)

    async def set_setting(self, key, value):
        return await self._write_str("settings", json.dumps({key: value}))
