"""BLE GATT central for the fuel-level sensor -- see
../fuel-level/ble_server.py's own module docstring for the exact GATT
layout this reads. Much simpler than aircon_ble.py/heater_ble.py: read-only
(no set_*() writes from this panel at all -- calibration is done directly
against the sensor over BLE by some other tool, see
../fuel-level/README.md), one characteristic actually needed (Battery
Level), so no debounce/generation-counter machinery, no MTU exchange (a
single-byte payload never needs a bigger one), no password/handshake
concept at all.

Also unlike AirconClient/HeaterClient, this device never gates anything --
screens/__init__.py's module docstring covers why Home needs the AirCon or
heater to be connected depending on the selected mode; the fuel level is
purely an ambient reading shown on Home's own arc (see screens/home.py) and
Info's device list, with no full-screen Disconnected takeover and no
mandatory first-boot pairing step. Structurally still mirrors
AirconClient/HeaterClient's own run()/reconnect-loop/scan_for_*() shape,
and shares ble_shared.py's radio_lock/canonical_device()/
discovery_lock_for() the same way those two already share them with each
other -- one physical BLE radio on this board, now split three ways, and
../hvac-sim/ can now advertise all three devices (AirCon, heater, fuel
sensor) from one combined process/one BLE address, same as it already did
for just AirCon+heater before the fuel sensor existed -- see that
package's own README for why one Mac generally only reliably advertises
one peripheral identity at a time. _find_device() routes through
canonical_device() for exactly that scenario: without it, a fresh
device.connect() to an address AirconClient/HeaterClient already holds
fails outright (OSError 5 EIO, confirmed for the AC/heater pair already --
see ble_shared.canonical_device()'s own docstring), and discovery_lock_for()
serializes this client's own GATT discovery against theirs on that shared
connection the same way. Both are uncontended no-ops against real hardware
(a real fuel sensor is always a genuinely separate physical device, with
its own address, from a real AirCon/heater).

Requires `aioble` on the device -- see ../README.md.
"""

import asyncio

import aioble
import bluetooth

import ble_shared
import panel_settings
from fuel_ble_config import BATTERY_LEVEL_UUID, BATTERY_SVC_UUID, FUEL_SERVICE_UUID

_SVC = bluetooth.UUID(FUEL_SERVICE_UUID)

_SCAN_DURATION_MS = 5000
_PICKER_SCAN_DURATION_MS = 4000  # scan_for_fuel_sensors()'s default -- see screens.ConnectTile
_RECONNECT_DELAY_MS = 5000


class FuelState:
    def __init__(self):
        self.connected = False
        # 0-100, or None before the first reading has ever arrived -- kept
        # distinct from "reads 0%" (an empty tank is a real, meaningful
        # value) since screens/home.py's arc needs to tell "never got a
        # reading yet" apart from "got one, and it's zero".
        self.percent = None


