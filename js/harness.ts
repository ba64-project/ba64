/** Batch harness for conformance/run.py. Protocol: stdin first line = N, then N
 * items; stdout = N results. encode: hex -> ba64 text. decode: ba64 -> hex or
 * "!CODE". See python/harness.py for the full protocol description. */
import { Buffer } from "node:buffer";
import { encode, decode, Ba64Error } from "./ba64.ts";

const mode = process.argv[2];
const chunks: Buffer[] = [];
process.stdin.on("data", (c) => chunks.push(c));
process.stdin.on("end", () => {
  const data = Buffer.concat(chunks).toString("utf8").split("\n");
  const n = parseInt(data[0], 10);
  const items = data.slice(1, 1 + n);
  const out: string[] = [];
  for (const item of items) {
    if (mode === "encode") {
      out.push(encode(new Uint8Array(Buffer.from(item, "hex"))));
    } else {
      try {
        out.push(Buffer.from(decode(item)).toString("hex"));
      } catch (e) {
        if (e instanceof Ba64Error) out.push("!" + e.code);
        else throw e;
      }
    }
  }
  process.stdout.write(out.join("\n"));
});
