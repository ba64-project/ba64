# Cross-language conformance caveats

Findings surfaced by running six independent implementations against one shared
corpus. Each is a real interoperability fact, recorded so the corpus stays an
honest oracle.

## 1. `E_PAYLOAD` vs `E_LENGTH_MISMATCH` on a *truncated* DEFLATE stream is decoder-dependent

**What.** For a DEFLATE payload that ends before its final block completes (a
truncated stream), zlib (Python, Java), Go `compress/flate`, and Rust
`miniz_oxide` all raise an error — surfaced by ba64 as **`E_PAYLOAD`**. .NET's
`System.IO.Compression.DeflateStream` instead treats *premature end of input as
end of stream*: it returns the bytes decoded so far without error, so ba64 on
.NET surfaces **`E_LENGTH_MISMATCH`** (the decoded length simply falls short of
`decoded_len`).

Verified directly: .NET's `DeflateStream` throws only for *structurally invalid*
blocks (a stored block whose `NLEN != ~LEN`, a reserved `BTYPE=11`, etc.). It
does **not** throw for a stored block with valid `NLEN` but missing data, nor for
a Huffman stream cut mid-symbol — it decodes what it can and reports EOF.

The same leniency means .NET accepts a payload that ends at a block boundary
**without a final (`BFINAL=1`) block** — e.g. a sync-flushed non-final block —
where zlib/flate/miniz require the final block and raise `E_PAYLOAD`. A conforming
*encoder* always emits a final block, so round-trips are unaffected; only crafted
inputs differ. One narrow case is closed on every implementation: an **empty
payload** is never a valid DEFLATE stream, so all six (C# via an explicit guard)
return `E_PAYLOAD` for it.

**Why it is not a bug in any implementation.** Both codes correctly *reject* the
corrupt frame; they differ only in classification. RFC 1951 does not prescribe an
error for "ran out of input," and the CRC-32 (spec §2.2) still guarantees no
silently-wrong bytes are ever returned. The safety property holds on every
platform; only the taxonomy label differs.

**How the corpus handles it.**
- The auto-generated `vectors/differential.json` **excludes** `E_PAYLOAD` and
  `E_LENGTH_MISMATCH` on corrupt payloads entirely (the generator filters them),
  so it remains a byte-exact / exact-code oracle all six decoders agree on. Its
  error coverage comes from structurally-determined codes (`E_BASE64`,
  `E_TRUNCATED`, `E_HEADER`, `E_VERSION`, `E_METHOD`, `E_LIMIT_EXCEEDED`,
  `E_CHECKSUM`) plus thousands of valid-decode agreements.
- The one curated vector that lands on this boundary,
  `decode_errors.json → payload_truncated_stream`, carries an
  `"error_alt": ["E_LENGTH_MISMATCH"]` field. Every conformance runner accepts
  the primary code **or** any `error_alt`, so all six pass while the vector still
  documents zlib's behavior as primary.

**Guidance for callers.** Treat `E_PAYLOAD` and `E_LENGTH_MISMATCH` as the same
outcome — "the frame is corrupt, reject it." Do not branch application logic on
which of the two a truncated payload produces; it is not portable. All other
taxonomy codes are exact across every implementation.

## Scope

This is the only cross-language divergence found. Valid inputs decode
byte-for-byte identically on all six implementations, and every *structural*
error (base64, header, version, method, limit, header-truncation, checksum) is
exact across all six.
