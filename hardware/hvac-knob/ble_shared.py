"""The one thing genuinely shared between aircon_ble.py and heater_ble.py --
everything else about the two protocols (UUIDs, frame format, state shape)
is independent, deliberately not factored together (see
aircon_ble_config.py's module docstring).

radio_lock guards every aioble.scan() call across both clients' background
reconnect loops (AirconClient._find_device()/HeaterClient._find_device())
and both Connect screens' device pickers (AirconClient.scan_for_aircons(),
HeaterClient.scan_for_heaters()) -- aioble likely can't run two scans at
once (confirmed true for two overlapping calls *within* aircon_ble.py
before this existed as its own module). Also held across each client's
own device.connect() call (_connect_and_run(), both files) -- NOT just
scan-vs-scan: confirmed on real hardware (both clients starting up at once
at boot) that one client's connect() racing the other's scan() raises
OSError 16 from aioble's scan __aenter__, which is presumably the same
underlying "the radio is already busy with another GAP procedure"
constraint extended to connecting, not just scanning. Deliberately NOT
held for the rest of a connection's lifetime once established (just long
enough to get from "start connecting" to "connected or failed") --
holding it that long would block the other client's scanning for as long
as this one stays connected, which isn't needed (an established
connection's normal traffic doesn't appear to contend with the other
client's scan the way actively connecting or scanning does) and would
defeat the "heater never blocks the AirCon" design goal if the AirCon
client were the one left waiting.

Even with this, both clients' run() loops still need their own defensive
try/except around the whole scan+connect attempt (not just the connect
part) -- this lock reduces how often the underlying radio operation
collides, it doesn't guarantee it never will, and letting an occasional
OSError (16 or otherwise) escape run() entirely kills that client's
reconnect loop for the rest of the boot rather than just failing the one
attempt.
"""

import asyncio

radio_lock = asyncio.Lock()

# Shared scan timing -- same values both clients' scan calls already used
# independently before this module existed. Not a hard requirement that
# they match, just no reason found yet for them to differ.
SCAN_INTERVAL_US = 30000
SCAN_WINDOW_US = 30000
