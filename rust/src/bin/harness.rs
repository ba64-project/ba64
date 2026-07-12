//! Batch harness for conformance/run.py. See python/harness.py for the protocol.
use std::io::{self, Read, Write};

fn to_hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}
fn from_hex(s: &str) -> Vec<u8> {
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap()).collect()
}

fn main() {
    let mode = std::env::args().nth(1).unwrap();
    let mut data = String::new();
    io::stdin().read_to_string(&mut data).unwrap();
    let mut lines = data.split('\n');
    let n: usize = lines.next().unwrap().trim().parse().unwrap();
    let items: Vec<&str> = lines.take(n).collect();
    let mut out = Vec::with_capacity(n);
    for item in items {
        if mode == "encode" {
            out.push(ba64::encode(&from_hex(item)));
        } else {
            match ba64::decode(item) {
                Ok(b) => out.push(to_hex(&b)),
                Err(e) => out.push(format!("!{}", e.code())),
            }
        }
    }
    io::stdout().write_all(out.join("\n").as_bytes()).unwrap();
}
