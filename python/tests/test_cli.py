"""Test layer 3c — CLI round-trips through real pipes and files (IT backbone)."""

import base64
import os
import subprocess
import sys

import pytest

def _find_cli():
    # Walk upward for cli.py so the subprocess resolves under mutmut's mutants/
    # copy too (where the local dir may not contain cli.py).
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        cand = os.path.join(d, "cli.py")
        if os.path.exists(cand):
            return cand
        d = os.path.dirname(d)
    raise RuntimeError("cli.py not found")


CLI = _find_cli()


def run(args, stdin):
    return subprocess.run([sys.executable, CLI, *args], input=stdin,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.mark.parametrize("data", [b"", b"a", b"Hello, world!", b"A" * 4096,
                                  os.urandom(4096), bytes(range(256))])
def test_encode_decode_roundtrip_through_pipes(data):
    enc = run(["encode"], data)
    assert enc.returncode == 0
    dec = run(["decode"], enc.stdout)
    assert dec.returncode == 0
    assert dec.stdout == data


def test_encode_output_is_ascii_text_plus_newline():
    enc = run(["encode"], b"Hello, world!")
    assert enc.stdout == b"SGVsbG8sIHdvcmxkIQ==\n"


def test_decode_tolerates_trailing_newline_from_encode():
    # encode adds a newline; decode must strip exactly one and still verify
    enc = run(["encode"], b"A" * 1024)          # compressible -> "=..." frame
    assert enc.stdout.endswith(b"\n")
    dec = run(["decode"], enc.stdout)
    assert dec.returncode == 0 and dec.stdout == b"A" * 1024


def test_decode_error_prints_code_to_stderr_not_payload():
    r = run(["decode"], b"SGVsbG8")             # bad padding -> E_BASE64
    assert r.returncode == 2
    assert r.stderr.strip() == b"E_BASE64"
    assert r.stdout == b""


def test_decode_max_len_flag():
    data = b"x" * 2000
    enc = run(["encode"], data)
    r = run(["decode", "--max-decoded-len", "1999"], enc.stdout)
    # frame claims 2000; if compressed path was taken the limit trips
    if enc.stdout.startswith(b"="):
        assert r.returncode == 2 and r.stderr.strip() == b"E_LIMIT_EXCEEDED"
    else:
        assert r.returncode == 0


def test_encode_level_flag():
    data = b"repeat " * 100
    enc = run(["encode", "--level", "9"], data)
    dec = run(["decode"], enc.stdout)
    assert dec.stdout == data


@pytest.mark.slow
def test_large_stream_roundtrip_via_files(tmp_path):
    data = os.urandom(20 * 2 ** 20) + b"A" * (20 * 2 ** 20)  # 40 MiB mixed
    src = tmp_path / "in.bin"
    enc_f = tmp_path / "out.ba64"
    src.write_bytes(data)
    with open(src, "rb") as i, open(enc_f, "wb") as o:
        assert subprocess.run([sys.executable, CLI, "encode"], stdin=i,
                              stdout=o).returncode == 0
    with open(enc_f, "rb") as i:
        dec = subprocess.run([sys.executable, CLI, "decode"], stdin=i,
                             stdout=subprocess.PIPE)
    assert dec.stdout == data
