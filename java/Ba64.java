import java.util.Base64;
import java.util.zip.CRC32;
import java.util.zip.DataFormatException;
import java.util.zip.Deflater;
import java.util.zip.Inflater;

/**
 * ba64 — binary-to-text encoding that is never larger than standard base64.
 *
 * Reference Java implementation of the v1 format (see ../spec.md). Standard
 * library only (java.util.zip, java.util.Base64). The normative algorithm is
 * spec.md §4. Encoding is a relation, not a function — equality/dedup/MAC
 * comparisons MUST operate on the decoded bytes.
 */
public final class Ba64 {
    public static final long DEFAULT_MAX_DECODED_LEN = 64L << 20; // 64 MiB (spec §7)

    private static final int VERSION = 0x01;
    private static final int METHOD_DEFLATE_RAW = 0x01;

    private Ba64() {}

    /** A decode failure carrying a machine-readable taxonomy code (spec §5). */
    public static final class Ba64Exception extends RuntimeException {
        private final String code;
        public Ba64Exception(String code) { super(code); this.code = code; }
        public String code() { return code; }
    }

    private static final Base64.Encoder B64E = Base64.getEncoder();
    private static final Base64.Decoder B64D = Base64.getDecoder();

    /** Canonical RFC 4648 §4 base64 decode, else E_BASE64. Java's decoder is
     * lenient about padding/trailing bits, so strictness is by
     * decode-then-re-encode-and-compare (spec §4 note). */
    private static byte[] b64CanonicalDecode(String s) {
        byte[] raw;
        try {
            raw = B64D.decode(s);
        } catch (IllegalArgumentException e) {
            throw new Ba64Exception("E_BASE64");
        }
        if (!B64E.encodeToString(raw).equals(s)) throw new Ba64Exception("E_BASE64");
        return raw;
    }

    private static byte[] leb128Encode(long n) {
        byte[] tmp = new byte[10];
        int i = 0;
        while (true) {
            int b = (int) (n & 0x7f);
            n >>>= 7;
            if (n != 0) tmp[i++] = (byte) (b | 0x80);
            else { tmp[i++] = (byte) b; byte[] out = new byte[i]; System.arraycopy(tmp, 0, out, 0, i); return out; }
        }
    }

    /** Returns {value, newPos} packed as long[]{value, pos}. */
    private static long[] leb128Decode(byte[] buf, int pos) {
        long value = 0;
        int shift = 0, start = pos;
        while (true) {
            if (pos >= buf.length) throw new Ba64Exception("E_TRUNCATED");
            int b = buf[pos] & 0xff;
            pos++;
            if (pos - start > 9) throw new Ba64Exception("E_HEADER");
            value |= (long) (b & 0x7f) << shift;
            if ((b & 0x80) == 0) {
                if (pos - start > 1 && b == 0) throw new Ba64Exception("E_HEADER"); // non-minimal
                return new long[] { value, pos };
            }
            shift += 7;
        }
    }

    /** Inflate raw DEFLATE with a hard output cap; detect exact end and trailing
     * bytes. Cap allocation at what DEFLATE could produce from the payload
     * (~1032x+64) so a small frame claiming a huge size stays cheap (spec §7). */
    private static byte[] inflateExact(byte[] payload, long decodedLen) {
        long bound = (long) payload.length * 1032 + 64;
        // A real DEFLATE stream can't produce more than `bound` bytes, so the
        // output buffer never needs to exceed it even when decodedLen is larger.
        int cap = (int) Math.min(Math.min(decodedLen, bound) + 1, Integer.MAX_VALUE);
        byte[] out = new byte[cap];
        Inflater inf = new Inflater(true); // nowrap = raw DEFLATE
        inf.setInput(payload);
        int total = 0;
        try {
            while (!inf.finished()) {
                if (total == out.length) throw new Ba64Exception("E_LENGTH_MISMATCH"); // exceeded cap
                int n = inf.inflate(out, total, out.length - total);
                if (n > 0) {
                    total += n;
                    if (total > decodedLen) throw new Ba64Exception("E_LENGTH_MISMATCH");
                } else if (inf.finished()) {
                    break;
                } else {
                    throw new Ba64Exception("E_PAYLOAD"); // needsInput (truncated) or no progress
                }
            }
        } catch (DataFormatException e) {
            throw new Ba64Exception("E_PAYLOAD"); // malformed stream
        }
        if (inf.getRemaining() != 0) throw new Ba64Exception("E_PAYLOAD"); // trailing bytes
        inf.end();
        byte[] result = new byte[total];
        System.arraycopy(out, 0, result, 0, total);
        return result;
    }

