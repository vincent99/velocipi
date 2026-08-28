"""Wire-format encode/decode for the heater's binary framed BLE protocol.
Mirrors ../hvac-knob/heater_ble.py's `_encode_frame()`/`_checksum()`/
`_drain_frames()`/`_handle_frame()` exactly (same header layout, same
checksum, same "device echoes cmd1+128" convention), just from the
peripheral (server) side instead of the central (client) side -- see this
repo's ../hvac-knob/heater_ble_config.py for the authoritative byte-by-
byte frame documentation this implements.

No incoming-write reassembly buffer here, unlike heater_ble.py's own
_notify_loop() on the client side: every frame this simulator's client
(heater_ble.py) ever sends is well under the default ATT MTU (a CMD_RUN
write is 12 bytes total), so each GATT write request `ble_server.py`
receives already contains one complete frame in practice -- reassembly
would be dead code for what this simulator needs to exercise. If you're
using this against some *other* BLE central that writes larger fragmented
payloads, that assumption is exactly where to start.
"""

import config


class FrameError(Exception):
    pass


def checksum(buf, length):
    """8-bit sum of buf[0:length-1], mod 256 -- `length` is the frame's own
    total length (including the checksum byte itself), matching
    heater_ble.py's _checksum().
    """
    return sum(buf[: length - 1]) & 0xFF


def encode_frame(cmd1, cmd2, payload=b""):
    length = 8 + len(payload) + 1  # header(8) + payload + checksum
    buf = bytearray(length)
    buf[0] = config.HEAD_1
    buf[1] = config.HEAD_2
    buf[2] = config.PROTOCOL_VERSION
    buf[3] = 0  # sequence number -- always 0, nothing this sim sends is multi-packet
    buf[4] = length & 0xFF
    buf[5] = (length >> 8) & 0xFF
    buf[6] = cmd1 & 0xFF
    buf[7] = cmd2 & 0xFF
    buf[8 : 8 + len(payload)] = payload
    buf[length - 1] = checksum(buf, length)
    return bytes(buf)


def encode_response(cmd1, cmd2, payload=b""):
    """What this simulator actually sends for every outgoing frame (direct
    acks and unsolicited status pushes alike) -- byte 6 carries cmd1+128,
    the same convention heater_ble.py's _handle_frame() decodes on the
    client side. Never call encode_frame() directly for anything this
    server sends; this is the one real entry point.
    """
    return encode_frame((cmd1 + 128) & 0xFF, cmd2, payload)


def decode_frame(frame):
    """Parses one already-complete frame (see this module's own docstring
    for why no reassembly is needed here) into (cmd1, cmd2, payload).
    Raises FrameError on anything that doesn't check out -- callers should
    treat that as "ignore this write", the same way heater_ble.py's own
    _drain_frames()/_handle_frame() treat a bad frame as noise rather than
    a fatal error.

    Deliberately does NOT expect the +128 response encoding here -- that's
    only ever applied to what the *device* sends back (see
    encode_response()); a real central always writes plain cmd1 values
    (e.g. 1 for CMD_RUN), which is exactly what heater_ble.py's own
    _write_frame() sends and what this function expects to receive.
    """
    frame = bytes(frame)
    if len(frame) < 9:
        raise FrameError("frame too short: %d bytes" % len(frame))
    if frame[0] != config.HEAD_1 or frame[1] != config.HEAD_2:
        raise FrameError("bad header: %02x %02x" % (frame[0], frame[1]))
    total_len = frame[4] | (frame[5] << 8)
    if total_len != len(frame):
        raise FrameError("declared length %d != actual %d" % (total_len, len(frame)))
    if checksum(frame, total_len) != frame[total_len - 1]:
        raise FrameError("checksum mismatch")
    cmd1, cmd2 = frame[6], frame[7]
    payload = frame[8 : total_len - 1]
    return cmd1, cmd2, payload
