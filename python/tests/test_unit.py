"""Unit tests — every branch and every error path of ba64.py, explicitly.

These do not depend on the vector corpus: they construct each boundary by hand
so the branch-coverage gate stands on its own.
"""

import base64
import zlib

import pytest

import ba64
from _frames import build_frame, deflate_stored, frame_text, stored_text


def err(text, code, **kw):
    with pytest.raises(ba64.Ba64Error) as ei:
        ba64.decode(text, **kw)
    assert ei.value.code == code
    return ei.value


# --- plain form (step 1) -----------------------------------------------------

def test_empty_string_is_empty_bytes():
    assert ba64.decode("") == b""

def test_plain_roundtrip_and_identity_to_base64():
    for data in (b"", b"a", b"ab", b"abc", bytes(range(256)), b"Hello, world!"):
        s = base64.b64encode(data).decode()
        assert ba64.decode(s) == data

def test_plain_bad_base64_non_alphabet():
    err("=@@@", "E_BASE64")          # frame body non-alphabet (via step 2)
    err("@@@@", "E_BASE64")          # plain non-alphabet

def test_plain_bad_padding():
    err("SGVsbG8", "E_BASE64")

def test_plain_non_canonical_trailing_bits():
    err("QR==", "E_BASE64")          # decodes but re-encodes differently

def test_plain_whitespace_rejected():
    err("SGVs bG8=", "E_BASE64")


# --- frame header (steps 3-7) ------------------------------------------------

def test_frame_version_missing_truncated():
    err("=", "E_TRUNCATED")          # empty frame body -> no version byte

def test_frame_bad_version():
    err(frame_text(build_frame(b"Hi", version=0x02)), "E_VERSION")

def test_frame_method_missing_truncated():
    err(frame_text(bytes([0x01])), "E_TRUNCATED")  # version only

def test_frame_bad_method():
    for m in (0x00, 0x02, 0xEF, 0xF0, 0xFF):
        err(frame_text(build_frame(b"Hi", method=m)), "E_METHOD")

def test_leb128_truncated_mid_varint():
    # version, method, then a lone continuation byte -> exhausted mid-varint
    err(frame_text(bytes([0x01, 0x01, 0x80])), "E_TRUNCATED")

def test_leb128_non_minimal():
    err(frame_text(bytes([0x01, 0x01, 0x80, 0x00, 0, 0, 0, 0])), "E_HEADER")

def test_leb128_too_long():
    body = bytes([0x01, 0x01]) + bytes([0x80] * 10) + b"\x00\x00\x00\x00"
    err(frame_text(body), "E_HEADER")

def test_multibyte_varint_accepted():
    # decoded_len needs 2 varint bytes (>=128); a valid stored frame must decode
    data = b"z" * 200
    assert ba64.decode(stored_text(data)) == data

def test_crc_truncated():
    # complete 1-byte varint but fewer than 4 crc bytes remain
    body = bytes([0x01, 0x01, 0x02]) + b"\x00\x00\x00"  # only 3 crc bytes
    err(frame_text(body), "E_TRUNCATED")


# --- limits (step 6) ---------------------------------------------------------

def test_limit_exceeded_before_allocation():
    frame = build_frame(b"", decoded_len=8 * 2 ** 30, payload=b"", crc=0)
    err(frame_text(frame), "E_LIMIT_EXCEEDED")

def test_limit_is_per_call_parameter():
    data = b"x" * 1000
    text = stored_text(data)
    err(text, "E_LIMIT_EXCEEDED", max_decoded_len=999)
    assert ba64.decode(text, max_decoded_len=1000) == data


# --- payload (step 8) --------------------------------------------------------

def test_payload_malformed():
    frame = build_frame(b"", decoded_len=4, payload=b"\xde\xad\xbe\xef", crc=0)
    err(frame_text(frame), "E_PAYLOAD")

def test_payload_truncated_stream():
    frame = build_frame(b"Hello", payload=deflate_stored(b"Hello")[:-2],
                        decoded_len=5, crc=zlib.crc32(b"Hello") & 0xFFFFFFFF)
    err(frame_text(frame), "E_PAYLOAD")

def test_payload_trailing_bytes():
    frame = build_frame(b"Hi", payload=deflate_stored(b"Hi") + b"\x00")
    err(frame_text(frame), "E_PAYLOAD")


# --- length mismatch (step 8) ------------------------------------------------

