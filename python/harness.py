#!/usr/bin/env python3
"""Batch harness for cross-language conformance (conformance/run.py).

Protocol (stdin/stdout), line-based, count-prefixed so empty items are
unambiguous:

  stdin  : first line = N, then N item lines
  stdout : N result lines

  encode : each item is hex(input bytes)     -> result is the ba64 text
  decode : each item is a ba64 text          -> result is hex(bytes) or "!CODE"
"""

import sys

from ba64 import decode, encode, Ba64Error


def main():
    mode = sys.argv[1]
    data = sys.stdin.buffer.read().decode("utf-8", "surrogateescape").split("\n")
    n = int(data[0])
    items = data[1:1 + n]
    out = []
    for item in items:
        if mode == "encode":
            out.append(encode(bytes.fromhex(item)))
        else:
            try:
                out.append(decode(item).hex())
            except Ba64Error as e:
                out.append("!" + e.code)
    sys.stdout.write("\n".join(out))


if __name__ == "__main__":
    main()
