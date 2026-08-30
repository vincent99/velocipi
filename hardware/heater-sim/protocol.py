"""Wire-format encode/decode for the heater's binary framed BLE protocol.
Mirrors ../hvac-knob/heater_ble.py's `_encode_frame()`/`_checksum()`/
`_drain_frames()`/`_apply_status()` exactly (same fixed 8-byte app->device
frame shape, same checksum, same XOR-obfuscated 48-byte device->app status
shape), just from the peripheral (server) side instead of the central
(client) side -- see this repo's ../hvac-knob/heater_ble_config.py for the
authoritative byte-by-byte documentation this implements.

Both directions are fixed-length (8 bytes app->device, 48 bytes
device->app) -- unlike this sim's own earlier (wrong) assumption of a
variable-length app->device frame with an explicit length field, there's no
reassembly-buffer concern here at all: every GATT write this simulator's
client (heater_ble.py) ever sends is exactly 8 bytes, well under the
default ATT MTU, so each GATT write request `ble_server.py` receives
already contains one complete frame.
"""

import config


class FrameError(Exception):
    pass


def checksum(buf):
    """(sum(buf[0:7]) + 1) & 0xFF -- matches heater_ble.py's _checksum()
    exactly, confirmed against real captured frames there.
    """
    return (sum(buf[0:7]) + 1) & 0xFF


def decode_frame(frame):
    """Parses one app->device write (always exactly 8 bytes) into
    (password, cmd, param1, param2). Raises FrameError on anything that
    doesn't check out -- callers should treat that as "ignore this write",
    the same way heater_ble.py's own _drain_frames()/_handle_status_frame()
    treat a bad frame as noise rather than a fatal error.

    The password (bytes 2-3, base-100 split, high byte first) rides along
    on every frame in this protocol version -- there's no separate
    handshake/login frame the way this sim's own earlier (wrong) protocol
    guess had -- so it's returned here rather than decoded by a dedicated
    function; ble_server.py's caller checks it against whatever password
    (if any) this sim was configured to require.
    """
    frame = bytes(frame)
    if len(frame) != 8:
        raise FrameError("expected 8 bytes, got %d" % len(frame))
    if frame[0] != config.HEAD_1 or frame[1] != config.HEAD_2:
        raise FrameError("bad header: %02x %02x" % (frame[0], frame[1]))
    if checksum(frame) != frame[7]:
        raise FrameError("checksum mismatch")
    password = frame[2] * 100 + frame[3]
    cmd, param1, param2 = frame[4], frame[5], frame[6]
    return password, cmd, param1, param2


def encode_status(cmd_echo, on, gear, fault_code=0):
    """Builds one device->app status push -- fixed NOTIFY_LEN bytes, XOR-
    obfuscated with NOTIFY_XOR_KEY, matching heater_ble.py's _apply_status()
    decode exactly (see heater_ble_config.py's NOTIFY_XOR_KEY comment for
    the full field layout).

    Encodes what's confirmed against real hardware (header, cmd echo,
    on/off, gear -- 0-indexed on the wire, `gear` here is this sim's own
    1-indexed controller.py value, converted at this boundary) plus
    fault_code, which is NOT confirmed (see heater_ble_config.py's
    NOTIFY_OFF_FAULT comment -- included anyway so --fault has something
    real to exercise on the panel side). Everything else (mode,
    temperature-related fields, the mostly-constant "remainder") is left
    zeroed rather than guessed at, since this sim has no confirmed
    encoding for any of it.
    """
    decoded = bytearray(config.NOTIFY_LEN)
    decoded[0] = 0xAA
    decoded[1] = 0x66
    decoded[2] = cmd_echo & 0xFF
    decoded[config.NOTIFY_OFF_ON] = 1 if on else 0
    decoded[config.NOTIFY_OFF_FAULT] = fault_code & 0xFF
    decoded[config.NOTIFY_OFF_GEAR] = (gear - 1) & 0xFF
    key = config.NOTIFY_XOR_KEY
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(decoded))
