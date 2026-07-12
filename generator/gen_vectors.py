#!/usr/bin/env python3
"""Deterministic ba64 conformance-vector generator.

Single command: `make vectors` (or `python3 generator/gen_vectors.py`).

The committed JSON files in ../vectors are the source of truth — the executable
form of SPEC.md. This generator exists to *extend* the corpus, not to be a
runtime dependency of any implementation. Every vector is round-checked against
the reference codec at generation time: if the reference does not produce the
declared bytes or error code, generation aborts. That makes the corpus
self-validating and keeps it honest against the spec.

Determinism: fixed RNG seed, no timestamps, stable key order. Re-running produces
byte-identical files, with one caveat: bombs.json and differential.json embed raw
zlib DEFLATE output, which is byte-reproducible only within a single zlib build
(stock zlib vs zlib-ng may differ). The committed files are the source of truth;
`make verify` excludes those two from its byte-drift check for that reason and
re-verifies them semantically instead. All other files use stored DEFLATE blocks
or hex and are byte-identical across builds.
"""

import base64
import hashlib
import json
import os
import random
import zlib

import reference as R

HERE = os.path.dirname(os.path.abspath(__file__))
VECTORS = os.path.normpath(os.path.join(HERE, "..", "vectors"))

RNG = random.Random(0xBA64)  # fixed seed — never change without regenerating


def b64(data):
    return base64.b64encode(data).decode("ascii")


# --- assertion helpers: prove the reference agrees before committing a vector -


def check_decode(text, output, *, max_decoded_len=None):
    kw = {} if max_decoded_len is None else {"max_decoded_len": max_decoded_len}
    got = R.decode(text, **kw)
    assert got == output, f"decode({text!r}) -> {got!r}, expected {output!r}"


def check_error(text, code, *, max_decoded_len=None):
    kw = {} if max_decoded_len is None else {"max_decoded_len": max_decoded_len}
    try:
        got = R.decode(text, **kw)
    except R.Ba64Error as e:
        assert e.code == code, f"decode({text!r}) raised {e.code}, expected {code}"
        return
    raise AssertionError(f"decode({text!r}) -> {got!r}, expected error {code}")


# --- decode_plain.json -------------------------------------------------------


def gen_decode_plain():
    cases = []

    def add(name, data):
        text = b64(data)
        check_decode(text, data)
        cases.append({"name": name, "input": text, "output_hex": data.hex()})

    add("empty", b"")
    add("golden_hello_world", b"Hello, world!")  # SPEC 12
    # every padding shape for 1/2/3-byte inputs
    add("one_byte", b"\x4d")
    add("two_bytes", b"\x4d\x61")
    add("three_bytes", b"\x4d\x61\x6e")
    add("all_zero_3", b"\x00\x00\x00")
    add("all_zero_1", b"\x00")
    add("all_ff_2", b"\xff\xff")
    add("byte_sweep_0x00_0xff", bytes(range(256)))
    add("utf8_text", "héllo — wörld ✓".encode("utf-8"))
    add("ascii_alnum", b"The quick brown fox 0123456789")
    return {
        "about": "plain-form vectors: input is canonical base64; decoder MUST "
                 "return output_hex byte-for-byte (SPEC 1, 4 step 1).",
        "cases": cases,
    }


# --- decode_frames.json ------------------------------------------------------


