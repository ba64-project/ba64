# Contributing to ba64

Six implementations, **one shared spec**: the JSON files in `vectors/` are the
source of truth. Every implementation must reproduce every decode vector's bytes
exactly and raise every error vector's exact code. If they disagree, something is
wrong — and CI won't let it merge.

The normative format spec is maintained separately; `vectors/` is its executable
form and what every implementation is tested against.

## Layout

```
vectors/           the executable spec — decode/encode/error/differential cases
generator/         builds vectors/ deterministically (extend it, don't hand-edit)
conformance/       cross-language runners (run_all.sh, run.py) + CAVEATS.md
python/ js/ go/ rust/ java/ csharp/    one single-file codec each
bench/ carriers/ oss-fuzz/             benchmark, Temporal codec, fuzzing config
```

## Run the tests

Corpus + the whole matrix (needs the toolchains installed):

```sh
make verify     # corpus is deterministic and passes the reference
make cross      # every language passes the shared corpus
make matrix     # 6×6 encoder/decoder agreement over 10k inputs
```

Per language:

| Language | Command (from repo root) |
|---|---|
| Python | `make py-cov` (100% branch gate) · `make py-mutation` |
| TypeScript | `cd js && node conformance.ts && node --test` |
| Go | `cd go && go test -cover ./...` |
| Rust | `cd rust && cargo test` |
| Java | `cd java && javac Ba64.java Ba64Test.java && java Ba64Test` |
| C# | `cd csharp && dotnet run -c Release` |

## Ground rules

- **One file, no runtime deps** per codec (Rust's `miniz_oxide` is the single
  sanctioned exception — never hand-roll DEFLATE).
- **Match the spec's ordered checks** exactly, so every bad input maps to one
  deterministic error code (mirror the Python reference in `python/ba64.py`).
- **The wire format is frozen.** v1 never changes; new capability only ever comes
  through new method IDs in a future spec revision.
- **A bug becomes a permanent test.** Fix it, then add the minimized input to
  `vectors/decode_errors.json` (via the generator) so all six languages are
  regression-tested against it forever.
- Encoding is non-canonical — never assert exact encoder *output*; assert the
  invariants (roundtrips, floor, marker-iff-smaller).

## Style

- Commit messages are terse (e.g. `initial`, `fix rust cap`).
- Match the surrounding code; keep comments small.
