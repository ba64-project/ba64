# Releasing ba64

One version, one tagged commit, six registries. `VERSION` is the single source of
truth; every package manifest carries the same number. Publishing is a **gated,
credentialed, manual** step — this file is the checklist, not an automated push.

## Pre-flight (must all be green on the release commit)

```sh
make verify           # corpus deterministic + reference green
make py-gate          # 100% branch, slow ITs
make py-mutation      # >=95% killed, survivors documented
make cross            # all six pass the shared corpus
make matrix           # 6x6 encoder/decoder agreement over 10k inputs
python bench/bench.py  # size table matches the README claims
```

The README's three claims must still hold: no silent corruption (sweeps),
never-larger-than-base64 (floor), and the benchmark table.

## Tag

```sh
git tag -a v$(cat VERSION) -m "ba64 v$(cat VERSION)"
git push origin v$(cat VERSION)
```

All six packages publish from **this exact commit**.

## Per-registry publish

| Registry | Dir | Command |
|---|---|---|
| PyPI | `python/` | `python -m build && twine upload dist/*` |
| npm | `js/` | `npm publish --access public` |
| crates.io | `rust/` | `cargo publish` |
| Go module | `go/` | consumers pin the git tag; `go list -m ba64@v$(cat VERSION)` |
| Maven Central | `java/` | `mvn -f pom.xml deploy` (signed, via OSSRH) |
| NuGet | `csharp/pack/` | `dotnet pack -c Release && dotnet nuget push bin/Release/Ba64.*.nupkg` |

Go has no registry: publishing **is** the tag. The module path resolves once the
tag is pushed.

## Version bump

A release is a v1 patch/minor only — **the v1 wire format is frozen forever**
(spec §13). Evolution happens through new method IDs in a future spec revision,
never by changing this format. Bump `VERSION`, update every manifest to match
(they are checked for drift in CI), regenerate nothing in `vectors/`.

## Post-release

- OSS-Fuzz: submit `oss-fuzz/` (Python + Rust harnesses) — see that directory.
- Announce the carrier package (`carriers/temporal/`).
- Watch the nightly fuzz workflow; promote any finding into `vectors/`.
