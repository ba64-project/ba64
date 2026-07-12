# ba64

**A drop-in replacement for base64 that is often much smaller — and never bigger.**

ba64 compresses your data and base64-encodes it, but *only keeps the compressed
form when it actually comes out shorter*. So:

- 📦 **Smaller** — JSON, logs, and other structured text shrink to a fraction of
  their base64 size (see [the numbers](#how-small)).
- 🛡️ **Never bigger** — if compression doesn't help (already-compressed or
  encrypted data), you get plain base64, byte-for-byte. Guaranteed.
- 🔌 **Drop-in** — plain output *is* standard base64, so a ba64 decoder reads all
  your existing base64 unchanged. Migrate readers first, flip on compression later.
- ✅ **Safe** — a built-in checksum means a corrupted value is always a clear
  error, never silently-wrong bytes.

Available in **Python, TypeScript/Node, Go, Rust, Java, and C#** — one small,
dependency-free file each.

## Install

The packages will be published to PyPI / npm / crates.io / Maven Central / NuGet
with the v1.0.0 release. **Today, vendor the single file** — that's the blessed
distribution model (it has no dependencies):

| Language | File to copy | Coming soon |
|---|---|---|
| Python | `python/ba64.py` | `pip install ba64` |
| TypeScript / Node | `js/ba64.ts` | `npm install ba64` |
| Go | `go/ba64.go` | `go get github.com/ba64-project/ba64/go` |
| Rust | `rust/src/lib.rs` | `cargo add ba64` |
| Java | `java/Ba64.java` | Maven Central `io.ba64:ba64` |
| C# | `csharp/Ba64.cs` | `dotnet add package Ba64` |

## Use

**Python**
```python
import ba64

text = ba64.encode(b'{"user":"alice","role":"admin"}')  # str, e.g. "=AQ..."
data = ba64.decode(text)                                 # bytes, the original

try:
    ba64.decode(from_untrusted_source)
except ba64.Ba64Error as e:
    print(e.code)   # e.g. "E_CHECKSUM", "E_BASE64", ... (never silently wrong)
```

**TypeScript / Node**
```ts
import { encode, decode, Ba64Error } from "ba64";

const text = encode(new TextEncoder().encode("…"));  // string
const data = decode(text);                            // Uint8Array
```

<details>
<summary><b>Go, Rust, Java, C#</b></summary>

```go
text := ba64.Encode(data)          // string
out, err := ba64.Decode(text)      // []byte, error (*ba64.Error has .Code())
```
```rust
let text = ba64::encode(data);     // String
let out  = ba64::decode(&text)?;   // Vec<u8>; Err is ba64::Error, .code()
```
```java
String text = Ba64.encode(data);   // String
byte[] out  = Ba64.decode(text);   // throws Ba64.Ba64Exception (.code())
```
```csharp
string text = Ba64.Encode(data);   // string
byte[] out  = Ba64.Decode(text);   // throws Ba64.Ba64Exception (.Code)
```
</details>

Every implementation exposes the same shape: `encode(bytes) -> text`,
`decode(text) -> bytes`, and one error type with a machine-readable `.code`.
Decoding a `max_decoded_len`/`maxDecodedLen` parameter (default 64 MiB) caps how
much a single value may expand — protection against decompression bombs.

> [!IMPORTANT]
> **Don't compare the encoded text.** The same input can produce *different*
> valid ba64 strings (compression isn't unique). Any equality check, dedup,
> cache key, or HMAC must run on the **decoded bytes**, never on the ba64 text.
> Also: don't compress attacker-controlled data next to secrets when the output
> size is observable (a CRIME/BREACH-style leak). See [SECURITY.md](SECURITY.md).

## How small? <a name="how-small"></a>

Measured by [`bench/bench.py`](bench/bench.py) — run it yourself:

| Payload | base64 | ba64 | size vs base64 |
|---|--:|--:|--:|
| JSON API response | 7,256 B | 633 B | **9%** |
| Structured logs | 18,720 B | 581 B | **3%** |
| HTML fragment | 4,080 B | 165 B | **4%** |
| Random / encrypted | 5,464 B | 5,464 B | **100%** (falls back to plain) |

Savings depend on how repetitive your data is; incompressible data always lands
on the plain-base64 floor.

## How it works

A ba64 string is one of two forms, told apart by the first character:

```
plain form:       base64(input)          — never starts with "=", identical to base64
compressed form:  "=" + base64( version | method | length | crc32 | deflate(input) )
```

The leading `=` is inside the base64 alphabet (so it survives any base64-safe
channel) but can never begin a *real* base64 string (padding is end-only) — so
the two forms are unambiguous. The CRC-32 is computed over your original bytes,
which is what makes "never silently wrong" a guarantee rather than a hope.

The encoder emits the compressed form **only if it's strictly shorter**; ties go
to plain. That single rule is why ba64 is never larger than base64.

## Is it trustworthy?

The six implementations are checked against **one shared conformance corpus**, and
cross-checked against each other:

- **36/36** — every encoder's output decodes correctly under every decoder, over
  10,000 randomized inputs (`make matrix`).
- **Zero silent corruptions** — exhaustive bit-flip, truncation, and
  frame-corruption sweeps across all six: a damaged value is always a typed
  error, never wrong bytes.
- **100% branch coverage** and **≥95% mutation kill** on the reference
  implementation; property tests, fuzzing, and bomb-safety checks throughout.

```sh
make cross     # all six languages pass the shared corpus
make matrix    # 6×6 encoder/decoder agreement over 10k inputs
```

## Docs & contributing

- [SECURITY.md](SECURITY.md) — threat model, bomb handling, disclosure.
- [RELEASING.md](RELEASING.md) — how a coordinated v1.0.0 release is cut.
- [conformance/CAVEATS.md](conformance/CAVEATS.md) — one documented cross-language
  edge case (.NET on truncated DEFLATE streams).
- The wire format is frozen for v1 and specified as an Internet-Draft (published
  separately). Evolution happens only via new method IDs — decoders reject what
  they don't recognize, loudly and typed.

Each codec is a single file with no runtime dependencies (Rust uses one crate,
`miniz_oxide`, for DEFLATE). Vendoring is encouraged.
