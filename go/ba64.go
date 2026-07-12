// Package ba64 implements the ba64 v1 binary-to-text encoding: never larger than
// standard base64, with a leading '=' marking a compressed (raw DEFLATE) frame
// and a CRC-32 over the decoded bytes so a decoder never silently returns wrong
// data. The normative algorithm is spec.md §4; this file implements it exactly.
//
// Standard library only (compress/flate, hash/crc32, encoding/base64,
// encoding/binary). Encoding is a relation, not a function — the same input may
// yield different valid ba64 texts, so equality/dedup/MAC must use decoded bytes.
package ba64

import (
	"bytes"
	"compress/flate"
	"encoding/base64"
	"encoding/binary"
	"hash/crc32"
	"io"
)

// DefaultMaxDecodedLen is the default decode limit (64 MiB, spec §7).
const DefaultMaxDecodedLen = 64 << 20

const (
	version         = 0x01
	methodDeflateRaw = 0x01
)

// Error is a decode failure carrying a machine-readable taxonomy code (spec §5):
// one of E_BASE64, E_TRUNCATED, E_HEADER, E_VERSION, E_METHOD, E_LIMIT_EXCEEDED,
// E_PAYLOAD, E_LENGTH_MISMATCH, E_CHECKSUM. Branch on Code, never the string.
type Error struct{ code string }

func (e *Error) Error() string { return e.code }

// Code returns the taxonomy code.
func (e *Error) Code() string { return e.code }

func errc(code string) error { return &Error{code: code} }

// b64CanonicalDecode decodes canonical RFC 4648 §4 base64 or returns E_BASE64.
// Go's decoder ignores non-zero trailing bits, so strictness comes from
// decode-then-re-encode-and-compare (spec §4 note).
func b64CanonicalDecode(s string) ([]byte, error) {
	raw, err := base64.StdEncoding.DecodeString(s)
	if err != nil {
		return nil, errc("E_BASE64")
	}
	if base64.StdEncoding.EncodeToString(raw) != s {
		return nil, errc("E_BASE64")
	}
	return raw, nil
}

func leb128Encode(n uint64) []byte {
	var out []byte
	for {
		b := byte(n & 0x7f)
		n >>= 7
		if n != 0 {
			out = append(out, b|0x80)
		} else {
			return append(out, b)
		}
	}
}

// leb128Decode reads a minimal unsigned LEB128 at pos, returning (value, newPos).
// E_TRUNCATED if the buffer ends mid-varint; E_HEADER if > 9 bytes or non-minimal.
func leb128Decode(buf []byte, pos int) (uint64, int, error) {
	var value uint64
	var shift uint
	start := pos
	for {
		if pos >= len(buf) {
			return 0, 0, errc("E_TRUNCATED")
		}
		b := buf[pos]
		pos++
		if pos-start > 9 {
			return 0, 0, errc("E_HEADER")
		}
		value |= uint64(b&0x7f) << shift
		if b&0x80 == 0 {
			if pos-start > 1 && b == 0 {
				return 0, 0, errc("E_HEADER") // non-minimal
			}
			return value, pos, nil
		}
		shift += 7
	}
}

// inflateExact inflates payload (raw DEFLATE) with a hard output cap of
// decodedLen. bytes.Reader implements io.ByteReader, so flate consumes exactly
// the stream and br.Len() reveals trailing bytes. Returns E_LENGTH_MISMATCH if
// the cap is exceeded, E_PAYLOAD if malformed/truncated or trailing bytes remain.
func inflateExact(payload []byte, decodedLen int) ([]byte, error) {
	br := bytes.NewReader(payload)
	fr := flate.NewReader(br)
	defer fr.Close()
	out, err := io.ReadAll(io.LimitReader(fr, int64(decodedLen)+1))
	if err != nil {
		return nil, errc("E_PAYLOAD") // truncated or malformed stream
	}
	if len(out) > decodedLen { // exceeded the cap (O(cap) memory)
		return nil, errc("E_LENGTH_MISMATCH")
	}
	if br.Len() != 0 { // bytes remain after the final block
		return nil, errc("E_PAYLOAD")
	}
	return out, nil
}

// Encode races raw DEFLATE at the given level (0..9, use 6 by default via
// EncodeLevel) against plain base64 and returns the shorter text (spec §6).
func Encode(data []byte) string { return EncodeLevel(data, 6) }

// EncodeLevel encodes with an explicit DEFLATE level.
func EncodeLevel(data []byte, level int) string {
	plain := base64.StdEncoding.EncodeToString(data)
	var b bytes.Buffer
	w, err := flate.NewWriter(&b, level)
	if err != nil {
		return plain // invalid level: fall back to the always-plain encoder (spec §6.4)
	}
	_, _ = w.Write(data)
	_ = w.Close()
	payload := b.Bytes()

	frame := []byte{version, methodDeflateRaw}
	frame = append(frame, leb128Encode(uint64(len(data)))...)
	var crc [4]byte
	binary.LittleEndian.PutUint32(crc[:], crc32.ChecksumIEEE(data))
	frame = append(frame, crc[:]...)
	frame = append(frame, payload...)

	candidate := "=" + base64.StdEncoding.EncodeToString(frame)
	if len(candidate) < len(plain) {
		return candidate
	}
	return plain
}

// Decode decodes a ba64 text to bytes, or returns an *Error. Implements the
// ordered checks of spec §4 with the default 64 MiB limit.
func Decode(text string) ([]byte, error) { return DecodeMax(text, DefaultMaxDecodedLen) }

// DecodeMax decodes with an explicit maximum decoded length (spec §7).
func DecodeMax(text string, maxDecodedLen int) ([]byte, error) {
	if maxDecodedLen < 0 {
		maxDecodedLen = 0 // a negative limit must not wrap to a huge uint64
	}
	if len(text) == 0 || text[0] != '=' { // step 1: plain form
		return b64CanonicalDecode(text)
	}

	frame, err := b64CanonicalDecode(text[1:]) // step 2
	if err != nil {
		return nil, err
	}

	if len(frame) < 1 { // step 3: version
		return nil, errc("E_TRUNCATED")
	}
	if frame[0] != version {
		return nil, errc("E_VERSION")
	}
	if len(frame) < 2 { // step 4: method
		return nil, errc("E_TRUNCATED")
	}
	if frame[1] != methodDeflateRaw {
		return nil, errc("E_METHOD")
	}

	value, pos, err := leb128Decode(frame, 2) // step 5
	if err != nil {
		return nil, err
	}
	if value > uint64(maxDecodedLen) { // step 6: before any big allocation
		return nil, errc("E_LIMIT_EXCEEDED")
	}
	decodedLen := int(value)

	if len(frame)-pos < 4 { // step 7: crc32
		return nil, errc("E_TRUNCATED")
	}
	crcStored := binary.LittleEndian.Uint32(frame[pos : pos+4])
	payload := frame[pos+4:]

	out, err := inflateExact(payload, decodedLen) // step 8
	if err != nil {
		return nil, err
	}
	if len(out) != decodedLen {
		return nil, errc("E_LENGTH_MISMATCH")
	}
	if crc32.ChecksumIEEE(out) != crcStored { // step 9
		return nil, errc("E_CHECKSUM")
	}
	return out, nil // step 10
}
