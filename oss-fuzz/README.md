# OSS-Fuzz integration

Ready-to-submit [OSS-Fuzz](https://github.com/google/oss-fuzz) config for ba64 —
free continuous fuzzing on the same infrastructure as SQLite and zlib.

Files here mirror what lands in `oss-fuzz/projects/ba64/`:

- `project.yaml` — metadata, sanitizers (ASan + UBSan), engine (libFuzzer).
- `Dockerfile` — clones the repo onto the Python base-builder.
- `build.sh` — compiles `python/fuzz/fuzz_decode.py` and `fuzz_roundtrip.py`,
  seeding each from the shared corpus (`python/fuzz/seed_corpus.py`).

Submission is a manual, gated step (a PR to google/oss-fuzz with a maintainer as
`primary_contact`), done after v1 publication. The Rust harnesses (`rust/`, via
cargo-fuzz) attach as a second `language: rust` project.

**Permanent-corpus rule:** every OSS-Fuzz finding is minimized and promoted into
`vectors/decode_errors.json`, so it regression-tests all six implementations
forever.
