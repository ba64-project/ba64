"""Test layer 3a — the shared conformance corpus, exact error codes."""

import pytest

import ba64
from conftest import load_vectors


@pytest.mark.parametrize("c", load_vectors("decode_plain.json"),
                         ids=lambda c: c["name"])
def test_decode_plain(c):
    assert ba64.decode(c["input"]) == bytes.fromhex(c["output_hex"])


@pytest.mark.parametrize("c", load_vectors("decode_frames.json"),
                         ids=lambda c: c["name"])
def test_decode_frames(c):
    assert ba64.decode(c["input"]) == bytes.fromhex(c["output_hex"])


@pytest.mark.parametrize("c", load_vectors("decode_errors.json"),
                         ids=lambda c: c["name"])
def test_decode_errors(c):
    with pytest.raises(ba64.Ba64Error) as ei:
        ba64.decode(c["input"])
    assert ei.value.code in [c["error"]] + c.get("error_alt", []), c["name"]


@pytest.mark.parametrize("c", load_vectors("bombs.json"),
                         ids=lambda c: c["name"])
def test_bombs_rejected(c):
    kw = {"max_decoded_len": c["max_decoded_len"]} if "max_decoded_len" in c else {}
    with pytest.raises(ba64.Ba64Error) as ei:
        ba64.decode(c["input"], **kw)
    assert ei.value.code == c["error"], c["name"]


@pytest.mark.parametrize("c", load_vectors("encode_props.json"),
                         ids=lambda c: c["name"])
def test_encode_props(c):
    import base64
    data = bytes.fromhex(c["input_hex"])
    enc = ba64.encode(data)
    plain = base64.b64encode(data).decode()
    props = c["props"]
    assert ba64.decode(enc) == data                       # roundtrip
    assert len(enc) <= len(plain)                          # floor
    if "compressed" in props:
        assert enc.startswith("=")
    if "plain" in props:
        assert enc == plain
