/**
 * ba64 — binary-to-text encoding that is never larger than standard base64.
 *
 * Reference TypeScript implementation of the v1 format (see ../spec.md). Single
 * file, standard library only (node:zlib, node:buffer). The normative algorithm
 * is spec.md §4; this module implements it exactly.
 *
 *   encode(new TextEncoder().encode("Hello, world!"))  // "SGVsbG8sIHdvcmxkIQ=="
 *   decode("=AQECDg4XTQECAP3/SGk=")                     // Uint8Array of "Hi"
 *
 * Encoding is a relation, not a function: the same input may yield different
 * valid ba64 texts. Decoding is a function. Equality/dedup/MAC comparisons MUST
 * operate on the decoded bytes.
 */
import zlib from "node:zlib";
import { Buffer } from "node:buffer";

export const DEFAULT_MAX_DECODED_LEN = 64 * 2 ** 20; // 64 MiB (spec §7)

const VERSION = 0x01;
const METHOD_DEFLATE_RAW = 0x01;
const Z_FINISH = zlib.constants.Z_FINISH;

export type Ba64Code =
  | "E_BASE64" | "E_TRUNCATED" | "E_HEADER" | "E_VERSION" | "E_METHOD"
  | "E_LIMIT_EXCEEDED" | "E_PAYLOAD" | "E_LENGTH_MISMATCH" | "E_CHECKSUM";

/** A decode failure carrying a machine-readable taxonomy code (spec §5). */
export class Ba64Error extends Error {
  code: Ba64Code;
  constructor(code: Ba64Code) {
    super(code);
    this.name = "Ba64Error";
    this.code = code;
  }
}

/** Decode canonical RFC 4648 §4 base64, else throw E_BASE64. Strictness is by
 * decode-then-re-encode-and-compare (spec §4 note): Node's base64 decoder is
 * lenient, so any input that does not round-trip to itself is non-canonical. */
function b64CanonicalDecode(s: string): Buffer {
  const raw = Buffer.from(s, "base64");
  if (raw.toString("base64") !== s) throw new Ba64Error("E_BASE64");
  return raw;
}

function leb128Encode(n: number): Buffer {
  const out: number[] = [];
  let v = BigInt(n);
  for (;;) {
    const b = Number(v & 0x7fn);
    v >>= 7n;
    if (v) out.push(b | 0x80);
    else { out.push(b); return Buffer.from(out); }
  }
}

/** Read a minimal unsigned LEB128 at `pos`; return [value (BigInt), newPos].
 * E_TRUNCATED if the buffer ends mid-varint; E_HEADER if > 9 bytes or
 * non-minimal (spec §2.1). */
function leb128Decode(buf: Buffer, pos: number): [bigint, number] {
  let value = 0n;
  let shift = 0n;
  const start = pos;
  for (;;) {
    if (pos >= buf.length) throw new Ba64Error("E_TRUNCATED");
    const b = buf[pos];
    pos += 1;
    if (pos - start > 9) throw new Ba64Error("E_HEADER");
    value |= BigInt(b & 0x7f) << shift;
    if ((b & 0x80) === 0) {
      if (pos - start > 1 && b === 0) throw new Ba64Error("E_HEADER"); // non-minimal
      return [value, pos];
    }
    shift += 7n;
  }
}

/** Inflate `payload` (raw DEFLATE) with a hard output cap; return the exact
 * output. Throws E_LENGTH_MISMATCH if the cap is exceeded, E_PAYLOAD if the
 * stream is malformed, truncated, or has trailing bytes after the final block. */
function inflateExact(payload: Buffer, cap: number): Buffer {
  const engine = new zlib.InflateRaw({ maxOutputLength: cap });
  let out: Buffer;
  try {
    // `_processChunk` is Node-internal (validated on Node 18-26): it inflates in
    // one shot and exposes `bytesWritten` (input consumed), which the public
    // sync API does not, letting us detect trailing bytes exactly. If a future
    // Node changes it, the catch below maps the failure to E_PAYLOAD.
    out = (engine as any)._processChunk(payload, Z_FINISH);
  } catch (e: any) {
    if (e && e.code === "ERR_BUFFER_TOO_LARGE") throw new Ba64Error("E_LENGTH_MISMATCH");
    throw new Ba64Error("E_PAYLOAD"); // Z_BUF_ERROR (truncated / malformed)
  }
  if (engine.bytesWritten !== payload.length) throw new Ba64Error("E_PAYLOAD"); // trailing bytes
  return out;
}

export function encode(data: Uint8Array, opts: { level?: number } = {}): string {
  const level = opts.level ?? 6;
  const buf = Buffer.from(data.buffer, data.byteOffset, data.byteLength);
  const plain = buf.toString("base64");
  const payload = zlib.deflateRawSync(buf, { level });
  const crc = Buffer.alloc(4);
  crc.writeUInt32LE(zlib.crc32(buf) >>> 0, 0);
  const frame = Buffer.concat([
    Buffer.from([VERSION, METHOD_DEFLATE_RAW]),
    leb128Encode(buf.length),
    crc,
    payload,
  ]);
  const candidate = "=" + frame.toString("base64");
  return candidate.length < plain.length ? candidate : plain;
}

export function decode(text: string, opts: { maxDecodedLen?: number } = {}): Uint8Array {
  // Normalize the limit to a non-negative safe integer so a caller-supplied
  // Infinity / NaN / non-integer (or a limit above 2^53) can never leak a
  // RangeError out of BigInt()/maxOutputLength — decode returns bytes or a
  // Ba64Error, nothing else.
  let limit = opts.maxDecodedLen ?? DEFAULT_MAX_DECODED_LEN;
  if (!Number.isFinite(limit)) limit = Number.MAX_SAFE_INTEGER; // Infinity/NaN -> practical max
  limit = Math.max(0, Math.floor(limit));

  if (!text.startsWith("=")) return new Uint8Array(b64CanonicalDecode(text)); // step 1

  const frame = b64CanonicalDecode(text.slice(1)); // step 2

  if (frame.length < 1) throw new Ba64Error("E_TRUNCATED"); // step 3
  if (frame[0] !== VERSION) throw new Ba64Error("E_VERSION");

  if (frame.length < 2) throw new Ba64Error("E_TRUNCATED"); // step 4
  if (frame[1] !== METHOD_DEFLATE_RAW) throw new Ba64Error("E_METHOD");

  const [value, pos] = leb128Decode(frame, 2); // step 5

  if (value > BigInt(limit)) throw new Ba64Error("E_LIMIT_EXCEEDED"); // step 6
  const decodedLen = Number(value); // value <= limit <= MAX_SAFE_INTEGER, so exact

  if (frame.length - pos < 4) throw new Ba64Error("E_TRUNCATED"); // step 7
  const crcStored = frame.readUInt32LE(pos);
  const payload = frame.subarray(pos + 4);

  // step 8: cap of zero must still cap (spec §7) — cap at 1 and check length below
  const out = inflateExact(payload, Math.max(decodedLen, 1));
  if (out.length !== decodedLen) throw new Ba64Error("E_LENGTH_MISMATCH");

  if ((zlib.crc32(out) >>> 0) !== crcStored) throw new Ba64Error("E_CHECKSUM"); // step 9
  return new Uint8Array(out); // step 10
}
