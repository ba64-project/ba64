# ba64

ba64 is a smaller drop-in replacement for base64.

It does the same job as base64. It turns binary data into safe text. The
difference is that ba64 compresses your data first, but only when that makes the
text shorter. If compression does not help, you get plain base64. So ba64 is
never bigger than base64. For text like JSON and logs it is usually much smaller.

## Why use it

- **Smaller.** JSON, logs, and similar text often shrink to under 10% of their
  base64 size.
- **Never bigger.** If compression does not help, ba64 gives you plain base64,
  byte for byte. This is guaranteed.
- **Drop-in.** Plain ba64 output is normal base64. Your existing base64 readers
  keep working. You can switch readers over first, then turn on compression later.
- **Safe.** A built-in checksum catches corruption. A damaged value is always a
  clear error. You never get wrong bytes back.

Six versions are available: Python, TypeScript/Node, Go, Rust, Java, and C#. Each
is one small file with no dependencies.

## Examples

Short text does not compress, so ba64 gives you plain base64. It is byte for byte
the same string.

```
input:   Hello, world!
base64:  SGVsbG8sIHdvcmxkIQ==   (20 chars)
ba64:    SGVsbG8sIHdvcmxkIQ==   (20 chars, identical)
```

Repetitive text compresses a lot. ba64 marks the compressed form with a leading
`=`.

```
input:   [{"id":0,"status":"active","plan":"pro"}, ... 15 items]   (695 bytes)
base64:  928 chars
ba64:    =AQG3BTtcolWLrlbKTFGyUjDQUVAqLkksKS0GcpQSk0syy1KVgGIFOYl5IJGConylWh0Fq
         GpDklQbkaTamCTVJiSpNiVJtRlJqs1JUm1BkmpL0mKHxMgkLTYNSYtOQ9Li05CoCI0FAA==
         (141 chars, about 15% of the base64 size)
```

Both decode back to the exact original bytes.

## How much smaller

Real numbers from [`bench/bench.py`](bench/bench.py). Run it yourself.

| Payload | base64 | ba64 | size vs base64 |
|---|--:|--:|--:|
| JSON API response | 7,256 B | 633 B | **9%** |
| Structured logs | 18,720 B | 581 B | **3%** |
| HTML fragment | 4,080 B | 165 B | **4%** |
| Random / encrypted | 5,464 B | 5,464 B | **100%** (falls back to plain) |

The savings depend on how repetitive your data is. Random or already-compressed
data does not shrink, so ba64 just gives you plain base64.

## Install

The packages will ship to PyPI, npm, crates.io, Maven Central, and NuGet with the
v1.0.0 release. For now, copy the single file into your project. It has no
dependencies.

| Language | File to copy |
|---|---|
| Python | `python/ba64.py` |
| TypeScript / Node | `js/ba64.ts` |
| Go | `go/ba64.go` |
| Rust | `rust/src/lib.rs` |
| Java | `java/Ba64.java` |
| C# | `csharp/Ba64.cs` |

## Use

Every version has the same shape. `encode` takes bytes and returns text. `decode`
takes text and returns the original bytes. Errors carry a `code` you can branch
on. `decode` also takes an optional size limit (default 64 MiB) that guards
against decompression bombs.

**Python**

```python
import ba64

text = ba64.encode(b"hello world")   # a string
data = ba64.decode(text)             # the original bytes

try:
    ba64.decode(untrusted)
except ba64.Ba64Error as e:
    print(e.code)                    # for example "E_CHECKSUM"
```

**TypeScript / Node**

```ts
import { encode, decode, Ba64Error } from "ba64";

const text = encode(new TextEncoder().encode("hello world"));  // a string
const data = decode(text);                                      // a Uint8Array

try {
  decode(untrusted);
} catch (e) {
  if (e instanceof Ba64Error) console.log(e.code);              // "E_CHECKSUM"
}
```

**Go**

```go
text := ba64.Encode([]byte("hello world"))   // string
data, err := ba64.Decode(text)               // []byte, error
if err != nil {
    code := err.(*ba64.Error).Code()         // for example "E_CHECKSUM"
}
```

