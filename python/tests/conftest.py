"""Shared test fixtures: make `import ba64` work and locate the vector corpus."""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
PYDIR = HERE.parent                # python/ (or mutants/ under mutmut)

sys.path.insert(0, str(PYDIR))     # so `import ba64` / `import cli` resolve


def _find_vectors():
    # Walk upward so the corpus resolves regardless of CWD — mutmut runs the
    # suite from a copied mutants/ directory where relative paths shift.
    d = HERE
    for _ in range(8):
        cand = d / "vectors"
        if (cand / "decode_plain.json").exists():
            return cand
        d = d.parent
    raise RuntimeError("vectors/ corpus not found above " + str(HERE))


VECTORS = _find_vectors()


def load_vectors(name):
    """Return the `cases` list from vectors/<name>."""
    with open(VECTORS / name, encoding="utf-8") as f:
        return json.load(f)["cases"]