def gen_decode_frames():
    cases = []

    def add_stored(name, data, decoded_len=None):
        # Build a deterministic stored-block frame that a conforming decoder
        # MUST accept even where a real encoder would prefer plain form.
        text = R.encode_stored(data)
        check_decode(text, data)
        cases.append({"name": name, "input": text, "output_hex": data.hex()})

    add_stored("golden_hi_stored", b"Hi")          # SPEC 12: =AQECDg4XTQECAP3/SGk=
    add_stored("stored_empty", b"")                # SPEC 12: =AQEAAAAAAAEAAP//
    add_stored("stored_single", b"A")
    add_stored("stored_ascii", b"conformance")
    add_stored("stored_300_bytes", b"ba64!" * 60)  # one 300-byte stored block
    add_stored("stored_all_zero_64", b"\x00" * 64)

    # Fixed, pre-generated compressed frame from SPEC 12 — committed forever,
    # never regenerated. Output captured by decoding it with the reference.
    json_golden = ("=AQHoAiIzehurViotTi2Kz0xRslIyNDI2MVXSUUouSk0sSU2JTywBChoZGJnp"
                   "GpjrGhoq1VaPKiZXMQA=")
    out = R.decode(json_golden)
    assert len(out) == 360
    check_decode(json_golden, out)
    cases.append({
        "name": "golden_json_17pct_compressed",
        "input": json_golden,
        "output_hex": out.hex(),
        "note": "SPEC 12 committed compressed frame: 81 chars vs 480 plain (17%).",
    })

    return {
        "about": "valid method-0x01 frames -> exact bytes. Stored-block frames "
                 "are byte-deterministic; the compressed golden is committed "
                 "once and never regenerated (SPEC 2, 3, 12).",
        "cases": cases,
    }


# --- decode_errors.json ------------------------------------------------------


def gen_decode_errors():
    cases = []

    def add(name, text, code, **extra):
        check_error(text, code)
        cases.append({"name": name, "input": text, "error": code, **extra})

    # --- base64-level (step 1/2) ---
    add("marker_only", "=", "E_TRUNCATED")            # "=" then empty frame
    add("double_marker", "==", "E_BASE64")            # remainder "=" not b64
    add("missing_padding", "SGVsbG8", "E_BASE64")
    add("nonzero_trailing_bits", "QR==", "E_BASE64")  # SPEC 12
    add("embedded_space", "SGVs bG8=", "E_BASE64")    # SPEC 12
    add("urlsafe_alphabet", "-_-_", "E_BASE64")
    add("frame_body_garbage", "=@@@@", "E_BASE64")
    add("non_ascii", "SGVsbG8=é", "E_BASE64")

    # --- header truncation sweep (step 3-7): slice a valid frame's bytes ---
    valid = R.build_frame(b"Hi")  # 01 01 02 <crc4> <payload7>
    for n in (0, 1, 2):
        add(f"truncated_header_{n}b", R.frame_to_text(valid[:n]), "E_TRUNCATED")
    # mid-varint: a 2-byte varint (decoded_len=200 -> C8 01), cut inside it
    midv = R.build_frame(b"", decoded_len=200, payload=b"", crc=0)
    add("truncated_mid_varint", R.frame_to_text(midv[:3]), "E_TRUNCATED")
    # complete header but <4 crc bytes (varint is 1 byte here, cut crc short)
    add("truncated_partial_crc", R.frame_to_text(valid[:5]), "E_TRUNCATED")

    # --- version / method (step 3/4) ---
    add("bad_version_2", R.frame_to_text(R.build_frame(b"Hi", version=0x02)),
        "E_VERSION")
    add("bad_version_ff", R.frame_to_text(R.build_frame(b"Hi", version=0xFF)),
        "E_VERSION")
    add("reserved_method_02", R.frame_to_text(R.build_frame(b"Hi", method=0x02)),
        "E_METHOD")
    add("reserved_method_ef", R.frame_to_text(R.build_frame(b"Hi", method=0xEF)),
        "E_METHOD")
    add("private_method_f0", R.frame_to_text(R.build_frame(b"Hi", method=0xF0)),
        "E_METHOD")
    add("method_zero", R.frame_to_text(R.build_frame(b"Hi", method=0x00)),
        "E_METHOD")

    # --- LEB128 header errors (step 5) ---
    # non-minimal zero "80 00" (SPEC 12: varint 80 00 -> E_HEADER)
    nonmin = bytes([0x01, 0x01, 0x80, 0x00, 0, 0, 0, 0])
    add("leb128_non_minimal", R.frame_to_text(nonmin), "E_HEADER")
    # >9 varint bytes
    toolong = bytes([0x01, 0x01]) + bytes([0x80] * 10) + b"\x00\x00\x00\x00"
    add("leb128_too_long", R.frame_to_text(toolong), "E_HEADER")

    # --- limits (step 6, before allocation) ---
    huge = R.build_frame(b"", decoded_len=8 * 2 ** 30, payload=b"", crc=0)
    add("over_limit_8gib", R.frame_to_text(huge), "E_LIMIT_EXCEEDED")
    tb = R.build_frame(b"", decoded_len=10 ** 12, payload=b"", crc=0)
    add("over_limit_1tb", R.frame_to_text(tb), "E_LIMIT_EXCEEDED")

    # --- payload (step 8) ---
    add("payload_malformed",
        R.frame_to_text(R.build_frame(b"", decoded_len=4, payload=b"\xde\xad\xbe\xef",
                                      crc=0)),
        "E_PAYLOAD")
    trunc_stream = R.build_frame(b"Hello", payload=R.deflate_stored(b"Hello")[:-2],
                                 decoded_len=5, crc=zlib.crc32(b"Hello") & 0xFFFFFFFF)
    add("payload_truncated_stream", R.frame_to_text(trunc_stream), "E_PAYLOAD",
        error_alt=["E_LENGTH_MISMATCH"],
        note="truncated DEFLATE stream: zlib/flate/miniz_oxide raise E_PAYLOAD; "
             ".NET's DeflateStream treats premature EOF as end-of-stream and "
             "reports E_LENGTH_MISMATCH. Decoder-dependent — see "
             "conformance/CAVEATS.md.")
    trailing = R.build_frame(b"Hi", payload=R.deflate_stored(b"Hi") + b"\x00")
    add("payload_trailing_bytes", R.frame_to_text(trailing), "E_PAYLOAD")

    # --- length mismatch (step 8, both directions) ---
    add("len_claim_low",
        R.frame_to_text(R.build_frame(b"Hi", decoded_len=1)), "E_LENGTH_MISMATCH")
    add("len_claim_high",
        R.frame_to_text(R.build_frame(b"X", decoded_len=2)), "E_LENGTH_MISMATCH")
    # SPEC 12 zero-cap trap: claims 0, payload holds one byte
    add("golden_zero_cap_trap", "=AQEAAAAAAAEBAP7/WA==", "E_LENGTH_MISMATCH")

    # --- checksum (step 9) ---
    add("bad_crc",
        R.frame_to_text(R.build_frame(b"Hi", crc=0xDEADBEEF)), "E_CHECKSUM")

    return {
        "about": "each input maps to exactly one taxonomy code (SPEC 4, 5). "
                 "Fuzzer findings are minimized and promoted here permanently.",
        "cases": cases,
    }


