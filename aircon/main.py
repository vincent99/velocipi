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
import gc
import machine
import network
import ntptime
import config
import log
import web_server

from sensors import TemperatureSensors, PWMMonitor
from actuators import Relays, RGBLed, Buzzer
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


async def watchdog_task():
    """Arm the watchdog quickly so it can recover a hung BLE or WiFi init.
    The timeout is set to 8 s (hardware max); we feed every 4 s.
    The WDT will fire if any synchronous call blocks the event loop for > 8 s
    (e.g. a hung BLE stack init), triggering a hard reset which runs cyw43_deinit
    and clears the dirty CYW43 BT state that causes the hang on soft reboot."""
    await asyncio.sleep(2)  # let the first loop iteration of each task run
    log.log('watchdog', 'arming')
    wdt = machine.WDT(timeout=8000)
    while True:
        wdt.feed()
        await asyncio.sleep(4)


async def monitor_task():
    """Periodically log memory and open connection count."""
    while True:
        await asyncio.sleep(60)
        before = gc.mem_free()
        gc.collect()
        after = gc.mem_free()
        log.log('monitor', f'mem_free={after}  reclaimed={after-before}  alloc={gc.mem_alloc()}  web_active={web_server._active}')


def _start_webrepl():
    """Start WebREPL if a password file exists at /webrepl_cfg.py. Does not raise."""
    try:
        import webrepl
        webrepl.start()
        log.log('webrepl', 'started')
    except Exception as e:
        log.log('webrepl', f'start failed: {e}')


async def wifi_task():
    """Background task: connect to WiFi and reconnect whenever the link drops."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.config(pm=0xa11140)  # CYW43_NO_POWERSAVE_MODE — keep radio always-on
    already_connected = False
    webrepl_started = False
    while True:
        if wlan.isconnected():
            if not already_connected:
                log.log('wifi', f'connected — http://{wlan.ifconfig()[0]}/')
                _sync_ntp()
                if not webrepl_started:
                    _start_webrepl()
                    webrepl_started = True
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
    # ── Disable power-save modes (always-on device) ───────────────────────────
    # GPIO23 controls the SMPS mode on Pico W/2W.
    # Low (default) = pulse-skipping PFM mode; High = forced PWM, lower ripple,
    # better RF performance for the CYW43 running WiFi + BLE simultaneously.
    machine.Pin(23, machine.Pin.OUT, value=1)

    # ── Hardware init ─────────────────────────────────────────────────────────
    log.log('system', 'init: sensors')
    sensors = TemperatureSensors()
    pwm     = PWMMonitor()
    log.log('system', 'init: actuators')
    relays  = Relays()
    led     = RGBLed()
    buzzer  = Buzzer()

    # ── Controller (loads persisted state) ────────────────────────────────────
    log.log('system', 'init: controller')
    ctrl = ACController(relays, led, sensors, pwm)

    # ── Web server ────────────────────────────────────────────────────────────
    log.log('system', 'init: web')
    web = WebServer(ctrl)

    asyncio.create_task(led.run())
    asyncio.create_task(buzzer.double_beep())

    # ── Schedule all tasks — each is independent via create_task ─────────────
    # Priority order: sensors + control loop first, BLE second, WiFi/web last.
    # BLE construction (aioble.register_services) is deferred into its own task
    # so it cannot block the control loop from starting.
    # Using create_task (not gather) so a crash or hang in one task does not
    # block any other task from running.
    async def guarded(name, coro):
        log.log(name, 'task started')
        try:
            await coro
        except Exception as e:
            log.log('crash', f'{name}: {e}')

    async def ble_task():
        log.log('system', 'init: BLE')
        ble = BLEServer(ctrl)
        ctrl.on_state_change = ble.notify_state_changed
        log.log('system', 'init: BLE done')
        await ble.run()

    asyncio.create_task(guarded('sensors',  sensors.run()))
    asyncio.create_task(guarded('ctrl',     ctrl.run()))
    asyncio.create_task(guarded('watchdog', watchdog_task()))
    asyncio.create_task(guarded('monitor',  monitor_task()))
    asyncio.create_task(guarded('ble',      ble_task()))
    asyncio.create_task(guarded('wifi',     wifi_task()))
    asyncio.create_task(guarded('web',      web.run()))

    log.log('system', 'all tasks scheduled')

    # Keep main alive so the event loop continues running.
    while True:
        await asyncio.sleep(3600)


asyncio.run(main())
