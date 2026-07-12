# Security policy

ba64 is a codec, not a security primitive. This file records the threat model
baked into the format (normative detail in [spec.md §7–8](spec.md)) and how to
report issues.

## Threat model and guarantees

**Integrity, not authenticity.** The CRC-32 detects accidental corruption and
decompressor divergence end-to-end — it is not a MAC. An attacker who can rewrite
the ciphertext can recompute the CRC. Where malice is in scope, verify a
MAC/signature over the **decoded bytes** at the application layer (over decoded,
not encoded — encoding is non-canonical).

**Decompression bombs — handled structurally.**
- The decoder rejects a claimed `decoded_len` above the caller's limit (default
  64 MiB) **before any allocation proportional to that size** — a 100-byte frame
  claiming 8 GiB costs O(header) work → `E_LIMIT_EXCEEDED`.
- Inflation is hard-capped at `decoded_len`; a payload that inflates past its
  claim stops at the cap → `E_LENGTH_MISMATCH`, in O(cap) memory.
- **A cap of zero still caps.** `decoded_len = 0` whose payload hides megabytes
  fails after at most one byte, not after inflating everything. Some inflate APIs
  treat an output limit of `0` as "unlimited" (Python's `max_length`) — the known
  trap, covered by a permanent vector (`bombs.json` / `spec.md §7, §12`).
- `max_decoded_len` MUST be a per-call parameter, never a global.

**Compression side channel (CRIME/BREACH class).** If output length is observable
to an adversary who controls part of an input placed alongside secrets,
compression leaks secret content through size. Do **not** ba64-compress
attacker-influenced data concatenated with secrets in such settings; use plain
base64 (a conforming encoder mode, `spec.md §6.4`) for those payloads.

**One string, one meaning.** Canonical RFC 4648 base64 + minimal LEB128 + the
ordered checks of `spec.md §4` give every ba64 text exactly one interpretation
(specific bytes, or one specific error code). No decode-side malleability.

**Error hygiene.** Decoder errors MUST NOT echo payload or decoded content by
default — inputs may be secrets and errors land in logs. The error code and an
offset suffice.

## Reporting a vulnerability

Until a published disclosure address exists, report privately via a GitHub
security advisory on this repository (Security → Report a vulnerability). Please
do not open a public issue for suspected memory-safety, bomb-handling, or
silent-corruption defects. Every confirmed finding becomes a permanent
conformance vector so all implementations are regression-tested against it.

## Scope note

This document tracks the format's guarantees. Coverage/fuzzing/mutation results
that back them up are produced in later phases (see `execution_plan.md`); this
file will link the running fuzzers and OSS-Fuzz status once they exist.