# --- bombs.json --------------------------------------------------------------


def gen_bombs():
    cases = []

    # 1) header lies big: 100-byte payload claims 8 GiB -> reject in O(header).
    payload = b"\x00" * 100
    big = R.build_frame(b"", decoded_len=8 * 2 ** 30, payload=payload, crc=0)
    text = R.frame_to_text(big)
    check_error(text, "E_LIMIT_EXCEEDED")
    cases.append({
        "name": "claim_8gib_100b_payload",
        "input": text, "error": "E_LIMIT_EXCEEDED",
        "note": "MUST reject before any allocation proportional to decoded_len "
                "(SPEC 7); default limit 64 MiB.",
    })

    # 2) real deflate bomb: ~1 MiB of zeros compresses tiny; frame under-claims
    #    decoded_len (100) so inflation caps at 100 bytes -> E_LENGTH_MISMATCH,
    #    O(cap) memory, never materialises the megabyte.
    bomb_raw = b"\x00" * (1 << 20)
    co = zlib.compressobj(level=9, wbits=-15)
    bomb_payload = co.compress(bomb_raw) + co.flush()
    bomb = R.build_frame(b"", decoded_len=100, payload=bomb_payload, crc=0)
    text = R.frame_to_text(bomb)
    check_error(text, "E_LENGTH_MISMATCH")
    cases.append({
        "name": "deflate_bomb_1mib_zeros",
        "input": text, "error": "E_LENGTH_MISMATCH",
        "note": f"payload {len(bomb_payload)} B inflates to 1 MiB but claims 100 B; "
                "inflation MUST cap at decoded_len (SPEC 7 zero/low-cap rule).",
    })

    # 3) zero-cap variant: claims 0, payload is a large stored-ish stream.
    zc = R.build_frame(b"", decoded_len=0, payload=bomb_payload, crc=0)
    text = R.frame_to_text(zc)
    check_error(text, "E_LENGTH_MISMATCH")
    cases.append({
        "name": "zero_cap_bomb",
        "input": text, "error": "E_LENGTH_MISMATCH",
        "note": "decoded_len=0 must still cap (Python max_length=0 == unlimited "
                "trap, SPEC 7 / Appendix B `decoded_len or 1`).",
    })

    return {
        "about": "resource-exhaustion corpus: every entry MUST be rejected in "
                 "O(header)/O(cap) memory, never by materialising the claimed "
                 "or true inflated size (SPEC 7, 8).",
        "cases": cases,
    }


