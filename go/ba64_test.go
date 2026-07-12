package ba64

import (
	"bytes"
	"compress/flate"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"hash/crc32"
	"math/rand"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

type vcase struct {
	Name          string   `json:"name"`
	Input         string   `json:"input"`
	OutputHex     *string  `json:"output_hex"`
	Error         string   `json:"error"`
	ErrorAlt      []string `json:"error_alt"`
	InputHex      string   `json:"input_hex"`
	Props         []string `json:"props"`
	MaxDecodedLen *int     `json:"max_decoded_len"`
}

func load(t *testing.T, name string) []vcase {
	t.Helper()
	b, err := os.ReadFile(filepath.Join("..", "vectors", name))
	if err != nil {
		t.Fatal(err)
	}
	var doc struct {
		Cases []vcase `json:"cases"`
	}
	if err := json.Unmarshal(b, &doc); err != nil {
		t.Fatal(err)
	}
	return doc.Cases
}

func codeOf(err error) string {
	if e, ok := err.(*Error); ok {
		return e.Code()
	}
	return "non-taxonomy: " + err.Error()
}

func expectBytes(t *testing.T, input, outHex, name string) {
	got, err := Decode(input)
	if err != nil {
		t.Errorf("%s: unexpected error %v", name, err)
		return
	}
	if hex.EncodeToString(got) != outHex {
		t.Errorf("%s: decode -> %s, want %s", name, hex.EncodeToString(got), outHex)
	}
}

func expectError(t *testing.T, input, code, name string, max int, alt ...string) {
	_, err := DecodeMax(input, max)
	if err == nil {
		t.Errorf("%s: expected error %s, got nil", name, code)
		return
	}
	c := codeOf(err)
	accepted := append([]string{code}, alt...)
	for _, a := range accepted {
		if c == a {
			return
		}
	}
	t.Errorf("%s: got %s, want one of %v", name, c, accepted)
}

func TestErrorShape(t *testing.T) {
	_, err := Decode("SGVsbG8") // bad padding
	e, ok := err.(*Error)
	if !ok || e.Code() != "E_BASE64" || e.Error() != "E_BASE64" {
		t.Fatalf("bad error shape: %v", err)
	}
}

func TestConformance(t *testing.T) {
	for _, c := range load(t, "decode_plain.json") {
		expectBytes(t, c.Input, *c.OutputHex, "plain/"+c.Name)
	}
	for _, c := range load(t, "decode_frames.json") {
		expectBytes(t, c.Input, *c.OutputHex, "frame/"+c.Name)
	}
	for _, c := range load(t, "decode_errors.json") {
		expectError(t, c.Input, c.Error, "err/"+c.Name, DefaultMaxDecodedLen, c.ErrorAlt...)
	}
	for _, c := range load(t, "bombs.json") {
		max := DefaultMaxDecodedLen
		if c.MaxDecodedLen != nil {
			max = *c.MaxDecodedLen
		}
		expectError(t, c.Input, c.Error, "bomb/"+c.Name, max)
	}
}

func TestEncodeProps(t *testing.T) {
	for _, c := range load(t, "encode_props.json") {
		data, _ := hex.DecodeString(c.InputHex)
		enc := Encode(data)
		plain := base64.StdEncoding.EncodeToString(data)
		got, err := Decode(enc)
		if err != nil || hex.EncodeToString(got) != c.InputHex {
			t.Errorf("%s: roundtrip failed", c.Name)
		}
		if len(enc) > len(plain) {
			t.Errorf("%s: floor violated", c.Name)
		}
		for _, p := range c.Props {
			if p == "compressed" && !strings.HasPrefix(enc, "=") {
				t.Errorf("%s: expected compressed", c.Name)
			}
			if p == "plain" && enc != plain {
				t.Errorf("%s: expected plain", c.Name)
			}
		}
	}
	// level knob must reach flate (not be dropped)
	d := bytes.Repeat([]byte("The quick brown fox. "), 60)
	if EncodeLevel(d, 1) == EncodeLevel(d, 9) {
		t.Error("level argument has no effect")
	}
}

func TestDifferential(t *testing.T) {
	for _, c := range load(t, "differential.json") {
		if c.OutputHex != nil {
			expectBytes(t, c.Input, *c.OutputHex, "diff/"+c.Name)
		} else {
			expectError(t, c.Input, c.Error, "diff/"+c.Name, DefaultMaxDecodedLen)
		}
	}
}

// --- property ---------------------------------------------------------------

func TestPropertyRoundtrip(t *testing.T) {
	r := rand.New(rand.NewSource(0xBA64))
	for i := 0; i < 5000; i++ {
		var data []byte
		if r.Intn(2) == 0 {
			data = make([]byte, r.Intn(64))
			r.Read(data)
		} else {
			data = bytes.Repeat([]byte{byte(r.Intn(3))}, r.Intn(300))
		}
		got, err := Decode(Encode(data))
		if err != nil || !bytes.Equal(got, data) {
			t.Fatalf("roundtrip failed for %x", data)
		}
	}
}

func TestPropertyFloorAndMarker(t *testing.T) {
	r := rand.New(rand.NewSource(1))
	for i := 0; i < 5000; i++ {
		var data []byte
		if r.Intn(2) == 0 {
			data = make([]byte, r.Intn(80))
			r.Read(data)
		} else {
			data = bytes.Repeat([]byte("ab "), r.Intn(60))
		}
		enc := Encode(data)
		plain := base64.StdEncoding.EncodeToString(data)
		if len(enc) > len(plain) {
			t.Fatalf("floor violated for %x", data)
		}
		if strings.HasPrefix(enc, "=") != (len(enc) < len(plain)) {
			t.Fatalf("marker-iff-smaller violated for %x", data)
		}
	}
}

func TestPropertyNoCrash(t *testing.T) {
	r := rand.New(rand.NewSource(2))
	for i := 0; i < 20000; i++ {
		b := make([]byte, r.Intn(40))
		for j := range b {
			b[j] = byte(r.Intn(128))
		}
		_, err := Decode(string(b))
		if err != nil {
			if _, ok := err.(*Error); !ok {
				t.Fatalf("non-taxonomy error: %v", err)
			}
		}
	}
}

// --- chaos ------------------------------------------------------------------

func validStrings(t *testing.T) []struct{ in, out string } {
	var v []struct{ in, out string }
	for _, c := range load(t, "decode_plain.json") {
		v = append(v, struct{ in, out string }{c.Input, *c.OutputHex})
	}
	for _, c := range load(t, "decode_frames.json") {
		v = append(v, struct{ in, out string }{c.Input, *c.OutputHex})
	}
	return v
}

func assertSafe(t *testing.T, s string) {
	_, err := Decode(s)
	if err != nil {
		if _, ok := err.(*Error); !ok {
			t.Fatalf("non-taxonomy error on %q: %v", s, err)
		}
	}
}

func TestChaosBitFlipSweep(t *testing.T) {
	total := 0
	for _, v := range validStrings(t) {
		b := []byte(v.in)
		for i := range b {
			for bit := 0; bit < 8; bit++ {
				m := append([]byte(nil), b...)
				m[i] ^= 1 << bit
				assertSafe(t, string(m))
				total++
			}
		}
	}
	if total < 2000 {
		t.Fatalf("only %d bit-flips", total)
	}
}

func TestChaosTruncationSweep(t *testing.T) {
	for _, v := range validStrings(t) {
		for n := 0; n < len(v.in); n++ {
			assertSafe(t, v.in[:n])
		}
	}
}

func TestChaosFrameCorruptionNeverSilent(t *testing.T) {
	for _, c := range load(t, "decode_frames.json") {
		frame, _ := base64.StdEncoding.DecodeString(c.Input[1:])
		for i := range frame {
			for bit := 0; bit < 8; bit++ {
				m := append([]byte(nil), frame...)
				m[i] ^= 1 << bit
				text := "=" + base64.StdEncoding.EncodeToString(m)
				got, err := Decode(text)
				if err != nil {
					if _, ok := err.(*Error); !ok {
						t.Fatalf("non-taxonomy error: %v", err)
					}
					continue
				}
				if hex.EncodeToString(got) != *c.OutputHex {
					t.Fatalf("frame silently returned wrong bytes")
				}
			}
		}
	}
}

func TestChaosInflationCapBoundsMemory(t *testing.T) {
	const inflated = 128 << 20
	var b bytes.Buffer
	w, _ := flate.NewWriter(&b, 9)
	_, _ = w.Write(make([]byte, inflated))
	_ = w.Close()
	var crc [4]byte
	frame := append([]byte{version, methodDeflateRaw, 100}, crc[:]...) // decoded_len=100
	frame = append(frame, b.Bytes()...)
	text := "=" + base64.StdEncoding.EncodeToString(frame)

	var m0, m1 runtime.MemStats
	runtime.GC()
	runtime.ReadMemStats(&m0)
	_, err := Decode(text)
	runtime.ReadMemStats(&m1)
	if codeOf(err) != "E_LENGTH_MISMATCH" {
		t.Fatalf("want E_LENGTH_MISMATCH, got %v", err)
	}
	if grew := int64(m1.TotalAlloc - m0.TotalAlloc); grew > 32<<20 {
		t.Fatalf("cap not enforced: allocated %d bytes", grew)
	}
}

// unused import guard
var _ = binary.LittleEndian
var _ = crc32.IEEE

// --- native fuzz harnesses (go test -fuzz) ----------------------------------

func FuzzDecode(f *testing.F) {
	for _, c := range load(&testing.T{}, "decode_errors.json") {
		f.Add(c.Input)
	}
	f.Fuzz(func(t *testing.T, s string) {
		_, err := Decode(s) // must return bytes or a taxonomy error, never panic
		if err != nil {
			if _, ok := err.(*Error); !ok {
				t.Fatalf("non-taxonomy error: %v", err)
			}
		}
	})
}

func FuzzRoundtrip(f *testing.F) {
	f.Add([]byte("hello"))
	f.Fuzz(func(t *testing.T, data []byte) {
		got, err := Decode(Encode(data))
		if err != nil || !bytes.Equal(got, data) {
			t.Fatalf("roundtrip broken for %x", data)
		}
		if len(Encode(data)) > len(base64.StdEncoding.EncodeToString(data)) {
			t.Fatalf("floor broken for %x", data)
		}
	})
}
