"""Persists the panel's own settings -- which AirCon controller and which
heater to connect to -- to flash, independent of either device's own
settings (the AirCon's live in aircon_ble.AirconState.settings, synced over
BLE from its 0006 settings characteristic; the heater has no equivalent).

Same minimal try/except-on-load pattern as ../aircon/storage.py.
"""

import json

_FILE = "/panel_settings.json"


def _load():
    try:
        with open(_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _update(key, value):
    data = _load()
    data[key] = value
    with open(_FILE, "w") as f:
        json.dump(data, f)


def get_aircon_device_name():
    """Returns the previously-picked AirCon's BLE device name, or "" if
    none has been chosen yet. main.py/screens.App treat "" as "go straight
    to the Connect screen on startup" -- see screens.App.__init__.
    """
    return _load().get("aircon_device_name", "")


def set_aircon_device_name(name):
    _update("aircon_device_name", name)


def get_heater_device_name():
    """Returns the previously-picked heater's BLE device name, or "" if
    none has been chosen (either never asked, or explicitly skipped -- see
    get_heater_skipped()). Unlike the AirCon, "" here does NOT necessarily
    mean "show the Connect screen" -- screens.App only shows the heater's
    Connect screen once, the first time Home would otherwise become
    reachable, and never again once that one-time decision (pick a device,
    or skip) has been made -- see screens/__init__.py's module docstring.
    """
    return _load().get("heater_device_name", "")


def set_heater_device_name(name):
    _update("heater_device_name", name)


def get_heater_skipped():
    """True once the user has explicitly chosen "no heater" on the Connect
    screen (screens.ConnectTile's skip entry, only offered when pairing a
    heater -- see its allow_skip param) rather than ever picking one.

    NOT set by giving up on the password screen (see screens/__init__.py's
    App._HEATER_PASSWORD_TIMEOUT_MS) -- that give-up is deliberately
    per-boot only, not persisted here, since "don't have the PIN handy
    right now" is likely temporary in a way "I don't have a heater" isn't;
    the next boot will offer the password screen again rather than staying
    silenced forever.

    Distinct from get_heater_device_name() == "" so screens.App can tell
    "never asked yet" (show Connect) apart from "asked, and the answer was
    no" (never show the Connect screen again).
    """
    return bool(_load().get("heater_skipped", False))


def set_heater_skipped(skipped):
    _update("heater_skipped", skipped)


def get_heater_password():
    """Returns the previously-entered heater password as an int 0-9999, or
    None if one has never been entered -- heater_ble.HeaterClient treats
    None the same as 0 when it needs an actual byte value to send (some
    heaters may not require a handshake at all, in which case this never
    gets read), so the None/0 distinction here exists only so this file's
    on-disk JSON reads sensibly ("no password on record" vs. "the
    password on record is 0000"), not because any caller branches on it.
    """
    v = _load().get("heater_password")
    return v if isinstance(v, int) else None


def set_heater_password(password):
    _update("heater_password", password)
