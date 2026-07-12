//! Property-based invariants (proptest).

use ba64::{decode, encode, encode_level, Error};
use proptest::prelude::*;

fn plain_len(n: usize) -> usize {
    (n + 2) / 3 * 4
}

proptest! {
    #[test]
    fn roundtrip(data in prop::collection::vec(any::<u8>(), 0..4096)) {
        prop_assert_eq!(decode(&encode(&data)).unwrap(), data);
    }

    #[test]
    fn roundtrip_compressible(runs in 0usize..400) {
        let data = b"log line ".repeat(runs);
        prop_assert_eq!(decode(&encode(&data)).unwrap(), data);
    }

    #[test]
    fn floor_and_marker(data in prop::collection::vec(any::<u8>(), 0..4096)) {
        let enc = encode(&data);
        prop_assert!(enc.len() <= plain_len(data.len()), "floor");
        prop_assert_eq!(enc.starts_with('='), enc.len() < plain_len(data.len()));
    }

    #[test]
    fn decode_never_panics(s in ".{0,256}") {
        // decode is total: Ok or a taxonomy Err, never a panic.
        match decode(&s) {
            Ok(_) => {}
            Err(e) => { let _: &str = e.code(); }
        }
    }

    #[test]
    fn level_is_honoured_where_it_matters(runs in 20usize..400) {
        let data = b"the quick brown fox ".repeat(runs);
        // both levels must round-trip; output may differ
        prop_assert_eq!(decode(&encode_level(&data, 1)).unwrap(), data.clone());
        prop_assert_eq!(decode(&encode_level(&data, 9)).unwrap(), data);
    }
}

#[test]
fn error_codes_are_stable() {
    assert_eq!(decode("SGVsbG8").unwrap_err(), Error::Base64);
    assert_eq!(decode("SGVsbG8").unwrap_err().code(), "E_BASE64");
}
