#!/usr/bin/env python3
"""Decode a PBZX stream from stdin to stdout, bounded to one chunk in memory.

Use with `bsdtar -xOf Xcode_12.5.1.xip Content`. This only decodes data;
it does not authenticate Apple's XIP signature or accept license agreements.
"""
import lzma
import struct
import sys


def read_exact(stream, count):
    data = bytearray()
    while len(data) < count:
        part = stream.read(count - len(data))
        if not part:
            raise ValueError("truncated PBZX stream")
        data.extend(part)
    return bytes(data)


def decode(source, destination):
    if read_exact(source, 4) != b"pbzx":
        raise ValueError("not a PBZX stream")
    flags, = struct.unpack(">Q", read_exact(source, 8))
    while flags & (1 << 24):
        flags, length = struct.unpack(">2Q", read_exact(source, 16))
        if not 0 < length <= 64 * 1024 * 1024:
            raise ValueError("invalid PBZX chunk length")
        data = read_exact(source, length)
        if length == 1 << 24:
            destination.write(data)
        else:
            decoder = lzma.LZMADecompressor(memlimit=256 * 1024 * 1024)
            output = decoder.decompress(data, max_length=64 * 1024 * 1024)
            if not decoder.eof or decoder.unused_data:
                raise ValueError("incomplete or oversized XZ chunk")
            destination.write(output)


if __name__ == "__main__":
    try:
        decode(sys.stdin.buffer, sys.stdout.buffer)
    except (ValueError, lzma.LZMAError) as error:
        sys.exit(str(error))
