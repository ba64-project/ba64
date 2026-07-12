"""ba64 reference codec — GENERATOR TOOL, NOT THE SHIPPING LIBRARY.

This is the exact normative reference from SPEC.md Appendix B, plus a few
deterministic frame-construction helpers used only to build conformance
vectors. The shipped Python implementation lives in ../python/ba64.py
(Phase 2) and must be developed independently against the vectors this
module helps produce. Nothing here is part of any release artifact.
"""

import base64
import struct
import zlib

# --- Normative reference (SPEC.md Appendix B, verbatim behaviour) ------------


class Ba64Error(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _b64_canonical_decode(s):
    try:
        raw = base64.b64decode(s, validate=True)
    except Exception:
        raise Ba64Error("E_BASE64")
    if base64.b64encode(raw).decode("ascii") != s:  # padding + zero trailing bits
        raise Ba64Error("E_BASE64")
    return raw


def _leb128_encode(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _leb128_decode(buf, pos):
    value = shift = 0
    start = pos
    while True:
        if pos >= len(buf):
            raise Ba64Error("E_TRUNCATED")
        b = buf[pos]
        pos += 1
        if pos - start > 9:
            raise Ba64Error("E_HEADER")
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            if pos - start > 1 and b == 0:
                raise Ba64Error("E_HEADER")  # non-minimal
            return value, pos
        shift += 7


def encode(data, *, level=6):
    plain = base64.b64encode(data).decode("ascii")
    co = zlib.compressobj(level=level, wbits=-15)  # raw DEFLATE
    payload = co.compress(data) + co.flush()
    frame = (
        bytes((0x01, 0x01))
        + _leb128_encode(len(data))
        + struct.pack("<I", zlib.crc32(data) & 0xFFFFFFFF)
        + payload
    )
    cand = "=" + base64.b64encode(frame).decode("ascii")
    return cand if len(cand) < len(plain) else plain  # floor rule; tie -> plain


def decode(text, *, max_decoded_len=64 * 2 ** 20):
    if not text.startswith("="):  # step 1: plain form
        return _b64_canonical_decode(text)
    frame = _b64_canonical_decode(text[1:])  # step 2
    if len(frame) < 1:
        raise Ba64Error("E_TRUNCATED")  # step 3
    if frame[0] != 0x01:
        raise Ba64Error("E_VERSION")
    if len(frame) < 2:
        raise Ba64Error("E_TRUNCATED")  # step 4
    if frame[1] != 0x01:
        raise Ba64Error("E_METHOD")
    decoded_len, pos = _leb128_decode(frame, 2)  # step 5
    if decoded_len > max_decoded_len:  # step 6 -- before
        raise Ba64Error("E_LIMIT_EXCEEDED")  # any allocation
    if len(frame) - pos < 4:
        raise Ba64Error("E_TRUNCATED")  # step 7
    crc_stored = struct.unpack("<I", frame[pos:pos + 4])[0]
    payload = frame[pos + 4:]
    d = zlib.decompressobj(wbits=-15)  # step 8
    try:
        # CAUTION: Python's max_length=0 means UNLIMITED, so a claimed
        # length of zero must be capped at 1 and checked below (see SPEC 7).
        out = d.decompress(payload, decoded_len or 1)
    except zlib.error:
        raise Ba64Error("E_PAYLOAD")
    if len(out) > decoded_len or d.unconsumed_tail:  # tried to exceed cap
        raise Ba64Error("E_LENGTH_MISMATCH")
    if not d.eof:  # ended mid-stream
        raise Ba64Error("E_PAYLOAD")
    if d.unused_data:  # bytes after final block
        raise Ba64Error("E_PAYLOAD")
    if len(out) != decoded_len:  # clean end, wrong count
        raise Ba64Error("E_LENGTH_MISMATCH")
    if zlib.crc32(out) & 0xFFFFFFFF != crc_stored:  # step 9
        raise Ba64Error("E_CHECKSUM")
    return out


# --- Deterministic frame construction (vector-building only) -----------------
#
# Real encoders emit non-canonical DEFLATE (level/library dependent). For
# byte-exact DECODE vectors we build frames from *stored* DEFLATE blocks, which
# are fully deterministic. A frame built this way is a valid method-0x01 frame
# that a conforming decoder MUST accept even though a real encoder — obeying the
# floor rule — would usually prefer plain base64 for the same input (SPEC 4:
# decoders validate the grammar, not encoder optimality).


def deflate_stored(data):
    """Raw-DEFLATE encode `data` as a single final stored block (RFC 1951 3.2.4)."""
    if len(data) > 0xFFFF:
        raise ValueError("stored-block helper handles <=65535 bytes per block")
    ln = len(data)
    return bytes([0x01]) + struct.pack("<H", ln) + struct.pack("<H", ln ^ 0xFFFF) + data


def build_frame(data, *, version=0x01, method=0x01, decoded_len=None,
                crc=None, payload=None):
    """Assemble a raw frame with per-field overrides for building error vectors.

    Defaults produce a valid stored-block frame for `data`. Any field may be
    overridden to construct a deliberately malformed frame.
    """
    if decoded_len is None:
        decoded_len = len(data)
    if crc is None:
        crc = zlib.crc32(data) & 0xFFFFFFFF
    if payload is None:
        payload = deflate_stored(data)
    return (
        bytes([version, method])
        + _leb128_encode(decoded_len)
        + struct.pack("<I", crc)
        + payload
    )


def frame_to_text(frame):
    """Wrap a raw frame as a ba64 compressed-form string."""
    return "=" + base64.b64encode(frame).decode("ascii")


def encode_stored(data):
    """ba64 compressed-form text for `data` using a deterministic stored block."""
    return frame_to_text(build_frame(data))
