# ba64 — Go

Single file, standard library only (`ba64.go`: `compress/flate`, `hash/crc32`,
`encoding/base64`). Implements the v1 format (`../spec.md`).

```go
ba64.Encode([]byte("Hello, world!"))     // "SGVsbG8sIHdvcmxkIQ=="
out, err := ba64.Decode("=AQECDg4XTQECAP3/SGk=") // []byte("Hi"), nil
// err is *ba64.Error; branch on err.(*ba64.Error).Code()
```

`Encode` / `EncodeLevel`, `Decode` / `DecodeMax`; `*Error` with `Code()` from the
nine-code taxonomy.

## Test & verify

```sh
go test -cover ./...                     # conformance + differential + property + chaos
go test -run=x -fuzz=FuzzDecode          # native coverage-guided fuzzing
go test -run=x -fuzz=FuzzRoundtrip
```

- **100% statement coverage** on `ba64.go`.
- Passes every shared vector + the 4000-case differential vs the Python
  reference; bit-flip / truncation sweeps and the inflation-cap bomb green.
- Native fuzzers ran ~1M+ executions clean.

## Note

`compress/flate` reads through a `bytes.Reader` (which implements
`io.ByteReader`), so the inflater consumes exactly the DEFLATE stream and
`Reader.Len()` reveals trailing bytes — giving exact `E_PAYLOAD` detection.
