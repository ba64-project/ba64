/** Drive every committed vector through the TS codec. Standalone (no deps),
 * runnable with `node conformance.ts`. Exit non-zero on any mismatch. */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { encode, decode, Ba64Error } from "./ba64.ts";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const VECTORS = path.join(HERE, "..", "vectors");

function load(name: string): any[] {
  return JSON.parse(readFileSync(path.join(VECTORS, name), "utf8")).cases;
}
const hex = (b: Uint8Array) => Buffer.from(b).toString("hex");
const unhex = (s: string) => new Uint8Array(Buffer.from(s, "hex"));

let checks = 0;
function fail(msg: string): never { throw new Error(msg); }

function expectBytes(input: string, outputHex: string, name: string) {
  const got = hex(decode(input));
  if (got !== outputHex) fail(`${name}: decode -> ${got}, want ${outputHex}`);
  checks++;
}
function expectError(input: string, code: string, name: string, max?: number, alt: string[] = []) {
  const accepted = [code, ...alt];
  try {
    decode(input, max !== undefined ? { maxDecodedLen: max } : {});
  } catch (e) {
    if (e instanceof Ba64Error) {
      if (!accepted.includes(e.code)) fail(`${name}: got ${e.code}, want ${accepted}`);
      checks++;
      return;
    }
    throw e;
  }
  fail(`${name}: expected error ${code}`);
}

for (const c of load("decode_plain.json")) expectBytes(c.input, c.output_hex, "plain/" + c.name);
for (const c of load("decode_frames.json")) expectBytes(c.input, c.output_hex, "frame/" + c.name);
for (const c of load("decode_errors.json")) expectError(c.input, c.error, "err/" + c.name, undefined, c.error_alt ?? []);
for (const c of load("bombs.json")) expectError(c.input, c.error, "bomb/" + c.name, c.max_decoded_len);

for (const c of load("encode_props.json")) {
  const data = unhex(c.input_hex);
  const enc = encode(data);
  const plain = Buffer.from(data).toString("base64");
  if (hex(decode(enc)) !== c.input_hex) fail(`encode/${c.name}: roundtrip`);
  if (enc.length > plain.length) fail(`encode/${c.name}: floor`);
  if (c.props.includes("compressed") && !enc.startsWith("=")) fail(`encode/${c.name}: not compressed`);
  if (c.props.includes("plain") && enc !== plain) fail(`encode/${c.name}: not plain`);
  checks++;
}

for (const c of load("differential.json")) {
  if (c.output_hex !== undefined) expectBytes(c.input, c.output_hex, "diff");
  else expectError(c.input, c.error, "diff");
}

console.log(`ba64.ts: ${checks} vector checks passed (incl. 4000 differential vs Python reference)`);
