"""
Entry point for the AirCon Pico 2W controller.

Boot sequence:
  1. Connect to WiFi
  2. Initialise hardware (sensors, relays, LED, servo, buzzer)
  3. Restore persisted settings into the controller
  4. Start asyncio tasks: temperature loop, AC control loop, BLE server, web server
  5. Beep twice to indicate ready
"""

import asyncio
import network
import config
from sensors import TemperatureSensors, PWMMonitor
from actuators import Relays, RGBLed, Servo, Buzzer
from controller import ACController
from ble_server import BLEServer
from web_server import WebServer


async def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print(f'Connecting to {config.WIFI_SSID} ...')
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        for _ in range(20):
            if wlan.isconnected():
                break
            await asyncio.sleep(1)

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print(f'WiFi connected — http://{ip}/')
        return ip
    else:
        print('WiFi failed; web server will not be reachable')
        return None


async def main():
    await connect_wifi()

    # ── Hardware init ─────────────────────────────────────────────────────────
    sensors = TemperatureSensors()
    pwm     = PWMMonitor()
    relays  = Relays()
    led     = RGBLed()
    servo   = Servo()
    buzzer  = Buzzer()

    # ── Controller (loads persisted state) ────────────────────────────────────
    ctrl = ACController(relays, servo, led, sensors, pwm)

    # ── Servers ───────────────────────────────────────────────────────────────
    ble = BLEServer(ctrl)
    web = WebServer(ctrl)

    # Ready signal
    asyncio.create_task(buzzer.double_beep())

    print(f'Mode: {ctrl.mode}  Setpoint: {ctrl.setpoint}°F  Delta: {ctrl.delta}°F')

    # ── Run all tasks concurrently ────────────────────────────────────────────
    await asyncio.gather(
        sensors.run(),   # read temperature probes continuously
        ctrl.run(),      # auto-mode control loop
        ble.run(),       # BLE GATT server
        web.run(),       # HTTP server
    )


asyncio.run(main())
