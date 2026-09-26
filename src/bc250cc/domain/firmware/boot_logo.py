"""The boot logo inside a BC-250 BIOS image: finding it, replacing it, and
proving that nothing else changed.

Where the logo lives, read from every image in the catalog (P2.00, P3.00,
the Chipset Menu mod, P5.00 and the sixteen MeiMeiDXE v3 variants) and from
two community mods that change it::

    16 MiB SPI image
    └─ firmware volume at 0xAE0000, 3.125 MiB: one file, then free space
       └─ file 9E21FD93… (a volume image) holding one LZMA section
          └─ a 12-byte raw section, then a volume section
             └─ the DXE volume: about 190 drivers, one FFS file each
                └─ file 7BB28B99… (freeform) holding one LZMA section
                   ├─ raw section: the picture, a JPEG in every catalog image
                   └─ UI section: its name

The sixteen MeiMeiDXE images differ from one another in that one file and
nothing else: their publisher replaced it, moved the few files after it and
resized the DXE volume to fit. ``replace_logo`` does exactly that and no
more. Everything outside the volume at 0xAE0000 stays byte for byte, and the
result is read back from scratch and compared, file by file, with the image
it was made from before it can reach a USB drive.

The reader is strict on purpose. An image that differs from the reviewed
layout in any detail (a second file in the volume, a checksum, an alignment
attribute, a byte of free space that is not 0xFF) is refused rather than
worked around, because a mistake here leaves a board that does not start.

Compression is passed in (``compress``/``decompress``) so this module stays
pure; ``bc250cc.infrastructure.firmware.lzma1`` provides the real codec.
"""

from __future__ import annotations

import struct
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from .catalog import ROM_BYTES

#: The picture's size in pixels: that of the MeiMeiDXE logos, the largest
#: flashed on this board that we know of.
LOGO_WIDTH = 672
LOGO_HEIGHT = 378
#: The largest logo MeiMeiDXE ships is 87 KiB. This cap keeps every result
#: inside the largest DXE volume known to boot (see ``LARGEST_KNOWN_VOLUME``).
MAX_LOGO_BYTES = 80 * 1024
#: MeiMeiDXE v3 "SteamOS BlackOut 2": the largest DXE volume, decompressed,
#: in any image known to start on a BC-250.
LARGEST_KNOWN_VOLUME = 0x448000

VOLUME_OFFSET = 0xAE0000
VOLUME_LENGTH = 0x320000

#: A function turning bytes into a firmware LZMA stream, or back.
Codec = Callable[[bytes], bytes]


class BootLogoError(ValueError):
    """The image or the picture is not one a logo can be put into."""


def _guid(text: str) -> bytes:
    return uuid.UUID(text).bytes_le


#: EFI_FIRMWARE_FILE_SYSTEM2_GUID: both volumes are FFS2 volumes.
_FFS2 = _guid("8c8ce578-8a3d-4f1c-9935-896185c32dd3")
#: The file at 0xAE0000 that carries the compressed DXE volume.
_DXE_FILE = _guid("9e21fd93-9c72-4c15-8c4b-e77f1db2d792")
#: EDK2's LZMA_CUSTOM_DECOMPRESS_GUID.
_LZMA = _guid("ee4e5898-3914-4259-9d6e-dc7bd79403cf")
#: AMI's boot logo file.
_LOGO_FILE = _guid("7bb28b99-61bb-11d5-9a5d-0090273fc14d")

_VOLUME_SIGNATURE = b"_FVH"
#: Memory mapped, erase polarity 1, 8-byte alignment and the rest, as every
#: catalog image sets them.
_VOLUME_ATTRIBUTES = 0x0004FEFF
#: The volume header with its one-entry block map.
_HEADER_LENGTH = 72
_BLOCK = 0x1000
#: The extended header sits inside a pad file right after the volume header.
_EXT_PAD_FILE = bytes.fromhex("ff" * 16 + "f4aaf0002c0000f8")
_EXT_HEADER = 96
_EXT_HEADER_SIZE = 20
#: The first real file: the end of the extended header, 8-byte aligned.
_FIRST_FILE = 120

_FILE_HEADER = 24
#: EFI_FILE_HEADER_VALID | EFI_FILE_DATA_VALID, stored inverted (polarity 1).
_FILE_STATE = 0xF8
#: The data checksum of a file without FFS_ATTRIB_CHECKSUM.
_NO_CHECKSUM = 0xAA
_FREEFORM = 0x02
_VOLUME_FILE = 0x0B

