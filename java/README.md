# ba64 — Java

Single file, standard library only (`Ba64.java`: `java.util.zip.Deflater/Inflater`
with `nowrap`, `java.util.zip.CRC32`, `java.util.Base64`). Implements the v1
format (`../spec.md`).

```java
Ba64.encode("Hello, world!".getBytes());   // "SGVsbG8sIHdvcmxkIQ=="
Ba64.decode("=AQECDg4XTQECAP3/SGk=");       // byte[] "Hi"
// throws Ba64.Ba64Exception; branch on e.code()
```

`encode(data[, level])`, `decode(text[, maxDecodedLen])`; `Ba64Exception` with
`code()` from the nine-code taxonomy.

## Test & verify

```sh
javac Ba64.java Ba64Test.java && java Ba64Test
```

- ~49.5k checks pass: every shared vector + the 4000-case differential vs the
  Python reference, plus property and chaos (bit-flip / truncation / frame
  corruption) sweeps.
- `Ba64Test` includes a minimal JSON parser (the JDK ships none) to read the
  shared corpus — no third-party dependency.

## Note

`Inflater(true)` with `getRemaining()` gives exact trailing-byte detection;
inflation is capped at `decoded_len` for bomb safety (spec §7). Continuous
fuzzing (Jazzer) and JaCoCo coverage are CI-scale follow-ups.
