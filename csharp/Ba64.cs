using System;
using System.IO;
using System.IO.Compression;

namespace Ba64Lib;

/// <summary>
/// ba64 — binary-to-text encoding that is never larger than standard base64.
/// Reference C# implementation of the v1 format (see ../spec.md). Standard
/// library only (System.IO.Compression, System.Convert). The normative
/// algorithm is spec.md §4. Encoding is a relation, not a function —
/// equality/dedup/MAC comparisons MUST operate on the decoded bytes.
/// </summary>
public static class Ba64
{
    public const long DefaultMaxDecodedLen = 64L << 20; // 64 MiB (spec §7)
    private const byte Version = 0x01;
    private const byte MethodDeflateRaw = 0x01;

    /// <summary>A decode failure carrying a taxonomy code (spec §5).</summary>
    public sealed class Ba64Exception : Exception
    {
        public string Code { get; }
        public Ba64Exception(string code) : base(code) => Code = code;
    }

    // --- CRC-32/ISO-HDLC, hand-rolled table (poly 0xEDB88320) ---------------
    private static readonly uint[] CrcTable = BuildCrcTable();
    private static uint[] BuildCrcTable()
    {
        var t = new uint[256];
        for (uint i = 0; i < 256; i++)
        {
            uint c = i;
            for (int k = 0; k < 8; k++)
                c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1;
            t[i] = c;
        }
        return t;
    }
    private static uint Crc32(ReadOnlySpan<byte> data)
    {
        uint crc = 0xFFFFFFFF;
        foreach (byte b in data)
            crc = CrcTable[(crc ^ b) & 0xff] ^ (crc >> 8);
        return crc ^ 0xFFFFFFFF;
    }

    // --- base64 (canonical, via decode-then-re-encode-and-compare) ----------
    private static byte[] B64CanonicalDecode(string s)
    {
        byte[] raw;
        try { raw = Convert.FromBase64String(s); }
        catch (FormatException) { throw new Ba64Exception("E_BASE64"); }
        if (Convert.ToBase64String(raw) != s) throw new Ba64Exception("E_BASE64");
        return raw;
    }

    // --- LEB128 -------------------------------------------------------------
    private static byte[] Leb128Encode(ulong n)
    {
        Span<byte> tmp = stackalloc byte[10];
        int i = 0;
        while (true)
        {
            byte b = (byte)(n & 0x7f);
            n >>= 7;
            if (n != 0) tmp[i++] = (byte)(b | 0x80);
            else { tmp[i++] = b; return tmp[..i].ToArray(); }
        }
    }
    private static (ulong value, int pos) Leb128Decode(byte[] buf, int pos)
    {
        ulong value = 0; int shift = 0, start = pos;
        while (true)
        {
            if (pos >= buf.Length) throw new Ba64Exception("E_TRUNCATED");
            int b = buf[pos];
            pos++;
            if (pos - start > 9) throw new Ba64Exception("E_HEADER");
            value |= (ulong)(b & 0x7f) << shift;
            if ((b & 0x80) == 0)
            {
                if (pos - start > 1 && b == 0) throw new Ba64Exception("E_HEADER"); // non-minimal
                return (value, pos);
            }
            shift += 7;
        }
    }

    // Lazily yields one byte per Read so DeflateStream consumes exactly the
    // stream (no over-read), letting us detect trailing bytes precisely.
    private sealed class LazyStream : Stream
    {
        private readonly byte[] _d;
        public int Consumed;
        public LazyStream(byte[] d) => _d = d;
        public override int Read(byte[] b, int o, int c)
        {
            if (Consumed >= _d.Length || c == 0) return 0;
            b[o] = _d[Consumed++];
            return 1;
        }
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => _d.Length;
        public override long Position { get => Consumed; set { } }
        public override void Flush() { }
        public override long Seek(long a, SeekOrigin b) => 0;
        public override void SetLength(long a) { }
        public override void Write(byte[] a, int b, int c) { }
    }