_GUID_DEFINED = 0x02
_USER_INTERFACE = 0x15
_VOLUME_IMAGE = 0x17
_RAW = 0x19
_GUIDED_HEADER = 24
_PROCESSING_REQUIRED = 0x0001
#: Sections and files record their size in three bytes.
_LARGEST_SIZE = 0xFFFFFF
#: The 12-byte raw section that puts the DXE volume 16 bytes into the payload.
_PAYLOAD_PAD = bytes.fromhex("0c000019") + bytes(8)

_ERASED = 0xFF


@dataclass(frozen=True)
class _File:
    name: bytes
    type: int
    #: The whole file, header included.
    data: bytes


@dataclass(frozen=True)
class LogoSlot:
    """Where the logo is in one image, and what it holds now."""

    #: The DXE volume, decompressed.
    volume: bytes
    files: tuple[_File, ...]
    #: Position of the logo file in ``files``.
    index: int
    #: The picture as stored: a JPEG in every catalog image.
    picture: bytes
    #: The UI section naming the picture, header included; it is kept.
    name_section: bytes


# ----------------------------------------------------------------- helpers

def _align(value: int, boundary: int) -> int:
    return (value + boundary - 1) & ~(boundary - 1)


def _sum8(data: bytes) -> int:
    return sum(data) & 0xFF


def _sum16(data: bytes) -> int:
    return sum(struct.unpack(f"<{len(data) // 2}H", data)) & 0xFFFF


def _refuse(where: str, what: str) -> BootLogoError:
    return BootLogoError(f"{where}: {what}. This firmware image is not one a logo can be added to.")


def _erased(data: bytes) -> bool:
    return data.count(_ERASED) == len(data)


# ----------------------------------------------------------------- reading

def _check_volume_header(volume: bytes, where: str) -> None:
    if len(volume) < _FIRST_FILE:
        raise _refuse(where, "the volume is truncated")
    if volume[:16] != bytes(16) or volume[16:32] != _FFS2 or volume[40:44] != _VOLUME_SIGNATURE:
        raise _refuse(where, "no FFS2 volume header")
    length = struct.unpack_from("<Q", volume, 32)[0]
    attributes, header_length, _checksum, ext_offset = struct.unpack_from("<IHHH", volume, 44)
    if length != len(volume):
        raise _refuse(where, "the volume length does not match its header")
    if (attributes, header_length, ext_offset, volume[54], volume[55]) != (
        _VOLUME_ATTRIBUTES, _HEADER_LENGTH, _EXT_HEADER, 0, 2,
    ):
        raise _refuse(where, "unexpected volume attributes")
    blocks, block_length, end_blocks, end_length = struct.unpack_from("<IIII", volume, 56)
    if block_length != _BLOCK or blocks * _BLOCK != length or (end_blocks, end_length) != (0, 0):
        raise _refuse(where, "unexpected block map")
    if _sum16(volume[:_HEADER_LENGTH]) != 0:
        raise _refuse(where, "the volume header checksum is wrong")
    if volume[_HEADER_LENGTH:_EXT_HEADER] != _EXT_PAD_FILE:
        raise _refuse(where, "unexpected extended header")
    if struct.unpack_from("<I", volume, _EXT_HEADER + 16)[0] != _EXT_HEADER_SIZE:
        raise _refuse(where, "unexpected extended header size")
    if not _erased(volume[_EXT_HEADER + _EXT_HEADER_SIZE:_FIRST_FILE]):
        raise _refuse(where, "unexpected bytes before the first file")


def _read_file(volume: bytes, offset: int, where: str) -> _File:
    if offset + _FILE_HEADER > len(volume):
        raise _refuse(where, "a file header runs past the end of the volume")
    header = volume[offset:offset + _FILE_HEADER]
    size = int.from_bytes(header[20:23], "little")
    if header[19] != 0:
        raise _refuse(where, "a file has attributes")
    if header[23] != _FILE_STATE:
        raise _refuse(where, "a file is not in the valid state")
    if size < _FILE_HEADER or offset + size > len(volume):
        raise _refuse(where, "a file size runs past the volume")
    check = bytearray(header)
    check[17] = 0
    check[23] = 0
    if _sum8(check) != 0:
        raise _refuse(where, "a file header checksum is wrong")
    if header[17] != _NO_CHECKSUM:
        raise _refuse(where, "a file data checksum is not the expected one")
    return _File(name=bytes(header[:16]), type=header[18], data=bytes(volume[offset:offset + size]))


