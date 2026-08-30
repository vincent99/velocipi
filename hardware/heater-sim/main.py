#!/usr/bin/env python3
"""Heater BLE simulator -- entry point.

Advertises a BLE peripheral matching the real heater's identity closely
enough for ../hvac-knob/heater_ble.py's scan_for_heaters() to find it
(name starts with config.NAME_PREFIX, i.e. "BYD-") and its protocol exactly
(see protocol.py/config.py) -- backed by an in-memory state machine
(controller.py) instead of a real heater core. No pairing/setup needed on
this side beyond running it: point the panel at it from its own Connect
screen for the heater (see ../hvac-knob/README.md's "Connect /
Disconnected screens"), same as you would a real unit.

Unlike ../aircon-sim/ (which the panel's AirCon Connect screen finds by an
exact, configured device name), this one is found the same way a real
heater is: scanned by name *prefix*, then picked from a list. So there's no
config file to point the panel at in advance -- just run this, then use the
knob to pick "BYD-Sim" (or whatever --name/config.BLE_DEVICE_NAME is set
to) off the Connect screen's roller like any other heater.

If the panel's Connect screen never finds this sim (but does find
../aircon-sim/ running alongside it): see config.py's BLE_DEVICE_NAME
comment first -- keep --name under 10 characters. That's the one
configuration confirmed, on real hardware, to actually reach the panel's
scan reliably (mirroring ../aircon-sim/'s own working name length) --
a longer name was also tried and did NOT get found despite `bless` itself
reporting a clean "did start advertising" for it, so don't trust that
library's own internal warning thresholds over an actual scan result.

Usage:
    python3 main.py
    python3 main.py --fault 3
    python3 main.py --password 1234
    python3 main.py --name BYD-2
"""

import argparse
import asyncio
import logging

import config
from controller import SimHeaterController
from ble_server import SimBLEServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)-16s %(message)s")
logger = logging.getLogger("heater-sim")

_RUN_MODE_NAME = {
    config.RUN_MODE_GEAR: "gear",
    config.RUN_MODE_THERMOSTAT: "thermostat",
    config.RUN_MODE_VENT: "vent",
    config.RUN_MODE_HIGH: "high",
}


def _status_line(ctrl):
    s = ctrl.get_state()
    return "on=%-5s mode=%-10s run_param=%-3d now_gear=%-3d fault=%d" % (
        s["on"],
        _RUN_MODE_NAME.get(s["run_mode"], s["run_mode"]),
        s["run_param"],
        s["now_gear"],
        s["fault_code"],
    )


async def _status_printer(ctrl):
    while True:
        logger.info(_status_line(ctrl))
        await asyncio.sleep(5)


async def main(args):
    loop = asyncio.get_running_loop()

    ctrl = SimHeaterController(fault_code=args.fault, password=args.password)
    server = SimBLEServer(ctrl, device_name=args.name)

    logger.info("starting BLE GATT server %r (service %s)", server.device_name, config.BLE_SVC_UUID)
    if args.password is not None:
        logger.info("password required: %04d -- every frame not carrying this gets silently ignored, see ble_server.py's _on_write()", args.password)
    else:
        logger.info("no password configured -- every frame accepted regardless of its embedded password bytes")
    await server.start(loop)
    logger.info("waiting for connections from the AirCon knob panel's heater Connect screen...")

    try:
        await asyncio.gather(ctrl.run(), _status_printer(ctrl))
    finally:
        await server.server.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fault",
        type=int,
        default=0,
        help="Seed state.fault_code with this value at startup (for testing the panel's error display -- see screens/home.py's refresh() and screens/info.py). NOT a confirmed real-hardware byte -- see heater_ble_config.py's NOTIFY_OFF_FAULT comment; this exercises the panel's plumbing, not a known real fault format",
    )
    parser.add_argument(
        "--password",
        type=int,
        default=None,
        help="Require this 4-digit PIN (0-9999) -- every incoming frame carries a password (see heater_ble_config.py's frame-format comment; there's no separate handshake/login command in this protocol version), checked against this on every write, see ble_server.py's _on_write(). Omit entirely to simulate a unit with no password (the default; every frame is accepted regardless of its embedded password bytes)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Advertised device name, overriding config.BLE_DEVICE_NAME (default: %r). Must start with config.NAME_PREFIX (%r) or the panel's Connect screen won't find it. Keep it under 10 characters on macOS -- see this file's own module docstring." % (config.BLE_DEVICE_NAME, config.NAME_PREFIX),
    )
    cli_args = parser.parse_args()
    if cli_args.password is not None and not (0 <= cli_args.password <= 9999):
        parser.error("--password must be between 0 and 9999")
    if cli_args.name is not None:
        if not cli_args.name.startswith(config.NAME_PREFIX):
            parser.error("--name must start with %r or the panel's scan_for_heaters() will never match it" % config.NAME_PREFIX)
        if len(cli_args.name) >= 10:
            logger.warning(
                "--name %r is 10 characters or more -- confirmed on real hardware "
                "that this sim isn't reliably found by the panel's scan in that "
                "range on macOS, even though bless itself reports advertising "
                "cleanly (see config.py's BLE_DEVICE_NAME comment for the full "
                "story). Not a concern on Linux/BlueZ.",
                cli_args.name,
            )
    try:
        asyncio.run(main(cli_args))
    except KeyboardInterrupt:
        pass
