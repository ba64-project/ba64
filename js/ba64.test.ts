/** Property + chaos tests for ba64.ts (node:test, no external deps). */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import zlib from "node:zlib";
import { Buffer } from "node:buffer";
import { encode, decode, Ba64Error } from "./ba64.ts";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const VECTORS = path.join(HERE, "..", "vectors");
const load = (n: string) => JSON.parse(readFileSync(path.join(VECTORS, n), "utf8")).cases;
const b64 = (b: Uint8Array) => Buffer.from(b).toString("base64");

// deterministic PRNG (mulberry32) so failures reproduce
function rng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function randBytes(r: () => number, n: number): Uint8Array {
  const a = new Uint8Array(n);
  for (let i = 0; i < n; i++) a[i] = Math.floor(r() * 256);
  return a;
}

test("conformance: all committed vectors, exact codes", () => {
  const hex = (b: Uint8Array) => Buffer.from(b).toString("hex");
  const unhex = (s: string) => new Uint8Array(Buffer.from(s, "hex"));
  const expectErr = (input: string, code: string, max?: number, alt: string[] = []) =>
    assert.throws(() => decode(input, max !== undefined ? { maxDecodedLen: max } : {}),
      (e: any) => e instanceof Ba64Error && [code, ...alt].includes(e.code), `${input} -> ${code}`);

  for (const c of load("decode_plain.json")) assert.equal(hex(decode(c.input)), c.output_hex);
  for (const c of load("decode_frames.json")) assert.equal(hex(decode(c.input)), c.output_hex);
  for (const c of load("decode_errors.json")) expectErr(c.input, c.error, undefined, c.error_alt ?? []);
  for (const c of load("bombs.json")) expectErr(c.input, c.error, c.max_decoded_len);
  for (const c of load("encode_props.json")) {
    const data = unhex(c.input_hex), enc = encode(data), plain = b64(data);
    assert.equal(hex(decode(enc)), c.input_hex);
    assert.ok(enc.length <= plain.length);
    if (c.props.includes("compressed")) assert.ok(enc.startsWith("="));
    if (c.props.includes("plain")) assert.equal(enc, plain);
  }
  for (const c of load("differential.json")) {
    if (c.output_hex !== undefined) assert.equal(hex(decode(c.input)), c.output_hex);
    else expectErr(c.input, c.error);
  }
  // level knob must reach zlib (not be dropped)
  const d = Buffer.from("The quick brown fox. ".repeat(60));
  assert.notEqual(encode(d, { level: 1 }), encode(d, { level: 9 }));
});

test("property: roundtrip", () => {
  const r = rng(0xba64);
  for (let i = 0; i < 3000; i++) {
    const kind = r();
    const data = kind < 0.5 ? randBytes(r, Math.floor(r() * 64))
      : new Uint8Array(Math.floor(r() * 300)).fill(Math.floor(r() * 3));
    assert.deepEqual(decode(encode(data)), data);
  }
});

test("property: floor + marker-iff-strictly-smaller", () => {
  const r = rng(1);
  for (let i = 0; i < 3000; i++) {
    const data = r() < 0.5 ? randBytes(r, Math.floor(r() * 80))
      : Buffer.from("ab ".repeat(Math.floor(r() * 60)));
    const enc = encode(data);
    const plain = b64(data);
    assert.ok(enc.length <= plain.length, "floor");
    assert.equal(enc.startsWith("="), enc.length < plain.length);
    if (!enc.startsWith("=")) assert.equal(enc, plain);
  }
});

test("property: decode never throws non-Ba64Error", () => {
  const r = rng(2);
  for (let i = 0; i < 5000; i++) {
    const n = Math.floor(r() * 40);
    let s = "";
    for (let j = 0; j < n; j++) s += String.fromCharCode(Math.floor(r() * 128));
    try { const out = decode(s); assert.ok(out instanceof Uint8Array); }
    catch (e) { assert.ok(e instanceof Ba64Error, `non-taxonomy throw: ${e}`); }
  }
});

function validStrings(): string[] {
  return [...load("decode_plain.json"), ...load("decode_frames.json")].map((c) => c.input);
}
const safe = (s: string) => {
  try { assert.ok(decode(s) instanceof Uint8Array); }
  catch (e) { assert.ok(e instanceof Ba64Error, `non-taxonomy throw: ${e}`); }
};

test("chaos: bit-flip sweep", () => {
  let total = 0;
  for (const s of validStrings()) {
    const bytes = Buffer.from(s, "latin1");
    for (let i = 0; i < bytes.length; i++)
      for (let bit = 0; bit < 8; bit++) {
        const m = Buffer.from(bytes); m[i] ^= 1 << bit;
        safe(m.toString("latin1")); total++;
      }
  }
  assert.ok(total > 2000);
});

test("chaos: truncation sweep", () => {
  for (const s of validStrings())
    for (let n = 0; n < s.length; n++) safe(s.slice(0, n));
});

test("chaos: frame corruption never silently wrong", () => {
  for (const c of load("decode_frames.json")) {
    const frame = Buffer.from(c.input.slice(1), "base64");
    const original = c.output_hex;
    for (let i = 0; i < frame.length; i++)
      for (let bit = 0; bit < 8; bit++) {
        const m = Buffer.from(frame); m[i] ^= 1 << bit;
        const text = "=" + m.toString("base64");
        try {
          const out = Buffer.from(decode(text)).toString("hex");
          assert.equal(out, original, "frame silently returned wrong bytes");
        } catch (e) { assert.ok(e instanceof Ba64Error); }
      }
  }
});

test("chaos: inflation cap bounds memory", () => {
  const inflated = 128 * 2 ** 20;
  const payload = zlib.deflateRawSync(Buffer.alloc(inflated), { level: 9 });
  const crc = Buffer.alloc(4); // wrong crc is fine; length check fires first
  const frame = Buffer.concat([Buffer.from([1, 1, 100 & 0x7f]), crc, payload]);
  // decoded_len = 100 (single LEB128 byte)
  const text = "=" + frame.toString("base64");
  const before = process.memoryUsage().rss;
  assert.throws(() => decode(text), (e: any) => e instanceof Ba64Error && e.code === "E_LENGTH_MISMATCH");
  const delta = process.memoryUsage().rss - before;
  assert.ok(delta < 32 * 2 ** 20, `cap not enforced: rss grew ${delta}`);
});
