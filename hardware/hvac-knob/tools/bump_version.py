"""Bumps screens/info.py's KNOB_VERSION: major += 1, minor reset to 0, any
patch component dropped (e.g. "2.1.4" -> "3.0") -- run on the host by `make
install` before compiling/syncing, so every full install ships a version
bump visible on the knob's Info screen. Not tied to git/semver in any other
way -- this is purely "is what's on the device newer than last time".
"""

import pathlib
import re

_INFO_PY = pathlib.Path(__file__).resolve().parent.parent / "screens" / "info.py"
_PATTERN = re.compile(r'(KNOB_VERSION = ")(\d+)(?:\.\d+)*(")')


def main():
    text = _INFO_PY.read_text()

    def bump(m):
        major = int(m.group(2)) + 1
        return "%s%d.0%s" % (m.group(1), major, m.group(3))

    new_text, count = _PATTERN.subn(bump, text, count=1)
    if count != 1:
        raise SystemExit("bump_version: KNOB_VERSION not found in %s" % _INFO_PY)

    _INFO_PY.write_text(new_text)
    print("bump_version: %s" % _PATTERN.search(new_text).group(0))


if __name__ == "__main__":
    main()
