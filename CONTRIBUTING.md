# Contributing to ba64

Six versions share one spec. The JSON files in `vectors/` are the source of
truth. Every version must reproduce every decode vector's bytes exactly. Every
version must raise every error vector's exact code. If they disagree, something is
wrong. CI will not let it merge.

The normative format spec is kept separately. `vectors/` is its runnable form.
That is what every version is tested against.

## Layout

```
vectors/           the runnable spec. decode, encode, error, and differential cases
generator/         builds vectors/ deterministically. extend it, do not hand-edit
conformance/       cross-language runners (run_all.sh, run.py) and CAVEATS.md
python/ js/ go/ rust/ java/ csharp/    one single-file codec each
bench/ carriers/ oss-fuzz/             benchmark, Temporal codec, fuzzing config
```

## Run the tests

Corpus and the full matrix. Needs the toolchains installed.

```sh
make verify     # corpus is deterministic and passes the reference
make cross      # every language passes the shared corpus
make matrix     # 6x6 encoder and decoder agreement over 10k inputs
```

Per language:

| Language | Command (from repo root) |
|---|---|
| Python | `make py-cov` then `make py-mutation` |
| TypeScript | `cd js && node conformance.ts && node --test` |
| Go | `cd go && go test -cover ./...` |
| Rust | `cd rust && cargo test` |
| Java | `cd java && javac Ba64.java Ba64Test.java && java Ba64Test` |
| C# | `cd csharp && dotnet run -c Release` |

## Ground rules

- One file per codec. No runtime dependencies. Rust uses one crate, `miniz_oxide`,
  for DEFLATE. Never hand-roll DEFLATE.
- Follow the spec's ordered checks exactly. Every bad input maps to one error
  code. Mirror the Python reference in `python/ba64.py`.
- The wire format is frozen. v1 never changes. New features only come through new
  method IDs in a future spec revision.
- A bug becomes a permanent test. Fix it. Then add the minimized input to
  `vectors/decode_errors.json` through the generator. Now all six versions are
  tested against it forever.
- Encoding is not unique. Do not assert exact encoder output. Assert the
  invariants instead. Those are roundtrip, floor, and marker-iff-smaller.

## Style

- Keep commit messages short. For example `initial` or `fix rust cap`.
- Match the surrounding code. Keep comments small.
- Write plain sentences. Avoid em dashes.
