import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;

/** Standalone test runner (no JUnit): conformance, differential, property,
 * chaos. Includes a minimal JSON parser since the JDK ships none. */
public class Ba64Test {
    static int checks = 0;
    static int failures = 0;

    // --- minimal JSON parser --------------------------------------------------
    static final class JP {
        final String s; int i;
        JP(String s) { this.s = s; }
        Object parse() { skip(); Object v = value(); skip(); return v; }
        void skip() { while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++; }
        Object value() {
            skip();
            char c = s.charAt(i);
            if (c == '{') return obj();
            if (c == '[') return arr();
            if (c == '"') return str();
            if (c == 't') { i += 4; return Boolean.TRUE; }
            if (c == 'f') { i += 5; return Boolean.FALSE; }
            if (c == 'n') { i += 4; return null; }
            return num();
        }
        Map<String,Object> obj() {
            Map<String,Object> m = new HashMap<>(); i++; skip();
            if (s.charAt(i) == '}') { i++; return m; }
            while (true) {
                skip(); String k = str(); skip(); i++; // ':'
                m.put(k, value()); skip();
                if (s.charAt(i) == ',') { i++; continue; }
                i++; return m; // '}'
            }
        }
        List<Object> arr() {
            List<Object> a = new ArrayList<>(); i++; skip();
            if (s.charAt(i) == ']') { i++; return a; }
            while (true) {
                a.add(value()); skip();
                if (s.charAt(i) == ',') { i++; continue; }
                i++; return a; // ']'
            }
        }
        String str() {
            StringBuilder b = new StringBuilder(); i++; // opening quote
            while (true) {
                char c = s.charAt(i++);
                if (c == '"') return b.toString();
                if (c == '\\') {
                    char e = s.charAt(i++);
                    switch (e) {
                        case 'n': b.append('\n'); break;
                        case 't': b.append('\t'); break;
                        case 'r': b.append('\r'); break;
                        case 'b': b.append('\b'); break;
                        case 'f': b.append('\f'); break;
                        case '/': b.append('/'); break;
                        case '\\': b.append('\\'); break;
                        case '"': b.append('"'); break;
                        case 'u': b.append((char) Integer.parseInt(s.substring(i, i + 4), 16)); i += 4; break;
                        default: b.append(e);
                    }
                } else b.append(c);
            }
        }
        Double num() {
            int st = i;
            while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
            return Double.parseDouble(s.substring(st, i));
        }
    }

    @SuppressWarnings("unchecked")
    static List<Map<String,Object>> load(String name) throws Exception {
        String txt = Files.readString(Path.of("..", "vectors", name));
        Map<String,Object> doc = (Map<String,Object>) new JP(txt).parse();
        List<Object> cases = (List<Object>) doc.get("cases");
        List<Map<String,Object>> out = new ArrayList<>();
        for (Object o : cases) out.add((Map<String,Object>) o);
        return out;
    }

    // --- helpers --------------------------------------------------------------
    static String toHex(byte[] b) {
        StringBuilder s = new StringBuilder();
        for (byte x : b) s.append(String.format("%02x", x));
        return s.toString();
    }
    static byte[] fromHex(String s) {
        byte[] b = new byte[s.length() / 2];
        for (int i = 0; i < b.length; i++) b[i] = (byte) Integer.parseInt(s.substring(2 * i, 2 * i + 2), 16);
        return b;
    }
    static void check(boolean cond, String msg) {
        checks++;
        if (!cond) { failures++; System.out.println("FAIL: " + msg); }
    }
    static String codeOf(Runnable r) {
        try { r.run(); return "NO_ERROR"; }
        catch (Ba64.Ba64Exception e) { return e.code(); }
        catch (Throwable t) { return "NON_TAXONOMY:" + t; }
    }

    // --- suites ---------------------------------------------------------------
    static void conformance() throws Exception {
        for (Map<String,Object> c : load("decode_plain.json"))
            check(toHex(Ba64.decode((String) c.get("input"))).equals(c.get("output_hex")), "plain/" + c.get("name"));
        for (Map<String,Object> c : load("decode_frames.json"))
            check(toHex(Ba64.decode((String) c.get("input"))).equals(c.get("output_hex")), "frame/" + c.get("name"));
        for (Map<String,Object> c : load("decode_errors.json")) {
            String got = codeOf(() -> Ba64.decode((String) c.get("input")));
            List<Object> accepted = new ArrayList<>();
            accepted.add(c.get("error"));
            if (c.get("error_alt") != null) accepted.addAll((List<Object>) c.get("error_alt"));
            check(accepted.contains(got), "err/" + c.get("name") + " got " + got + " want " + accepted);
        }
        for (Map<String,Object> c : load("bombs.json")) {
            long max = c.get("max_decoded_len") != null ? (long)(double)(Double) c.get("max_decoded_len") : Ba64.DEFAULT_MAX_DECODED_LEN;
            check(codeOf(() -> Ba64.decode((String) c.get("input"), max)).equals(c.get("error")), "bomb/" + c.get("name"));
        }
    }

