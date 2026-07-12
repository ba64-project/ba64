"""Test layer 2 — property-based invariants (hypothesis). The UT backbone."""

import base64

from hypothesis import given
from hypothesis import strategies as st

import ba64


@given(st.binary(max_size=4096))
def test_roundtrip(data):
    assert ba64.decode(ba64.encode(data)) == data


import pytest


@pytest.mark.slow
def test_roundtrip_large():
    # explicit large blobs (deterministic) rather than hypothesis-generated,
    # which trips the large-base-example health check.
    import random
    rng = random.Random(0xBA64)
    for size in (100_000, 1_000_000, 10 * 2 ** 20):
        for data in (bytes(rng.getrandbits(8) for _ in range(size)),   # floor
                     b"log line repeated " * (size // 18)):            # compresses
            assert ba64.decode(ba64.encode(data)) == data


@given(st.binary(max_size=4096))
def test_floor_invariant(data):
    assert len(ba64.encode(data)) <= len(base64.b64encode(data).decode())


@given(st.binary(max_size=4096))
def test_marker_iff_strictly_smaller(data):
    enc = ba64.encode(data)
    plain = base64.b64encode(data).decode()
    # compressed form emitted iff it is strictly shorter (spec §6 floor rule)
    assert enc.startswith("=") == (len(enc) < len(plain))
    if not enc.startswith("="):
        assert enc == plain


@given(st.text(max_size=512))
def test_decode_text_never_crashes(s):
    try:
        out = ba64.decode(s)
    except ba64.Ba64Error:
        return
    assert isinstance(out, bytes)


@given(st.binary(max_size=512))
def test_decode_arbitrary_bytes_as_latin1_never_crashes(raw):
    s = raw.decode("latin-1")
    try:
        out = ba64.decode(s)
    except ba64.Ba64Error:
        return
    assert isinstance(out, bytes)


@given(st.binary(max_size=4096))
def test_reencode_stability(data):
    s = ba64.encode(data)
    # encoding may differ, meaning may not
    assert ba64.decode(ba64.encode(ba64.decode(s))) == ba64.decode(s)
