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

canonical_device()/discovery_lock_for() below are the second thing shared
between the two clients: support for AirconClient and HeaterClient
resolving to the *same physical BLE address* -- only ever expected against
../hvac-sim/'s combined single-peripheral simulator (a real AirCon and a
real heater are always two separate physical devices with separate
addresses, so this path is inert in production), needed because BLE only
supports one link-layer connection per peer address at all -- confirmed on
real hardware that a second, independent device.connect() to an address
the other client already holds fails outright (OSError 5 EIO), not just
contends for the radio the way scan-vs-scan/connect-vs-scan do (which
radio_lock above already covers). See canonical_device()'s own docstring
for the actual mechanism (reusing aioble's own Device.connect() caching,
not a from-scratch connection wrapper).
"""

import asyncio
import struct

import bluetooth

radio_lock = asyncio.Lock()

# Shared scan timing -- same values both clients' scan calls already used
# independently before this module existed. Not a hard requirement that
# they match, just no reason found yet for them to differ.
SCAN_INTERVAL_US = 30000
SCAN_WINDOW_US = 30000

# addr_type,addr -> the canonical aioble.Device instance for that address --
# see canonical_device().
_devices = {}
# Same key shape -> asyncio.Lock() -- see discovery_lock_for().
_discovery_locks = {}


def _addr_key(device):
    return (device.addr_type, bytes(device.addr))


def canonical_device(device):
    """Returns the single aioble.Device instance AirconClient and
    HeaterClient should both use for `device`'s address, registering
    `device` itself as that instance the first time this address is seen
    (by either client) and returning the already-registered one on every
    call after that, including from the *other* client.

    Needed because aioble.Device.connect() only skips re-connecting ("if
    self._connection: return self._connection" -- see aioble's own
    device.py) when called on the exact same Python object twice: Device
    defines __eq__/__hash__ by address, but that doesn't make two
    separately-scanned Device instances for the same address share
    anything at the instance-attribute level, and confirmed by reading
    aioble's own central.py, each client's own aioble.scan() session
    (_find_device(), scan_for_aircons()/scan_for_heaters()) always
    creates a brand new Device object per address it sees -- its
    ScanResult cache is private to that one scan() call, never shared
    across separate scan sessions, let alone across the two different
    client classes.

    Only ever called from each client's own _find_device() (the
    connection-establishing scan) -- scan_for_aircons()/
    scan_for_heaters() (the Connect screen's picker scans) don't need
    this, since screens.ConnectTile only ever uses their results' *name*
    (client.set_device_name(name)), never the Device object itself; the
    actual connect always goes through a fresh _find_device() scan later.

    Routing both clients' _find_device() through this means that once
    either one has connected, the other resolving to the same address
    gets back that exact same (already-connected) Device instance, so its
    own device.connect() call sees self._connection already populated and
    returns it directly -- no second connect attempt (and no OSError 5
    EIO, see this module's own docstring) -- letting both clients
    independently discover their own GATT services and subscribe to their
    own characteristics over what is, underneath, one shared link-layer
    connection (see discovery_lock_for() for the one thing that still
    needs to be serialized between them when this happens).

    No expiry/cleanup needed: aioble itself resets a Device's own
    self._connection back to None on disconnect (device.py's
    DeviceConnection.device_task()), so a stale-but-cached entry here
    still correctly reconnects fresh on its own next use regardless of
    how long it's sat in this dict.
    """
    key = _addr_key(device)
    existing = _devices.get(key)
    if existing is not None:
        return existing
    _devices[key] = device
    return device


def discovery_lock_for(device):
    """One asyncio.Lock() per address, for AirconClient/HeaterClient
    _connect_and_run() to hold around their own GATT discovery
    (service()/characteristic() lookups) and subscribe() calls --
    confirmed elsewhere in this codebase (aircon_ble.py's own
    _connect_and_run() comment) that aioble only allows one discovery in
    flight per connection at a time; two clients doing discovery
    concurrently on a connection they're sharing (see canonical_device())
    would collide with "ValueError: Discovery in progress" the exact same
    way aircon_ble.py's own 7 characteristics already needed sequential
    (not concurrent) subscription within just that one client. Uncontended
    (so effectively a no-op) whenever the two clients aren't sharing an
    address, which is every real-hardware case.
    """
    key = _addr_key(device)
    lock = _discovery_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _discovery_locks[key] = lock
    return lock


def mtu_exchange_needed(connection):
    """True the first time this is checked for a given `connection` object,
    False on every call after that -- lets AirconClient/HeaterClient each
    trigger at most one MTU exchange request between them on a connection
    they might be sharing (see canonical_device()'s own docstring).

    Needed because MTU is negotiated once *per connection*, not once per
    client: confirmed on real hardware that a second explicit exchange
    request on an already-negotiated connection isn't just redundant, the
    underlying BLE stack rejects it outright (`OSError 120 EALREADY`). (A
    *separate* issue, a same-looking "service not found" turning up right
    after -- see discover_all()'s own docstring -- turned out to have a
    different root cause, not this one; this function only needs to
    prevent the EALREADY itself.) Only called from inside
    discovery_lock_for() -- see both clients' _connect_and_run() -- so
    there's no race on the check-then-mark below even though it isn't
    atomic on its own.

    Marks connection directly (a plain attribute, not a separate
    address-keyed dict here) so it's automatically fresh on every new
    connection: aioble constructs a brand new DeviceConnection instance
    per successful connect() (see its own device.py), which starts with no
    such attribute set, rather than this module needing its own
    disconnect/cleanup hook to reset anything.
    """
    if getattr(connection, "_mtu_exchange_attempted", False):
        return False
    connection._mtu_exchange_attempted = True
    return True


_CCCD_UUID = bluetooth.UUID(0x2902)
_CCCD_NOTIFY = 1
_CCCD_INDICATE = 2


async def discover_all(connection):
    """Returns {service_uuid: (ClientService, {char_uuid: (ClientCharacteristic,
    {desc_uuid: ClientDescriptor})})} for `connection` -- discovering it (once,
    unfiltered: every service, every characteristic under each, every
    descriptor under each of those) the first time this is called for a
    given connection object, and returning the same cached map on every
    call after that, including from the *other* client if sharing (see
    canonical_device()'s own docstring).

    Needed because AirconClient's and HeaterClient's own UUID-filtered
    discovery (the way each independently used to look up just its own
    service via connection.service(uuid)) was confirmed on real hardware
    to come back empty the second time it's tried on an already-discovered
    shared connection, even though the peripheral genuinely does still
    expose that second service -- root cause not confirmed (a GATT
    client-side discovery cache on this board's BLE stack that only
    remembers whatever the *first* client's own filtered query actually
    asked for? A bless/CoreBluetooth peripheral-side quirk answering a
    second, differently-filtered "Discover Primary Service by Service
    UUID" ATT request incorrectly? Both are plausible, no way to tell
    which from this side alone) -- but a second *subscribe()* on a shared
    connection is exposed to the exact same risk, since aioble's own
    subscribe() internally does its own characteristic.descriptor(uuid)
    discovery call every time it's invoked (see aioble's client.py), so
    discovering descriptors up front here too and writing the CCCD
    directly (see subscribe() below) avoids relying on that a second time
    as well, not just the service/characteristic lookups.

    Costs one full unfiltered sweep of the peripheral's entire GATT
    database on the first connection to it, instead of only discovering
    exactly what's needed -- negligible next to the multi-second BLE round
    trips already involved in connecting at all, and only paid once per
    connection regardless of how many characteristics either client ends
    up actually using.

    Marks connection directly with the completed map (a plain attribute,
    same pattern as mtu_exchange_needed()), so it's naturally fresh again
    on the next real connection -- aioble constructs a brand new
    DeviceConnection instance per successful connect() (see its own
    device.py), which starts with no such attribute set.
    """
    cached = getattr(connection, "_discovered", None)
    if cached is not None:
        return cached

    # Three separate, fully-drained passes -- NOT services() with
    # characteristics()/descriptors() nested inside its own still-open
    # `async for` body. connection._discover (the single-discovery-in-
    # flight slot -- see aioble's own client.py, ClientDiscover._start())
    # only clears once a discovery's *entire* result stream has been
    # consumed through to its done status, not after each individual
    # result -- starting a characteristics discovery while the outer
    # services discovery is still mid-iteration collides with itself
    # ("ValueError: Discovery in progress"), independent of whether
    # there's a second client sharing this connection at all. Collecting
    # each level into a plain list before moving to the next forces that
    # level's discovery to fully finish (including its own done-status
    # wait) first -- plain `async for` loops, not async comprehensions
    # (`[x async for x in y]`, valid Python but not used anywhere else in
    # this codebase and not confirmed supported by this MicroPython
    # build).
    services = []
    async for service in connection.services():
        services.append(service)
    # Diagnostic: which service UUIDs an unfiltered discovery pass on this
    # connection actually turned up -- left in permanently (cheap, one line
    # per connection) since "the service I wanted wasn't in here" is
    # otherwise silent all the way up to whichever caller's own "service
    # not found" print, with no way to tell "peripheral genuinely only has
    # one service" apart from "this discovery pass itself came back
    # incomplete" after the fact.
    print("ble_shared: discover_all: found %d service(s): %s" % (len(services), [s.uuid for s in services]))

    result = {}
    for service in services:
        chars = []
        async for char in service.characteristics():
            chars.append(char)

        char_map = {}
        for char in chars:
            descs = {}
            async for desc in char.descriptors():
                descs[desc.uuid] = desc
            char_map[char.uuid] = (char, descs)

        result[service.uuid] = (service, char_map)

    connection._discovered = result
    return result


def find_entry(mapping, uuid_int):
    """Looks up `uuid_int` (a plain int, e.g. heater_ble_config.
    SERVICE_UUID/CHAR_UUID, both 0xFFEx) in `mapping` (discover_all()'s
    own return value, or one of its nested per-service characteristic
    maps), trying both the compact 16-bit `bluetooth.UUID(uuid_int)` form
    and the algorithmically-expanded 128-bit
    "0000XXXX-0000-1000-8000-00805F9B34FB" string form.

    Needed because MicroPython's own bluetooth.UUID does not consider
    these equal (or hash equal) even though they're the same logical
    UUID (confirmed elsewhere in this codebase -- see heater_ble_config.
    py's SERVICE_UUID comment) -- and, confirmed on real hardware,
    different peripherals report a standard-range UUID like the heater's
    own 0xFFE0/0xFFE1 in different forms over the wire: a real heater
    reports it compact, matching heater_ble_config.py's own SERVICE_UUID/
    CHAR_UUID constants directly; ../hvac-sim/, registering it via a
    128-bit string with `bless`, was confirmed (by comparing what
    discover_all()'s own diagnostic print showed for it against the
    compact form standard services like 0x1800 print as) reporting it
    back over ATT in expanded 128-bit form instead -- so a lookup using
    only the compact form (the one that matches real hardware) silently
    never found it against this sim specifically, regardless of whether
    discovery/caching/locking around it was otherwise correct.

    The 32-bit short-UUID form doesn't get the same treatment -- nothing
    in this codebase uses one. A fully custom 128-bit UUID (the AirCon's
    own) has no compact form to begin with and doesn't need this at all;
    bluetooth.UUID(a_128_bit_value) already matches directly regardless
    of which side constructed it.
    """
    entry = mapping.get(bluetooth.UUID(uuid_int))
    if entry is not None:
        return entry
    return mapping.get(bluetooth.UUID("0000%04x-0000-1000-8000-00805f9b34fb" % uuid_int))


async def subscribe(char, descs, notify=True, indicate=False):
    """Equivalent to `await char.subscribe(notify=notify,
    indicate=indicate)` (aioble's own client.py), but writes to an
    already-discovered CCCD descriptor (`descs`, the per-characteristic
    dict discover_all() returns) instead of aioble's own subscribe()
    triggering its own fresh characteristic.descriptor(uuid) discovery
    call -- see discover_all()'s own docstring for why a second discovery
    of any kind on an already-discovered shared connection isn't reliable.
    Raises ValueError("CCCD not found") the same way aioble's own
    subscribe() does if `descs` doesn't have one.
    """
    cccd = descs.get(_CCCD_UUID)
    if cccd is None:
        raise ValueError("CCCD not found")
    await cccd.write(struct.pack("<H", _CCCD_NOTIFY * notify + _CCCD_INDICATE * indicate))
