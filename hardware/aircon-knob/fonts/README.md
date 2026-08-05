# Fonts

`nasalization_16.bin` and `nasalization_34.bin` are the
[Nasalization](../../../ui/public/fonts/Nasalization.otf) font (also used by
the web UI, `ui/`), converted to LVGL's runtime-loadable binary font format
with [`lv_font_conv`](https://github.com/lvgl/lv_font_conv) so they can be
loaded from the filesystem at runtime (`theme.py`'s `lv.binfont_create(...)`
calls) instead of needing to be compiled into the firmware.

Regenerate (or add a size) with:

```bash
npx lv_font_conv \
  --font ../../../ui/public/fonts/Nasalization.otf \
  --size 16 --bpp 4 --format bin \
  -r 0x20-0x7E -r 0xB0 \
  -o nasalization_16.bin --lv-font-name nasalization_16
```

`-r 0x20-0x7E` is printable ASCII; `-r 0xB0` adds the ° (degree) glyph used
in temperature readouts. `--bpp 4` antialiases; drop to `2` or `1` if flash
space is tight. These two files must be synced to the device alongside the
`.py` files (see the root README's "Sync project files" task) -- LVGL loads
them from the device's filesystem at `theme.py` import time, not from flash
compiled in.
