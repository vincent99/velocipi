# `mpremote` must be on PATH. Deploys straight to the RP2350's onboard
# filesystem over USB-serial -- plain stock MicroPython here, no
# cross-compile step like hvac-knob's custom LVGL build needs.

MPREMOTE ?= mpremote

RUNTIME_PY := boot.py main.py config.py controller.py sensors.py actuators.py ble_server.py web_server.py storage.py log.py
WEB_ASSETS := index.html aircon.png webrepl.html webrepl.css webrepl.js term.js FileSaver.js

.PHONY: help sync install dev repl reset undev wifi nowatch watch

help:
	@echo "Targets:"
	@echo "  sync     copy runtime .py + web assets to the board (routine iteration)"
	@echo "  install  sync, then reset so main.py reruns from flash"
	@echo "  dev      sync, reset, then drop into a repl"
	@echo "  repl     mpremote repl"
	@echo "  reset    mpremote reset"
	@echo "  undev    remove boot.py/main.py so the board stops autorunning main.py,"
	@echo "           then reset -- for bench debugging over repl"
	@echo "  wifi     push wifi_client.json + wifi_ap.json -- device-specific"
	@echo "           creds, deliberately NOT part of sync/install"
	@echo "  nowatch  push the /nowatch flag to disable the watchdog while iterating"
	@echo "  watch    remove /nowatch to re-enable the watchdog"

# Runtime code + the web UI assets web_server.py serves (index.html,
# aircon.png, and the browser WebREPL client files). Deliberately excludes
# wifi_client.json/wifi_ap.json (see `wifi` target) and /nowatch (see
# `nowatch`/`watch`) -- those are device-specific / dev-only, not something
# every sync should stomp on.
sync:
	$(MPREMOTE) cp $(RUNTIME_PY) $(WEB_ASSETS) :

install:
	$(MAKE) sync
	sleep 2
	$(MPREMOTE) reset

dev: sync
	$(MPREMOTE) reset
	sleep 2
	$(MPREMOTE) repl

repl:
	$(MPREMOTE) repl

reset:
	$(MPREMOTE) reset

undev:
	$(MPREMOTE) fs rm boot.py main.py
	$(MPREMOTE) reset

wifi:
	$(MPREMOTE) cp wifi_client.json wifi_ap.json :

nowatch:
	$(MPREMOTE) cp nowatch :

watch:
	$(MPREMOTE) fs rm nowatch
