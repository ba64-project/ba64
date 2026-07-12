"""ba64 — binary-to-text encoding that is never larger than standard base64.

Reference implementation for the v1 format (see ../spec.md). Single file, zero
dependencies beyond the standard library. The normative algorithm is spec.md §4;
this module implements it exactly.

    >>> encode(b"Hello, world!")
    'SGVsbG8sIHdvcmxkIQ=='
    >>> decode(encode(b"Hello, world!"))
    b'Hello, world!'

Encoding is a *relation*, not a function: the same input may yield different
valid ba64 texts across levels/versions/libraries. Decoding is a function. Any
equality, dedup, cache-key, or MAC comparison MUST operate on decoded bytes.
"""

import base64
import struct
import zlib

__all__ = ["encode", "decode", "Ba64Error", "DEFAULT_MAX_DECODED_LEN"]

DEFAULT_MAX_DECODED_LEN = 64 * 2 ** 20  # 64 MiB (spec.md §7)

_VERSION = 0x01
_METHOD_DEFLATE_RAW = 0x01


class Ba64Error(ValueError):
    """A ba64 decode failure carrying a machine-readable taxonomy code (spec §5).

    ``code`` is one of: E_BASE64, E_TRUNCATED, E_HEADER, E_VERSION, E_METHOD,
    E_LIMIT_EXCEEDED, E_PAYLOAD, E_LENGTH_MISMATCH, E_CHECKSUM. Branch on
    ``err.code``; never parse the message. Messages never echo payload or
    decoded content (spec §8, error hygiene).
    """

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _b64_canonical_decode(s):
    """Decode canonical RFC 4648 §4 base64, else raise E_BASE64.

    Rejects non-alphabet characters, whitespace, bad padding, and non-zero
    trailing bits. Strictness comes from decode-then-re-encode-and-compare
    (spec §4 implementation note): any input that does not round-trip to itself
    is not canonical.
    """
    try:
        raw = base64.b64decode(s, validate=True)
    except Exception:  # binascii.Error (a ValueError) on non-alphabet/bad length
        raise Ba64Error("E_BASE64")
    if base64.b64encode(raw).decode("ascii") != s:
        raise Ba64Error("E_BASE64")
    return raw


def _leb128_encode(n):
    """Unsigned LEB128, minimally encoded (spec §2.1)."""
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
    """Read a minimal unsigned LEB128 at ``pos``; return (value, new_pos).

    E_TRUNCATED if the buffer ends mid-varint; E_HEADER if longer than 9 bytes
    or non-minimally encoded (spec §2.1).
    """
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
                raise Ba64Error("E_HEADER")  # trailing zero byte -> non-minimal
            return value, pos
        shift += 7


def encode(data, *, level=6):
    """Encode ``data`` (bytes) to a ba64 text (str).

    Races raw DEFLATE at ``level`` (zlib 1–9, default 6) against plain base64 and
    returns whichever final text is shorter; ties take the plain form. Therefore
    ``len(encode(x)) <= len(base64(x))`` for every input (spec §6 floor rule).
    """
    plain = base64.b64encode(data).decode("ascii")
    co = zlib.compressobj(level=level, wbits=-15)  # raw DEFLATE, no wrapper
    payload = co.compress(data) + co.flush()
    frame = (
        bytes((_VERSION, _METHOD_DEFLATE_RAW))
        + _leb128_encode(len(data))
        + struct.pack("<I", zlib.crc32(data) & 0xFFFFFFFF)
        + payload
    )
    candidate = "=" + base64.b64encode(frame).decode("ascii")
    return candidate if len(candidate) < len(plain) else plain


def decode(text, *, max_decoded_len=DEFAULT_MAX_DECODED_LEN):
    """Decode a ba64 text (str) to bytes, or raise :class:`Ba64Error`.

    Implements the ordered checks of spec §4 so every invalid input maps to
    exactly one taxonomy code. ``max_decoded_len`` (default 64 MiB) is enforced
    before any allocation proportional to the claimed size, and inflation is
    hard-capped at ``decoded_len`` — a small frame claiming a huge size costs
    O(header) work (spec §7).
    """
    if not text.startswith("="):  # step 1: plain form (empty string -> b"")
        return _b64_canonical_decode(text)

    frame = _b64_canonical_decode(text[1:])  # step 2

    if len(frame) < 1:  # step 3: version
        raise Ba64Error("E_TRUNCATED")
    if frame[0] != _VERSION:
        raise Ba64Error("E_VERSION")

    if len(frame) < 2:  # step 4: method
        raise Ba64Error("E_TRUNCATED")
    if frame[1] != _METHOD_DEFLATE_RAW:
        raise Ba64Error("E_METHOD")

    decoded_len, pos = _leb128_decode(frame, 2)  # step 5

    if decoded_len > max_decoded_len:  # step 6: before any big allocation
        raise Ba64Error("E_LIMIT_EXCEEDED")

    if len(frame) - pos < 4:  # step 7: crc32
        raise Ba64Error("E_TRUNCATED")
    crc_stored = struct.unpack("<I", frame[pos:pos + 4])[0]
    payload = frame[pos + 4:]

    # step 8: inflate with a hard output cap of decoded_len. Python's max_length=0
    # means "unlimited", so a claimed length of zero is capped at 1 and the excess
    # is caught below (spec §7 zero-cap rule).
    inflater = zlib.decompressobj(wbits=-15)
    try:
        out = inflater.decompress(payload, decoded_len or 1)
    except zlib.error:
        raise Ba64Error("E_PAYLOAD")
    if len(out) > decoded_len or inflater.unconsumed_tail:  # exceeded the cap
        raise Ba64Error("E_LENGTH_MISMATCH")
    if not inflater.eof:  # payload exhausted before the final block completed
        raise Ba64Error("E_PAYLOAD")
    if inflater.unused_data:  # bytes remain after the final block
        raise Ba64Error("E_PAYLOAD")
    if len(out) != decoded_len:  # clean stream, wrong length
        raise Ba64Error("E_LENGTH_MISMATCH")

    if zlib.crc32(out) & 0xFFFFFFFF != crc_stored:  # step 9
        raise Ba64Error("E_CHECKSUM")
    return out  # step 10
