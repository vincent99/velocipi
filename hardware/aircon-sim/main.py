#!/usr/bin/env python3
"""AirCon BLE simulator -- entry point.

Advertises the same BLE GATT service the real RP2350 firmware in
../aircon/ does (see config.py), backed by an in-memory state machine +
thermal model (controller.py) instead of real relays/sensors. Point
../hvac-knob/ble_config.py at this device (it already matches by default
-- same name, same placeholder-that-you-fill-in service UUID) to exercise
the panel's full UI without the physical AC hardware.

Usage:
    python3 main.py
    python3 main.py --error "This is a test"
"""

import argparse
import asyncio
import logging
import time

import config
from controller import SimController
from ble_server import SimBLEServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)-16s %(message)s")
logger = logging.getLogger("aircon-sim")


def _status_line(ctrl):
    s = ctrl.get_state()
    cur = s["current_temp"]
    return (
        "mode=%-4s fan=%-6s setpoint=%.0f°F circ=%-7s "
        "compressor=%-3s current=%s cabin=%s blower=%s"
        % (
            s["mode"],
            s["fan"],
            s["setpoint"],
            s["circulation"],
            s["compressor"],
            "%.1f" % cur if cur is not None else "--",
            "%.1f" % s["cabin_temp"] if s["cabin_temp"] is not None else "--",
            "%.1f" % s["blower_temp"] if s["blower_temp"] is not None else "--",
        )
    )


async def _status_printer(ctrl):
    while True:
        logger.info(_status_line(ctrl))
        await asyncio.sleep(5)


async def main(args):
    loop = asyncio.get_running_loop()

    ctrl = SimController()
    if args.error:
        # Seeded once at startup, not re-applied afterward -- SimController
        # already clears self.error on its own (a mode/fan change, or
        # _auto_control() once a full auto-mode cycle finds a real temp
        # reading -- see controller.py), same as the real firmware would,
        # so this is only meant to get a knob-side error display (red
        # current-temp background, Info screen's error text) up for testing
        # without needing to fake an actual fault condition.
        ctrl.error = args.error
    server = SimBLEServer(ctrl)

    logger.info("starting BLE GATT server %r (service %s)", config.BLE_DEVICE_NAME, config.BLE_SVC_UUID)
    await server.start(loop)
    logger.info("waiting for connections from the AirCon knob panel...")

    try:
        await asyncio.gather(ctrl.run(), _status_printer(ctrl))
    finally:
        await server.server.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--error", default="", help="Seed state.error with this message at startup (for testing the knob's error display)")
    cli_args = parser.parse_args()
    try:
        asyncio.run(main(cli_args))
    except KeyboardInterrupt:
        pass
