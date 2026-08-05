# AirCon knob — MicroPython + LVGL port

A Python port of the [CrowPanel 1.28"-HMI ESP32 Rotary Display](https://www.elecrow.com/wiki/CrowPanel_1.28inch-HMI_ESP32_Rotary_Display.html)
firmware in `../temp_knob/firmware/` (C++/Arduino/LVGL): same board, same
direct-BLE-to-the-AirCon-controller architecture, same 5 screens — but this
one uses real LVGL widgets through MicroPython's LVGL bindings instead of
either the C++ firmware's Arduino toolchain or a hand-rolled framebuf UI.
See that directory's README for the hardware/pin background; this one only
covers what's different about the Python version.

**Nothing here depends on `../temp_knob/`'s LVGL Editor project or its
component library/fonts/icons** — this is a from-scratch, self-contained
implementation of just the AirCon control UI. Text uses the
[Nasalization](../../ui/public/fonts/Nasalization.otf) font also used by the
web UI (`ui/`) — see `fonts/README.md`.

## Why not PlatformIO

PlatformIO does not support MicroPython (confirmed with a PlatformIO
maintainer's own reply in their community forum — "We currently don't
support MicroPython"). There is no `platformio.ini` here. Instead, `.vscode/`
is set up around the **MicroPico** extension (`paulober.pico-w-go`, which
despite the name has explicit experimental ESP32-S3 support) plus
`mpremote`/`esptool` tasks for what MicroPico doesn't cover: building/flashing
the custom MicroPython+LVGL firmware image itself, and installing `aioble`.

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
   under `build/`): run the **"MicroPython+LVGL: Write custom firmware"**
   task after editing the `.bin` path (and **"MicroPython: Erase flash"**
   first if updating from a previous firmware).
4. **Install `aioble`** (BLE central library — a custom LVGL build doesn't
   change the BLE side, and `aioble` still isn't bundled): run the
   **"MicroPython: Install aioble (mip)"** task.
5. **AirCon identity**: `ble_config.py` already matches the real controller
   firmware's `../aircon/config.py` (and `../aircon-sim/config.py`, the
   desktop simulator — see that directory if you want to test the panel
   without the physical AC hardware). If you ever change the device name or
   UUIDs on the real controller, update all three to match, plus the Pi's
   `.env` (`AirConConfig.DeviceName`/`ServiceUUID` in
   `server/config/config.go`) if it's connecting too.
6. Run **"MicroPico: Configure project"** from the command palette once —
   sets up MicroPython stubs/autocomplete in `.vscode/settings.json`
   (intentionally not hand-written here so it doesn't fight that command;
   this is also how you get `lvgl` autocomplete for the exact binding your
   firmware build produced).

## Build / run / debug loop

- **First, on a fresh firmware/wiring**: **"MicroPython: Check LVGL API
  surface (run this first!)"** — see "Before running main.py" below.
- **Fastest iteration**: **"MicroPython: Run main.py (mounted, no copy)"** —
  uses `mpremote mount . run main.py` to execute straight off your computer's
  filesystem over the serial link (fonts included, since `fonts/` is part of
  the mounted tree), no copying to flash. Great for edit-run-repeat; Ctrl-C
  to stop.
- **Deploy for standalone/offline running**: **"MicroPython: Sync project
  files to device"** copies the `.py` files and `fonts/` to flash so it runs
  standalone on power-up (via `main.py`'s standard MicroPython auto-run
  convention).
- **REPL** (prints, tracebacks, poking at objects live): **"MicroPython:
  REPL"**, or use MicroPico's own built-in REPL terminal/status-bar buttons —
  that's the closest thing to a "debugger" here. Neither stock MicroPython
  nor this LVGL build has a real source-level step-debugger; this project
  doesn't pretend otherwise.
- **"MicroPython: Soft reset"** restarts the board (re-running
  `boot.py`/`main.py` if the files were synced to flash).

## Files

| File | Purpose |
| --- | --- |
| `boot.py` / `main.py` | Boot-time setup, a startup splash shown before touch/encoder/BLE init, then the asyncio loop pumping `lv.timer_handler()` and periodically pushing BLE state into widgets. |
| `check_lvgl_api.py` | Standalone LVGL API surface sanity check — run this before `main.py` on a fresh setup; see "Before running main.py" below. |
| `ble_config.py` | AirCon device name / service / characteristic UUIDs — edit this first. |
| `aircon_ble.py` | `aioble`-based BLE GATT central; mirrors `server/hardware/aircon/aircon.go` and `../temp_knob/firmware/src/aircon_ble.cpp`. Unaffected by the LVGL switch — BLE and graphics are independent. |
| `hal.py` | Display/touch setup via lvgl_micropython's built-in `gc9a01`/`cst816s` drivers, plus a custom `lv.indev` for the rotary encoder. |
| `encoder.py` | Rotary encoder quadrature decode + button (no built-in driver for this exists). |
| `theme.py` | Colors (mirrors `../temp_knob/ui/globals.xml`'s tokens) and the Nasalization fonts, loaded via `lv.binfont_create()`. |
| `screens.py` | The 5 actual screens, built from real LVGL widgets (`lv.tileview`, `lv.arc`, `lv.roller`, `lv.slider`) — a close Python port of `../temp_knob/firmware/src/ui_app.cpp`. |
| `fonts/` | The converted Nasalization `.bin` fonts; see `fonts/README.md`. |
| `images/splash.bin` | Startup splash image, converted from `aircon.png` (240×240, matches the panel exactly) with LVGL's own `LVGLImage.py` converter into LVGL's native runtime-loadable binary image format — same reasoning as the fonts: doesn't depend on a PNG decoder being compiled into the firmware build. Regenerate with `python3 LVGLImage.py --ofmt BIN --cf RGB565 -o images aircon.png` then `mv images/aircon.bin images/splash.bin` (`--name` didn't actually rename the output in testing, despite the tool's own `--help` claiming it does for single-file input — hence the manual `mv`). `LVGLImage.py` lives in upstream LVGL's `scripts/` folder; needs `pip install pypng lz4`. Loaded via `lv.image_dsc_t` constructed from its raw pixel bytes, not via `img.set_src(path)` — see "Not hardware-verified" below for why. |

## If the board won't boot / never shows up as a USB serial device

This bit on real hardware once: `main.py` used to `import screens` at the
top of the file, before `lv.init()` ran. `screens.py` imports `theme.py`,
which used to call `lv.binfont_create(...)` at **module import time** —
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
recovery approach: get a **bare REPL first** (don't let `main.py` auto-run —
temporarily rename it, or interrupt with Ctrl-C fast enough after a reset if
the board does briefly enumerate), then paste `hal.py`'s and `screens.py`'s
logic in piece by piece over the REPL (`lv.init()`, then `hal.hal_init(...)`,
then one screen at a time) to find exactly which call hard-crashes rather
than raises — that boundary is almost always "something called before the
subsystem it depends on was initialized," the same shape as this bug.

## Before running main.py: check the LVGL API surface

`check_lvgl_api.py` exists because of exactly the kind of bug described in
"Not hardware-verified" below turning up for real: `main.py` first ran
successfully up through `lv.init()`, then hit
`AttributeError: 'module' object has no attribute 'group_set_default'` --
`lv_group_set_default(group)` turned out to be bound as a method
(`group.set_default()`), not a bare `lv.` function, unlike `lv.group_create()`
(no existing instance to attach a method to, since it's the constructor).
Fixed in `main.py`. That's one AttributeError found and fixed by actually
running it on hardware; there was no way to be sure it was the only one.

Run **"MicroPython: Check LVGL API surface (run this first!)"** (`mpremote
run check_lvgl_api.py`) before `main.py` — it builds one of every widget/indev/
group call this project makes and prints OK/FAIL for each, all in one pass,
instead of discovering them one flash-cycle at a time. If something FAILs,
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
  (worked around with plain `0` in `screens.py` — both `LV_ANIM_OFF` and
  `LV_ROLLER_MODE_NORMAL` are long-standing `0` upstream).
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
   writing; a newer release may have renamed something. Not yet exercised
   against a live AirCon controller or `../aircon-sim/`.
2. **BLE single-central contention** — same accepted tradeoff as the C++
   version: if the AirCon controller only accepts one BLE central connection,
   this panel and the Pi's `aircon.Client` can't both be connected at once.
3. **`theme.py`'s fonts** (`lv.binfont_create()`) — never independently
   verified the way the splash image was. Not raising is no longer trusted
   as proof of success on this build (see finding 7 above) — worth watching
   for once `screens.py`'s actual text-bearing widgets are reachable and
   visible on the panel.

## Screens

On power-up, a full-screen splash (`images/splash.bin`, converted from
`aircon.png`) shows for ~2 seconds before anything else happens — including
before touch/encoder/BLE init — so there's visible proof the panel and
display path are alive even if something further into startup fails. Then:
same control surface and interaction model as the C++ version — an
`lv.tileview` of tiles (swipe with touch to move between them) sharing one
`lv.group` for the rotary encoder (turn to move focus / adjust the focused
control when in "edit" mode, press to toggle edit mode — LVGL's standard
`LV_INDEV_TYPE_ENCODER` convention):

1. **Home** — setpoint (arc, knob-adjustable), mode/fan/compressor summary,
   current cabin temp, connection status.
2. **Mode / Fan** — mode (off/fan/auto/cool) and fan speed (low/medium/high)
   rollers.
3. **Circulation** — recirculate/fresh-air roller.
4. **Settings** — one slider per key the controller reports in its settings
   map (dynamic, rebuilt live if the key set changes), range approximated as
   ±10 around the controller's compiled-in default.
5. **Status** — cabin/blower/exhaust/baggage/tail temperatures and any error
   string from the controller.
