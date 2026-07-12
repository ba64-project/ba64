//! ba64 — binary-to-text encoding that is never larger than standard base64.
//!
//! Reference Rust implementation of the v1 format (see ../spec.md). The only
//! runtime dependency is `miniz_oxide` for DEFLATE (spec §3, the sanctioned
//! exception — never hand-roll inflate); base64 and CRC-32 are implemented here.
//! The normative algorithm is spec.md §4.
//!
//! Encoding is a relation, not a function. Equality/dedup/MAC comparisons MUST
//! operate on the decoded bytes.

use miniz_oxide::deflate::compress_to_vec;
use miniz_oxide::inflate::core::{decompress, inflate_flags, DecompressorOxide};
use miniz_oxide::inflate::TINFLStatus;

pub const DEFAULT_MAX_DECODED_LEN: u64 = 64 << 20; // 64 MiB (spec §7)

const VERSION: u8 = 0x01;
const METHOD_DEFLATE_RAW: u8 = 0x01;

/// A decode failure with a machine-readable taxonomy code (spec §5).
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum Error {
    Base64,
    Truncated,
    Header,
    Version,
    Method,
    LimitExceeded,
    Payload,
    LengthMismatch,
    Checksum,
}

impl Error {
    /// The fixed conformance code string, e.g. "E_BASE64".
    pub fn code(self) -> &'static str {
        match self {
            Error::Base64 => "E_BASE64",
            Error::Truncated => "E_TRUNCATED",
            Error::Header => "E_HEADER",
            Error::Version => "E_VERSION",
            Error::Method => "E_METHOD",
            Error::LimitExceeded => "E_LIMIT_EXCEEDED",
            Error::Payload => "E_PAYLOAD",
            Error::LengthMismatch => "E_LENGTH_MISMATCH",
            Error::Checksum => "E_CHECKSUM",
        }
    }
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.code())
    }
}
impl std::error::Error for Error {}

// --- base64 (canonical RFC 4648 §4, strict) ---------------------------------

const B64: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

fn b64_encode(data: &[u8]) -> String {
    let mut out = String::with_capacity((data.len() + 2) / 3 * 4);
    for chunk in data.chunks(3) {
        let b = [
            chunk[0],
            *chunk.get(1).unwrap_or(&0),
            *chunk.get(2).unwrap_or(&0),
        ];
        let n = (b[0] as u32) << 16 | (b[1] as u32) << 8 | b[2] as u32;
        out.push(B64[(n >> 18 & 63) as usize] as char);
        out.push(B64[(n >> 12 & 63) as usize] as char);
        out.push(if chunk.len() > 1 { B64[(n >> 6 & 63) as usize] as char } else { '=' });
        out.push(if chunk.len() > 2 { B64[(n & 63) as usize] as char } else { '=' });
    }
    out
}

fn b64_val(c: u8) -> Option<u32> {
    match c {
        b'A'..=b'Z' => Some((c - b'A') as u32),
        b'a'..=b'z' => Some((c - b'a' + 26) as u32),
        b'0'..=b'9' => Some((c - b'0' + 52) as u32),
        b'+' => Some(62),
        b'/' => Some(63),
        _ => None,
    }
}

/// Strict canonical base64 decode: rejects non-alphabet characters, wrong
/// length, bad padding, and non-zero trailing bits (spec §1, §4). Equivalent to
/// decode-then-re-encode-and-compare, done directly.
fn b64_decode(s: &str) -> Result<Vec<u8>, Error> {
    let b = s.as_bytes();
    if b.len() % 4 != 0 {
        return Err(Error::Base64);
    }
    let nchunks = b.len() / 4;
    let mut out = Vec::with_capacity(nchunks * 3);
    for (ci, chunk) in b.chunks(4).enumerate() {
        let last = ci == nchunks - 1;
        let (c2_pad, c3_pad) = (chunk[2] == b'=', chunk[3] == b'=');
        // '=' only in the last group, only in positions 2/3, and never "XX=X".
        if chunk[0] == b'=' || chunk[1] == b'=' || (c2_pad && !c3_pad) {
            return Err(Error::Base64);
        }
        if (c2_pad || c3_pad) && !last {
            return Err(Error::Base64);
        }
        let pad = c2_pad as usize + c3_pad as usize;
        let v0 = b64_val(chunk[0]).ok_or(Error::Base64)?;
        let v1 = b64_val(chunk[1]).ok_or(Error::Base64)?;
        let v2 = if c2_pad { 0 } else { b64_val(chunk[2]).ok_or(Error::Base64)? };
        let v3 = if c3_pad { 0 } else { b64_val(chunk[3]).ok_or(Error::Base64)? };
        let n = v0 << 18 | v1 << 12 | v2 << 6 | v3;
        out.push((n >> 16 & 0xff) as u8);
        if pad < 2 {
            out.push((n >> 8 & 0xff) as u8);
        }
        if pad < 1 {
            out.push((n & 0xff) as u8);
        }
        // canonical: unused trailing bits MUST be zero (spec §1)
        if pad == 1 && n & 0xff != 0 {
            return Err(Error::Base64);
        }
        if pad == 2 && (n >> 8) & 0xff != 0 {
            return Err(Error::Base64);
        }
    }
    Ok(out)
}

// --- CRC-32/ISO-HDLC (poly 0xEDB88320) --------------------------------------

