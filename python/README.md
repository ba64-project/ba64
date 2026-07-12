# ba64 — Python reference implementation

Single file, zero runtime dependencies (`ba64.py`), implementing the v1 format
(`../spec.md`). This is the reference the other five languages are checked
against.

```python
import ba64
ba64.encode(b"Hello, world!")            # -> 'SGVsbG8sIHdvcmxkIQ=='
ba64.decode("=AQECDg4XTQECAP3/SGk=")     # -> b'Hi'
try:
    ba64.decode("SGVsbG8")               # bad padding
except ba64.Ba64Error as e:
    e.code                               # -> 'E_BASE64'  (branch on the code, never the message)
```

API (spec §10): `encode(data, *, level=6) -> str`,
`decode(text, *, max_decoded_len=67_108_864) -> bytes`, and `Ba64Error` carrying
a `.code` from the nine-code taxonomy.

CLI (`cli.py`): `ba64 encode|decode` over stdin/stdout — see `python cli.py -h`.

## Testing (the point of this package)

| Layer | Files | Gate |
|---|---|---|
| Unit (branch + boundary) | `tests/test_unit.py` | 100% branch on `ba64.py` |
| Property (hypothesis) | `tests/test_property.py` | roundtrip, floor, marker-iff-smaller, no-crash |
| Conformance + differential | `tests/test_conformance.py`, `tests/test_differential.py` | exact codes; ≡ stdlib base64 on the plain path |
| Chaos | `tests/test_chaos.py` | bit-flip + truncation sweeps; bomb memory cap |
| CLI IT | `tests/test_cli.py` | pipe/file roundtrips incl. 40 MiB stream |
| Mutation | `MUTANTS.md` | ≥95% killed; survivors documented equivalent |

From the repo root:

```sh
make py-cov        # full fast suite under branch coverage, fails under 100%
make py-slow       # heavy perf/IT tests (10 MiB roundtrips, 40 MiB CLI)
make py-mutation   # mutmut; expect 191 killed / 2 timeout / 9 equivalent survivors
```

Coverage-guided fuzzing lives in `fuzz/` (atheris; see `fuzz/README.md` for why
it runs on Linux CI, not this authoring box — the deterministic chaos sweeps
cover the same contract here).

## Current gate results

- **100% branch coverage** (86 stmts, 36 branches, 0 partial) on `ba64.py`.
- **Mutation: 95.5% killed** (191/202 + 2 timeouts); all 9 survivors are proven
  equivalent mutants, documented in `MUTANTS.md`.
- Full conformance corpus green; large bit-flip / truncation sweeps clean.

24 h-continuous fuzzing and OSS-Fuzz enrollment are later-phase, run on CI/OSS-Fuzz
infrastructure (see `execution_plan.md`), not claimed here as already-run.
