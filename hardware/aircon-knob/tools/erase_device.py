"""Erases everything on the device's flash filesystem except _KEEP, driven
entirely from the host via `mpremote fs ls`/`rm`

Keeps panel_settings.json: the panel's own persisted BLE device pairing, unrelated to code and not something a full reinstall should force the user to redo.
Keeps lib/: where `make install-aioble` (mpremote mip install) puts aioble -- not something `install` provisions itself, so erasing it would leave the device unable to import aioble until someone re-ran that separately.
"""

import subprocess
import sys

_KEEP = {"panel_settings.json", "lib"}  # lib/ is where `make install-aioble` (mpremote mip install) puts aioble


def main():
    mpremote = sys.argv[1] if len(sys.argv) > 1 else "mpremote"

    # --no-verbose: without it, `ls` also prints a "ls :" header line ahead
    # of the actual listing (see mpremote's own commands.do_filesystem()),
    # which would otherwise need filtering out here too.
    out = subprocess.run(
        [mpremote, "fs", "ls", "--no-verbose", ":"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    names = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # ls prints "{:12} {}{}".format(size, name, "/" if dir else "")
        # (mpremote's own do_filesystem()) -- the trailing "/" marks a
        # directory but isn't part of the real name.
        _size, name = line.split(None, 1)
        names.append(name.rstrip("/"))

    to_remove = [n for n in names if n not in _KEEP]
    if not to_remove:
        print("erase_device: nothing to remove")
        return

    subprocess.run([mpremote, "fs", "rm", "-r"] + to_remove, check=True)
    print("erase_device: removed %s" % ", ".join(to_remove))


if __name__ == "__main__":
    main()
