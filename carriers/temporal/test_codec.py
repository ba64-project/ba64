"""Tests for the ba64 Temporal codec's byte-level transform (no SDK needed)."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from ba64_codec import decode_payload_bytes, encode_payload_bytes


def test_roundtrip_realistic_workflow_args():
    raw = json.dumps({
        "workflow": "ProcessOrder",
        "args": [{"order_id": i, "items": ["sku-1", "sku-2"], "total": 42.50,
                  "customer": {"id": i, "tier": "gold"}} for i in range(20)],
    }).encode()
    encoded = encode_payload_bytes(raw)
    assert decode_payload_bytes(encoded) == raw
    assert len(encoded) < len(raw), "structured workflow args should shrink"
    print(f"\nworkflow args: {len(raw)} B raw -> {len(encoded)} B ba64 "
          f"({len(encoded) / len(raw):.0%})")


def test_incompressible_takes_floor():
    raw = os.urandom(2048)
    encoded = encode_payload_bytes(raw)
    assert decode_payload_bytes(encoded) == raw
    import base64
    assert len(encoded) == len(base64.b64encode(raw))  # floor: plain base64


def test_limit_is_enforced():
    raw = b"x" * 100_000
    encoded = encode_payload_bytes(raw)
    try:
        decode_payload_bytes(encoded, max_decoded_len=1000)
        assert False, "expected limit rejection"
    except ba64_error() as e:
        assert e.code == "E_LIMIT_EXCEEDED"


def ba64_error():
    import ba64
    return ba64.Ba64Error


if __name__ == "__main__":
    test_roundtrip_realistic_workflow_args()
    test_incompressible_takes_floor()
    test_limit_is_enforced()
    print("carrier (Temporal PayloadCodec) transform: all tests passed")