**Rust**

```rust
let text = ba64::encode(b"hello world");   // String
let data = ba64::decode(&text).unwrap();   // Vec<u8>

match ba64::decode(untrusted) {
    Ok(bytes) => { /* use bytes */ }
    Err(e) => eprintln!("{}", e.code()),   // for example "E_CHECKSUM"
}
```

**Java**

```java
String text = Ba64.encode("hello world".getBytes());  // String
byte[] data = Ba64.decode(text);                       // byte[]

try {
    Ba64.decode(untrusted);
} catch (Ba64.Ba64Exception e) {
    System.out.println(e.code());                      // "E_CHECKSUM"
}
```

**C#**

```csharp
string text = Ba64.Encode(Encoding.UTF8.GetBytes("hello world"));  // string
byte[] data = Ba64.Decode(text);                                    // byte[]

try {
    Ba64.Decode(untrusted);
} catch (Ba64.Ba64Exception e) {
    Console.WriteLine(e.Code);                                      // "E_CHECKSUM"
}
```

## Encode a file

ba64 works on bytes, so encoding a file is just reading it, encoding, and writing
the text. Decoding reverses it back to the exact original file.

**Command line** (the Python CLI reads stdin, writes stdout):

```sh
python python/cli.py encode < photo.jpg  > photo.ba64
python python/cli.py decode < photo.ba64 > photo.out.jpg
# photo.out.jpg is byte for byte the same as photo.jpg
```

**Python**

```python
import ba64, pathlib

raw = pathlib.Path("photo.jpg").read_bytes()
pathlib.Path("photo.ba64").write_text(ba64.encode(raw))

back = ba64.decode(pathlib.Path("photo.ba64").read_text())
assert back == raw
```

**Go**

```go
raw, _ := os.ReadFile("photo.jpg")
os.WriteFile("photo.ba64", []byte(ba64.Encode(raw)), 0644)

text, _ := os.ReadFile("photo.ba64")
back, _ := ba64.Decode(string(text))   // back == raw
```

**Node**

```ts
import { readFileSync, writeFileSync } from "node:fs";
import { encode, decode } from "ba64";

const raw = readFileSync("photo.jpg");
writeFileSync("photo.ba64", encode(new Uint8Array(raw)));

const back = decode(readFileSync("photo.ba64", "utf8"));   // back equals raw
```

## One rule to remember

Do not compare the encoded text. The same input can produce different valid ba64
strings, because compression is not unique. Compare the decoded bytes instead.
This applies to equality checks, dedup, cache keys, and HMAC. See
[SECURITY.md](SECURITY.md) for the details.

## How it works

A ba64 string comes in one of two forms. The first character tells them apart.

```
plain form:       base64(input)
compressed form:  "=" + base64( header + deflate(input) )
```

Plain form never starts with `=`. It is identical to standard base64. Compressed
form starts with `=`. That character is legal base64 but can never start a real
base64 string, so there is no ambiguity.

The header holds a version, a method, the original length, and a CRC-32 of your
original bytes. The checksum is what makes "never wrong bytes" a guarantee. The
encoder keeps the compressed form only when it is strictly shorter. That is why
ba64 is never larger than base64.

## Is it tested

Yes. All six versions are checked against one shared set of test vectors. They are
also checked against each other.

- Every encoder's output decodes correctly under every decoder. That is 36 pairs,
  over 10,000 random inputs.
- Damaged input is always a clear error. Bit-flip and truncation tests across all
  six versions produced zero silent corruptions.
- The reference version has 100% branch coverage and a 95% mutation score.

```sh
make cross     # every language passes the shared test vectors
make matrix    # 6x6 encoder and decoder agreement over 10k inputs
```

See [CONTRIBUTING.md](CONTRIBUTING.md) to run the tests and add to the project.
[RELEASING.md](RELEASING.md) covers how a release is cut. The v1 format is frozen.
It never changes. New features would only ever come through new method IDs.
