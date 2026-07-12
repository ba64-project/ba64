using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using Ba64Lib;

class Program
{
    static int checks = 0, failures = 0;

    static JsonElement Load(string name)
    {
        string path = Path.Combine("..", "vectors", name);
        return JsonDocument.Parse(File.ReadAllText(path)).RootElement.GetProperty("cases");
    }
    static string ToHex(byte[] b)
    {
        var sb = new StringBuilder();
        foreach (byte x in b) sb.Append(x.ToString("x2"));
        return sb.ToString();
    }
    static byte[] FromHex(string s)
    {
        var b = new byte[s.Length / 2];
        for (int i = 0; i < b.Length; i++) b[i] = Convert.ToByte(s.Substring(2 * i, 2), 16);
        return b;
    }
    static void Check(bool cond, string msg)
    {
        checks++;
        if (!cond) { failures++; Console.WriteLine("FAIL: " + msg); }
    }
    static string CodeOf(Action a)
    {
        try { a(); return "NO_ERROR"; }
        catch (Ba64.Ba64Exception e) { return e.Code; }
        catch (Exception e) { return "NON_TAXONOMY:" + e.GetType().Name; }
    }

    static void Conformance()
    {
        foreach (var c in Load("decode_plain.json").EnumerateArray())
            Check(ToHex(Ba64.Decode(c.GetProperty("input").GetString())) == c.GetProperty("output_hex").GetString(), "plain");
        foreach (var c in Load("decode_frames.json").EnumerateArray())
            Check(ToHex(Ba64.Decode(c.GetProperty("input").GetString())) == c.GetProperty("output_hex").GetString(), "frame");
        foreach (var c in Load("decode_errors.json").EnumerateArray())
        {
            string input = c.GetProperty("input").GetString(), want = c.GetProperty("error").GetString();
            var accepted = new List<string> { want };
            if (c.TryGetProperty("error_alt", out var alt))
                foreach (var a in alt.EnumerateArray()) accepted.Add(a.GetString());
            string got = CodeOf(() => Ba64.Decode(input));
            Check(accepted.Contains(got), $"err/{c.GetProperty("name").GetString()} got {got} want {string.Join("/", accepted)}");
        }
        foreach (var c in Load("bombs.json").EnumerateArray())
        {
            string input = c.GetProperty("input").GetString();
            long max = c.TryGetProperty("max_decoded_len", out var m) ? m.GetInt64() : Ba64.DefaultMaxDecodedLen;
            Check(CodeOf(() => Ba64.DecodeMax(input, max)) == c.GetProperty("error").GetString(), "bomb");
        }
    }

    static void EncodeProps()
    {
        foreach (var c in Load("encode_props.json").EnumerateArray())
        {
            byte[] data = FromHex(c.GetProperty("input_hex").GetString());
            string enc = Ba64.Encode(data), plain = Convert.ToBase64String(data);
            Check(ToHex(Ba64.Decode(enc)) == c.GetProperty("input_hex").GetString(), "roundtrip");
            Check(enc.Length <= plain.Length, "floor");
            foreach (var p in c.GetProperty("props").EnumerateArray())
            {
                if (p.GetString() == "compressed") Check(enc.StartsWith("="), "compressed");
                if (p.GetString() == "plain") Check(enc == plain, "plain");
            }
        }
        byte[] d = Encoding.ASCII.GetBytes(string.Concat(System.Linq.Enumerable.Repeat("The quick brown fox. ", 60)));
        Check(Ba64.EncodeLevel(d, 1) != Ba64.EncodeLevel(d, 9), "level knob reaches deflate");
    }

    static void Differential()
    {
        foreach (var c in Load("differential.json").EnumerateArray())
        {
            string input = c.GetProperty("input").GetString();
            if (c.TryGetProperty("output_hex", out var oh))
                Check(ToHex(Ba64.Decode(input)) == oh.GetString(), "diff bytes");
            else
                Check(CodeOf(() => Ba64.Decode(input)) == c.GetProperty("error").GetString(), "diff err");
        }
    }