def _files(volume: bytes, where: str) -> tuple[_File, ...]:
    """Every file of a volume, refusing anything but files and erased space."""
    _check_volume_header(volume, where)
    files: list[_File] = []
    offset = _FIRST_FILE
    while offset + _FILE_HEADER <= len(volume) and not _erased(volume[offset:offset + _FILE_HEADER]):
        found = _read_file(volume, offset, where)
        files.append(found)
        end = offset + len(found.data)
        offset = _align(end, 8)
        if not _erased(volume[end:min(offset, len(volume))]):
            raise _refuse(where, "the gap between two files is not erased")
    if not _erased(volume[offset:]):
        raise _refuse(where, "the free space is not erased")
    return tuple(files)


def _lzma_stream(body: bytes, where: str) -> bytes:
    """The stream of a file body that is one LZMA section and nothing else."""
    if len(body) < _GUIDED_HEADER:
        raise _refuse(where, "the compressed section is truncated")
    if body[3] != _GUID_DEFINED or int.from_bytes(body[:3], "little") != len(body):
        raise _refuse(where, "the file is not one compressed section")
    if body[4:20] != _LZMA:
        raise _refuse(where, "the section is not LZMA compressed")
    if struct.unpack_from("<HH", body, 20) != (_GUIDED_HEADER, _PROCESSING_REQUIRED):
        raise _refuse(where, "unexpected compressed section header")
    return body[_GUIDED_HEADER:]


def _decompress(stream: bytes, decompress: Codec, where: str) -> bytes:
    try:
        return decompress(stream)
    except BootLogoError:
        raise
    except Exception as error:  # noqa: BLE001 - any codec failure means "refuse"
        raise _refuse(where, f"the compressed data does not decode ({error})") from error


def _dxe_volume(rom: bytes, decompress: Codec) -> bytes:
    where = "BIOS image"
    if len(rom) != ROM_BYTES:
        raise _refuse(where, "it is not a 16 MiB image")
    outer = rom[VOLUME_OFFSET:VOLUME_OFFSET + VOLUME_LENGTH]
    files = _files(outer, "volume at 0xAE0000")
    if len(files) != 1 or files[0].name != _DXE_FILE or files[0].type != _VOLUME_FILE:
        raise _refuse(where, "the volume at 0xAE0000 does not hold the DXE volume alone")
    payload = _decompress(
        _lzma_stream(files[0].data[_FILE_HEADER:], where), decompress, "DXE volume"
    )
    if payload[:len(_PAYLOAD_PAD)] != _PAYLOAD_PAD:
        raise _refuse(where, "unexpected start of the DXE payload")
    section = payload[len(_PAYLOAD_PAD):]
    if len(section) < 4 or section[3] != _VOLUME_IMAGE or int.from_bytes(section[:3], "little") != len(section):
        raise _refuse(where, "the DXE payload is not one volume section")
    return section[4:]


def read_logo(rom: bytes, *, decompress: Codec) -> LogoSlot:
    """The logo of a BIOS image, and everything needed to replace it."""
    volume = _dxe_volume(rom, decompress)
    files = _files(volume, "DXE volume")
    matches = [index for index, found in enumerate(files) if found.name == _LOGO_FILE]
    if len(matches) != 1:
        raise _refuse("DXE volume", "there is not exactly one boot logo file")
    index = matches[0]
    logo = files[index]
    if logo.type != _FREEFORM:
        raise _refuse("logo file", "unexpected file type")
    inner = _decompress(
        _lzma_stream(logo.data[_FILE_HEADER:], "logo file"), decompress, "logo file"
    )
    picture_size = int.from_bytes(inner[:3], "little")
    if len(inner) < 4 or inner[3] != _RAW or not 4 <= picture_size <= len(inner):
        raise _refuse("logo file", "the picture section is missing")
    name_offset = _align(picture_size, 4)
    if inner[picture_size:name_offset] != bytes(name_offset - picture_size):
        raise _refuse("logo file", "unexpected padding after the picture")
    name_section = inner[name_offset:]
    if (
        len(name_section) < 6
        or name_section[3] != _USER_INTERFACE
        or int.from_bytes(name_section[:3], "little") != len(name_section)
        or len(name_section) % 2
        or name_section[-2:] != b"\0\0"
    ):
        raise _refuse("logo file", "the picture's name section is missing")
    return LogoSlot(
        volume=volume,
        files=files,
        index=index,
        picture=inner[4:picture_size],
        name_section=name_section,
    )


# ------------------------------------------------------------ the picture

_BASELINE = 0xC0
#: Every other start-of-frame: progressive, lossless, hierarchical, arithmetic.
_OTHER_FRAMES = frozenset({0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF})
#: Components 1, 2 and 3 sampled 2x2, 1x1 and 1x1: 4:2:0, as in every
#: catalog logo.
_SAMPLING = ((1, 0x22), (2, 0x11), (3, 0x11))


