"""ba64 PayloadCodec for Temporal — shrink workflow/activity payloads under the
gRPC message-size ceiling without the boilerplate of a hand-rolled gzip codec.

A Temporal PayloadCodec transforms every Payload leaving the client and restores
it on the way back. This one ba64-encodes the serialized payload: JSON workflow
arguments and results (the common case) drop to a fraction of their size, while
incompressible payloads take the floor and are never larger than plain base64.

Usage (with `pip install temporalio`):

    from ba64_codec import Ba64PayloadCodec
    client = await Client.connect(
        "localhost:7233",
        data_converter=dataclasses.replace(
            temporalio.converter.default(), payload_codec=Ba64PayloadCodec()
        ),
    )

The codec is safe by construction: `max_decoded_len` bounds decompression (a
hostile server cannot force unbounded allocation), and ba64's CRC guarantees a
corrupted payload is a typed error, never silently-wrong workflow input.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "python"))
import ba64

ENCODING = b"binary/ba64"


def encode_payload_bytes(raw: bytes) -> bytes:
    """Serialized-payload bytes -> ba64 text bytes (ASCII)."""
    return ba64.encode(raw).encode("ascii")


def decode_payload_bytes(data: bytes, *, max_decoded_len: int = 8 * 2 ** 20) -> bytes:
    """ba64 text bytes -> original serialized-payload bytes."""
    return ba64.decode(data.decode("ascii"), max_decoded_len=max_decoded_len)


try:  # real Temporal integration when the SDK is installed
    from temporalio.api.common.v1 import Payload
    from temporalio.converter import PayloadCodec

    class Ba64PayloadCodec(PayloadCodec):
        def __init__(self, *, max_decoded_len: int = 8 * 2 ** 20):
            self._max = max_decoded_len

        async def encode(self, payloads):
            return [
                Payload(metadata={"encoding": ENCODING},
                        data=encode_payload_bytes(p.SerializeToString()))
                for p in payloads
            ]

        async def decode(self, payloads):
            out = []
            for p in payloads:
                if p.metadata.get("encoding") == ENCODING:
                    inner = Payload()
                    inner.ParseFromString(decode_payload_bytes(p.data, max_decoded_len=self._max))
                    out.append(inner)
                else:
                    out.append(p)
            return out

except ImportError:  # SDK absent: the byte-level transform above is still usable
    Ba64PayloadCodec = None
