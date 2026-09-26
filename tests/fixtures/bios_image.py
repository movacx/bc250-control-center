"""A synthetic BC-250 BIOS image: the real layout, none of the real code.

Only what ``boot_logo`` reads is real: the firmware volume at 0xAE0000, the
compressed DXE volume inside it, and the logo file in that. The rest of the
16 MiB is a byte pattern, so a change anywhere shows. The drivers are
stand-ins of different lengths, so files land on and off 8-byte boundaries.

This writer is deliberately separate from ``boot_logo`` and written from the
layout read out of the catalog's images, not from that module: it is the
second implementation the tests hold the first against. Built twice with two
pictures, the images must come out byte for byte what ``replace_logo`` makes
of one with the other.
"""

from __future__ import annotations

import struct
import uuid

from bc250cc.infrastructure.firmware import lzma1

ROM_BYTES = 16 * 1024 * 1024
OUTER_AT = 0xAE0000
OUTER_LENGTH = 0x320000


def guid(text: str) -> bytes:
    return uuid.UUID(text).bytes_le


FFS2 = guid("8c8ce578-8a3d-4f1c-9935-896185c32dd3")
DXE_FILE = guid("9e21fd93-9c72-4c15-8c4b-e77f1db2d792")
LZMA = guid("ee4e5898-3914-4259-9d6e-dc7bd79403cf")
LOGO_FILE = guid("7bb28b99-61bb-11d5-9a5d-0090273fc14d")
OUTER_NAME = guid("4f1c52d3-d824-4d2a-a2f0-ec40c23c5916")
DXE_NAME = guid("5c60f367-a505-419a-859e-2a4ff6ca6fe5")


def section(kind: int, body: bytes) -> bytes:
    return (4 + len(body)).to_bytes(3, "little") + bytes((kind,)) + body


def lzma_section(data: bytes, compress=lzma1.compress) -> bytes:
    return section(0x02, LZMA + struct.pack("<HH", 24, 0x0001) + compress(data))


def ffs(name: bytes, kind: int, body: bytes, *, attributes: int = 0, state: int = 0xF8) -> bytes:
    size = 24 + len(body)
    header = bytearray(name + bytes((0, 0xAA, kind, attributes)) + size.to_bytes(3, "little") + bytes((state,)))
    covered = sum(header) - header[17] - header[23]
    header[16] = -covered & 0xFF
    return bytes(header) + body


def volume(files: list[bytes], name: bytes, length: int | None = None) -> bytes:
    """An FFS2 volume: header, the pad file holding the extended header, files."""
    body = bytearray()
    body += bytes.fromhex("ff" * 16 + "f4aaf0002c0000f8")  # pad file header
    body += name + struct.pack("<I", 20)  # extended header
    body += b"\xff" * 4
    for data in files:
        while (72 + len(body)) % 8:
            body += b"\xff"
        body += data
    used = 72 + len(body)
    if length is None:
        length = (used + 0xFFF) & ~0xFFF
    body += b"\xff" * (length - used)
    header = bytearray(
        bytes(16) + FFS2 + struct.pack("<Q", length) + b"_FVH"
        + struct.pack("<IHHHBB", 0x0004FEFF, 72, 0, 96, 0, 2)
        + struct.pack("<IIII", length // 0x1000, 0x1000, 0, 0)
    )
    checksum = -sum(struct.unpack("<36H", header)) & 0xFFFF
    struct.pack_into("<H", header, 50, checksum)
    return bytes(header) + bytes(body)


def driver(index: int) -> bytes:
    code = bytes((index * 37 + offset) % 251 for offset in range(900 + index * 13))
    name = f"Driver{index}".encode("utf-16-le") + b"\0\0"
    body = section(0x10, code)
    body += bytes(-len(body) % 4) + section(0x15, name)
    return ffs(guid(f"00000000-0000-4000-8000-{index:012d}"), 0x07, body)


def logo(picture: bytes, name: str = "Logo.bmp") -> bytes:
    raw = section(0x19, picture)
    inner = raw + bytes(-len(raw) % 4) + section(0x15, name.encode("utf-16-le") + b"\0\0")
    return ffs(LOGO_FILE, 0x02, lzma_section(inner))


def dxe_volume(picture: bytes, *, before: int = 5, after: int = 3, name: str = "Logo.bmp") -> bytes:
    files = [driver(index) for index in range(before)]
    files.append(logo(picture, name))
    files += [driver(100 + index) for index in range(after)]
    return volume(files, DXE_NAME)


def image(picture: bytes = b"\xff\xd8 the logo it shipped with \xff\xd9", *, outer_files=None, **options) -> bytes:
    """A whole 16 MiB image whose DXE volume holds ``picture`` as its logo."""
    payload = bytes.fromhex("0c000019") + bytes(8) + section(0x17, dxe_volume(picture, **options))
    files = outer_files if outer_files is not None else [ffs(DXE_FILE, 0x0B, lzma_section(payload))]
    outer = volume(files, OUTER_NAME, OUTER_LENGTH)
    pattern = bytes((index * 7 + 3) % 256 for index in range(4096))
    rom = bytearray(pattern * (ROM_BYTES // len(pattern)))
    rom[OUTER_AT:OUTER_AT + OUTER_LENGTH] = outer
    return bytes(rom)