    static void Property()
    {
        var r = new Random(0xBA64);
        for (int i = 0; i < 5000; i++)
        {
            byte[] data;
            if (r.Next(2) == 0) { data = new byte[r.Next(64)]; r.NextBytes(data); }
            else { data = new byte[r.Next(300)]; Array.Fill(data, (byte)r.Next(3)); }
            Check(System.Linq.Enumerable.SequenceEqual(Ba64.Decode(Ba64.Encode(data)), data), "roundtrip");
            string enc = Ba64.Encode(data), plain = Convert.ToBase64String(data);
            Check(enc.Length <= plain.Length, "floor");
            Check(enc.StartsWith("=") == (enc.Length < plain.Length), "marker-iff-smaller");
        }
        for (int i = 0; i < 20000; i++)
        {
            int n = r.Next(40);
            var sb = new StringBuilder();
            for (int j = 0; j < n; j++) sb.Append((char)r.Next(128));
            string s = sb.ToString();
            string code = CodeOf(() => Ba64.Decode(s));
            Check(!code.StartsWith("NON_TAXONOMY"), "no-crash: " + code);
        }
    }

    static void Chaos()
    {
        var valid = new List<(string input, string outHex)>();
        foreach (var name in new[] { "decode_plain.json", "decode_frames.json" })
            foreach (var c in Load(name).EnumerateArray())
                valid.Add((c.GetProperty("input").GetString(), c.GetProperty("output_hex").GetString()));

        int total = 0;
        var latin1 = Encoding.Latin1;
        foreach (var (input, _) in valid)
        {
            byte[] b = latin1.GetBytes(input);
            for (int i = 0; i < b.Length; i++)
                for (int bit = 0; bit < 8; bit++)
                {
                    byte[] m = (byte[])b.Clone(); m[i] ^= (byte)(1 << bit);
                    string s = latin1.GetString(m);
                    Check(!CodeOf(() => Ba64.Decode(s)).StartsWith("NON_TAXONOMY"), "bitflip");
                    total++;
                }
            for (int n = 0; n < input.Length; n++)
            {
                string s = input.Substring(0, n);
                Check(!CodeOf(() => Ba64.Decode(s)).StartsWith("NON_TAXONOMY"), "trunc");
            }
        }
        Check(total > 2000, "bit-flip count");

        foreach (var c in Load("decode_frames.json").EnumerateArray())
        {
            string input = c.GetProperty("input").GetString(), original = c.GetProperty("output_hex").GetString();
            byte[] frame = Convert.FromBase64String(input.Substring(1));
            for (int i = 0; i < frame.Length; i++)
                for (int bit = 0; bit < 8; bit++)
                {
                    byte[] m = (byte[])frame.Clone(); m[i] ^= (byte)(1 << bit);
                    string text = "=" + Convert.ToBase64String(m);
                    try { Check(ToHex(Ba64.Decode(text)) == original, "frame silently wrong"); }
                    catch (Ba64.Ba64Exception) { }
                }
        }

        // memory cap: 128 MiB inflation claimed as 100 -> length mismatch, cheap
        byte[] big;
        using (var ms = new MemoryStream())
        {
            using (var dz = new DeflateStream(ms, CompressionLevel.SmallestSize, true))
                dz.Write(new byte[128 << 20], 0, 128 << 20);
            big = ms.ToArray();
        }
        var fr = new List<byte> { 1, 1, 100, 0, 0, 0, 0 };
        fr.AddRange(big);
        string bomb = "=" + Convert.ToBase64String(fr.ToArray());
        Check(CodeOf(() => Ba64.Decode(bomb)) == "E_LENGTH_MISMATCH", "memory-cap bomb");
    }

    // Batch harness for conformance/run.py. See python/harness.py for the protocol.
    static int Harness(string mode)
    {
        string[] lines = Console.In.ReadToEnd().Split('\n');
        int n = int.Parse(lines[0].Trim());
        var outp = new StringBuilder();
        for (int i = 1; i <= n; i++)
        {
            string item = lines[i], res;
            if (mode == "encode") res = Ba64.Encode(FromHex(item));
            else
            {
                try { res = ToHex(Ba64.Decode(item)); }
                catch (Ba64.Ba64Exception e) { res = "!" + e.Code; }
            }
            if (i > 1) outp.Append('\n');
            outp.Append(res);
        }
        Console.Out.Write(outp.ToString());
        return 0;
    }

    static int Main(string[] args)
    {
        if (args.Length > 0) return Harness(args[0]);
        Conformance();
        EncodeProps();
        Differential();
        Property();
        Chaos();
        Console.WriteLine($"Ba64.cs: {checks} checks, {failures} failures");
        return failures > 0 ? 1 : 0;
    }
}