def test_length_mismatch_claim_low():
    err(frame_text(build_frame(b"Hi", decoded_len=1)), "E_LENGTH_MISMATCH")

def test_length_mismatch_claim_high():
    err(frame_text(build_frame(b"X", decoded_len=2)), "E_LENGTH_MISMATCH")

def test_zero_cap_trap():
    # decoded_len=0 but payload yields a byte -> must fail after <=1 byte
    frame = build_frame(b"", decoded_len=0, payload=deflate_stored(b"Q"),
                        crc=zlib.crc32(b"Q") & 0xFFFFFFFF)
    err(frame_text(frame), "E_LENGTH_MISMATCH")

def test_zero_len_valid_empty_block():
    frame = build_frame(b"", decoded_len=0, payload=deflate_stored(b""), crc=0)
    assert ba64.decode(frame_text(frame)) == b""


# --- checksum (step 9) -------------------------------------------------------

def test_bad_checksum():
    err(frame_text(build_frame(b"Hi", crc=0xDEADBEEF)), "E_CHECKSUM")


# --- happy-path frame decode (step 10 return) --------------------------------

def test_valid_stored_frame_decodes():
    assert ba64.decode(stored_text(b"conformance")) == b"conformance"


# --- encode branches ---------------------------------------------------------

def test_encode_compresses_repetitive():
    enc = ba64.encode(b"A" * 1024)
    assert enc.startswith("=")
    assert ba64.decode(enc) == b"A" * 1024

def test_encode_floor_on_incompressible():
    import os
    blob = os.urandom(1024)
    enc = ba64.encode(blob)
    assert not enc.startswith("=")
    assert enc == base64.b64encode(blob).decode()

def test_encode_tie_takes_plain():
    # tiny input: header overhead guarantees plain form
    assert ba64.encode(b"") == ""
    assert ba64.encode(b"a") == base64.b64encode(b"a").decode()

def test_encode_level_argument_still_roundtrips():
    data = b"repeat " * 50
    for level in (1, 6, 9):
        assert ba64.decode(ba64.encode(data, level=level)) == data


# --- boundary hardening (kills off-by-one / dropped-arg mutants) -------------
# Each case pins a header-length boundary or the level knob so an adjacent
# mutation (< vs <=, n vs n±1, dropped argument) changes an observable code.

def test_one_byte_frame_bad_version_is_version_not_truncated():
    # distinguishes `len(frame) < 1` from `<= 1` / `< 2`
    err(frame_text(bytes([0x02])), "E_VERSION")

def test_two_byte_frame_bad_method_is_method_not_truncated():
    # distinguishes `len(frame) < 2` from `<= 2` / `< 3`
    err(frame_text(bytes([0x01, 0x02])), "E_METHOD")

def test_full_header_empty_payload_is_payload_not_truncated():
    # distinguishes `len(frame) - pos < 4` from `<= 4` / `< 5`: exactly 4 crc
    # bytes and zero payload must pass the header and fail in the inflater.
    err(frame_text(build_frame(b"", decoded_len=5, payload=b"", crc=0)), "E_PAYLOAD")

def test_nine_byte_varint_is_accepted_then_limit():
    # a maximal 9-byte LEB128 must parse (then hit the limit), not be rejected
    # as an over-long header — distinguishes `pos - start > 9` from `>= 9`.
    frame = build_frame(b"", decoded_len=1 << 56, payload=b"", crc=0)
    err(frame_text(frame), "E_LIMIT_EXCEEDED")

def test_ten_byte_varint_is_header_error():
    # a terminating 10-byte LEB128 must be rejected as over-long —
    # distinguishes `pos - start > 9` from `> 10`.
    body = bytes([0x01, 0x01]) + bytes([0x80] * 9 + [0x01]) + b"\x00\x00\x00\x00"
    err(frame_text(body), "E_HEADER")

def test_level_argument_actually_changes_output():
    # the level knob must reach zlib — distinguishes passing `level=level` from
    # dropping it (which would pin every call to the default).
    data = b"The quick brown fox. " * 60
    assert ba64.encode(data, level=1) != ba64.encode(data, level=9)


# --- exception shape ---------------------------------------------------------

def test_error_carries_code_and_is_valueerror():
    e = err("SGVsbG8", "E_BASE64")
    assert isinstance(e, ValueError)
    assert e.code == "E_BASE64"
    assert str(e) == "E_BASE64"
