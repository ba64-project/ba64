"""Self-contained frame builders for tests.

Deliberately independent of generator/reference.py and of ba64.py itself, so
tests construct frames by hand rather than trusting the code under test.
"""

import struct
import zlib


def leb128(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def deflate_stored(data):
    """One final stored DEFLATE block (RFC 1951 §3.2.4); deterministic."""
    assert len(data) <= 0xFFFF
    ln = len(data)
    return bytes([0x01]) + struct.pack("<H", ln) + struct.pack("<H", ln ^ 0xFFFF) + data


def build_frame(data, *, version=0x01, method=0x01, decoded_len=None,
                crc=None, payload=None):
    if decoded_len is None:
        decoded_len = len(data)
    if crc is None:
        crc = zlib.crc32(data) & 0xFFFFFFFF
    if payload is None:
        payload = deflate_stored(data)
    return bytes([version, method]) + leb128(decoded_len) + struct.pack("<I", crc) + payload


def frame_text(frame_bytes):
    import base64
    return "=" + base64.b64encode(frame_bytes).decode("ascii")


def stored_text(data):
    return frame_text(build_frame(data))