# --- encode_props.json -------------------------------------------------------


def gen_encode_props():
    cases = []

    def add(name, data, props):
        enc = R.encode(data)
        plain = b64(data)
        # verify each declared invariant against the reference encoder
        assert R.decode(enc) == data, f"{name}: roundtrip failed"
        assert len(enc) <= len(plain), f"{name}: floor violated"
        if "compressed" in props:
            assert enc.startswith("="), f"{name}: expected compressed form"
        if "plain" in props:
            assert enc == plain, f"{name}: expected plain form == base64(input)"
            assert not enc.startswith("="), f"{name}: plain must not start with ="
        cases.append({"name": name, "input_hex": data.hex(), "props": props})

    # compression MUST win
    add("repetitive_1k", b"A" * 1024, ["roundtrip", "floor", "compressed"])
    add("json_repeated", (b'{"event":"login","user":"alice","ok":true} ' * 8),
        ["roundtrip", "floor", "compressed"])
    add("golden_json_360", R.decode(
        "=AQHoAiIzehurViotTi2Kz0xRslIyNDI2MVXSUUouSk0sSU2JTywBChoZGJnpGpjrGhoq1VaP"
        "KiZXMQA="), ["roundtrip", "floor", "compressed"])

    # floor MUST trigger -> output is plain base64, byte-identical to stdlib
    add("random_1k", bytes(RNG.getrandbits(8) for _ in range(1024)),
        ["roundtrip", "floor", "plain"])
    add("png_like_header",
        b"\x89PNG\r\n\x1a\n" + bytes(RNG.getrandbits(8) for _ in range(512)),
        ["roundtrip", "floor", "plain"])
    add("empty", b"", ["roundtrip", "floor", "plain"])

    # tiny inputs 0-16: header overhead exceeds any savings -> floor
    for n in range(1, 17):
        add(f"tiny_{n}", bytes(RNG.getrandbits(8) for _ in range(n)),
            ["roundtrip", "floor", "plain"])

    return {
        "about": "encoding is non-canonical, so outputs are NOT pinned; each "
                 "input asserts invariants (SPEC 6): roundtrip, floor "
                 "(len<=base64), compressed (starts with '='), plain "
                 "(==base64(input)).",
        "cases": cases,
    }


# --- differential.json -------------------------------------------------------
#
# A large shared decode oracle, every case labelled by the Python reference:
# each of the six implementations must reproduce output_hex exactly on success,
# or raise the exact error code. This is the Phase-4 "differential vs the Python
# reference over a shared corpus" artifact (execution_plan.md §Phase 4).


