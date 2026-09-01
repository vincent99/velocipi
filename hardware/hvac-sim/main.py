#!/usr/bin/env python3
"""Combined AirCon + Heater + Fuel-sensor BLE simulator -- entry point.

Desktop/Raspberry Pi stand-in for all three real BLE peripherals this
project's knob panel (../hvac-knob/) talks to -- the AC controller
(../aircon/), the parking heater, and the fuel-level sensor
(../fuel-level/) -- from one process, one BlessServer, one advertised
identity (config.BLE_DEVICE_NAME). Replaces the previous ../aircon-sim/ +
../heater-sim/ split, which ran as two independent processes and turned
out not to reliably coexist on one Mac's Bluetooth radio -- each looked
like it advertised successfully in isolation, but running more than one at
once, only one at a time actually reached the air. Merging into one
process/one CBPeripheralManager sidesteps that entirely -- see
ble_server.py's own module docstring for the full story, and
../hvac-knob/fuel_ble.py's own module docstring for how that client shares
its BLE connection/discovery with AirconClient/HeaterClient the same way
those two already share with each other, needed now that all three
resolve to this one process's one BLE address.

Each device is independently optional -- see --ac-only/--heat-only/
--no-fuel below -- useful if you only want to exercise one device's flow
and don't want the others' roller entries showing up on the panel's
Connect screens at all. --ac-only/--heat-only also exclude the fuel sensor
(the word "only" wouldn't mean much otherwise) -- use --no-fuel on its own
to keep AC+heater but drop just the fuel sensor.

Usage:
    python3 main.py
    python3 main.py --ac-only
    python3 main.py --heat-only
    python3 main.py --no-fuel
    python3 main.py --ac-error "This is a test"
    python3 main.py --heat-fault 3
    python3 main.py --heat-password 1234
    python3 main.py --fuel-percent 40
    python3 main.py --name my-sim
"""

import argparse
import asyncio
import logging

import config
from ac_controller import SimController
from heat_controller import SimHeaterController
from fuel_controller import SimFuelController
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
    return "heat: on=%-5s cooling=%-5s mode=%-10s run_param=%-3d now_gear=%-3d fault=%d" % (
        s["on"],
        s["cooling"],
        _HEAT_RUN_MODE_NAME.get(s["run_mode"], s["run_mode"]),
        s["run_param"],
        s["now_gear"],
        s["fault_code"],
    )


def _fuel_status_line(ctrl):
    s = ctrl.get_state()
    return "fuel: percent=%5.1f%% voltage=%.3fV cal_zero=%.2fV cal_full=%.2fV" % (
        s["percent"],
        s["voltage"],
        s["cal_zero_v"],
        s["cal_full_v"],
    )


