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
FIRMWARE ?= "tools/lvgl_micropy_ESP32_GENERIC_S3-SPIRAM_OCT-8.bin"

BOOT_MAIN_PY := boot.py main.py
COMPILE_PY := ble_config.py panel_settings.py serial_link.py theme.py hal.py encoder.py aircon_ble.py
COMPILE_MPY := $(COMPILE_PY:.py=.mpy)

SCREENS_PY := $(wildcard screens/*.py)
SCREENS_MPY := $(SCREENS_PY:.py=.mpy)

ALL_MPY := $(COMPILE_MPY) $(SCREENS_MPY)

.PHONY: help fast-install install sync dev repl reset check install-aioble flash mpy-screens precompile mpy-clean bump-version

help:
	@echo "Targets:"
	@echo "  install        full clean deploy to knob"
	@echo "  fast-install   full deploy without erasing"
	@echo "                 to .mpy, erase old code on the device, sync the fresh"
	@echo "                 .mpy set, soft-reset -- for a real 'ship this' deploy,"
	@echo "                 not routine iteration (that's sync/dev, below)"
	@echo "  sync           precompile screens/ then copy them to device"
	@echo "  dev            sync, then reset the board so it reruns main.py from flash
	@echo "  repl           mpremote repl"
	@echo "  reset          mpremote soft reset"
	@echo "  check          run test/check_lvgl_api.py on the device (run before main.py on a fresh setup)"
	@echo "  mpy-screens    precompile screens/*.py -> screens/*.mpy (only rebuilds changed files)"
	@echo "  precompile        precompile every tracked .py (top-level + screens/) -> .mpy"
	@echo "  mpy-clean      remove all tracked *.mpy"
	@echo "  bump-version   bump screens/info.py's KNOB_VERSION (major+1, minor reset to 0)"
	@echo "  install-aioble mpremote mip install aioble"
	@echo "  flash          erase and write FIRMWARE=... (default: $(FIRMWARE)) to flash"

# Precompile screen files.  Required after any screens/*.py edit,
# screens are too large to compile on-device.
mpy-screens: $(SCREENS_MPY)

# install's full-clean-deploy version of the source
precompile: $(ALL_MPY)

# One pattern rule for both: `%` matches the full path including any
# directory component, so this already covers screens/foo.py -> screens/
# foo.mpy as well as a bare top-level foo.py -> foo.mpy.
%.mpy: %.py
	$(MPY_CROSS) -o $@ -s $(notdir $<) $<

mpy-clean:
	rm -f $(ALL_MPY)

bump-version:
	python3 tools/bump_version.py

sync: mpy-screens
	$(MPREMOTE) cp boot.py main.py ble_config.py panel_settings.py serial_link.py theme.py hal.py encoder.py aircon_ble.py : + cp -r screens : + cp -r images :

fast-install:
	$(MAKE) precompile
	sleep 2
	$(MPREMOTE) cp $(BOOT_MAIN_PY) $(COMPILE_MPY) : + cp -r screens : + cp -r images :
	sleep 2
	$(MPREMOTE) soft-reset

install:
	python3 tools/erase_device.py $(MPREMOTE)
	$(MAKE) fast-install

dev: sync
	$(MPREMOTE) reset
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
