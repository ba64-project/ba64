//! Conformance, differential, and chaos tests driven by the shared corpus.

use ba64::{decode, decode_max, encode, encode_level};
use serde_json::Value;
use std::fs;

fn load(name: &str) -> Vec<Value> {
    let text = fs::read_to_string(format!("../vectors/{name}")).unwrap();
    let v: Value = serde_json::from_str(&text).unwrap();
    v["cases"].as_array().unwrap().clone()
}
fn to_hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}
fn from_hex(s: &str) -> Vec<u8> {
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap()).collect()
}

fn expect_bytes(input: &str, out_hex: &str, name: &str) {
    match decode(input) {
        Ok(b) => assert_eq!(to_hex(&b), out_hex, "{name}"),
        Err(e) => panic!("{name}: unexpected error {}", e.code()),
    }
}
fn expect_error(input: &str, code: &str, name: &str, max: u64) {
    expect_error_alt(input, code, &[], name, max);
}
fn expect_error_alt(input: &str, code: &str, alt: &[&str], name: &str, max: u64) {
    match decode_max(input, max) {
        Ok(b) => panic!("{name}: expected {code}, got {} bytes", b.len()),
        Err(e) => {
            let c = e.code();
            assert!(c == code || alt.contains(&c), "{name}: got {c}, want {code} or {alt:?}");
        }
    }
}

#[test]
fn conformance_vectors() {
    for c in load("decode_plain.json") {
        expect_bytes(c["input"].as_str().unwrap(), c["output_hex"].as_str().unwrap(), "plain");
    }
    for c in load("decode_frames.json") {
        expect_bytes(c["input"].as_str().unwrap(), c["output_hex"].as_str().unwrap(), "frame");
    }
    for c in load("decode_errors.json") {
        let alt: Vec<&str> = c["error_alt"].as_array().map(|a| a.iter().map(|x| x.as_str().unwrap()).collect()).unwrap_or_default();
        expect_error_alt(c["input"].as_str().unwrap(), c["error"].as_str().unwrap(), &alt, "err", ba64::DEFAULT_MAX_DECODED_LEN);
    }
    for c in load("bombs.json") {
        let max = c["max_decoded_len"].as_u64().unwrap_or(ba64::DEFAULT_MAX_DECODED_LEN);
        expect_error(c["input"].as_str().unwrap(), c["error"].as_str().unwrap(), "bomb", max);
    }
}

#[test]
fn encode_props() {
    for c in load("encode_props.json") {
        let data = from_hex(c["input_hex"].as_str().unwrap());
        let enc = encode(&data);
        let plain_len = (data.len() + 2) / 3 * 4;
        assert_eq!(decode(&enc).unwrap(), data, "roundtrip");
        assert!(enc.len() <= plain_len, "floor");
        for p in c["props"].as_array().unwrap() {
            match p.as_str().unwrap() {
                "compressed" => assert!(enc.starts_with('=')),
                "plain" => assert!(!enc.starts_with('=')),
                _ => {}
            }
        }
    }
    let d = b"The quick brown fox. ".repeat(60);
    assert_ne!(encode_level(&d, 1), encode_level(&d, 9), "level must reach deflate");
}

#[test]
fn differential_vs_python() {
    for c in load("differential.json") {
        let input = c["input"].as_str().unwrap();
        if let Some(h) = c["output_hex"].as_str() {
            expect_bytes(input, h, "diff");
        } else {
            expect_error(input, c["error"].as_str().unwrap(), "diff", ba64::DEFAULT_MAX_DECODED_LEN);
        }
    }
}

// --- chaos ------------------------------------------------------------------

fn valid_strings() -> Vec<String> {
    let mut v = Vec::new();
    for name in ["decode_plain.json", "decode_frames.json"] {
        for c in load(name) {
            v.push(c["input"].as_str().unwrap().to_string());
        }
    }
    v
}
fn assert_safe(s: &str) {
    // must return Ok or a taxonomy Err — decode is total and never panics
    let _ = decode(s);
}

#[test]
fn chaos_bit_flip_sweep() {
    let mut total = 0;
    for s in valid_strings() {
        let bytes = s.into_bytes();
        for i in 0..bytes.len() {
            for bit in 0..8 {
                let mut m = bytes.clone();
                m[i] ^= 1 << bit;
                assert_safe(&String::from_utf8_lossy(&m));
                total += 1;
            }
        }
    }
    assert!(total > 2000);
}

#[test]
fn chaos_truncation_sweep() {
    for s in valid_strings() {
        for n in 0..s.len() {
            // slice on a char boundary (vectors are ASCII)
            if s.is_char_boundary(n) {
                assert_safe(&s[..n]);
            }
        }
    }
}

#[test]
fn chaos_frame_corruption_never_silent() {
    for c in load("decode_frames.json") {
        let input = c["input"].as_str().unwrap();
        let frame = decode_b64_helper(&input[1..]);
        let original = c["output_hex"].as_str().unwrap();
        for i in 0..frame.len() {
            for bit in 0..8 {
                let mut m = frame.clone();
                m[i] ^= 1 << bit;
                let text = format!("={}", encode_b64_helper(&m));
                if let Ok(out) = decode(&text) {
                    assert_eq!(to_hex(&out), original, "frame silently returned wrong bytes");
                }
            }
        }
    }
}

#[test]
fn bomb_capped_returns_length_mismatch() {
    // 128 MiB of zeros, frame claims 100 -> must reject as length mismatch and,
    // by inflate_exact's payload-bounded cap, allocate O(claim) not O(128 MiB).
    let payload = miniz_helper_compress(&vec![0u8; 128 << 20]);
    let mut frame = vec![1u8, 1, 100]; // version, method, decoded_len=100
    frame.extend_from_slice(&[0, 0, 0, 0]); // crc (length check fires first)
    frame.extend_from_slice(&payload);
    let text = format!("={}", encode_b64_helper(&frame));
    assert_eq!(decode(&text).unwrap_err().code(), "E_LENGTH_MISMATCH");
}

// tiny base64 + deflate helpers for building corruption/bomb inputs
fn encode_b64_helper(data: &[u8]) -> String {
    const A: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::new();
    for ch in data.chunks(3) {
        let b = [ch[0], *ch.get(1).unwrap_or(&0), *ch.get(2).unwrap_or(&0)];
        let n = (b[0] as u32) << 16 | (b[1] as u32) << 8 | b[2] as u32;
        out.push(A[(n >> 18 & 63) as usize] as char);
        out.push(A[(n >> 12 & 63) as usize] as char);
        out.push(if ch.len() > 1 { A[(n >> 6 & 63) as usize] as char } else { '=' });
        out.push(if ch.len() > 2 { A[(n & 63) as usize] as char } else { '=' });
    }
    out
}
fn decode_b64_helper(s: &str) -> Vec<u8> {
    // vectors are canonical; a lenient decode is fine for test scaffolding
    let idx = |c: u8| "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        .bytes().position(|x| x == c).unwrap() as u32;
    let b: Vec<u8> = s.bytes().filter(|&c| c != b'=').collect();
    let mut out = Vec::new();
    for ch in b.chunks(4) {
        let mut n = 0u32;
        for &c in ch { n = n << 6 | idx(c); }
        n <<= 6 * (4 - ch.len());
        let bytes = ch.len() - 1;
        for k in 0..bytes { out.push((n >> (16 - 8 * k) & 0xff) as u8); }
    }
    out
}
fn miniz_helper_compress(data: &[u8]) -> Vec<u8> {
    miniz_oxide::deflate::compress_to_vec(data, 9)
}