async def _status_printer(ac_ctrl, heat_ctrl, fuel_ctrl):
    while True:
        if ac_ctrl is not None:
            logger.info(_ac_status_line(ac_ctrl))
        if heat_ctrl is not None:
            logger.info(_heat_status_line(heat_ctrl))
        if fuel_ctrl is not None:
            logger.info(_fuel_status_line(fuel_ctrl))
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

    # --ac-only/--heat-only exclude the fuel sensor too (see this module's
    # own docstring) -- --no-fuel is the independent way to drop just this
    # one while keeping both of the others.
    fuel_ctrl = None
    if not args.ac_only and not args.heat_only and not args.no_fuel:
        fuel_ctrl = SimFuelController(percent=args.fuel_percent, drain_rate=args.fuel_drain_rate)

    # Lets ac_ctrl's own thermal model (_step_temps()'s cabin/panel probes)
    # react to the heater actively running -- see ac_controller.py's
    # _heater_cabin_target(). None (the attribute's own default) whenever
    # heat_ctrl doesn't exist at all (--heat-only's mirror, --ac-only).
    if ac_ctrl is not None:
        ac_ctrl.heater_ctrl = heat_ctrl

    server = SimBLEServer(ac_ctrl, heat_ctrl, fuel_ctrl, device_name=args.name)

    logger.info(
        "starting BLE GATT server %r (ac=%s heat=%s fuel=%s)",
        server.device_name,
        ac_ctrl is not None,
        heat_ctrl is not None,
        fuel_ctrl is not None,
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

    tasks = [_status_printer(ac_ctrl, heat_ctrl, fuel_ctrl)]
    if ac_ctrl is not None:
        tasks.append(ac_ctrl.run())
    if heat_ctrl is not None:
        tasks.append(heat_ctrl.run())
    if fuel_ctrl is not None:
        tasks.append(fuel_ctrl.run())

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
        help="Only simulate the AirCon -- no heater or fuel-sensor service registered or advertised at all",
    )
    only_group.add_argument(
        "--heat-only",
        action="store_true",
        help="Only simulate the heater -- no AirCon or fuel-sensor service registered or advertised at all",
    )
    parser.add_argument(
        "--no-fuel",
        action="store_true",
        help="Don't simulate the fuel sensor -- no Battery/Fuel Level service registered or advertised at "
        "all. Independent of --ac-only/--heat-only (either of those already implies this too)",
    )
    parser.add_argument(
        "--fuel-percent",
        type=float,
        default=None,
        help="Starting fuel tank level, 0-100 (default: config.DEFAULT_FUEL_PERCENT, %r)"
        % config.DEFAULT_FUEL_PERCENT,
    )
    parser.add_argument(
        "--fuel-drain-rate",
        type=float,
        default=None,
        # "%%/minute", not "%/minute" -- .format(), not %, does this
        # method's own default-value substitution (deliberately, unlike
        # every other --xxx-only/--heat-fault/etc. help string above,
        # which all use %) specifically so the literal "%%" survives
        # intact into argparse's OWN internal help-text expansion pass
        # (which also uses %-formatting, e.g. for %(default)s -- see
        # argparse's own HelpFormatter), collapsing to a single literal
        # "%" only there. Doing this substitution with % instead, the way
        # every other help string here does, collapses "%%" to a bare "%"
        # too early -- confirmed: argparse's own pass then chokes on the
        # resulting literal "%/minute" ("unsupported format character
        # '/'"), since a bare "%" followed by a non-format character isn't
        # valid for ITS pass either.
        help="%%/minute the simulated tank drains on its own -- see fuel_controller.py's own comment. 0 "
        "disables draining entirely (default: config.DEFAULT_FUEL_DRAIN_PCT_PER_MIN, {!r})".format(
            config.DEFAULT_FUEL_DRAIN_PCT_PER_MIN
        ),
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
        "(default: %r). For heater/fuel-sensor discovery to reliably find it (unless --ac-only), it needs "
        "\"sim\" as its own space/hyphen/edge-delimited word (e.g. \"my-sim\", not \"mysim\") -- see "
        "../hvac-knob/heater_ble.py's scan_for_heaters()/fuel_ble.py's scan_for_fuel_sensors() docstrings' "
        "SIM NAME MATCH paragraphs. Keep it under 10 characters total on macOS -- see this package's own "
        "README's Platform notes."
        % config.BLE_DEVICE_NAME,
    )
    cli_args = parser.parse_args()
    if cli_args.heat_password is not None and not (0 <= cli_args.heat_password <= 9999):
        parser.error("--heat-password must be between 0 and 9999")
    if cli_args.fuel_percent is not None and not (0.0 <= cli_args.fuel_percent <= 100.0):
        parser.error("--fuel-percent must be between 0 and 100")
    if cli_args.fuel_drain_rate is not None and cli_args.fuel_drain_rate < 0:
        parser.error("--fuel-drain-rate must be >= 0")
    if cli_args.name is not None and not cli_args.ac_only:
        # Mirrors heater_ble.py's scan_for_heaters()/fuel_ble.py's
        # scan_for_fuel_sensors() SIM NAME MATCH checks exactly (see this
        # argument's own help text) -- a soft warning, not a hard error,
        # since heater's own NAME_PREFIX ("BYD-...")/fuel's own
        # FUEL_SERVICE_UUID fallback still work too, and there's no way to
        # check either without importing the knob's own config modules
        # from this desktop package.
        if "sim" not in cli_args.name.lower().replace("-", " ").split():
            logger.warning(
                '--name %r doesn\'t have "sim" as its own word -- the heater/fuel-sensor Connect screens\' '
                "scans may not find it, see ../hvac-knob/heater_ble.py's scan_for_heaters()/fuel_ble.py's "
                "scan_for_fuel_sensors() docstrings",
                cli_args.name,
            )
        if len(cli_args.name) >= 10:
            logger.warning(
                "--name %r is 10 characters or more -- confirmed on real hardware that this isn't reliably "
                "advertised alongside both GATT services on macOS, even though bless itself reports "
                "advertising cleanly. See config.py's BLE_DEVICE_NAME comment.",
                cli_args.name,
            )
    try:
        asyncio.run(main(cli_args))
    except KeyboardInterrupt:
        pass
