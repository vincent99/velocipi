"""Persist and restore AC settings to/from flash."""

import json
import config

_KEYS = (
    'mode', 'fan', 'setpoint', 'circulation', 'delta',
    'fan_high_thresh', 'fan_med_thresh', 'fan_change_interval',
    'auto_loop_interval', 'temp_read_interval', 'ble_notify', 'ble_device_name',
)


def load():
    """Return a dict of saved values; empty dict if file is missing or corrupt."""
    try:
        with open(config.STORAGE_FILE) as f:
            data = json.load(f)
        return {k: data[k] for k in _KEYS if k in data}
    except Exception:
        return {}


def save(state):
    """Write only the persisted keys from the controller state object."""
    data = {k: getattr(state, k) for k in _KEYS}
    with open(config.STORAGE_FILE, 'w') as f:
        json.dump(data, f)
