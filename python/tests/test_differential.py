"""Test layer 3b — differential vs the standard library.

On the plain path, ba64 must be byte-for-byte equivalent to stdlib base64 in
both directions, over a large seeded corpus.
"""

import base64
import random

import ba64


def _corpus(n=10_000, seed=0xBA64):
    rng = random.Random(seed)
    for _ in range(n):
        kind = rng.random()
        if kind < 0.4:                       # incompressible -> floor path
            size = rng.randint(0, 64)
            yield bytes(rng.getrandbits(8) for _ in range(size))
        elif kind < 0.7:                     # compressible
            size = rng.randint(0, 256)
            yield bytes([rng.choice(b"ab ")]) * size
        else:                                # small structured
            yield rng.choice([b"", b"\x00", b"\xff" * rng.randint(0, 32),
                              b"the quick brown fox"])


def test_plain_decode_equivalent_to_stdlib():
    for data in _corpus():
        s = base64.b64encode(data).decode()
        assert ba64.decode(s) == base64.b64decode(s)


def test_floor_path_encode_equivalent_to_stdlib():
    for data in _corpus():
        enc = ba64.encode(data)
        if not enc.startswith("="):          # floor path taken
            assert enc == base64.b64encode(data).decode()


def test_roundtrip_over_corpus():
    for data in _corpus():
        assert ba64.decode(ba64.encode(data)) == data
