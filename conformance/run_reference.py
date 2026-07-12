#!/usr/bin/env python3
"""Stub conformance runner — Phase 1 exit gate.

Consumes the committed vectors/*.json and drives them through the reference
codec, exactly as each future language implementation will drive them through
its own. It also verifies vectors/SHA256SUMS so a hand-edited or stale corpus
fails loudly. This is the machine that proves the corpus is a runnable spec.

In Phase 2+ each implementation ships its own runner in the same shape; this one
targets generator/reference.py so the corpus is exercised the moment it is built.

Exit 0 = all green. Non-zero = a vector disagreed or a checksum failed.
"""

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "generator"))
import reference as R  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
VECTORS = os.path.normpath(os.path.join(HERE, "..", "vectors"))


def load(name):
    with open(os.path.join(VECTORS, name), encoding="utf-8") as f:
        return json.load(f)["cases"]


def verify_checksums():
    path = os.path.join(VECTORS, "SHA256SUMS")
    with open(path, encoding="utf-8") as f:
        entries = [line.split(None, 1) for line in f if line.strip()]
    for digest, name in entries:
        name = name.strip()
        with open(os.path.join(VECTORS, name), "rb") as g:
            actual = hashlib.sha256(g.read()).hexdigest()
        if actual != digest:
            raise AssertionError(f"SHA256 mismatch for {name}: corpus modified "
                                 f"without regenerating")
    return len(entries)


def run_decode(name, want_output=True):
    passed = 0
    for c in load(name):
        text = c["input"]
        kw = {"max_decoded_len": c["max_decoded_len"]} if "max_decoded_len" in c else {}
        if want_output:
            got = R.decode(text, **kw)
            expect = bytes.fromhex(c["output_hex"])
            assert got == expect, f"{name}/{c['name']}: {got!r} != {expect!r}"
        else:
            accepted = [c["error"]] + c.get("error_alt", [])
            try:
                got = R.decode(text, **kw)
            except R.Ba64Error as e:
                assert e.code in accepted, \
                    f"{name}/{c['name']}: got {e.code}, want {accepted}"
            else:
                raise AssertionError(
                    f"{name}/{c['name']}: {got!r}, want error {c['error']}")
        passed += 1
    return passed


def run_encode_props(name):
    import base64
    passed = 0
    for c in load(name):
        data = bytes.fromhex(c["input_hex"])
        enc = R.encode(data)
        plain = base64.b64encode(data).decode("ascii")
        props = c["props"]
        assert R.decode(enc) == data, f"{name}/{c['name']}: roundtrip"
        assert len(enc) <= len(plain), f"{name}/{c['name']}: floor"
        if "compressed" in props:
            assert enc.startswith("="), f"{name}/{c['name']}: not compressed"
        if "plain" in props:
            assert enc == plain, f"{name}/{c['name']}: not plain==base64"
        passed += 1
    return passed


def run_mixed(name):
    """Cases carrying either output_hex (success) or error (raise that code)."""
    passed = 0
    for c in load(name):
        if "output_hex" in c:
            got = R.decode(c["input"])
            assert got == bytes.fromhex(c["output_hex"]), f"{name}/{c.get('input')!r}"
        else:
            try:
                got = R.decode(c["input"])
            except R.Ba64Error as e:
                assert e.code == c["error"], f"{name}: got {e.code}, want {c['error']}"
            else:
                raise AssertionError(f"{name}: {got!r}, want error {c['error']}")
        passed += 1
    return passed


def main():
    n_files = verify_checksums()
    results = {
        "decode_plain.json": run_decode("decode_plain.json", want_output=True),
        "decode_frames.json": run_decode("decode_frames.json", want_output=True),
        "decode_errors.json": run_decode("decode_errors.json", want_output=False),
        "bombs.json": run_decode("bombs.json", want_output=False),
        "encode_props.json": run_encode_props("encode_props.json"),
        "differential.json": run_mixed("differential.json"),
    }
    total = sum(results.values())
    print(f"SHA256SUMS: {n_files} files verified")
    for name, n in results.items():
        print(f"  {name}: {n} cases green")
    print(f"OK — {total} vectors passed against the reference codec")


if __name__ == "__main__":
    main()