    private static byte[] InflateExact(byte[] payload, long decodedLen)
    {
        if (payload.Length == 0) throw new Ba64Exception("E_PAYLOAD"); // no DEFLATE stream at all
        long bound = (long)payload.Length * 1032 + 64;
        // A real DEFLATE stream can't produce more than `bound`, so the buffer
        // never needs to exceed it even when decodedLen is larger.
        int cap = (int)Math.Min(Math.Min(decodedLen, bound) + 1, int.MaxValue);
        var baseStream = new LazyStream(payload);
        var outBuf = new byte[cap];
        int total = 0;
        try
        {
            using var inf = new DeflateStream(baseStream, CompressionMode.Decompress);
            while (total < outBuf.Length)
            {
                int n = inf.Read(outBuf, total, outBuf.Length - total);
                if (n == 0) break;
                total += n;
            }
        }
        catch (InvalidDataException) { throw new Ba64Exception("E_PAYLOAD"); } // malformed/truncated
        if (total > decodedLen) throw new Ba64Exception("E_LENGTH_MISMATCH"); // exceeded cap
        if (baseStream.Consumed != payload.Length) throw new Ba64Exception("E_PAYLOAD"); // trailing bytes
        return outBuf[..total];
    }

    // --- public API ---------------------------------------------------------
    public static string Encode(byte[] data) => EncodeLevel(data, 6);

    public static string EncodeLevel(byte[] data, int level)
    {
        string plain = Convert.ToBase64String(data);
        var cl = level <= 0 ? CompressionLevel.NoCompression
               : level <= 3 ? CompressionLevel.Fastest
               : level <= 6 ? CompressionLevel.Optimal
               : CompressionLevel.SmallestSize;
        byte[] payload;
        using (var ms = new MemoryStream())
        {
            using (var d = new DeflateStream(ms, cl, true)) d.Write(data, 0, data.Length);
            payload = ms.ToArray();
        }
        using var frame = new MemoryStream();
        frame.WriteByte(Version);
        frame.WriteByte(MethodDeflateRaw);
        var len = Leb128Encode((ulong)data.Length);
        frame.Write(len, 0, len.Length);
        uint crc = Crc32(data);
        frame.WriteByte((byte)(crc & 0xff));
        frame.WriteByte((byte)(crc >> 8 & 0xff));
        frame.WriteByte((byte)(crc >> 16 & 0xff));
        frame.WriteByte((byte)(crc >> 24 & 0xff));
        frame.Write(payload, 0, payload.Length);

        string candidate = "=" + Convert.ToBase64String(frame.ToArray());
        return candidate.Length < plain.Length ? candidate : plain;
    }

    public static byte[] Decode(string text) => DecodeMax(text, DefaultMaxDecodedLen);

    public static byte[] DecodeMax(string text, long maxDecodedLen)
    {
        if (maxDecodedLen < 0) maxDecodedLen = 0; // a negative limit must not wrap to a huge ulong
        if (text.Length == 0 || text[0] != '=') return B64CanonicalDecode(text); // step 1

        byte[] frame = B64CanonicalDecode(text[1..]); // step 2

        if (frame.Length < 1) throw new Ba64Exception("E_TRUNCATED"); // step 3
        if (frame[0] != Version) throw new Ba64Exception("E_VERSION");
        if (frame.Length < 2) throw new Ba64Exception("E_TRUNCATED"); // step 4
        if (frame[1] != MethodDeflateRaw) throw new Ba64Exception("E_METHOD");

        var (value, pos) = Leb128Decode(frame, 2); // step 5
        if (value > (ulong)maxDecodedLen) throw new Ba64Exception("E_LIMIT_EXCEEDED"); // step 6
        long decodedLen = (long)value; // keep full width; a 32-bit cast would silently mis-length

        if (frame.Length - pos < 4) throw new Ba64Exception("E_TRUNCATED"); // step 7
        uint crcStored = (uint)(frame[pos] | frame[pos + 1] << 8 | frame[pos + 2] << 16 | frame[pos + 3] << 24);
        byte[] payload = frame[(pos + 4)..];

        byte[] outBytes = InflateExact(payload, decodedLen); // step 8
        if (outBytes.Length != decodedLen) throw new Ba64Exception("E_LENGTH_MISMATCH");

        if (Crc32(outBytes) != crcStored) throw new Ba64Exception("E_CHECKSUM"); // step 9
        return outBytes; // step 10
    }
}
