#!/usr/bin/env python3
"""ba64 command-line interface: binary on stdin, ba64 text on stdout, and back.

    ba64 encode < input.bin  > output.ba64      # bytes  -> ba64 text (+ newline)
    ba64 decode < output.ba64 > roundtrip.bin   # ba64 text -> bytes

Encode reads raw bytes from stdin and writes the ba64 text followed by a single
newline. Decode reads text from stdin, strips trailing CR/LF (the encoder's newline and
any channel decoration), and writes the decoded bytes. On a decode error it
prints the taxonomy code to stderr and exits 2 — never the payload (spec §8).
"""

import argparse
import sys

from ba64 import Ba64Error, decode, encode


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ba64", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_enc = sub.add_parser("encode", help="bytes (stdin) -> ba64 text (stdout)")
    p_enc.add_argument("-l", "--level", type=int, default=6,
                       help="DEFLATE level 1-9 (default 6)")

    p_dec = sub.add_parser("decode", help="ba64 text (stdin) -> bytes (stdout)")
    p_dec.add_argument("-m", "--max-decoded-len", type=int, default=None,
                       help="reject frames claiming more than this many bytes")

    args = parser.parse_args(argv)

    if args.cmd == "encode":
        data = sys.stdin.buffer.read()
        sys.stdout.buffer.write(encode(data, level=args.level).encode("ascii"))
        sys.stdout.buffer.write(b"\n")
        return 0

    text = sys.stdin.buffer.read().decode("ascii", errors="surrogateescape")
    # strip transport newline artifacts (LF, CRLF, doubled) — ba64 text never
    # contains CR/LF, so this only removes channel decoration (spec §9).
    text = text.rstrip("\r\n")
    kwargs = {}
    if args.max_decoded_len is not None:
        kwargs["max_decoded_len"] = args.max_decoded_len
    try:
        out = decode(text, **kwargs)
    except Ba64Error as e:
        print(e.code, file=sys.stderr)
        return 2
    sys.stdout.buffer.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