class FuelClient:
    def __init__(self, device_name=""):
        self.device_name = device_name  # "" until the user picks one on the Connect screen
        self.state = FuelState()
        self.dirty = asyncio.Event()
        self._char = None
        # The live aioble connection object, or None whenever not connected
        # -- same purpose as AirconClient/HeaterClient's own, letting
        # set_device_name() force-disconnect a still-live *different*
        # connection when the user picks a new sensor from screens.
        # ConnectTile.
        self._connection = None
        self._name_event = asyncio.Event()

    def _mark_dirty(self):
        self.dirty.set()

    def set_device_name(self, name):
        """Called by screens.ConnectTile when the user picks a device from
        the scan list, or by its "(No Fuel Sensor)" skip entry with name=""
        (see screens/__init__.py's fuel_connect_tile construction) -- both
        just change which device this client tries to stay connected to,
        with no separate persisted "skipped" flag to track (see
        panel_settings.get_fuel_device_name()'s own docstring for why not).
        """
        self.device_name = name
        panel_settings.set_fuel_device_name(name)
        self._name_event.set()
        if self._connection is not None:
            asyncio.create_task(self._disconnect_current())

    async def _disconnect_current(self):
        try:
            await self._connection.disconnect()
        except Exception as e:
            print("fuel_ble: disconnect (for device change) failed: %s" % e)

    async def run(self):
        """Runs forever: scan, connect, subscribe, reconnect on drop. Waits
        (without scanning) whenever no device has been picked yet --
        set_device_name() wakes this back up as soon as one is. Never
        blocks anything else on this outcome -- see this module's own
        docstring.
        """
        while True:
            if not self.device_name:
                self.state.connected = False
                self._mark_dirty()
                await self._name_event.wait()
                self._name_event.clear()
                continue

            try:
                device = await self._find_device()
                if device is not None:
                    await self._connect_and_run(device)
            except Exception as e:
                print("fuel_ble: connection error:", e)
            self.state.connected = False
            self._char = None
            self._connection = None
            self._mark_dirty()
            await asyncio.sleep_ms(_RECONNECT_DELAY_MS)

    async def _find_device(self):
        print("fuel_ble: scanning for %r..." % (self.device_name,))
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
                        # resolve to the same aioble.Device AirconClient/
                        # HeaterClient may already be connected on, when
                        # both happen to point at the same address (only
                        # ever expected against ../hvac-sim/'s combined
                        # peripheral).
                        return ble_shared.canonical_device(result.device)
        return None

    async def scan_for_fuel_sensors(self, duration_ms=_PICKER_SCAN_DURATION_MS):
        """Scans for any BLE peripheral advertising FUEL_SERVICE_UUID -- same
        shape as aircon_ble.AirconClient.scan_for_aircons(), see that
        method's own docstring for the (found, other_count) return shape
        and the NOT-hardware-verified caveats on result.services()/
        result.device.addr this shares with it.

        SIM NAME MATCH: also matches any device whose advertised name
        contains "sim" as its own word (case-insensitive, space/hyphen/
        edge-delimited) -- copied from heater_ble.HeaterClient.
        scan_for_heaters()'s own docstring, which explains the word-
        boundary rule in full; needed here for the same reason: ../
        hvac-sim/'s combined AC+heater+fuel advertisement is confirmed
        over the legacy 31-byte advertisement budget with just the first
        two devices already (see ../hvac-sim/config.py's own
        BLE_DEVICE_NAME comment), and FUEL_SERVICE_UUID -- a full 128-bit
        custom UUID, the most expensive kind to fit -- is even less likely
        to survive whatever gets silently trimmed once a third device's
        worth of UUIDs joins the same advertisement. The device's own
        advertised name is never trimmed away the same way, so matching on
        that instead is the reliable path against this sim. Unlike
        heater's own name-prefix matching (a real heater's vendor-
        controlled "BYD-..." name has nothing to do with this sim), this
        client has no real-hardware name convention of its own to match
        against first -- FUEL_SERVICE_UUID is the only real-hardware
        signal there is, so it stays the primary check, with SIM NAME
        MATCH purely as an additional way to match, not a replacement for
        it.
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
                        print("fuel_ble: scan: result.services() failed for %r: %s" % (name, e))
                        svcs = []
                    # "word" here means space/hyphen/string-edge delimited --
                    # see this method's own docstring's SIM NAME MATCH
                    # paragraph.
                    sim_matches = name and "sim" in name.lower().replace("-", " ").split()
                    svc_matches = _SVC in svcs
                    if name and (svc_matches or sim_matches):
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
        print("fuel_ble: connecting...")
        async with ble_shared.radio_lock:
            connection = await device.connect(timeout_ms=5000)
        self._connection = connection
        async with connection:
            async with ble_shared.discovery_lock_for(device):
                discovered = await ble_shared.discover_all(connection)
                entry = ble_shared.find_entry(discovered, BATTERY_SVC_UUID)
                if entry is None:
                    print("fuel_ble: battery service not found")
                    return
                _service, chars = entry
                char_entry = ble_shared.find_entry(chars, BATTERY_LEVEL_UUID)
                if char_entry is None:
                    print("fuel_ble: battery level characteristic not found")
                    return
                char, descs = char_entry
                self._char = char

                try:
                    await ble_shared.subscribe(char, descs, notify=True)
                except Exception as e:
                    print("fuel_ble: subscribe failed:", e)

            try:
                data = await char.read()
                self.state.percent = data[0]
            except Exception as e:
                print("fuel_ble: initial read failed:", e)

            self.state.connected = True
            self._mark_dirty()
            print("fuel_ble: connected")

            task = asyncio.create_task(self._notify_loop(char))
            try:
                await connection.disconnected()
            finally:
                task.cancel()
        print("fuel_ble: disconnected")

    async def _notify_loop(self, char):
        while True:
            try:
                data = await char.notified()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print("fuel_ble: notify loop ending: %s" % e)
                return
            try:
                self.state.percent = data[0]
                self._mark_dirty()
            except Exception as e:
                print("fuel_ble: notify decode failed: %s" % e)