def check_logo_jpeg(data: bytes) -> None:
    """Refuse any picture outside the profile the catalog's logos share.

    A baseline JPEG of exactly LOGO_WIDTH × LOGO_HEIGHT, 8-bit YCbCr 4:2:0 in
    one interleaved scan, no restart markers, at most MAX_LOGO_BYTES. The
    firmware's decoder has shown it reads that; nothing else is tried on it.
    """
    if len(data) > MAX_LOGO_BYTES:
        raise BootLogoError(f"The logo is {len(data)} bytes; at most {MAX_LOGO_BYTES} fit.")
    if data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
        raise BootLogoError("The logo is not a complete JPEG.")
    offset = 2
    frame = tables = quantization = False
    scans = 0
    while True:
        if offset + 2 > len(data) or data[offset] != 0xFF:
            raise BootLogoError("The logo JPEG is malformed.")
        marker = data[offset + 1]
        if marker == 0xD9:
            if offset + 2 != len(data) or scans != 1:
                raise BootLogoError("The logo JPEG does not end after its one scan.")
            return
        if offset + 4 > len(data):
            raise BootLogoError("The logo JPEG is malformed.")
        length = struct.unpack_from(">H", data, offset + 2)[0]
        segment = data[offset + 4:offset + 2 + length]
        if length < 2 or offset + 2 + length > len(data):
            raise BootLogoError("The logo JPEG is malformed.")
        if marker == _BASELINE:
            if frame or length != 17:
                raise BootLogoError("The logo JPEG has an unexpected frame.")
            precision, height, width, count = struct.unpack_from(">BHHB", segment)
            sampling = tuple((segment[6 + 3 * k], segment[7 + 3 * k]) for k in range(count))
            if (precision, width, height, sampling) != (8, LOGO_WIDTH, LOGO_HEIGHT, _SAMPLING):
                raise BootLogoError(
                    f"The logo is not a {LOGO_WIDTH} × {LOGO_HEIGHT} colour JPEG (4:2:0)."
                )
            frame = True
        elif marker in _OTHER_FRAMES:
            raise BootLogoError("The logo is a progressive JPEG; only baseline JPEGs are used.")
        elif marker == 0xC4:
            tables = True
        elif marker == 0xDB:
            quantization = True
        elif marker == 0xDD:
            raise BootLogoError("The logo JPEG uses restart markers.")
        elif marker == 0xDA:
            if not (frame and tables and quantization) or scans or segment[:1] != b"\x03":
                raise BootLogoError("The logo JPEG scan is not the one expected.")
            scans += 1
            offset = _scan_end(data, offset + 2 + length)
            continue
        elif not (0xE0 <= marker <= 0xEF or marker == 0xFE):
            raise BootLogoError(f"The logo JPEG has an unexpected marker 0x{marker:02X}.")
        offset += 2 + length


def _scan_end(data: bytes, offset: int) -> int:
    """The offset of the first marker after entropy-coded data."""
    while True:
        offset = data.find(b"\xff", offset)
        if offset < 0 or offset + 1 >= len(data):
            raise BootLogoError("The logo JPEG is cut short.")
        following = data[offset + 1]
        if following == 0x00 or following == 0xFF:
            offset += 1 if following == 0xFF else 2
            continue
        if 0xD0 <= following <= 0xD7:
            raise BootLogoError("The logo JPEG uses restart markers.")
        return offset


# ---------------------------------------------------------------- building

def _section(kind: int, body: bytes) -> bytes:
    size = 4 + len(body)
    if size > _LARGEST_SIZE:
        raise BootLogoError("A section is too large for the firmware format.")
    return size.to_bytes(3, "little") + bytes((kind,)) + body


def _lzma_section(data: bytes, compress: Codec) -> bytes:
    return _section(
        _GUID_DEFINED,
        _LZMA + struct.pack("<HH", _GUIDED_HEADER, _PROCESSING_REQUIRED) + compress(data),
    )


def _file(name: bytes, kind: int, body: bytes) -> bytes:
    size = _FILE_HEADER + len(body)
    if size > _LARGEST_SIZE:
        raise BootLogoError("A file is too large for the firmware format.")
    header = bytearray(name + bytes((0, _NO_CHECKSUM, kind, 0)) + size.to_bytes(3, "little") + bytes((_FILE_STATE,)))
    check = bytearray(header)
    check[17] = 0
    check[23] = 0
    header[16] = -_sum8(check) & 0xFF
    return bytes(header) + body