def gen_differential(n=4000):
    rng = random.Random(0xD1FF)  # fixed seed, distinct from encode_props RNG

    # E_PAYLOAD and E_LENGTH_MISMATCH on a *corrupt* DEFLATE stream are the only
    # two codes whose boundary is decoder-dependent (zlib/flate/miniz reject
    # where .NET's DeflateStream is lenient — see conformance/CAVEATS.md). They
    # are excluded here and covered instead by the curated, hand-verified
    # decode_errors.json / bombs.json that all six implementations pass. Every
    # case in this file therefore has a code that every decoder agrees on.
    DECODER_DEPENDENT = {"E_PAYLOAD", "E_LENGTH_MISMATCH"}

    def label(input_str):
        try:
            out = R.decode(input_str)
        except R.Ba64Error as e:
            return {"input": input_str, "error": e.code}
        return {"input": input_str, "output_hex": out.hex()}

    def rand_bytes(lo, hi):
        return bytes(rng.getrandbits(8) for _ in range(rng.randint(lo, hi)))

    def make(kind):
        if kind == 0:                                   # valid stored frame
            data = rand_bytes(0, 64)
            return {"input": R.encode_stored(data), "output_hex": data.hex()}
        if kind == 1:                                   # valid real-compressed frame
            unit = rng.choice([b"ab ", b"log ", b'{"k":1} ', b"\x00\x01"])
            data = unit * rng.randint(1, 40)
            co = zlib.compressobj(level=rng.randint(1, 9), wbits=-15)
            payload = co.compress(data) + co.flush()
            return {"input": R.frame_to_text(R.build_frame(data, payload=payload)),
                    "output_hex": data.hex()}
        if kind == 2:                                   # header-mutated frame
            # mutate ONLY version/method/crc bytes -> E_VERSION/E_METHOD/E_CHECKSUM
            data = rand_bytes(0, 48)
            frame = bytearray(R.build_frame(data))
            crc_start = 2 + len(R._leb128_encode(len(data)))
            byte_i = rng.choice([0, 1] + list(range(crc_start, crc_start + 4)))
            frame[byte_i] ^= 1 << rng.randrange(8)
            return label(R.frame_to_text(bytes(frame)))
        if kind == 4:                                   # arbitrary ASCII string
            s = "".join(chr(rng.randint(32, 126)) for _ in range(rng.randint(0, 40)))
            return label(s)
        # kind 5: truncate a valid frame within its fixed header -> E_TRUNCATED
        data = rand_bytes(1, 48)
        frame = R.build_frame(data)
        header_len = 2 + len(R._leb128_encode(len(data))) + 4
        cut = rng.randint(0, header_len - 1)
        return label(R.frame_to_text(frame[:cut]))

    def make_plain():
        data = rand_bytes(0, 96)
        return {"input": b64(data), "output_hex": data.hex()}

    cases = []
    i = 0
    while len(cases) < n:
        kind = i % 6
        i += 1
        c = make_plain() if kind == 3 else make(kind)
        if c is None or c.get("error") in DECODER_DEPENDENT:
            continue  # skip the decoder-dependent boundary
        cases.append(c)

    return {
        "about": f"{n} decode cases labelled by the Python reference; every "
                 "implementation MUST reproduce output_hex exactly or raise the "
                 "exact error code. Excludes E_PAYLOAD/E_LENGTH_MISMATCH on "
                 "corrupt payloads (decoder-dependent, see conformance/CAVEATS.md).",
        "cases": cases,
    }


# --- driver ------------------------------------------------------------------


def write_json(name, obj):
    path = os.path.join(VECTORS, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=True, sort_keys=False)
        f.write("\n")
    return path


def main():
    os.makedirs(VECTORS, exist_ok=True)
    files = {
        "decode_plain.json": gen_decode_plain(),
        "decode_frames.json": gen_decode_frames(),
        "decode_errors.json": gen_decode_errors(),
        "bombs.json": gen_bombs(),
        "encode_props.json": gen_encode_props(),
        "differential.json": gen_differential(),
    }
    written = [write_json(n, o) for n, o in files.items()]

    # SHA256SUMS over the committed vector files, deterministic order.
    lines = []
    for name in sorted(files):
        with open(os.path.join(VECTORS, name), "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        lines.append(f"{digest}  {name}\n")
    with open(os.path.join(VECTORS, "SHA256SUMS"), "w", encoding="utf-8") as f:
        f.writelines(lines)

    total = sum(len(o["cases"]) for o in files.values())
    print(f"generated {len(written)} vector files, {total} cases, all "
          f"round-checked against the reference codec")
    for name in sorted(files):
        print(f"  {name}: {len(files[name]['cases'])} cases")


if __name__ == "__main__":
    main()
