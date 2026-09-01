# `mpremote`/`esptool.py` must be on PATH. Unlike ../hvac-knob/, this
# project runs on a generic ESP32-S3 with the stock MicroPython firmware
# (no display/LVGL here) -- see README.md for where to get it. Any
# mpy-cross matching that firmware's own MicroPython version works if you
# bother precompiling at all; these files are small enough that plain .py
# works fine too, unlike ../hvac-knob/'s screens/ (see that project's own
# Makefile comment on why those specifically need it).

MPREMOTE ?= mpremote
ESPTOOL ?= esptool.py

# Edit this (or pass FIRMWARE=... on the command line) before `make flash`.
FIRMWARE ?= "firmware/ESP32_GENERIC_S3-*.bin"

PY_FILES := boot.py main.py config.py fuel_sensor.py ble_server.py storage.py

.PHONY: help sync dev repl reset install-aioble flash

help:
	@echo "Targets:"
	@echo "  sync           copy all .py files to the device"
	@echo "  dev            sync, then reset the board so it reruns main.py from flash"
	@echo "  repl           mpremote repl"
	@echo "  reset          mpremote soft reset"
	@echo "  install-aioble mpremote mip install aioble"
	@echo "  flash          erase and write FIRMWARE=... (default: $(FIRMWARE)) to flash"

sync:
	$(MPREMOTE) cp $(PY_FILES) :

dev: sync
	$(MPREMOTE) reset
	sleep 2
	$(MPREMOTE) repl

repl:
	$(MPREMOTE) repl

reset:
	$(MPREMOTE) reset

install-aioble:
	$(MPREMOTE) mip install aioble

flash:
	$(ESPTOOL) --chip esp32s3 -p /dev/tty.usbmodem101 -b 460800 --before default_reset --after hard_reset write_flash --flash_mode dio --flash_size 8MB --flash_freq 80m --erase-all 0x0 $(FIRMWARE)
