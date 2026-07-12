# Shared fuzz corpus

One corpus, synced into each language's fuzzer format (execution_plan.md Phase 5).
Each file is a raw decoder input (a ba64 text) seeded from the committed vectors,
so every fuzzer starts from inputs that already reach every branch.

Seed / refresh:

```sh
python python/fuzz/seed_corpus.py fuzz-corpus
```

The permanent-corpus rule (SQLite discipline): every fuzzer finding is minimized,
filed, and — once fixed — promoted into `vectors/decode_errors.json` (with its
required code), so it regression-tests **all six** implementations forever. New
seeds from the corpus flow back here.

Per-language fuzzers that consume this corpus:

| Language | Fuzzer | Consume corpus |
|---|---|---|
| Python | atheris (`python/fuzz/`) | `python fuzz/fuzz_decode.py fuzz-corpus/` |
| Go | native `go test -fuzz` | copy into `go/testdata/fuzz/FuzzDecode/` |
| Rust | cargo-fuzz (libFuzzer) | `cargo fuzz run decode fuzz-corpus/` |
| TypeScript | jazzer.js | `jazzer harness.ts -- fuzz-corpus/` |
| Java | Jazzer | classpath + corpus dir |
| C# | SharpFuzz | libFuzzer corpus dir |
