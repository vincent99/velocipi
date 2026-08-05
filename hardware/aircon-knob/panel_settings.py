"""Persists the panel's own settings -- currently just which AirCon
controller to connect to -- to flash, independent of the AirCon
controller's own settings (which live in aircon_ble.AirconState.settings,
synced over BLE from its 0006 settings characteristic).

Same minimal try/except-on-load pattern as ../aircon/storage.py.
"""

import json

_FILE = "/panel_settings.json"


def get_aircon_device_name():
    """Returns the previously-picked AirCon's BLE device name, or "" if
    none has been chosen yet. main.py/screens.App treat "" as "go straight
    to the Connect screen on startup" -- see screens.App.__init__.
    """
    try:
        with open(_FILE) as f:
            return json.load(f).get("aircon_device_name", "")
    except Exception:
        return ""


def set_aircon_device_name(name):
    with open(_FILE, "w") as f:
        json.dump({"aircon_device_name": name}, f)
