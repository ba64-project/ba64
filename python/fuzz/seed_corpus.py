#!/usr/bin/env python3
"""Seed a libFuzzer corpus directory from the committed conformance vectors.

    python fuzz/seed_corpus.py corpus/

Writes one file per valid and error vector input, so the fuzzer starts from
inputs that already reach every branch. No atheris dependency.
"""

import hashlib
import json
import os
import sys


def main(out_dir):
    here = os.path.dirname(os.path.abspath(__file__))
    vectors = os.path.normpath(os.path.join(here, "..", "..", "vectors"))
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    for name in ("decode_plain.json", "decode_frames.json", "decode_errors.json",
                 "bombs.json"):
        with open(os.path.join(vectors, name), encoding="utf-8") as f:
            for c in json.load(f)["cases"]:
                data = c["input"].encode("utf-8", "surrogatepass")
                digest = hashlib.sha1(data).hexdigest()
                with open(os.path.join(out_dir, digest), "wb") as g:
                    g.write(data)
                n += 1
    print(f"seeded {n} corpus files into {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "corpus")
