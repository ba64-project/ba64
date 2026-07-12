#!/usr/bin/env python3
"""Coverage-guided fuzz harness for the ba64 roundtrip (atheris).

The contract under test (spec §6): decode(encode(x)) == x for every bytes x, and
len(encode(x)) <= len(base64(x)). Any counterexample is a corpus-worthy bug.

Run where atheris is installed (see fuzz_decode.py for environment notes):

    python fuzz/fuzz_roundtrip.py -atheris_runs=1000000
"""

import base64
import os
import sys

import atheris

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
with atheris.instrument_imports():
    import ba64


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    level = 1 + (fdp.ConsumeIntInRange(0, 8))
    payload = fdp.ConsumeBytes(fdp.remaining_bytes())
    enc = ba64.encode(payload, level=level)
    assert ba64.decode(enc) == payload, "roundtrip broken"
    assert len(enc) <= len(base64.b64encode(payload)), "floor invariant broken"
    assert enc.startswith("=") == (len(enc) < len(base64.b64encode(payload)))


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
