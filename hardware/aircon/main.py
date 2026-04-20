"""
Entry point for the AirCon Pico 2W controller.

Boot sequence:
  1. Initialise hardware (sensors, relays, LED, servo, buzzer)
  2. Restore persisted settings into the controller
  3. Start asyncio tasks: temperature loop, AC control loop, BLE server, web server
  4. Beep twice to indicate ready
  5. WiFi connects in the background; web server becomes reachable once it's up
     and will reconnect automatically if the link drops
     Note: NTP is not used — the RTC starts at 2021-01-01 on each boot
     WebREPL is started from boot.py (password: purplemonkeydishwasher, port 8266)
"""

import asyncio
import gc
import machine
import network
import config
import log
import web_server

from sensors import TemperatureSensors, PWMMonitor
from actuators import Relays, RGBLed, Buzzer
from controller import ACController
from ble_server import BLEServer
from web_server import WebServer


async def watchdog_task():
    """Arm the watchdog after other tasks have started.
    Timeout is the hardware max (8388 ms); feed every 7 s giving ~1.3 s of
    headroom.  The WDT only fires if the event loop is completely stuck for
    >8 s — not just slow.
    If /nowatch exists on the filesystem, the watchdog is skipped entirely."""
    await asyncio.sleep_ms(100)
    try:
        import os
        os.stat('/nowatch')
        log.log('watchdog', 'disabled — /nowatch present')
        return
    except OSError:
        pass
    log.log('watchdog', 'arming')
    wdt = machine.WDT(timeout=8388)
    wdt.feed()
    log.log('watchdog', 'armed')
    while True:
        await asyncio.sleep(1)
        wdt.feed()


async def monitor_task():
    """Periodically log memory and open connection count."""
    while True:
        await asyncio.sleep(60)
        before = gc.mem_free()
        gc.collect()
        after = gc.mem_free()
        log.log('monitor', f'mem_free={after}  reclaimed={after-before}  alloc={gc.mem_alloc()}  web_active={web_server._active}')


def _start_ap(ctrl):
    """Configure and start WiFi AP mode if /wifi_ap.json is present."""
    ap_cfg = config.WIFI_AP_CONFIG
    if not ap_cfg:
        log.log('ap', 'no /wifi_ap.json — skipping')
        return
    try:
        ssid     = ap_cfg.get('ssid', '').strip() or ctrl.ble_device_name
        password = ap_cfg.get('password', '')
        # CYW43_AUTH_WPA2_AES_PSK = 0x00400004
        security = ap_cfg.get('security', 0x00400004)
        log.log('ap', f'activating — ssid={ssid}  security={security}  password={"(set)" if password else "(none)"}')
        ap = network.WLAN(network.AP_IF)
        ap.active(False)
        ap.config(ssid=ssid, password=password, security=security)
        ap.active(True)
        # No gateway/DNS — tells DHCP clients there is no internet route,
        # so iOS/Android won't try to tunnel internet traffic through the Pico
        # or show persistent "no internet" / "keep trying WiFi" prompts.
        ap.ifconfig(('192.168.4.1', '255.255.255.0', '0.0.0.0', '0.0.0.0'))
        log.log('ap', f'active={ap.active()}')
        cfg = ap.ifconfig()
        log.log('ap', f'ready — ssid={ssid}  ip={cfg[0]}  mask={cfg[1]}  gw={cfg[2]}')
        log.log('ap', f'status={ap.status()}')
    except Exception as e:
        import sys, io
        buf = io.StringIO()
        sys.print_exception(e, buf)
        log.log('ap', f'start error: {buf.getvalue()}')


async def wifi_task(ctrl):
    """Background task: start AP if configured, then connect as client and reconnect on drop."""
    _start_ap(ctrl)

    ap = network.WLAN(network.AP_IF) if config.WIFI_AP_CONFIG else None
    last_ap_status = None

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.config(pm=0xa11140)  # CYW43_NO_POWERSAVE_MODE — keep radio always-on
    already_connected = False
    while True:
        if ap:
            try:
                st = ap.status()
                cfg = ap.ifconfig()
                if st != last_ap_status:
                    log.log('ap', f'status={st}  ip={cfg[0]}  active={ap.active()}')
                    last_ap_status = st
            except Exception as e:
                log.log('ap', f'poll error: {e}')
        if wlan.isconnected():
            if not already_connected:
                log.log('wifi', f'connected — http://{wlan.ifconfig()[0]}/')
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
                already_connected = True
                log.log('wifi', f'connected — http://{wlan.ifconfig()[0]}/')
            else:
                wlan.disconnect()
                log.log('wifi', 'connection failed, retrying in 30s')
                await asyncio.sleep(30)
        else:
            log.log('wifi', 'no client SSID configured')
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
        ble = BLEServer(ctrl, led)
        ctrl.on_state_change = ble.notify_state_changed
        log.log('system', 'init: BLE done')
        await ble.run()

    asyncio.create_task(guarded('sensors',  sensors.run()))
    asyncio.create_task(guarded('ctrl',     ctrl.run()))
    asyncio.create_task(guarded('watchdog', watchdog_task()))
    asyncio.create_task(guarded('monitor',  monitor_task()))
    asyncio.create_task(guarded('ble',      ble_task()))
    asyncio.create_task(guarded('wifi',     wifi_task(ctrl)))
    asyncio.create_task(guarded('web',      web.run()))

    led.ready()
    log.log('system', 'all tasks scheduled')

    # Keep main alive so the event loop continues running.
    while True:
        await asyncio.sleep(3600)


asyncio.run(main())
