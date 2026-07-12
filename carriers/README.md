# Carriers

Thin, single-purpose packages that drop ba64 into systems with hard size ceilings
— published separately from the core codec so each stays tiny and optional.

## `temporal/` — Temporal `PayloadCodec` (flagship)

Temporal enforces a gRPC message-size limit and people routinely hand-roll gzip
codecs to stay under it. `Ba64PayloadCodec` does it in a few lines, with the floor
guarantee (never larger than base64) and CRC integrity built in.

```sh
python carriers/temporal/test_codec.py   # byte-level transform, no SDK required
```

Measured: realistic JSON workflow args compress to ~15% of raw; random payloads
take the floor. `max_decoded_len` bounds decompression so a hostile server cannot
force unbounded allocation.

## Fallback targets (per execution_plan.md Phase 6)

- **SQS/SNS wrapper** for the 256 KB message ceiling.
- **QR-payload helper** — squeeze more into a fixed QR capacity.

Both follow the same pattern as `temporal/`: encode on the way out, decode on the
way in, decoded-bytes are the source of truth for any equality/signature check.
