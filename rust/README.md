# ba64 — Rust

Single file (`src/lib.rs`). One runtime dependency — **`miniz_oxide`** for
DEFLATE — which is the format's sanctioned exception (spec §3: never hand-roll
inflate). base64 and CRC-32 are implemented in-file, so the runtime dependency
surface is exactly one crate.

```rust
ba64::encode(b"Hello, world!");            // "SGVsbG8sIHdvcmxkIQ=="
ba64::decode("=AQECDg4XTQECAP3/SGk=")?;    // b"Hi"
// Err is ba64::Error; match on it or call .code() -> &str
```

`encode` / `encode_level`, `decode` / `decode_max`; `Error` enum with
`.code()` from the nine-code taxonomy.

## Test & verify

```sh
cargo test        # conformance + differential + chaos (integration) + proptest
```

- Passes every shared vector + the 4000-case differential vs the Python
  reference; bit-flip / truncation sweeps and the capped-inflation bomb green.
- Property tests via `proptest` (dev-dependency); `serde_json` (dev-dependency)
  loads the shared corpus.

## Notes

- Inflation uses `miniz_oxide`'s low-level core so output is capped at
  `decoded_len` and the consumed-byte count gives exact trailing-byte detection.
- Buffer sizing is bounded by `min(decoded_len, 1032·payload + 64)` so a small
  frame claiming a huge size stays cheap (spec §7).
- `wasm32` target and `cargo-fuzz` / `cargo-llvm-cov` are follow-ups (Phase 4
  extras / Phase 6); correctness here is covered by the shared corpus + proptest
  + chaos sweeps.