def _volume(head: bytes, files: list[bytes]) -> bytes:
    """A DXE volume: the original header, then ``files`` packed as the
    firmware's own tools pack them, sized up to a whole block."""
    volume = bytearray(head)
    for data in files:
        volume += bytes((_ERASED,)) * (_align(len(volume), 8) - len(volume))
        volume += data
    length = _align(len(volume), _BLOCK)
    volume += bytes((_ERASED,)) * (length - len(volume))
    struct.pack_into("<Q", volume, 32, length)
    struct.pack_into("<I", volume, 56, length // _BLOCK)
    struct.pack_into("<H", volume, 50, 0)
    struct.pack_into("<H", volume, 50, -_sum16(bytes(volume[:_HEADER_LENGTH])) & 0xFFFF)
    return bytes(volume)


def replace_logo(rom: bytes, jpeg: bytes, *, compress: Codec, decompress: Codec) -> bytes:
    """``rom`` with its boot logo replaced by ``jpeg``, and nothing else changed.

    The result has already passed ``verify_replaced_logo`` when it is returned.
    """
    check_logo_jpeg(jpeg)
    slot = read_logo(rom, decompress=decompress)
    picture = _section(_RAW, jpeg)
    inner = picture + bytes(_align(len(picture), 4) - len(picture)) + slot.name_section
    logo = _file(_LOGO_FILE, _FREEFORM, _lzma_section(inner, compress))
    files = [logo if index == slot.index else found.data for index, found in enumerate(slot.files)]
    volume = _volume(slot.volume[:_FIRST_FILE], files)
    if len(volume) > LARGEST_KNOWN_VOLUME:
        raise BootLogoError("With this logo the firmware would be larger than any known to start.")
    payload = _PAYLOAD_PAD + _section(_VOLUME_IMAGE, volume)
    outer = rom[VOLUME_OFFSET:VOLUME_OFFSET + _FIRST_FILE] + _file(
        _DXE_FILE, _VOLUME_FILE, _lzma_section(payload, compress)
    )
    if len(outer) > VOLUME_LENGTH:
        raise BootLogoError("With this logo the firmware no longer fits in its flash region.")
    outer += bytes((_ERASED,)) * (VOLUME_LENGTH - len(outer))
    built = rom[:VOLUME_OFFSET] + outer + rom[VOLUME_OFFSET + VOLUME_LENGTH:]
    verify_replaced_logo(rom, built, jpeg, decompress=decompress)
    return built


# ------------------------------------------------------------- verifying

#: Volume header bytes a rebuild may change: the length, the checksum and
#: the block count.
_VOLUME_FIELDS = (range(32, 40), range(50, 52), range(56, 60))


def verify_replaced_logo(base: bytes, built: bytes, jpeg: bytes, *, decompress: Codec) -> None:
    """Prove ``built`` is ``base`` with ``jpeg`` as its logo and nothing else.

    Both images are read from scratch, so every checksum, size and alignment
    of ``built`` is checked by the same strict reader that accepted ``base``.
    """
    if len(built) != len(base):
        raise BootLogoError("The image with the new logo does not have the size of the original.")
    end = VOLUME_OFFSET + VOLUME_LENGTH
    if built[:VOLUME_OFFSET] != base[:VOLUME_OFFSET] or built[end:] != base[end:]:
        raise BootLogoError("The new image differs from the original outside the DXE region.")
    if built[VOLUME_OFFSET:VOLUME_OFFSET + _FIRST_FILE] != base[VOLUME_OFFSET:VOLUME_OFFSET + _FIRST_FILE]:
        raise BootLogoError("The new image changed the header of the DXE region.")
    before = read_logo(base, decompress=decompress)
    after = read_logo(built, decompress=decompress)
    if len(after.volume) > LARGEST_KNOWN_VOLUME:
        raise BootLogoError("The new DXE volume is larger than any known to start.")
    variable = {index for fields in _VOLUME_FIELDS for index in fields}
    for index in range(_FIRST_FILE):
        if index not in variable and after.volume[index] != before.volume[index]:
            raise BootLogoError("The new DXE volume header differs from the original.")
    if after.index != before.index or len(after.files) != len(before.files):
        raise BootLogoError("The new DXE volume does not hold the same files.")
    for index, (old, new) in enumerate(zip(before.files, after.files)):
        if index == before.index:
            if (new.name, new.type) != (old.name, old.type):
                raise BootLogoError("The logo file changed identity.")
            continue
        if new.data != old.data:
            raise BootLogoError("A file other than the logo changed.")
    if after.picture != jpeg:
        raise BootLogoError("The logo in the new image is not the one chosen.")
    if after.name_section != before.name_section:
        raise BootLogoError("The logo's name section changed.")
    check_logo_jpeg(after.picture)
