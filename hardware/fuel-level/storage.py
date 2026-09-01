"""Persist fuel-level calibration to/from flash -- same shape as
../aircon/storage.py, just for this project's own two fields.
"""

import json

import config

_KEYS = ("cal_zero_v", "cal_full_v")


def load():
    """Return a dict of saved values; empty dict if the file is missing or
    corrupt (e.g. first boot ever, or a power loss mid-write) -- callers
    fall back to config.DEFAULT_CAL_ZERO_V/FULL_V for whatever's absent.
    """
    try:
        with open(config.STORAGE_FILE) as f:
            data = json.load(f)
        return {k: data[k] for k in _KEYS if k in data}
    except Exception:
        return {}


def save(sensor):
    """Write both calibration fields from a fuel_sensor.FuelSensor instance
    -- always both, even though set_cal_zero()/set_cal_full() only ever
    change one at a time, so the file's shape never depends on which
    setter was called most recently.
    """
    data = {k: getattr(sensor, k) for k in _KEYS}
    with open(config.STORAGE_FILE, "w") as f:
        json.dump(data, f)
