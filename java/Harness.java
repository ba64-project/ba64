import java.nio.charset.StandardCharsets;

/** Batch harness for conformance/run.py. See python/harness.py for the protocol. */
public class Harness {
    static String bytesToHex(byte[] b) {
        StringBuilder s = new StringBuilder();
        for (byte x : b) s.append(String.format("%02x", x));
        return s.toString();
    }
    static byte[] hexToBytes(String s) {
        byte[] b = new byte[s.length() / 2];
        for (int i = 0; i < b.length; i++)
            b[i] = (byte) Integer.parseInt(s.substring(2 * i, 2 * i + 2), 16);
        return b;
    }

    public static void main(String[] args) throws Exception {
        String mode = args[0];
        String[] lines = new String(System.in.readAllBytes(), StandardCharsets.UTF_8).split("\n", -1);
        int n = Integer.parseInt(lines[0].trim());
        StringBuilder out = new StringBuilder();
        for (int i = 1; i <= n; i++) {
            String item = lines[i], res;
            if (mode.equals("encode")) {
                res = Ba64.encode(hexToBytes(item));
            } else {
                try { res = bytesToHex(Ba64.decode(item)); }
                catch (Ba64.Ba64Exception e) { res = "!" + e.code(); }
            }
            if (i > 1) out.append("\n");
            out.append(res);
        }
        System.out.print(out);
    }
}
