#!/usr/bin/env python3
"""Combined AirCon + Heater BLE simulator -- entry point.

Desktop/Raspberry Pi stand-in for BOTH real BLE peripherals this project's
knob panel (../hvac-knob/) talks to -- the AC controller (../aircon/) and
the parking heater -- from one process, one BlessServer, one advertised
identity (config.BLE_DEVICE_NAME). Replaces the previous ../aircon-sim/ +
../heater-sim/ split, which ran as two independent processes and turned
out not to reliably coexist on one Mac's Bluetooth radio -- each looked
like it advertised successfully in isolation, but running both at once,
only one at a time actually reached the air. Merging into one process/one
CBPeripheralManager sidesteps that entirely -- see ble_server.py's own
module docstring for the full story.

Either half is independently optional -- see --ac-only/--heat-only below --
useful if you only want to exercise one device's flow and don't want the
other one's roller entry showing up on the panel's Connect screens at all.

Usage:
    python3 main.py
    python3 main.py --ac-only
    python3 main.py --heat-only
    python3 main.py --ac-error "This is a test"
    python3 main.py --heat-fault 3
    python3 main.py --heat-password 1234
    python3 main.py --name HVAC-2
"""

import argparse
import asyncio
import logging

import config
from ac_controller import SimController
from heat_controller import SimHeaterController
from ble_server import SimBLEServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)-16s %(message)s")
logger = logging.getLogger("hvac-sim")

_HEAT_RUN_MODE_NAME = {
    config.RUN_MODE_GEAR: "gear",
    config.RUN_MODE_THERMOSTAT: "thermostat",
    config.RUN_MODE_VENT: "vent",
    config.RUN_MODE_HIGH: "high",
}


def _ac_status_line(ctrl):
    s = ctrl.get_state()
    cur = s["current_temp"]
    return (
        "ac:   mode=%-4s fan=%-6s setpoint=%.0f\xb0F circ=%-7s "
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


def _heat_status_line(ctrl):
    s = ctrl.get_state()
    return "heat: on=%-5s mode=%-10s run_param=%-3d now_gear=%-3d fault=%d" % (
        s["on"],
        _HEAT_RUN_MODE_NAME.get(s["run_mode"], s["run_mode"]),
        s["run_param"],
        s["now_gear"],
        s["fault_code"],
    )


async def _status_printer(ac_ctrl, heat_ctrl):
    while True:
        if ac_ctrl is not None:
            logger.info(_ac_status_line(ac_ctrl))
        if heat_ctrl is not None:
            logger.info(_heat_status_line(heat_ctrl))
        await asyncio.sleep(5)


async def main(args):
    loop = asyncio.get_running_loop()

    ac_ctrl = None
    if not args.heat_only:
        ac_ctrl = SimController()
        if args.ac_error:
            # Seeded once at startup, not re-applied afterward --
            # SimController already clears self.error on its own (a
            # mode/fan change, or _auto_control() once a full auto-mode
            # cycle finds a real temp reading), same as the real firmware
            # would, so this is only meant to get a knob-side error display
            # up for testing without needing to fake an actual fault
            # condition.
            ac_ctrl.error = args.ac_error

    heat_ctrl = None
    if not args.ac_only:
        heat_ctrl = SimHeaterController(fault_code=args.heat_fault, password=args.heat_password)

    server = SimBLEServer(ac_ctrl, heat_ctrl, device_name=args.name)

    logger.info(
        "starting BLE GATT server %r (ac=%s heat=%s)",
        server.device_name,
        ac_ctrl is not None,
        heat_ctrl is not None,
    )
    if heat_ctrl is not None:
        if args.heat_password is not None:
            logger.info(
                "heater password required: %04d -- every frame not carrying this gets silently ignored, "
                "see ble_server.py's _on_write_heat()",
                args.heat_password,
            )
        else:
            logger.info("no heater password configured -- every frame accepted regardless of its embedded password bytes")
    await server.start(loop)
    logger.info("waiting for connections from the knob panel...")

    tasks = [_status_printer(ac_ctrl, heat_ctrl)]
    if ac_ctrl is not None:
        tasks.append(ac_ctrl.run())
    if heat_ctrl is not None:
        tasks.append(heat_ctrl.run())

    try:
        await asyncio.gather(*tasks)
    finally:
        await server.server.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    only_group = parser.add_mutually_exclusive_group()
    only_group.add_argument(
        "--ac-only",
        action="store_true",
        help="Only simulate the AirCon -- no heater service registered or advertised at all",
    )
    only_group.add_argument(
        "--heat-only",
        action="store_true",
        help="Only simulate the heater -- no AirCon service registered or advertised at all",
    )
    parser.add_argument(
        "--ac-error",
        default="",
        help="Seed the AC's state.error with this message at startup (for testing the knob's error display)",
    )
    parser.add_argument(
        "--heat-fault",
        type=int,
        default=0,
        help="Seed the heater's state.fault_code with this value at startup (for testing the panel's error "
        "display -- see ../hvac-knob/screens/home.py's refresh() and screens/info.py). NOT a confirmed "
        "real-hardware byte -- see config.py's NOTIFY_OFF_FAULT comment; this exercises the panel's "
        "plumbing, not a known real fault format",
    )
    parser.add_argument(
        "--heat-password",
        type=int,
        default=None,
        help="Require this 4-digit PIN (0-9999) on the heater's frames -- every incoming frame carries a "
        "password (see config.py's frame-format comment; there's no separate handshake/login command in "
        "this protocol version), checked against this on every write, see ble_server.py's _on_write_heat(). "
        "Omit entirely to simulate a heater with no password (the default; every frame is accepted "
        "regardless of its embedded password bytes)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Advertised device name for the whole combined peripheral, overriding config.BLE_DEVICE_NAME "
        "(default: %r). Keep it short on macOS -- see this package's own README's Platform notes."
        % config.BLE_DEVICE_NAME,
    )
    cli_args = parser.parse_args()
    if cli_args.heat_password is not None and not (0 <= cli_args.heat_password <= 9999):
        parser.error("--heat-password must be between 0 and 9999")
    try:
        asyncio.run(main(cli_args))
    except KeyboardInterrupt:
        pass