    @SuppressWarnings("unchecked")
    static void encodeProps() throws Exception {
        for (Map<String,Object> c : load("encode_props.json")) {
            byte[] data = fromHex((String) c.get("input_hex"));
            String enc = Ba64.encode(data);
            String plain = java.util.Base64.getEncoder().encodeToString(data);
            check(toHex(Ba64.decode(enc)).equals(c.get("input_hex")), "encode roundtrip " + c.get("name"));
            check(enc.length() <= plain.length(), "encode floor " + c.get("name"));
            for (Object p : (List<Object>) c.get("props")) {
                if (p.equals("compressed")) check(enc.startsWith("="), "compressed " + c.get("name"));
                if (p.equals("plain")) check(enc.equals(plain), "plain " + c.get("name"));
            }
        }
        byte[] d = "The quick brown fox. ".repeat(60).getBytes();
        check(!Ba64.encode(d, 1).equals(Ba64.encode(d, 9)), "level knob reaches deflate");
    }

    static void differential() throws Exception {
        for (Map<String,Object> c : load("differential.json")) {
            String input = (String) c.get("input");
            if (c.get("output_hex") != null)
                check(toHex(Ba64.decode(input)).equals(c.get("output_hex")), "diff bytes");
            else
                check(codeOf(() -> Ba64.decode(input)).equals(c.get("error")), "diff err");
        }
    }

    static void property() {
        Random r = new Random(0xBA64);
        for (int i = 0; i < 5000; i++) {
            byte[] data;
            if (r.nextBoolean()) { data = new byte[r.nextInt(64)]; r.nextBytes(data); }
            else { data = new byte[r.nextInt(300)]; java.util.Arrays.fill(data, (byte) r.nextInt(3)); }
            byte[] got = Ba64.decode(Ba64.encode(data));
            check(java.util.Arrays.equals(got, data), "roundtrip");
            String plain = java.util.Base64.getEncoder().encodeToString(data);
            String enc = Ba64.encode(data);
            check(enc.length() <= plain.length(), "floor");
            check(enc.startsWith("=") == (enc.length() < plain.length()), "marker-iff-smaller");
        }
        for (int i = 0; i < 20000; i++) {
            StringBuilder sb = new StringBuilder();
            int n = r.nextInt(40);
            for (int j = 0; j < n; j++) sb.append((char) r.nextInt(128));
            String s = sb.toString();
            String code = codeOf(() -> Ba64.decode(s));
            check(code.equals("NO_ERROR") || !code.startsWith("NON_TAXONOMY"), "no-crash: " + code);
        }
    }

    static void chaos() throws Exception {
        List<String[]> valid = new ArrayList<>();
        for (String name : new String[]{"decode_plain.json", "decode_frames.json"})
            for (Map<String,Object> c : load(name))
                valid.add(new String[]{(String) c.get("input"), (String) c.get("output_hex")});

        int total = 0;
        for (String[] v : valid) {
            byte[] b = v[0].getBytes(java.nio.charset.StandardCharsets.ISO_8859_1);
            for (int i = 0; i < b.length; i++)
                for (int bit = 0; bit < 8; bit++) {
                    byte[] m = b.clone(); m[i] ^= (1 << bit);
                    String s = new String(m, java.nio.charset.StandardCharsets.ISO_8859_1);
                    String code = codeOf(() -> Ba64.decode(s));
                    check(!code.startsWith("NON_TAXONOMY"), "bitflip: " + code);
                    total++;
                }
            for (int n = 0; n < v[0].length(); n++) {
                String s = v[0].substring(0, n);
                String code = codeOf(() -> Ba64.decode(s));
                check(!code.startsWith("NON_TAXONOMY"), "trunc: " + code);
            }
        }
        check(total > 2000, "bit-flip count");

        // frame corruption never silently wrong
        for (Map<String,Object> c : load("decode_frames.json")) {
            String input = (String) c.get("input");
            byte[] frame = java.util.Base64.getDecoder().decode(input.substring(1));
            String original = (String) c.get("output_hex");
            for (int i = 0; i < frame.length; i++)
                for (int bit = 0; bit < 8; bit++) {
                    byte[] m = frame.clone(); m[i] ^= (1 << bit);
                    String text = "=" + java.util.Base64.getEncoder().encodeToString(m);
                    try {
                        byte[] out = Ba64.decode(text);
                        check(toHex(out).equals(original), "frame silently wrong");
                    } catch (Ba64.Ba64Exception e) { /* ok */ }
                }
        }
    }

    public static void main(String[] args) throws Exception {
        conformance();
        encodeProps();
        differential();
        property();
        chaos();
        System.out.println("Ba64.java: " + checks + " checks, " + failures + " failures");
        if (failures > 0) System.exit(1);
    }
}
