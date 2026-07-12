# ba64 — TypeScript / Node

Single file, standard library only (`ba64.ts`, uses `node:zlib`). Implements the
v1 format (`../spec.md`).

```ts
import { encode, decode, Ba64Error } from "./ba64.ts";
encode(new TextEncoder().encode("Hello, world!")); // "SGVsbG8sIHdvcmxkIQ=="
decode("=AQECDg4XTQECAP3/SGk=");                    // Uint8Array of "Hi"
```

`encode(data, {level})`, `decode(text, {maxDecodedLen})`, `Ba64Error` with
`.code` from the nine-code taxonomy.

## Test & verify

```sh
node conformance.ts                        # all shared vectors + 4000 differential
node --test                                # property + chaos + conformance
node --test --experimental-test-coverage   # coverage
```

- **100% line/branch/function coverage** on `ba64.ts` (Node built-in coverage).
- Passes every shared vector and the 4000-case differential vs the Python
  reference; bit-flip / truncation sweeps and the inflation-cap memory bomb green.

## Notes

- Raw DEFLATE via `node:zlib` (`deflateRawSync` / `InflateRaw`); exact-end and
  trailing-byte detection via the inflater's consumed-byte count. A browser build
  would swap to `CompressionStream("deflate-raw")` (async) or the Rust/wasm
  fallback.
- Continuous fuzzing (jazzer.js) is CI-scale; the deterministic chaos sweeps
  cover the same no-crash contract here.
