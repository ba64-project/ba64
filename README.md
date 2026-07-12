# ba64

A text encoding for binary data that is **never larger than standard base64**.
An encoder races raw DEFLATE against plain base64 and emits whichever final text
is shorter. Compressed output is marked by a leading `=`; everything else is
byte-identical to base64. A CRC-32 over the *decoded* bytes means a decoder
never silently returns wrong data.

Drop-in migration: the plain form **is** base64, so a ba64 decoder reads all your
existing base64 unchanged. Turn on compressing encoders only once every reader of
a channel understands ba64 (see [SPEC.md §9](spec.md)).

**Three honest claims** (each measured, not asserted):

1. **Never returns wrong bytes without an error.** The CRC-32 is over the decoded
   bytes. Across all six implementations, exhaustive bit-flip, truncation, and
   frame-corruption sweeps (24,480 single-bit frame corruptions + full bit-flip
   and truncation sweeps) produced **zero silent corruptions** — every corrupt
   frame is a typed error, never wrong data.
2. **Never larger than base64.** The floor rule guarantees
   `len(ba64(x)) ≤ len(base64(x))` for every input, by construction.
3. **Much smaller on structured payloads.** Measured by `bench/bench.py`:

   | Payload | base64 bytes | ba64 bytes | ba64 / base64 |
   |---|--:|--:|--:|
   | JSON API response | 7,256 | 633 | **9%** |
   | Structured logs | 18,720 | 581 | **3%** |
   | HTML fragment | 4,080 | 165 | **4%** |
   | Random / encrypted blob | 5,464 | 5,464 | **100% (floor → plain)** |

   Ratios depend on redundancy; incompressible data always takes the floor.

> [!IMPORTANT]
> **Encoding is non-canonical.** The same input may produce different valid ba64
> texts across encoders, versions, or compression levels (DEFLATE is a relation,
> not a function). Any equality check, deduplication, cache key, or MAC/HMAC MUST
> operate on the **decoded bytes**, never on the ba64 text. See
> [SPEC.md §6.5 / §8](spec.md) and [SECURITY.md](SECURITY.md).

## Format at a glance

```
plain form:       base64(input)                       # never starts with "="
compressed form:  "=" + base64(frame)
frame:            version(0x01) ‖ method(0x01) ‖ decoded_len(LEB128)
                  ‖ crc32(decoded bytes, LE) ‖ raw-DEFLATE payload
```

The full normative format, decoding algorithm, and nine-code error taxonomy are
in **[spec.md](spec.md)** (this repo's frozen `SPEC.md`). Golden examples:

```
""                       -> b""                 (empty plain form)
"SGVsbG8sIHdvcmxkIQ=="   -> b"Hello, world!"    (plain; compression can't beat 20 chars)
"=AQECDg4XTQECAP3/SGk="  -> b"Hi"               (deterministic stored-block frame)
```

## Design guarantees (structural)

These hold by construction from the spec, independent of implementation:

1. **Never larger than base64** — the floor rule: the compressed form is emitted
   only when strictly shorter, so `len(ba64(x)) ≤ len(base64(x))` for every input.
2. **Never wrong bytes without an error** — the CRC-32 is over the decoded bytes,
   so any channel corruption or decompressor divergence surfaces as `E_CHECKSUM`,
   never as silently wrong output.
3. **Bomb-safe by construction** — the decoder rejects an oversized claim before
   allocating and caps inflation at `decoded_len`; a 100-byte frame claiming 8 GiB
   costs O(header) work.

## Status

**Phases 0–4 complete: format frozen, corpus built, and all six implementations
ship and agree.** `bash conformance/run_all.sh` drives every language against the
one shared corpus.

| Area | State |
|---|---|
| `spec.md` (frozen `SPEC.md`) | ✅ v1, frozen once vectors tagged |
| `vectors/` corpus + generator (incl. 4000-case differential) | ✅ 4073 cases, self-validated, checksummed |
| `python/` reference | ✅ 100% branch, 95.5% mutation, chaos green |
| `js/` (TypeScript) | ✅ 100% branch (c8/built-in), all vectors + differential |
| `go/` | ✅ 100% statements, native fuzz clean, all vectors + differential |
| `rust/` (miniz_oxide only) | ✅ proptest + chaos, all vectors + differential |
| `java/` | ✅ ~49.5k checks, all vectors + differential |
| `csharp/` | ✅ ~49.5k checks, all vectors + differential |
| 6-way conformance + **6×6 matrix** (`conformance/run_all.sh`, `run.py`) | ✅ 36/36 pairs agree over 10k inputs |
| Shared fuzz corpus + nightly fuzz CI | ✅ `fuzz-corpus/`, Go native + Python atheris |
| Packaging (PyPI/npm/crates.io/Maven/NuGet/Go tag) + `RELEASING.md` | ✅ manifests ready; publish is a gated manual step |
| Benchmark + carrier (Temporal `PayloadCodec`) + OSS-Fuzz config | ✅ `bench/`, `carriers/`, `oss-fuzz/` |
| Internet-Draft (`draft/`) | ⏳ Phase 3 |

One documented cross-language caveat (`.NET` on truncated DEFLATE) lives in
[conformance/CAVEATS.md](conformance/CAVEATS.md).

Quick start: `make verify && make cross && make matrix` runs the corpus gate, the
six-way conformance, and the 6×6 matrix. See [RELEASING.md](RELEASING.md) for the
coordinated-release checklist.

Measured to date: 100% branch coverage and ≥95% mutation kill on the Python
reference; 36/36 cross-pair agreement over 10k inputs. Still on the roadmap:
24 h+ continuous fuzzing (nightly CI) and OSS-Fuzz enrollment (`oss-fuzz/`).

## The corpus

```
vectors/
  decode_plain.json    plain base64 passthrough -> exact bytes
  decode_frames.json   valid frames -> exact bytes (stored-block + committed golden)
  decode_errors.json   input -> required error code (the whole taxonomy)
  bombs.json           resource-exhaustion frames -> must reject in O(header)/O(cap)
  encode_props.json    inputs + invariants (roundtrip, floor, compressed, plain)
  differential.json    4000 Python-labeled cases every implementation must match
  SHA256SUMS           committed digests; runners verify before consuming
```

Regenerate/extend (deterministic, fixed seed):

```sh
make vectors        # generator/gen_vectors.py -> vectors/*.json + SHA256SUMS
make conformance    # conformance/run_reference.py -> drives every vector
```

The committed JSON is the source of truth; the generator exists to **extend** the
corpus, not to be a runtime dependency. Every vector is round-checked against the
reference codec at generation time — a vector whose declared output/error the
reference can't reproduce aborts the build.

## Specification & citation

The normative format is [spec.md](spec.md) (frozen `SPEC.md`). It is also written
as an independent Internet-Draft in [draft/draft-ba64-00.md](draft/draft-ba64-00.md)
(kramdown-rfc), with the conformance vectors as an appendix — the draft *is* the
spec. Cite as:

```
[EDITOR], "ba64: A Binary-to-Text Encoding That Is Never Larger Than Base64",
Internet-Draft draft-EDITOR-ba64-00, work in progress.
```

## Distribution

Vendoring is encouraged — each implementation is a single stdlib-only file (Rust's
`miniz_oxide` is the one sanctioned dependency; never hand-roll inflate).

## License / spec status

v1 is frozen forever once the conformance vectors are tagged; evolution happens
only through new method IDs. Decoders reject what they don't know, loudly and
typed. See [spec.md §13](spec.md).
