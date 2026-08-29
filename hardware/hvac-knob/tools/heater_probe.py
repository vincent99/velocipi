"""Standalone heater BLE probe -- talks to the AirHeaterBLE-protocol device
directly, with none of this project's own client code (heater_ble.py,
ble_shared.py, panel_settings.py, screens/, main.py's asyncio loop juggling
the AirCon client too) in the loop at all. A phone BLE scanner app already
confirms the heater advertises 0000FFE0 and exposes 0000FFE1 once connected,
so if this script -- talking to the same device with nothing else running
-- still can't find/use it, the problem is almost certainly on this side
(aioble/this firmware build's BLE stack), not the heater or its protocol.

Run directly from the host -- no need to `make sync` it onto the device
first, and it doesn't touch/overwrite anything already on the device:
    mpremote run tools/heater_probe.py

Edit TARGET_NAME below if your unit's advertised name differs.
"""

import asyncio
import aioble
import bluetooth
import machine

# Defensive: if this is run right after interrupting a live main.py session
# (mpremote run's Ctrl-C doesn't reset the board), main.py's own hardware
# watchdog -- armed at boot, unfed since the interrupt, and per its own
# docs impossible to disable once started -- can still be ticking down in
# the background and reset the board mid-script with no relation to BLE at
# all. machine.WDT() is idempotent on this port (re-calling it just gives a
# handle to the same peripheral rather than erroring), so this is safe
# whether or not one was already armed.
try:
    _wdt = machine.WDT(timeout=8000)
except Exception:
    _wdt = None


async def _feed_wdt():
    while True:
        if _wdt is not None:
            _wdt.feed()
        await asyncio.sleep_ms(1000)

TARGET_NAME = "BYD-E466E5C02E64"
SCAN_MS = 6000
SVC_UUID = bluetooth.UUID(0xFFE0)
CHAR_UUID = bluetooth.UUID(0xFFE1)
PASSWORD = 1234


def _checksum(buf):
    return (sum(buf[0:7]) + 1) & 0xFF


def _encode_frame(cmd, param1=0, param2=0):
    buf = bytearray(8)
    buf[0] = 0xAA
    buf[1] = 0x55
    buf[2] = PASSWORD // 100
    buf[3] = PASSWORD % 100
    buf[4] = cmd
    buf[5] = param1 & 0xFF
    buf[6] = param2 & 0xFF
    buf[7] = _checksum(buf)
    return bytes(buf)


async def main():
    asyncio.create_task(_feed_wdt())
    print("probe: scanning for %r (%dms)..." % (TARGET_NAME, SCAN_MS))
    device = None
    async with aioble.scan(SCAN_MS, interval_us=30000, window_us=30000, active=True) as scanner:
        async for result in scanner:
            name = result.name()
            if name:
                try:
                    addr = bytes(result.device.addr).hex()
                except Exception:
                    addr = "?"
                print("probe: saw %r addr=%s" % (name, addr))
            if name == TARGET_NAME and device is None:
                device = result.device
    if device is None:
        print("probe: never saw %r during the scan" % (TARGET_NAME,))
        return

    print("probe: connecting...")
    connection = await device.connect(timeout_ms=8000)
    print("probe: connected, mtu=%r" % (connection.mtu,))

    async with connection:
        # Experiment: a capture of the vendor iOS app's actual first-ever
        # pairing shows it negotiates MTU 247 (Client Rx MTU 527, Server Rx
        # MTU 247 -- contrary to the scratch doc's static-analysis guess
        # that iOS keeps the default). This connection never requests an
        # exchange at all and sits at the BLE default (23, 20 usable) --
        # the device's own notify payload is ~50 bytes, well over that. If
        # this heater's firmware just silently drops a notification it
        # can't fit in one packet (rather than fragmenting/truncating),
        # that alone would produce exactly the total silence seen so far.
        try:
            mtu = await connection.exchange_mtu(247)
            print("probe: exchange_mtu -> %r" % (mtu,))
        except Exception as e:
            print("probe: !! exchange_mtu failed: %s" % e)
        print("probe: enumerating ALL services (no UUID filter)...")
        found_target = False
        async for service in connection.services():
            print("probe:   service %s" % (service.uuid,))
            if service.uuid == SVC_UUID:
                found_target = True
        print("probe: FFE0 seen via full enumeration: %s" % found_target)

        print("probe: trying connection.service(FFE0) directly...")
        svc = await connection.service(SVC_UUID)
        print("probe:   result: %r" % (svc,))

        if svc is None and found_target:
            print("probe: !! full enumeration found it but the by-UUID lookup didn't -- aioble UUID-match bug")
        elif svc is None:
            print("probe: !! not found either way -- real discovery failure, not a lookup bug")
        else:
            print("probe: discovering characteristics of FFE0...")
            target_char = None
            async for char in svc.characteristics():
                is_target = char.uuid == CHAR_UUID
                print("probe:   char %s  properties=%r  (target=%s)" % (char.uuid, char.properties, is_target))
                if is_target:
                    target_char = char

            if target_char is not None:
                print("probe: subscribing to notify on FFE1...")
                try:
                    await target_char.subscribe(notify=True)
                    print("probe: subscribe() returned with no error")
                except Exception as e:
                    print("probe: !! subscribe failed: %s" % e)

                async def listen():
                    while True:
                        data = await target_char.notified()
                        print("probe: notify raw: %s" % (bytes(data).hex(),))

                listen_task = asyncio.create_task(listen())

                for cmd, p1, p2, label in (
                    (1, 0, 0, "CMD_READ"),
                    (3, 1, 0, "CMD_ON_OFF(1)"),
                ):
                    frame = _encode_frame(cmd, p1, p2)
                    print("probe: writing %s: %s" % (label, frame.hex()))
                    try:
                        await target_char.write(frame, response=True)
                        print("probe:   write() returned with no error (ack'd)")
                    except Exception as e:
                        print("probe:   !! write failed: %s" % e)
                    print("probe: waiting 4s for a notification...")
                    await asyncio.sleep(4)

                listen_task.cancel()

        print("probe: staying connected 3s to see if it drops on its own...")
        await asyncio.sleep(3)

    print("probe: disconnected")


asyncio.run(main())
