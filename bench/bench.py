#!/usr/bin/env python3
"""Benchmark ba64 vs standard base64 on representative payloads.

Produces the size-ratio table cited in the README (claim #3). Deterministic:
uses fixed synthetic-but-realistic samples, no network, no randomness. Run:

    python bench/bench.py            # markdown table
"""

import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import ba64


def json_api_response():
    return json.dumps({
        "users": [
            {"id": i, "name": f"user_{i}", "email": f"user_{i}@example.com",
             "active": True, "role": "member", "created_at": "2026-01-15T09:30:00Z"}
            for i in range(40)
        ],
        "page": 1, "per_page": 40, "total": 1287, "has_more": True,
    }).encode()


def log_lines():
    line = ('2026-07-11T12:34:56.789Z INFO  [request] method=GET '
            'path=/api/v1/users status=200 duration_ms=12 request_id=%08x\n')
    return "".join(line % i for i in range(120)).encode()


def jwt_like():
    # base64url tokens are high-entropy; compression cannot help -> floor
    return base64.urlsafe_b64encode(bytes(range(256)) * 4)


def html_fragment():
    return (b'<div class="card"><h2>Title</h2><p>Lorem ipsum dolor sit amet, '
            b'consectetur adipiscing elit.</p></div>\n' * 30)


def random_blob():
    import random
    rng = random.Random(0)
    return bytes(rng.getrandbits(8) for _ in range(4096))


SAMPLES = {
    "JSON API response": json_api_response(),
    "Structured logs": log_lines(),
    "HTML fragment": html_fragment(),
    "JWT-ish (base64url)": jwt_like(),
    "Random / encrypted blob": random_blob(),
}


def main():
    rows = []
    for name, data in SAMPLES.items():
        b64 = len(base64.b64encode(data))
        enc = ba64.encode(data)
        ba = len(enc)
        ratio = ba / b64
        rows.append((name, len(data), b64, ba, ratio, enc.startswith("=")))

    print(f"{'payload':<26} {'bytes':>7} {'base64':>8} {'ba64':>8} {'ratio':>7}  form")
    print("-" * 68)
    for name, raw, b64, ba, ratio, comp in rows:
        print(f"{name:<26} {raw:>7} {b64:>8} {ba:>8} {ratio:>6.0%}  "
              f"{'compressed' if comp else 'plain (floor)'}")

    print("\nMarkdown:\n")
    print("| Payload | base64 bytes | ba64 bytes | ba64 / base64 |")
    print("|---|--:|--:|--:|")
    for name, raw, b64, ba, ratio, comp in rows:
        print(f"| {name} | {b64:,} | {ba:,} | **{ratio:.0%}** |")


if __name__ == "__main__":
    main()
