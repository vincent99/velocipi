"""
Entry point for the AirCon Pico 2W controller.

Boot sequence:
  1. Initialise hardware (sensors, relays, LED, servo, buzzer)
  2. Restore persisted settings into the controller
  3. Start asyncio tasks: temperature loop, AC control loop, BLE server, web server
  4. Beep twice to indicate ready
  5. WiFi connects in the background; web server becomes reachable once it's up
     and will reconnect automatically if the link drops
"""

import asyncio
import network
import ntptime
import config
import log
from sensors import TemperatureSensors, PWMMonitor
from actuators import Relays, RGBLed, Servo, Buzzer
from controller import ACController
from ble_server import BLEServer
from web_server import WebServer


def _sync_ntp():
    """Synchronise RTC from NTP; logs success or failure. Does not raise."""
    try:
        ntptime.settime()
        import time
        t = time.localtime()
        log.log('ntp', f'time set — {t[0]}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d} UTC')
    except Exception as e:
        log.log('ntp', f'sync failed: {e}')


async def wifi_task():
    """Background task: connect to WiFi and reconnect whenever the link drops."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    already_connected = False
    while True:
        if wlan.isconnected():
            if not already_connected:
                log.log('wifi', f'connected — http://{wlan.ifconfig()[0]}/')
                _sync_ntp()
                already_connected = True
            await asyncio.sleep(10)
            continue
        already_connected = False

        if config.WIFI_SSID:
            log.log('wifi', f'connecting to {config.WIFI_SSID} ...')
            try:
                wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
            except Exception as e:
                log.log('wifi', f'connect error: {e}')
                await asyncio.sleep(30)
                continue

            for _ in range(20):
                if wlan.isconnected():
                    break
                await asyncio.sleep(1)

            if wlan.isconnected():
                log.log('wifi', f'connected — http://{wlan.ifconfig()[0]}/')
                _sync_ntp()
            else:
                wlan.disconnect()
                log.log('wifi', 'connection failed, retrying in 30s')
                await asyncio.sleep(30)
        else:
            log.log('wifi', 'no SSID configured')
            await asyncio.sleep(60)


async def main():
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
    ctrl.on_state_change = ble.notify_state_changed

    asyncio.create_task(led.run())
    asyncio.create_task(buzzer.double_beep())

    log.log('system', f'mode={ctrl.mode}  setpoint={ctrl.setpoint}°F  delta=±{ctrl.delta}°F')

    # ── Run all tasks concurrently ────────────────────────────────────────────
    await asyncio.gather(
        wifi_task(),     # connect/reconnect WiFi in background
        sensors.run(),   # read temperature probes continuously
        ctrl.run(),      # auto-mode control loop
        ble.run(),       # BLE GATT server
        web.run(),       # HTTP server
    )


asyncio.run(main())
