# ba64 — C# / .NET

Single file, standard library only (`Ba64.cs`: `System.IO.Compression.DeflateStream`,
`System.Convert`; CRC-32 is a hand-rolled table). Implements the v1 format
(`../spec.md`).

```csharp
Ba64.Encode(Encoding.UTF8.GetBytes("Hello, world!")); // "SGVsbG8sIHdvcmxkIQ=="
Ba64.Decode("=AQECDg4XTQECAP3/SGk=");                  // byte[] "Hi"
// throws Ba64.Ba64Exception; branch on e.Code
```

`Encode` / `EncodeLevel`, `Decode` / `DecodeMax`; `Ba64Exception` with `Code`
from the nine-code taxonomy.

## Test & verify

```sh
dotnet run -c Release      # conformance + differential + property + chaos
```

- ~49.5k checks pass: every shared vector + the 4000-case differential vs the
  Python reference, plus property and chaos sweeps. Vectors are parsed with
  stdlib `System.Text.Json`.

## Notes

- `DeflateStream` is fed through a lazy 1-byte stream so it consumes exactly the
  DEFLATE stream, giving precise trailing-byte detection; inflation is capped at
  `decoded_len` for bomb safety (spec §7).
- **Known divergence:** .NET's `DeflateStream` treats a *truncated* DEFLATE
  stream as end-of-stream (→ `E_LENGTH_MISMATCH`) where zlib/flate/miniz raise
  `E_PAYLOAD`. This is decoder-dependent and documented in
  `../conformance/CAVEATS.md`; the corpus accommodates it via `error_alt`.
- Continuous fuzzing (SharpFuzz) and coverlet coverage are CI-scale follow-ups.
