# `mpremote`/`esptool.py`/`mpy-cross` must all be on PATH -- mpy-cross in
# particular must be the EXACT build matching this project's custom
# firmware (bytecode format is version/config-sensitive), built from the
# same lvgl_micropython checkout used for the firmware itself
# (lib/micropython/mpy-cross), not a generic `brew install`ed one -- see
# README.md.

MPREMOTE ?= mpremote
ESPTOOL  ?= esptool.py
MPY_CROSS ?= mpy-cross

# Edit this (or pass FIRMWARE=... on the command line) before `make flash`.
FIRMWARE ?= CHANGE_ME_lvgl_micropython_esp32s3.bin

SCREENS_PY := $(wildcard screens/*.py)
SCREENS_MPY := $(SCREENS_PY:.py=.mpy)

.PHONY: help install sync dev repl reset check install-aioble flash mpy clean-mpy

help:
	@echo "Targets:"
	@echo "  install        precompile and copy all files to device (run this once first)"
	@echo "  sync           precompile screens/ then copy them to device"
	@echo "  dev            sync, then reset the board so it reruns main.py from flash -- run 'make repl' separately to watch output"
	@echo "  repl           mpremote repl"
	@echo "  reset          mpremote reset (soft reset)"
	@echo "  check          run test/check_lvgl_api.py on the device (run before main.py on a fresh setup)"
	@echo "  mpy            precompile screens/*.py -> screens/*.mpy (only rebuilds changed files)"
	@echo "  clean-mpy      remove screens/*.mpy"
	@echo "  install-aioble mpremote mip install aioble"
	@echo "  flash          erase and write FIRMWARE=... (default: $(FIRMWARE)) to flash"

# Required after any screens/*.py edit, in any workflow below (dev, sync,
# or install) -- import screens alone was enough to hard-crash the board
# with zero Python traceback once screens/ grew past some size (the
# on-device compiler running out of stack parsing the whole package in one
# `import screens`, not a bad LVGL call). Precompiled .mpy files take
# precedence over the matching .py at import time and are never recompiled
# on-device, sidestepping the crash entirely. `install`/`sync` (and `dev`,
# via `sync`) all depend on this so it happens automatically -- a stale
# .mpy can no longer silently win over a freshly-edited .py the way it
# could with the plain shell-command version of this step.
mpy: $(SCREENS_MPY)

screens/%.mpy: screens/%.py
	$(MPY_CROSS) -o $@ -s $(notdir $<) $<

clean-mpy:
	rm -f screens/*.mpy

sync: mpy
	$(MPREMOTE) cp boot.py main.py ble_config.py panel_settings.py serial_link.py theme.py hal.py encoder.py aircon_ble.py : + cp -r screens : + cp -r fonts : + cp -r images :

install: sync

dev: sync reset
	sleep 2
	$(MPREMOTE) repl

undev:
	$(MPREMOTE) fs rm boot.py main.py
	$(MPREMOTE) reset

repl:
	$(MPREMOTE) repl

reset:
	$(MPREMOTE) reset

check:
	$(MPREMOTE) run test/check_lvgl_api.py

install-aioble:
	$(MPREMOTE) mip install aioble

flash:
	$(ESPTOOL) --chip esp32s3 -p /dev/tty.usbmodem101 -b 460800 --before default_reset --after hard_reset write_flash --flash_mode dio --flash_size 8MB --flash_freq 80m --erase-all 0x0 $(FIRMWARE)
