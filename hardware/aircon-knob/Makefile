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

TOPLEVEL_PY := boot.py main.py ble_config.py panel_settings.py serial_link.py theme.py hal.py encoder.py aircon_ble.py
TOPLEVEL_MPY := $(TOPLEVEL_PY:.py=.mpy)

SCREENS_PY := $(wildcard screens/*.py)
SCREENS_MPY := $(SCREENS_PY:.py=.mpy)

ALL_MPY := $(TOPLEVEL_MPY) $(SCREENS_MPY)

.PHONY: help install sync dev repl reset check install-aioble flash mpy mpy-all clean-mpy bump-version

help:
	@echo "Targets:"
	@echo "  install        full clean deploy: bump KNOB_VERSION, precompile every .py"
	@echo "                 to .mpy, erase old code on the device, sync the fresh"
	@echo "                 .mpy set, soft-reset -- for a real 'ship this' deploy,"
	@echo "                 not routine iteration (that's sync/dev, below)"
	@echo "  sync           precompile screens/ then copy them to device"
	@echo "  dev            sync, then reset the board so it reruns main.py from flash -- run 'make repl' separately to watch output"
	@echo "  repl           mpremote repl"
	@echo "  reset          mpremote reset (soft reset)"
	@echo "  check          run test/check_lvgl_api.py on the device (run before main.py on a fresh setup)"
	@echo "  mpy            precompile screens/*.py -> screens/*.mpy (only rebuilds changed files)"
	@echo "  mpy-all        precompile every tracked .py (top-level + screens/) -> .mpy"
	@echo "  clean-mpy      remove all tracked *.mpy"
	@echo "  bump-version   bump screens/info.py's KNOB_VERSION (major+1, minor reset to 0)"
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

# install's full-clean-deploy version of the above -- every tracked .py,
# not just screens/. boot.py/main.py included: MicroPython's own boot
# sequence does a plain `import boot`/`import main` (name-based, not a
# literal file read), so boot.mpy/main.mpy work exactly the same as the
# .py originals, no special-casing needed.
mpy-all: $(ALL_MPY)

# One pattern rule for both: `%` matches the full path including any
# directory component, so this already covers screens/foo.py -> screens/
# foo.mpy as well as a bare top-level foo.py -> foo.mpy.
%.mpy: %.py
	$(MPY_CROSS) -o $@ -s $(notdir $<) $<

clean-mpy:
	rm -f $(ALL_MPY)

bump-version:
	python3 tools/bump_version.py

sync: mpy
	$(MPREMOTE) cp boot.py main.py ble_config.py panel_settings.py serial_link.py theme.py hal.py encoder.py aircon_ble.py : + cp -r screens : + cp -r images :

# Deliberately not `install: bump-version mpy-all` -- Make doesn't
# guarantee prerequisites of the same target run in listed order (only
# that they finish before this target's own recipe does), and bump-version
# editing screens/info.py *must* complete before mpy-all compiles it. Each
# $(MAKE) below is its own fully-sequential step instead.
install:
	$(MAKE) bump-version
	$(MAKE) mpy-all
	python3 tools/erase_device.py $(MPREMOTE)
	$(MPREMOTE) cp $(TOPLEVEL_MPY) : + cp -r screens : + cp -r images :
	$(MPREMOTE) soft-reset

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
