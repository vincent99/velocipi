# AirCon knob — MicroPython + LVGL port

A Python port of the [CrowPanel 1.28"-HMI ESP32 Rotary Display](https://www.elecrow.com/wiki/CrowPanel_1.28inch-HMI_ESP32_Rotary_Display.html)
firmware in `../temp_knob/firmware/` (C++/Arduino/LVGL): same board, same
direct-BLE-to-the-AirCon-controller architecture — but this one uses real
LVGL widgets through MicroPython's LVGL bindings instead of either the C++
firmware's Arduino toolchain or a hand-rolled framebuf UI, and has since
diverged from that version's screen layout/interaction model (see "Screens"
below) toward a touch-swipe + knob-gauge design. See that directory's README
for the hardware/pin background; this one only covers what's different
about the Python version.

**Nothing here depends on `../temp_knob/`'s LVGL Editor project or its
component library/fonts/icons** — this is a from-scratch, self-contained
implementation of just the AirCon control UI. Text uses LVGL's built-in
fonts (`lv.font_montserrat_*`) — an earlier version loaded a custom
Nasalization binfont to match the web UI's typography, but that turned out
unreliable on real hardware and was dropped; see `theme.py`'s docstring.

## Why not PlatformIO

PlatformIO does not support MicroPython (confirmed with a PlatformIO
maintainer's own reply in their community forum — "We currently don't
support MicroPython"). There is no `platformio.ini` here. Instead, the
`Makefile` wraps `mpremote`/`esptool`/`mpy-cross` directly for everything
this project needs: syncing files, running/mounting, precompiling
`screens/` (see "Build / run / debug loop" below), building/flashing the
custom MicroPython+LVGL firmware image, and installing `aioble`.

## Getting MicroPython + LVGL onto the board

Unlike stock MicroPython, LVGL bindings aren't part of the standard firmware
— you build a custom image with [**lvgl_micropython**](https://github.com/lvgl-micropython/lvgl_micropython),
which compiles in the LVGL Python bindings plus whichever display/touch
drivers you ask for (it has built-in drivers for both chips this board uses,
selected by name at build time — no separate driver-writing needed, unlike
the earlier hand-rolled framebuf version's driver files, which this port
deletes in favor of these).

1. **Prerequisites**: a C compiler toolchain (the build script wraps
   ESP-IDF and fetches what it needs) and Python 3. See the
   [lvgl_micropython README](https://github.com/lvgl-micropython/lvgl_micropython)
   for full prerequisites/troubleshooting.
2. **Clone and build**, somewhere outside this repo:
   ```bash
   git clone https://github.com/lvgl-micropython/lvgl_micropython.git
   cd lvgl_micropython
   python3 make.py esp32 BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT \
       DISPLAY=gc9a01 INDEV=cst816s
   ```
   `SPIRAM_OCT` matches this board's 8MB octal PSRAM. `DISPLAY=gc9a01` and
   `INDEV=cst816s` compile in the exact display/touch drivers `hal.py`
   expects (`import gc9a01`, `import cst816s`) — there's no built-in driver
   for the rotary encoder itself (it's a bespoke two-GPIO quadrature knob,
   not a standard peripheral), so that stays hand-written in `encoder.py`,
   wired up as a custom `lv.indev` in `hal.py`.
3. **Flash the resulting `.bin`** (path depends on the build, typically
   under `build/`): `make flash FIRMWARE=path/to/that.bin` — erases the flash
   first, then writes it.
4. **Install `aioble`** (BLE central library — a custom LVGL build doesn't
   change the BLE side, and `aioble` still isn't bundled): `make
   install-aioble`.
5. **AirCon identity**: `aircon_ble_config.py` already matches the real
   controller firmware's `../aircon/config.py` (and
   `../aircon-sim/config.py`, the desktop simulator — see that directory if
   you want to test the panel without the physical AC hardware). If you
   ever change the device name or UUIDs on the real controller, update all
   three to match, plus the Pi's `.env` (`AirConConfig.DeviceName`/
   `ServiceUUID` in `server/config/config.go`) if it's connecting too.
6. **Heater identity** (optional): `heater_ble_config.py` holds the second
   BLE peripheral's identity — a white-label parking-heater platform with
   no vendor protocol documentation at all, reconstructed by decompiling
   its Android app (see `../../scratch/airheater-ble-protocol.md` and that
   config file's own module docstring for the full story and every "NOT
   hardware-verified" caveat that implies). Nothing to edit here unless
   your specific unit's advertised name doesn't start with `BYD-` — pairing
   itself happens on the panel (see "Connect / Disconnected screens"
   below), not via a config constant, since unlike the AirCon there's no
   fixed device name to hardcode.

## Build / run / debug loop

All of this is `make` targets — see the `Makefile` (`make help` lists them
all). `mpremote`, `esptool.py`, and `mpy-cross` (see "Precompiling screens/"
below for why that last one matters) all need to be on `PATH`.

- **First, on a fresh firmware/wiring**: `make check` — see "Before running
  main.py" below.
- **First, always**: `make install` — copies everything (`.py`/`.mpy` files,
  `images/`) to flash so it runs standalone on power-up (via
  `main.py`'s standard MicroPython auto-run convention). Needed at least
  once before `dev` below will have anything to reboot into.
- **Fastest iteration after that**: `make dev` — syncs just `screens/` (see
  below) to flash, then resets the board so it reruns `main.py` from flash
  with the update. Run `make repl` separately (before or after) to watch the
  output. Deliberately **not** `mpremote mount . run main.py` — confirmed on
  real hardware that mounting and importing a `screens/` package this size
  still hard-resets the board with no Python traceback, the same failure as
  before precompiling to `.mpy` (see below), even with the `.mpy` files
  present and current. `mount` implements a real filesystem, but one that
  proxies every file operation back over the serial connection to the host
  one round trip at a time — plausibly still too slow for `screens/`'s ~8
  files even with on-device *compilation* skipped, since actual flash reads
  don't pay that per-chunk round-trip cost. `mpremote mount . run <file>` is
  still fine directly for anything that doesn't `import screens` (e.g.
  `test/check_lvgl_api.py`, `test/test_brightness.py`).
- **Precompiling `screens/`**: `make install`/`sync`/`dev` all depend on the
  `mpy` target, which recompiles only whatever `screens/*.py` changed since
  the last run (real Make dependency tracking, not a full rebuild every
  time) — so this happens automatically, not a step you need to remember.
  It matters because `import screens` alone hard-crashes the board with no
  Python traceback at all once that package grows past some size (confirmed
  on real hardware: the on-device compiler running out of stack parsing the
  whole package in one `import screens`, not a bad LVGL call) — a
  precompiled `screens/*.mpy` sitting next to the matching `.py` is loaded
  instead of compiled on-device, sidestepping *that* crash. Run `make mpy`
  directly if you want to precompile without also copying/running anything.
- **`make sync`** copies just the (precompiled) `screens/` package to the
  device — quick way to push a `screens/` change onto a board that's already
  otherwise up to date, without a full `install`. `dev` (above) is this plus
  a reset.
- **REPL** (prints, tracebacks, poking at objects live): `make repl` — the
  closest thing to a "debugger" here. Neither stock MicroPython nor this
  LVGL build has a real source-level step-debugger; this project doesn't
  pretend otherwise. If a flashed `main.py` won't let you back into a REPL at
  all, see the safe-mode boot-button escape hatch in "If the board won't
  boot" below.
- `make reset` soft-resets the board (re-running `boot.py`/`main.py` if the
  files were synced to flash).

## Files

| File | Purpose |
| --- | --- |
| `boot.py` / `main.py` | Boot-time setup, a startup splash shown before touch/encoder/BLE init, then the asyncio loop pumping `lv.timer_handler()` and periodically pushing BLE state into widgets. |
| `test/check_lvgl_api.py` | Standalone LVGL API surface sanity check — run this before `main.py` on a fresh setup; see "Before running main.py" below. |
| `Makefile` | `make help` for the full list — install/sync/dev/repl/reset/check, precompiling `screens/` to `.mpy`, flashing firmware, installing `aioble`. |
| `aircon_ble_config.py` | AirCon service / characteristic UUIDs — edit this first. No longer has a device *name* constant — see "Connect / Disconnected screens" below. Renamed from `ble_config.py` now that there's a second BLE peripheral in play (the heater) with its own, differently-shaped config file. |
| `aircon_ble.py` | `aioble`-based BLE GATT central for the AirCon controller; mirrors `server/hardware/aircon/aircon.go` and `../temp_knob/firmware/src/aircon_ble.cpp`. Unaffected by the LVGL switch — BLE and graphics are independent. `AirconClient` takes the device name to connect to (persisted by `panel_settings.py`) rather than a hardcoded constant, and can `scan_for_aircons()` for `screens.ConnectTile`'s picker. |
| `heater_ble_config.py` / `heater_ble.py` | The second BLE peripheral: a white-label parking-heater platform, completely unrelated protocol to the AirCon's (one binary framed protocol over a single characteristic, not one characteristic per field), reconstructed from decompiling its Android app — see `../../scratch/airheater-ble-protocol.md` and `heater_ble_config.py`'s own module docstring for the full story and every "NOT hardware-verified" caveat that implies. `HeaterClient` mirrors `AirconClient`'s shape closely (`scan_for_heaters()`, `set_device_name()`, a `run()` reconnect loop) so `screens.ConnectTile` can drive either client generically — see "Connect / Disconnected screens" below. Pairing is optional and non-blocking, unlike the AirCon's (see `screens/__init__.py`'s module docstring) — a missing/disconnected heater just means Home's "heat" mode and "auto" mode's heating branch quietly do nothing. |
| `ble_shared.py` | The one thing genuinely shared between `aircon_ble.py` and `heater_ble.py`: an `asyncio.Lock()` (`radio_lock`) serializing every `aioble.scan()` call across both clients' reconnect loops and both Connect screens' pickers, *and* each client's own `device.connect()` — confirmed on real hardware that a connect racing the other client's scan raises `OSError 16` — plus the scan interval/window constants both use. |
| `panel_settings.py` | Persists the panel's own settings — which AirCon controller and which heater to connect to — to flash, independent of either device's own settings (the AirCon's live in `aircon_ble.AirconState.settings`, synced over BLE; the heater has no equivalent). |
| `hal.py` | Display/touch setup via lvgl_micropython's built-in `gc9a01`/`cst816s` drivers. Touch self-registers as an LVGL pointer indev; the rotary encoder is returned as a plain `encoder.Encoder` object for the `screens/` package to poll directly, not wired through an `lv.indev`/`lv.group`. |
| `encoder.py` | Rotary encoder quadrature decode + button (no built-in driver for this exists). |
| `theme.py` | Colors (mirrors `../temp_knob/ui/globals.xml`'s tokens) and LVGL's built-in fonts (`lv.font_montserrat_*`) — see its own docstring for why not a custom font. |
| `screens/` | The panel's screens, built from real LVGL widgets (`lv.tileview`, `lv.arc`, `lv.roller`, `lv.line`). One module per screen — see "Screens" below and the table right after it. Diverged from a straight port of `../temp_knob/firmware/src/ui_app.cpp`. |
| `images/splash.bin` | Startup splash image, converted from `aircon.png` (240×240, matches the panel exactly) with LVGL's own `LVGLImage.py` converter into LVGL's native runtime-loadable binary image format — doesn't depend on a PNG decoder being compiled into the firmware build. Regenerate with `python3 LVGLImage.py --ofmt BIN --cf RGB565 -o images aircon.png` then `mv images/aircon.bin images/splash.bin` (`--name` didn't actually rename the output in testing, despite the tool's own `--help` claiming it does for single-file input — hence the manual `mv`). `LVGLImage.py` lives in upstream LVGL's `scripts/` folder; needs `pip install pypng lz4`. Loaded via `lv.image_dsc_t` constructed from its raw pixel bytes, not via `img.set_src(path)` — see "Not hardware-verified" below for why. |

## If the board won't boot / never shows up as a USB serial device

This bit on real hardware once: `main.py` used to `import screens` at the
top of the file, before `lv.init()` ran. The `screens/` package imports
`theme.py`, which used to call `lv.binfont_create(...)` at **module import time** —
meaning it ran during that top-of-file import, before `lv.init()` had set up
LVGL's internal state. That's not just wrong, it can crash hard *inside the
C binding* rather than raising a catchable Python exception — severely
enough to take the USB serial connection down with it (no clean traceback,
no REPL, the board doesn't re-enumerate after a reset). Fixed: `theme.py`'s
font loading is now behind `load_fonts()`, called from `main()` right after
`lv.init()`, and `main.py` imports `screens`/`theme` from inside `main()`
rather than at the top of the file, so nothing LVGL-related can run before
`lv.init()` again.

If you still hit a dead/non-enumerating board after that fix, the general
recovery approach: get a **bare REPL first**. The reliable way now: hold the
knob's push-button down while powering on or resetting the board — `main.py`
checks that pin before doing anything else risky (before even importing
`lvgl`) and, if held, skips running the app entirely, dropping straight to a
normal idle REPL instead. (Ctrl-C alone doesn't get you this: it works fine
on its own, but only reaches `main.py`'s own `except KeyboardInterrupt:
machine.soft_reset()` handler, which just reboots straight back into the
same app rather than leaving a lasting REPL — no help if the app itself is
what's wedged.) Fall back to temporarily renaming `main.py` off the device,
or racing Ctrl-C against a reset, only if the board is crashing somewhere
*before* that safe-mode check itself can run (a firmware-level problem, not
an application one). Then paste `hal.py`'s and `screens/`'s logic in piece by
piece over the REPL (`lv.init()`, then `hal.hal_init(...)`, then one screen
at a time) to find exactly which call hard-crashes rather than raises — that
boundary is almost always "something called before the subsystem it depends
on was initialized," the same shape as this bug.

## Before running main.py: check the LVGL API surface

`test/check_lvgl_api.py` exists because of exactly the kind of bug described in
"Not hardware-verified" below turning up for real: `main.py` first ran
successfully up through `lv.init()`, then hit
`AttributeError: 'module' object has no attribute 'group_set_default'` --
`lv_group_set_default(group)` turned out to be bound as a method
(`group.set_default()`), not a bare `lv.` function, unlike `lv.group_create()`
(no existing instance to attach a method to, since it's the constructor).
Fixed in `main.py`. That's one AttributeError found and fixed by actually
running it on hardware; there was no way to be sure it was the only one.

Run `make check` (`mpremote run test/check_lvgl_api.py`) before `main.py` —
it builds one of every widget/indev/group call this project makes and prints
OK/FAIL for each, all in one pass, instead of discovering them one
flash-cycle at a time. If something FAILs,
the fix is almost always one of:
- swap `lv.foo_bar(x, ...)` for `x.bar(...)` (or the reverse) — this project's
  guess was "single existing-instance argument → method, everything else
  (constructors, utilities, globals) → bare `lv.` function", which held for
  everything except `group_set_default`
- check the exact enum path (`lv.EVENT.VALUE_CHANGED` vs. some other nesting)
- as a last resort, `print(dir(lv))` / `print(dir(some_object))` over the REPL
  and compare against what the code expects

## Not hardware-verified

No physical CrowPanel, a live AirCon BLE peripheral, or a built
lvgl_micropython firmware image was available while writing the original
version of this project — everything below was found and fixed through
actual hands-on debugging on real hardware afterward.

**Confirmed working:**
- The full LVGL widget/style/group/indev API surface `check_lvgl_api.py`
  exercises, including two real corrections it found:
  `lv.group_set_default` is actually `group.set_default()`, and
  `lv.ANIM`/`lv.ROLLER_MODE` don't exist as nested enum classes at all
  (worked around with plain `0` in `screens/connect.py` — both `LV_ANIM_OFF`
  and `LV_ROLLER_MODE_NORMAL` are long-standing `0` upstream).
- `SPI.Bus`/`lcd_bus.SPIBus`/`gc9a01.GC9A01(...)` construction and the
  GC9A01 init command sequence itself (matches the known-working
  Arduino/LGFX reference almost line-for-line).
- Deferring `import aircon_ble` (and transitively `aioble`/`bluetooth`)
  until inside `main()`, after display/splash setup, rather than at module
  level. Importing it early left measurably less heap around and was
  strongly correlated with `lv.group_create()` — a trivial, argument-free
  call — failing with a huge, non-deterministic garbage allocation size
  (memory corruption/fragmentation from BLE stack init, not a legitimate
  allocation request). Also matches the original ask better: BLE now isn't
  touched until after the splash shows.
- **The display now renders correctly**, including the startup splash
  image. Found and fixed seven distinct, stacked issues to get there — see
  below. Each was necessary; none alone was sufficient, which made this the
  single hardest part of this port to debug (mostly silent failures, no
  exceptions, no logs).

**Display: seven issues found and fixed, one layer at a time:**

1. **No hardware reset.** `display_driver_framework.py`'s `DisplayDriver`
   never calls `.reset()` on the panel automatically — not in `__init__`,
   not in `_init_bus()`. Skipping it left the RST pin sitting at whatever
   `__init__` set it to and never releasing it — GC9A01's reset line is
   active-low, so the panel sat in permanent hardware reset, silently
   ignoring the entire (otherwise-correct) init command sequence. Fixed:
   explicit `reset_state=gc9a01.STATE_LOW` plus an explicit `display.reset()`
   call between construction and `.init()`.
2. **Missing board power-enable GPIOs.** Elecrow's own Arduino reference
   sketch for this board sets two GPIOs (pins 1 and 2 — not in the
   documented pinout table at all, only found in their example source) to
   output HIGH before touching the display or touch hardware at all,
   labeled only "power pin, output current." Undocumented purpose, but
   plausibly gates power to a shared rail feeding the display logic and/or
   backlight boost converter. Added as `hal.init_board_power()`, called
   first, before any display/touch/LVGL setup. Same source confirmed the
   power-status LED (pin 40) is active-low; turned on here too, as an
   independent "board is alive" signal separate from the display.
3. **Wrong color channel order.** A solid-red test fill rendered as solid
   blue — a clean R/B swap, not a garbled/scrambled color (which a byte-
   endianness issue would look like). Fixed: `color_byte_order=gc9a01.BYTE_ORDER_BGR`,
   matching the Arduino reference's `cfg.rgb_order = false` (BGR, in
   LovyanGFX's convention).
4. **LVGL's tick never advanced.** Nothing anywhere called `lv.tick_inc()`.
   Without it, `lv.timer_handler()` always sees zero elapsed time and never
   considers its periodic refresh due — except once, since LVGL forces an
   initial full render when a display/screen is first created regardless of
   the timer path. Symptom: exactly one successful render, ever, then
   permanently nothing, no matter what was drawn or how long
   `lv.timer_handler()` was pumped for — independent of the other issues
   here, and the one that actually explains "nothing redraws after the
   first thing." Fixed: `lv.tick_inc(ms)` before every `lv.timer_handler()`
   call, including in the main loop (which had the same gap and would have
   hit the same wall once past the splash).
5. **Buffer-size off-by-one in the vendored framework.** Once buffers were
   switched from the driver's auto-sized 1/10th-of-a-frame partial buffer
   (which visibly tore/wiped across ~10 separate flushes) to a single
   exact-full-frame buffer, a ~1-2px sliver at the bottom/right edge never
   got drawn. `display_driver_framework.py`'s `init()` has a one-time setup
   fast path that only triggers when the buffer size exactly equals the
   full frame size, and it computes the RAMWR address window as
   `x1 + display_width` / `y1 + display_height` — exclusive-style bounds,
   not the inclusive 0..239 GC9A01 actually wants. Real bug in the vendored
   framework, not ours to patch. Worked around in `hal.py`: buffers sized at
   *half* the full frame instead of exactly full — still just 2 flushes to
   cover the whole screen (vs. the original 10), but avoids the exact-size
   match that triggers the buggy fast path, so every flush goes through the
   ordinary per-area addressing in `_flush_cb()` instead (which uses LVGL's
   own already-inclusive area rect).
6. **Backlight sequencing.** GC9A01's init sequence (`_gc9a01_init.py`)
   never clears the screen itself — it just configures registers and turns
   the panel on — so whatever was already in GRAM from a previous run
   stayed visible (as random color noise) until the first real draw.
   `hal.hal_init_display()` no longer turns the backlight on itself;
   `main.py` clears to black first, flushes it for real (several pumps, one
   wasn't reliably enough), and only then turns the backlight on.
7. **The splash image needed a completely different loading approach.**
   Passing the file path to `img.set_src()` (LVGL's normal, documented way
   to load an image) silently produced nothing — no exception, and neither
   an unprefixed path nor `"S:"`/`"A:"` drive-letter prefixes made a
   difference, so it wasn't a filesystem-path issue (a plain Python
   `open()` read on the same path worked fine and returned byte-correct
   content). The file-based image decoder just doesn't render this raw
   binary format on this build, for reasons that never surfaced as a
   catchable error. Fixed in `main.py`'s `_show_splash()`: construct an
   `lv.image_dsc_t` directly from the image's raw RGB565 pixel bytes
   (stripping the 12-byte `LVGLImage.py` header) and pass that object to
   `set_src()` instead of the file path, bypassing the file/decoder path
   entirely.
8. **Touch — `cst816s.CST816S(device, ...)`'s `device` argument.** Three
   attempts before landing on the real answer: a parallel `i2c_bus.I2CBus`
   module (confirmed not to exist, clean `ImportError`); passing a plain
   `machine.I2C` instance directly (this build's `machine.I2C` *does* have
   a `.write()` method, unlike stock MicroPython, so that wasn't an
   `AttributeError` — but the specific combined write+read operation
   `cst816s.py`'s `write_readinto()` call needed raised
   `OSError: I2C operation not supported`, a driver/hardware-level
   rejection). Fixed: `hal.py`'s `_I2CRegDevice` adapter class, translating
   `cst816s.py`'s two calls (which always follow the shape "register
   address, then optionally read/write associated data") into
   `machine.I2C`'s own `writeto_mem()`/`readfrom_mem_into()` convenience
   methods — implemented as two separate, well-supported transactions
   instead of whichever single combined one wasn't. Also settled along the
   way: the real touch chip on this board is **CST816D**, not CST816S
   (`cst816s` is just the option name in lvgl_micropython's `INDEV=` list —
   there's no separate `cst816d`), confirmed compatible both by
   cross-referencing chip IDs against ESPHome's `cst816` component (which
   explicitly documents one driver covering the whole CST816 family) and,
   conclusively, by the real chip printing `Chip ID: 0xb6` on boot — exactly
   CST816D's ID. Touch is now fully working, confirmed with live on-screen
   coordinates and press/release feedback.

**Still open:**
1. **`aioble` API surface** — targets the central-role connect/subscribe flow
   documented in micropython-lib's `aioble` README/examples at the time of
   writing; a newer release may have renamed something. Confirmed working
   end-to-end against both a live AirCon controller and `../aircon-sim/`.
   One narrower piece is still unverified: `scan_for_aircons()`'s
   `result.device.addr`-based dedup of non-matching devices (for its "N
   other devices found" count) — falls back to an undeduplicated count if
   that attribute isn't there.
2. **BLE single-central contention** — same accepted tradeoff as the C++
   version: if the AirCon controller only accepts one BLE central connection,
   this panel and the Pi's `aircon.Client` can't both be connected at once.
3. **Two simultaneous central connections** (added with heater support) —
   holding two independent central connections open at once (one to the
   AirCon controller, one to the heater) does work on real hardware — but
   *establishing* them at the same time doesn't always: confirmed a
   connect() racing the other client's scan() raises `OSError 16`
   ("radio busy with another GAP procedure", presumably), which
   `ble_shared.radio_lock` now specifically serializes against (see that
   file's own docstring) rather than just scan-vs-scan the way it
   originally did. Both clients' `run()` loops also now catch this (and
   anything else `_find_device()`/`_connect_and_run()` might raise) around
   the whole scan+connect attempt, not just the connect half, after an
   earlier version let an uncaught scan failure permanently kill that
   client's reconnect loop for the rest of the boot — if you ever see an
   "unretrieved task exception" traceback naming `_find_device`, that's
   the bug this was; it shouldn't happen anymore, but if it does, that's
   the first thing to suspect.
4. **The heater protocol itself** — entirely reconstructed from decompiling
   the vendor's Android app (no vendor documentation exists at all), never
   tested against a live unit. See `../../scratch/airheater-ble-protocol.md`
   and `heater_ble_config.py`'s module docstring for exactly what's
   confirmed vs. a documented best guess (frame format and UUIDs are
   fairly confident; the exact `run_mode` numbering, heat-level range, and
   whether your specific unit even speaks this exact frame version rather
   than an older one are not).
5. **Heater password detection** (added alongside password entry support)
   — whether a unit requires a password is inferred from whether
   `CMD_HANDSHAKE` comes back explicitly rejected, not from any documented
   "this unit is password-protected" flag (none is known to exist) — see
   `heater_ble.py`'s module docstring, point 3, for the full heuristic and
   its deliberately-asymmetric handling of "no response at all". Tested
   against `../heater-sim/` (its `--password` flag), not yet against a
   real password-protected unit.
6. **`aioble.DeviceConnection.disconnect()`** (added for Info's "change
   device" buttons) — every other aioble call site in `aircon_ble.py`/
   `heater_ble.py` was confirmed against real hardware before this;
   `disconnect()` is the one exception, needed to force an already-live
   connection to drop when the user picks a *different* device rather than
   only from a nothing-connected-yet state (the only case the original
   pairing flow ever needed). Matches aioble's documented central-role API
   shape, not independently verified. If picking a new device from Info
   doesn't actually drop the old connection, see
   `AirconClient`/`HeaterClient._disconnect_current()`.

## Screens

| Module | Screen(s) |
| --- | --- |
| `screens/__init__.py` | `App` — owns which screen is showing, dispatches knob input, orchestrates the + shaped tileview grid. |
| `screens/widgets.py` | Shared LVGL widget-construction helpers used by more than one screen. |
| `screens/home.py` | Home. |
| `screens/connect.py` | Connect (AirCon and Heater both). |
| `screens/disconnected.py` | Disconnected (AirCon and Heater both). |
| `screens/heater_password.py` | Heater password entry — see "Connect / Disconnected screens" below. |
| `screens/info.py` | Info ("about" + device status/re-pairing). |

On power-up, a full-screen splash (`images/splash.bin`, converted from
`aircon.png`) shows for ~2 seconds before anything else happens — including
before touch/encoder/BLE init — so there's visible proof the panel and
display path are alive even if something further into startup fails. Then:
an `lv.tileview` arranged in a + shaped grid around the Home tile, navigated
by touch swipes (no knob push needed) instead of the C++ version's linear
tile strip:

- **Home** (center) — the only screen with real controls right now:
  - An outer dial gauge rings almost the whole panel edge. It's
    knob-adjustable: off→low/medium/high (not wrapping) when mode is
    off/fan/cool, heat level (not wrapping, `heater_ble_config.HEAT_LEVEL_MIN`/
    `MAX`) when mode is heat, or setpoint (bounded by the controller's
    BLE-reported `setpoint_min`/`setpoint_max` settings) when mode is auto.
    Cycling the mode button through all five (off/fan/cool/heat/auto) is
    the only way in or out of "heat" — see `screens/home.py`'s `MODES`
    comment for why this fifth mode is tracked locally on the panel rather
    than through the AirCon controller's own BLE mode characteristic (it
    has no slot for it). Auto mode also continuously compares the setpoint
    against current cabin temp every refresh and turns the heater on/off
    (in its own thermostat mode, targeting the same setpoint) whenever
    heating -- not cooling -- is what's actually needed; see
    `screens/home.py`'s `_update_auto_heat()`.
  - Inside the gauge, a 3-row grid: current cabin temp; mode and
    recirculation cells (act as buttons — tap-and-press to cycle through
    their options, see "Interaction model" below); setpoint (auto mode) or
    heat level (heat mode) and current fan speed. The bottom row's
    background turns dark blue while the compressor is running, or warm
    dark-orange while the heater is on (either from heat mode or auto
    mode's heating branch).
  - Swipe down → History, up → Settings, right → Temps.
- **History** (swipe down from Home, up to return) — placeholder.
- **Settings** (swipe up from Home, down to return) — placeholder. (The
  previous per-setting slider list moved out of the way for this — not
  gone, just not rebuilt into the new layout yet.)
- **Temps** (swipe right from Home, left to return) — placeholder. (Same
  deal: the previous cabin/blower/exhaust/baggage/tail readout moved out of
  the way, not gone.)
- **Info** (swipe left from Home, right to return) — app/controller
  identification, whatever error the controller last reported, and two
  buttons (same touch+knob-button "click" as Home's mode/recirc cells --
  see "Interaction model" below) showing which AirCon and which heater are
  currently configured (device name, or "Not configured") and whether each
  is connected right now. Clicking either reopens that device's Connect
  screen (`screens.App.request_reconnect()`) so a different one can be
  picked, even long after initial setup -- unlike the AirCon's original
  first-boot-only Connect screen, this is a real, repeatable "change
  device" control. Picking a new device disconnects whatever was
  previously connected first (`aircon_ble.AirconClient.set_device_name()`/
  `heater_ble.HeaterClient.set_device_name()`, both extended for this --
  see their own docstrings and the "Not hardware-verified" note below);
  clicking the Heater button in particular also un-skips heater pairing if
  it had previously been declined, since opening that screen is itself
  choosing to reconsider that decision. Home becomes reachable again once
  the newly-picked device connects (and, for a newly-picked heater, clears
  its own password check if it has one -- the same screens you'd see
  during initial pairing).

### Connect / Disconnected screens

Not part of the swipeable + grid — `screens.App` shows one of these
full-screen in place of the tileview instead. `screens.connect.ConnectTile`/
`screens.disconnected.DisconnectedTile` are generic now (constructed once
per device kind, told apart by a `label` and, for Connect, which client's
scan method to call) — `App` owns two independent pairs,
`aircon_connect_tile`/`aircon_disconnected_tile` and
`heater_connect_tile`/`heater_disconnected_tile`, sequenced one after the
other and gating Home very differently:

- **AirCon (mandatory, unchanged)** — based on whether a device has been
  picked (`panel_settings.get_aircon_device_name()`) and whether
  `aircon_ble.AirconClient` currently has a live connection
  (`client.state.connected`). Home is unreachable without one connected,
  full stop, exactly as before this file had any notion of a second
  device.
- **Heater (optional, asked once)** — shown, at most once per boot, right
  after the AirCon connects, and possibly spanning up to three screens in
  sequence before Home: pick a device (or skip), wait for it to connect
  (and its password handshake, if any, to resolve — see "Password screen"
  below), then -- only if that handshake came back rejected -- enter a
  password. If no heater has ever been picked *and* the user hasn't
  explicitly skipped pairing one (`panel_settings.get_heater_skipped()`),
  `heater_connect_tile` appears with a synthetic "Skip — No Heater" entry
  at the top of its roller (`screens.ConnectTile`'s `allow_skip`/
  `on_skip`) alongside any heaters found — picking Skip persists that
  choice and is never asked again. Picking a real heater moves to
  `heater_disconnected_tile` ("Connecting…") the same way the AirCon does,
  covering both the BLE connection itself and its handshake resolving
  (`heater_ble.HeaterState.password_required` going from `None` to a real
  `True`/`False`, usually within a few seconds) — up to
  `screens.App._HEATER_CONNECT_TIMEOUT_MS` (15s) combined, past which
  `App` gives up waiting and shows Home anyway (heater's own
  `HeaterClient.run()` reconnect loop keeps retrying in the background
  regardless). If the handshake explicitly rejected, `heater_password_tile`
  appears next instead of Home — see "Password screen" below. Once this
  whole sequence resolves one way or another (skip, successful connect
  with no password needed, a correct password entered, or either give-up
  timeout), `screens.App._heater_setup_done` latches permanently for the
  rest of this boot — the heater is never gated on again, and a later drop
  (or a later rejected handshake, e.g. if the unit's PIN gets changed on
  the device itself) just means `screens/home.py`'s "heat" mode / auto
  mode's heating branch quietly do nothing rather than a full-screen
  takeover.

Both Connect screens work identically otherwise: a knob-driven picker.
`AirconClient.scan_for_aircons()` scans for any BLE peripheral advertising
the AirCon service UUID (`aircon_ble_config.AIRCON_SERVICE_UUID`) — not by
name, since each physical controller can have its own custom
`BLE_DEVICE_NAME` (`../aircon/config.py`'s `set_ble_name()`).
`HeaterClient.scan_for_heaters()` instead matches on advertised name prefix
(`heater_ble_config.NAME_PREFIX`), since the heater has no service UUID of
its own to filter on (see that config file's module docstring) — but
returns the exact same `(found, other_count)` shape, so `ConnectTile`
doesn't need to know which kind of client it's driving. Until a real match
turns up, `ConnectTile` shows a spinner and "N other devices found" instead
of a roller with an unselectable "(none found)" entry (unless `allow_skip`
is set, in which case the roller — just its skip entry — shows immediately
instead of making an optional device wait through a scan first) —
reassurance that the radio itself is working, not just silently stuck at
zero. `ConnectTile` keeps re-scanning in a loop for as long as its screen
stays up (`_scan_loop()`), merging each pass into the running list rather
than clearing it, so devices that show up late still appear without
backing out and back in. Turning the knob moves the highlighted entry;
pressing the button picks it, persisting the choice
(`*Client.set_device_name()`) and moving to that device's Disconnected
("Connecting…") screen while the client attempts the connection.

**Disconnected** — a thick red X spanning the panel's corners on a black
background, with white "Connecting…"/"Disconnected [label]" text (on its
own red background box) centered on top (the AirCon's `label` is `""`,
reproducing the original bare "Connecting…"/"Disconnected" text exactly —
only the heater's says "Connecting… Heater"/"Disconnected Heater").
Says "Connecting…" until that device's BLE connection has been established
at least once this boot, "Disconnected" for any drop after that — tracked
independently per device (`screens.App._ever_connected` for the AirCon;
the heater's `heater_disconnected_tile` is always shown with
`ever_connected=False`, since — per the one-time-gate design above — it's
now structurally impossible for that screen to ever be shown again after
the heater's first successful connect of a boot, so it never has anything
but "Connecting…" to say). Pressing the knob on either Disconnected screen
goes to that same device's Connect screen, to pick a different one.

**Password screen** (`screens.heater_password.HeaterPasswordTile`, heater
only — the AirCon controller has no equivalent) — some physical heater
units apparently require a 4-digit PIN before accepting control commands;
whether yours does is detected, not configured, by sending a handshake
(`heater_ble_config.CMD_HANDSHAKE`) after every fresh connection and
reading whether it comes back explicitly rejected (see `heater_ble.py`'s
module docstring, point 3, for exactly what "detected" means here — it's a
best-effort heuristic reconstructed from a decompiled app, not a confirmed
protocol feature, and units that simply never answer this command at all
are deliberately read as "no password needed" rather than mistaken for
password-protected ones). This screen only ever appears after an explicit
rejection. Four digit cells plus a "Done" cell, one focused at a time
(purple fill, same `theme.COLOR_ACTIVE` used elsewhere for "actively
engaged") — turning the knob changes the focused digit's value (0-9,
wrapping); pressing the knob advances focus to the next digit, or, once
focus reaches "Done", submits the 4 digits as a password
(`heater_ble.HeaterClient.set_password()`, which also persists it via
`panel_settings.set_heater_password()` for future boots). A wrong
submission resets to "0000" with an "Incorrect, try again" status line
rather than leaving the previous (wrong) digits sitting there. This screen
has no dedicated Skip control of its own (a 6th cycle position past "Done"
didn't compose cleanly with "pressing while on Done submits" — see that
module's own docstring) — instead, `App` gives it its own generous
give-up timeout (`screens.App._HEATER_PASSWORD_TIMEOUT_MS`, 90s, separate
from `_HEATER_CONNECT_TIMEOUT_MS` since entering a PIN is an active user
task, not a passive wait for hardware) after which Home becomes reachable
anyway — deliberately **not** persisted via
`panel_settings.set_heater_skipped()` the way the Connect screen's own
Skip is, so a give-up here is offered again next boot rather than silenced
forever (see that function's own docstring for the reasoning).

### Interaction model

Different from LVGL's usual `LV_INDEV_TYPE_ENCODER` convention (turn to
move focus between group members, press to toggle "edit mode") — this
panel's knob always drives whichever control is "current" on the active
screen (nothing on the placeholder screens), and the touchscreen and knob's
push-button are mechanically coupled (pressing down on the screen is what
presses the button underneath, so you can't press one without touching the
screen too):

- Turning the knob adjusts the Home screen's gauge value (see above); does
  nothing on History/Settings/Temps/Info.
- A touch tap alone never does anything.
- A "click" on the mode/recirc cells (Home) or the AirCon/Heater device
  buttons (Info) needs a touch point on that cell *and* the knob's button
  down at some point during the touch — see `screens._wire_button()`, used
  by both.
- Swipes need only touch (no button) and move between tiles via the
  tileview's own gesture handling.

Connect, Disconnected, and the heater password screen are simpler and
purely knob-driven (no touch) — they aren't sharing panel space with any
swipe gesture, so there's no touch/swipe ambiguity to resolve there the way
`_wire_button()` handles for Home. The knob's button press is edge-detected
once per screen in `screens.App.poll_input()` rather than gated on touch.