fn crc32(data: &[u8]) -> u32 {
    let mut crc = 0xFFFF_FFFFu32;
    for &b in data {
        crc ^= b as u32;
        for _ in 0..8 {
            // mask = poly if the low bit is set, else 0 (branch-free)
            crc = (crc >> 1) ^ (0xEDB8_8320 & (!(crc & 1)).wrapping_add(1));
        }
    }
    !crc
}

// --- LEB128 -----------------------------------------------------------------

fn leb128_encode(mut n: u64) -> Vec<u8> {
    let mut out = Vec::new();
    loop {
        let b = (n & 0x7f) as u8;
        n >>= 7;
        if n != 0 {
            out.push(b | 0x80);
        } else {
            out.push(b);
            return out;
        }
    }
}

fn leb128_decode(buf: &[u8], mut pos: usize) -> Result<(u64, usize), Error> {
    let (mut value, mut shift) = (0u64, 0u32);
    let start = pos;
    loop {
        if pos >= buf.len() {
            return Err(Error::Truncated);
        }
        let b = buf[pos];
        pos += 1;
        if pos - start > 9 {
            return Err(Error::Header);
        }
        value |= ((b & 0x7f) as u64) << shift;
        if b & 0x80 == 0 {
            if pos - start > 1 && b == 0 {
                return Err(Error::Header); // non-minimal
            }
            return Ok((value, pos));
        }
        shift += 7;
    }
}

// --- inflate with hard cap + exact-end detection ----------------------------

fn inflate_exact(payload: &[u8], decoded_len: usize) -> Result<Vec<u8>, Error> {
    // Cap the output at decoded_len (spec §7), but never allocate more than
    // DEFLATE could possibly produce from this payload (~1032x + 64), so a small
    // frame claiming a large size stays cheap (spec §7 buffer-sizing SHOULD).
    let bound = payload.len().saturating_mul(1032).saturating_add(64);
    let cap = decoded_len.min(bound).saturating_add(1);
    let mut out = vec![0u8; cap];
    let mut r = DecompressorOxide::new();
    let flags = inflate_flags::TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF;
    let (status, in_consumed, out_written) = decompress(&mut r, payload, &mut out, 0, flags);
    match status {
        TINFLStatus::Done => {
            if out_written > decoded_len {
                Err(Error::LengthMismatch) // exceeded the cap
            } else if in_consumed != payload.len() {
                Err(Error::Payload) // trailing bytes after the final block
            } else {
                out.truncate(out_written);
                Ok(out)
            }
        }
        TINFLStatus::HasMoreOutput => Err(Error::LengthMismatch),
        _ => Err(Error::Payload), // truncated or malformed
    }
}

// --- public API -------------------------------------------------------------

/// Encode `data` to a ba64 text, racing DEFLATE at `level` (0..=10, use 6)
/// against plain base64 and returning the shorter (spec §6 floor rule).
pub fn encode_level(data: &[u8], level: u8) -> String {
    let plain = b64_encode(data);
    let payload = compress_to_vec(data, level);
    let mut frame = vec![VERSION, METHOD_DEFLATE_RAW];
    frame.extend_from_slice(&leb128_encode(data.len() as u64));
    frame.extend_from_slice(&crc32(data).to_le_bytes());
    frame.extend_from_slice(&payload);
    let candidate = format!("={}", b64_encode(&frame));
    if candidate.len() < plain.len() {
        candidate
    } else {
        plain
    }
}

/// Encode with the default DEFLATE level (6).
pub fn encode(data: &[u8]) -> String {
    encode_level(data, 6)
}

/// Decode a ba64 text to bytes with the default 64 MiB limit.
pub fn decode(text: &str) -> Result<Vec<u8>, Error> {
    decode_max(text, DEFAULT_MAX_DECODED_LEN)
}

/// Decode with an explicit maximum decoded length (spec §4, §7).
pub fn decode_max(text: &str, max_decoded_len: u64) -> Result<Vec<u8>, Error> {
    if !text.starts_with('=') {
        return b64_decode(text); // step 1: plain form (empty -> empty)
    }
    let frame = b64_decode(&text[1..])?; // step 2

    if frame.is_empty() {
        return Err(Error::Truncated); // step 3
    }
    if frame[0] != VERSION {
        return Err(Error::Version);
    }
    if frame.len() < 2 {
        return Err(Error::Truncated); // step 4
    }
    if frame[1] != METHOD_DEFLATE_RAW {
        return Err(Error::Method);
    }

    let (value, pos) = leb128_decode(&frame, 2)?; // step 5
    if value > max_decoded_len || value > usize::MAX as u64 {
        return Err(Error::LimitExceeded); // step 6 (also guards 32-bit usize truncation)
    }
    let decoded_len = value as usize;

    if frame.len() - pos < 4 {
        return Err(Error::Truncated); // step 7
    }
    let crc_stored = u32::from_le_bytes([frame[pos], frame[pos + 1], frame[pos + 2], frame[pos + 3]]);
    let payload = &frame[pos + 4..];

    let out = inflate_exact(payload, decoded_len)?; // step 8
    if out.len() != decoded_len {
        return Err(Error::LengthMismatch);
    }
    if crc32(&out) != crc_stored {
        return Err(Error::Checksum); // step 9
    }
    Ok(out) // step 10
}
