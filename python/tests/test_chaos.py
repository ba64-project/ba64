"""Test layer 4 — monkey/chaos: bit-flip and truncation sweeps, bomb resource caps.

The core safety claim: a decoder never silently returns wrong bytes for a frame
(the CRC catches every corruption), and never crashes with anything but a
Ba64Error on any input.
"""

import base64
import resource
import sys
import time

import pytest

import ba64
from conftest import load_vectors


def _valid_strings():
    """Every valid vector string (plain and frame forms)."""
    for name in ("decode_plain.json", "decode_frames.json"):
        for c in load_vectors(name):
            yield c["input"]


def _frame_vectors():
    """(frame_bytes, expected_bytes) for every valid *frame* vector."""
    import base64
    for c in load_vectors("decode_frames.json"):
        frame = base64.b64decode(c["input"][1:])  # strip leading "="
        yield frame, bytes.fromhex(c["output_hex"])


def _assert_no_crash(text):
    """Universal safety: any input yields bytes or a Ba64Error — never another
    exception, never a hang. (A corrupted string may reclassify into a different
    valid message; that is not corruption of *this* string's decoding.)"""
    try:
        out = ba64.decode(text)
    except ba64.Ba64Error:
        return
    assert isinstance(out, bytes)


def test_bit_flip_sweep():
    """Flip every bit of every valid vector string -> bytes or typed error."""
    total = 0
    for text in _valid_strings():
        raw = text.encode("ascii")
        for i in range(len(raw)):
            for bit in range(8):
                mutated = bytearray(raw)
                mutated[i] ^= (1 << bit)
                s = mutated.decode("latin-1")
                _assert_no_crash(s)
                total += 1
    assert total > 2000
    print(f"\nbit-flip sweep: {total} cases, zero crashes / non-taxonomy errors")


def test_truncation_sweep():
    """Every prefix of every valid vector string -> bytes or typed error."""
    total = 0
    for text in _valid_strings():
        for n in range(len(text)):
            _assert_no_crash(text[:n])
            total += 1
    print(f"\ntruncation sweep: {total} prefixes, zero crashes")


def test_append_garbage_sweep():
    for text in _valid_strings():
        for suffix in ("=", "A", "==", "\x00", "AAAA"):
            _assert_no_crash(text + suffix)


def test_frame_corruption_never_silent():
    """The CRC guarantee, precisely: mutate any bit of a valid frame's bytes,
    keep it in frame form (leading '=' intact), and decode MUST either raise a
    Ba64Error or return the *original* bytes — never silently-wrong content."""
    import base64
    total = 0
    for frame, original in _frame_vectors():
        for i in range(len(frame)):
            for bit in range(8):
                mutated = bytearray(frame)
                mutated[i] ^= (1 << bit)
                text = "=" + base64.b64encode(bytes(mutated)).decode("ascii")
                try:
                    out = ba64.decode(text)
                except ba64.Ba64Error:
                    total += 1
                    continue
                assert out == original, "frame silently returned wrong bytes"
                total += 1
    assert total > 2000
    print(f"\nframe-corruption sweep: {total} cases, zero silent corruptions")


def _maxrss_bytes():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss if sys.platform == "darwin" else rss * 1024  # macOS bytes, Linux KiB


def test_inflation_cap_bounds_memory():
    """The hard output cap must bound memory: a frame claiming 100 bytes whose
    payload would inflate to 128 MiB must reject after ~100 bytes, not after
    materialising the whole thing. Built in-test (too large to commit as a
    vector). This is the test that fails if the `max_length` cap is dropped."""
    import zlib
    from _frames import build_frame, frame_text
    inflated = 128 * 2 ** 20
    co = zlib.compressobj(9, wbits=-15)
    payload = co.compress(b"\x00" * inflated) + co.flush()
    bomb = frame_text(build_frame(b"", decoded_len=100, payload=payload, crc=0))
    before = _maxrss_bytes()
    with pytest.raises(ba64.Ba64Error) as ei:
        ba64.decode(bomb)
    delta = _maxrss_bytes() - before
    assert ei.value.code == "E_LENGTH_MISMATCH"
    assert delta < 32 * 2 ** 20, f"cap not enforced: RSS grew {delta} bytes"


@pytest.mark.parametrize("c", load_vectors("bombs.json"), ids=lambda c: c["name"])
def test_bombs_rejected_cheaply(c):
    before = _maxrss_bytes()
    start = time.perf_counter()
    with pytest.raises(ba64.Ba64Error) as ei:
        ba64.decode(c["input"])
    elapsed = time.perf_counter() - start
    delta = _maxrss_bytes() - before
    assert ei.value.code == c["error"], c["name"]
    # a frame claiming gigabytes must not have allocated gigabytes
    assert delta < 64 * 2 ** 20, f"{c['name']} grew RSS by {delta} bytes"
    assert elapsed < 1.0, f"{c['name']} took {elapsed:.3f}s"
