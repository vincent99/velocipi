"""Entry point for the fuel-level BLE peripheral -- a generic ESP32-S3
running plain stock MicroPython. Reads config.PIN_FUEL_ADC, converts to a
0-100% level via a two-point calibration, and serves both over BLE (see
ble_server.py's own module docstring for the exact GATT layout) so
../hvac-knob/ -- or any other BLE central, including a generic scanner app,
see that same docstring for why -- can read it.
"""

import asyncio

import config
from ble_server import FuelBLEServer
from fuel_sensor import FuelSensor


async def main():
    print("fuel-level: starting, version", config.VERSION)

    sensor = FuelSensor()
    server = FuelBLEServer(sensor)
    sensor.on_change = server.notify_state_changed

    asyncio.create_task(sensor.run())
    await server.run()


asyncio.run(main())
