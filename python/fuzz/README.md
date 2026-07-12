# Fuzzing (Test layer 4, coverage-guided)

Two [atheris](https://github.com/google/atheris) harnesses:

- `fuzz_decode.py` — `decode(arbitrary str)` must return bytes or raise exactly
  one `Ba64Error`, never crash.
- `fuzz_roundtrip.py` — `decode(encode(x)) == x` and the floor invariant, for
  arbitrary bytes and levels.

## Status in this environment

atheris does not build on the authoring toolchain (CPython 3.14 / macOS arm64);
it needs clang + a supported CPython (3.8–3.12 on Linux). These harnesses are
written to run unchanged there. The exhaustive **bit-flip and truncation sweeps**
in `tests/test_chaos.py` already exercise the same no-crash / no-silent-corruption
contract deterministically and run everywhere, so nothing is left unverified here
— continuous fuzzing is additive breadth, not the only guard.

## Running (Linux + atheris)

```sh
pip install atheris
python fuzz/seed_corpus.py corpus/          # seed from committed vectors
python fuzz/fuzz_decode.py    corpus/ -max_total_time=300
python fuzz/fuzz_roundtrip.py corpus/ -max_total_time=300
```

Nightly runs 4 h per harness (see `.github/workflows/nightly-fuzz.yml`). The
plan's 24 h-clean and OSS-Fuzz milestones (Phase 2 exit / Phase 6) run on that
infrastructure, not on a laptop.

## The permanent-corpus rule

Every finding is minimized and promoted into `vectors/decode_errors.json` (with
its required error code) so it regression-tests **all** implementations forever.
That is the SQLite discipline: a bug becomes a permanent test.
