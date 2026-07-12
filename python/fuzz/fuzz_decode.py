#!/usr/bin/env python3
"""Coverage-guided fuzz harness for ba64.decode on arbitrary input (atheris).

The contract under test (spec §4): decode() of ANY string returns bytes or
raises exactly one Ba64Error — never another exception, never a hang. Any
finding is minimized and promoted into vectors/decode_errors.json forever.

Run (where atheris is installed — Linux + clang; it does not build on the
CPython 3.14 / macOS used to author this):

    python fuzz/fuzz_decode.py -atheris_runs=1000000      # quick
    python fuzz/fuzz_decode.py corpus/                    # persistent corpus

Seed the corpus from the committed vectors first (see fuzz/README.md).
"""

import os
import sys

import atheris

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
with atheris.instrument_imports():
    import ba64


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    s = fdp.ConsumeUnicodeNoSurrogates(fdp.remaining_bytes())
    max_len = 1 + (len(data) % (1 << 20))  # vary the cap
    try:
        out = ba64.decode(s, max_decoded_len=max_len)
    except ba64.Ba64Error:
        return
    assert isinstance(out, bytes)


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