    public static String encode(byte[] data) { return encode(data, 6); }

    public static String encode(byte[] data, int level) {
        String plain = B64E.encodeToString(data);

        Deflater def = new Deflater(level, true); // nowrap = raw DEFLATE
        def.setInput(data);
        def.finish();
        byte[] buf = new byte[Math.max(64, data.length + 64)];
        java.io.ByteArrayOutputStream payload = new java.io.ByteArrayOutputStream();
        while (!def.finished()) {
            int n = def.deflate(buf);
            payload.write(buf, 0, n);
        }
        def.end();

        CRC32 crc = new CRC32();
        crc.update(data);
        long crcVal = crc.getValue();

        java.io.ByteArrayOutputStream frame = new java.io.ByteArrayOutputStream();
        frame.write(VERSION);
        frame.write(METHOD_DEFLATE_RAW);
        byte[] len = leb128Encode(data.length);
        frame.write(len, 0, len.length);
        frame.write((int) (crcVal & 0xff));
        frame.write((int) (crcVal >>> 8 & 0xff));
        frame.write((int) (crcVal >>> 16 & 0xff));
        frame.write((int) (crcVal >>> 24 & 0xff));
        byte[] p = payload.toByteArray();
        frame.write(p, 0, p.length);

        String candidate = "=" + B64E.encodeToString(frame.toByteArray());
        return candidate.length() < plain.length() ? candidate : plain;
    }

    public static byte[] decode(String text) { return decode(text, DEFAULT_MAX_DECODED_LEN); }

    public static byte[] decode(String text, long maxDecodedLen) {
        if (text.isEmpty() || text.charAt(0) != '=') return b64CanonicalDecode(text); // step 1

        byte[] frame = b64CanonicalDecode(text.substring(1)); // step 2

        if (frame.length < 1) throw new Ba64Exception("E_TRUNCATED"); // step 3
        if ((frame[0] & 0xff) != VERSION) throw new Ba64Exception("E_VERSION");
        if (frame.length < 2) throw new Ba64Exception("E_TRUNCATED"); // step 4
        if ((frame[1] & 0xff) != METHOD_DEFLATE_RAW) throw new Ba64Exception("E_METHOD");

        long[] vp = leb128Decode(frame, 2); // step 5
        long value = vp[0];
        int pos = (int) vp[1];

        if (Long.compareUnsigned(value, maxDecodedLen) > 0) throw new Ba64Exception("E_LIMIT_EXCEEDED"); // step 6
        long decodedLen = value; // keep full width; a 32-bit cast would silently mis-length

        if (frame.length - pos < 4) throw new Ba64Exception("E_TRUNCATED"); // step 7
        long crcStored = (frame[pos] & 0xffL) | (frame[pos + 1] & 0xffL) << 8
                | (frame[pos + 2] & 0xffL) << 16 | (frame[pos + 3] & 0xffL) << 24;
        byte[] payload = new byte[frame.length - pos - 4];
        System.arraycopy(frame, pos + 4, payload, 0, payload.length);

        byte[] out = inflateExact(payload, decodedLen); // step 8
        if (out.length != decodedLen) throw new Ba64Exception("E_LENGTH_MISMATCH");

        CRC32 crc = new CRC32();
        crc.update(out);
        if (crc.getValue() != crcStored) throw new Ba64Exception("E_CHECKSUM"); // step 9
        return out; // step 10
    }
}
