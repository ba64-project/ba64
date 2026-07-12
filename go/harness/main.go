// Batch harness for conformance/run.py. See python/harness.py for the protocol.
package main

import (
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"

	"ba64"
)

func main() {
	mode := os.Args[1]
	data, _ := io.ReadAll(os.Stdin)
	lines := strings.Split(string(data), "\n")
	n, _ := strconv.Atoi(strings.TrimSpace(lines[0]))
	items := lines[1 : 1+n]
	out := make([]string, 0, n)
	for _, item := range items {
		if mode == "encode" {
			b, _ := hex.DecodeString(item)
			out = append(out, ba64.Encode(b))
		} else {
			b, err := ba64.Decode(item)
			if err != nil {
				out = append(out, "!"+err.(*ba64.Error).Code())
			} else {
				out = append(out, hex.EncodeToString(b))
			}
		}
	}
	fmt.Print(strings.Join(out, "\n"))
}
