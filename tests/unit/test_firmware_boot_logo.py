"""Replacing the boot logo inside a BIOS image, against a synthetic image.

The synthetic image (tests/fixtures/bios_image.py) is written by a second,
independent implementation of the layout read out of the catalog's images.
The strongest check below follows from that: an image built with picture A,
given picture B by ``replace_logo``, must be byte for byte the image the
fixture builds with picture B. The rest pins every refusal, because each one
stands between a malformed image and a board that does not start.

The real images are checked the same way in
tests/infrastructure/test_boot_logo_real_images.py, when they are cached.
"""

from __future__ import annotations

import lzma
import struct

import pytest
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRect
from PyQt6.QtGui import QColor, QImage, QImageWriter, QPainter

from bc250cc.domain.firmware import boot_logo
from bc250cc.domain.firmware.boot_logo import (
    LOGO_HEIGHT,
    LOGO_WIDTH,
    MAX_LOGO_BYTES,
    VOLUME_LENGTH,
    VOLUME_OFFSET,
    BootLogoError,
    check_logo_jpeg,
    read_logo,
    replace_logo,
    verify_replaced_logo,
)
from bc250cc.infrastructure.firmware import lzma1
from tests.fixtures import bios_image

pytestmark = pytest.mark.skipif(bool(lzma1.available()), reason=lzma1.available() or "liblzma ready")

CODEC = {"compress": lzma1.compress, "decompress": lzma1.decompress}


def _jpeg(width=LOGO_WIDTH, height=LOGO_HEIGHT, *, quality=85, colour="#1e88e5", grey=False, progressive=False):
    image = QImage(width, height, QImage.Format.Format_RGB888)
    image.fill(QColor(0, 0, 0))
    painter = QPainter(image)
    painter.fillRect(QRect(width // 4, height // 4, width // 2, height // 2), QColor(colour))
    painter.end()
    if grey:
        image = image.convertToFormat(QImage.Format.Format_Grayscale8)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QImageWriter(buffer, b"jpeg")
    writer.setQuality(quality)
    writer.setProgressiveScanWrite(progressive)
    assert writer.write(image)
    buffer.close()
    return bytes(data)


@pytest.fixture(scope="module")
def pictures(qapp):
    return {"blue": _jpeg(), "orange": _jpeg(colour="#fb8c00")}


@pytest.fixture(scope="module")
def base():
    return bios_image.image()


# ------------------------------------------------------------------ reading

def test_the_logo_and_its_name_are_found(base):
    slot = read_logo(base, decompress=lzma1.decompress)
    assert slot.picture == b"\xff\xd8 the logo it shipped with \xff\xd9"
    assert slot.name_section[4:].decode("utf-16-le") == "Logo.bmp\0"
    assert slot.index == 5
    assert len(slot.files) == 9


# ----------------------------------------------------------------- replacing

def test_the_result_is_what_an_image_built_with_that_picture_would_be(base, pictures):
    """Two writers, one layout: nothing else moved, nothing else changed."""
    built = replace_logo(base, pictures["blue"], **CODEC)
    assert built == bios_image.image(pictures["blue"])


def test_only_the_logo_file_changes(base, pictures):
    built = replace_logo(base, pictures["blue"], **CODEC)
    before, after = read_logo(base, decompress=lzma1.decompress), read_logo(built, decompress=lzma1.decompress)
    assert built[:VOLUME_OFFSET] == base[:VOLUME_OFFSET]
    assert built[VOLUME_OFFSET + VOLUME_LENGTH:] == base[VOLUME_OFFSET + VOLUME_LENGTH:]
    assert [f.data for i, f in enumerate(after.files) if i != after.index] == [
        f.data for i, f in enumerate(before.files) if i != before.index
    ]
    assert after.picture == pictures["blue"]
    assert after.name_section == before.name_section
    assert len(after.volume) % 0x1000 == 0 and len(after.volume) > len(before.volume)


def test_a_logo_can_be_replaced_again(base, pictures):
    once = replace_logo(base, pictures["blue"], **CODEC)
    twice = replace_logo(once, pictures["orange"], **CODEC)
    assert twice == bios_image.image(pictures["orange"])
    assert read_logo(twice, decompress=lzma1.decompress).picture == pictures["orange"]


def test_a_logo_file_that_is_the_last_file_is_replaced_too(pictures):
    base = bios_image.image(after=0)
    assert replace_logo(base, pictures["blue"], **CODEC) == bios_image.image(pictures["blue"], after=0)


def test_a_result_larger_than_any_known_to_start_is_refused(monkeypatch, base, pictures):
    monkeypatch.setattr(boot_logo, "LARGEST_KNOWN_VOLUME", 0x1000)
    with pytest.raises(BootLogoError, match="larger than any known to start"):
        replace_logo(base, pictures["blue"], **CODEC)


# -------------------------------------------------------------- refusing

def _payload(picture=b"\xff\xd8x\xff\xd9", **options) -> bytes:
    return bytes.fromhex("0c000019") + bytes(8) + bios_image.section(
        0x17, bios_image.dxe_volume(picture, **options)
    )


def _outer_file(payload: bytes, **options) -> bytes:
    return bios_image.ffs(bios_image.DXE_FILE, 0x0B, bios_image.lzma_section(payload), **options)


def _with_eopm(data: bytes) -> bytes:
    return lzma1.PROPERTIES + struct.pack("<Q", len(data)) + lzma.compress(
        data, format=lzma.FORMAT_RAW,
        filters=[{"id": lzma.FILTER_LZMA1, "lc": 3, "lp": 0, "pb": 2, "dict_size": 1 << 24}],
    )


def _flip(rom: bytes, offset: int) -> bytes:
    changed = bytearray(rom)
    changed[offset] ^= 0x01
    return bytes(changed)


REFUSALS = {
    "not 16 MiB": lambda rom: rom[:-1],
    "no volume header": lambda rom: _flip(rom, VOLUME_OFFSET + 40),
    "volume checksum": lambda rom: _flip(rom, VOLUME_OFFSET + 50),
    "free space not erased": lambda rom: _flip(rom, VOLUME_OFFSET + VOLUME_LENGTH - 1),
    "file header checksum": lambda rom: _flip(rom, VOLUME_OFFSET + 120 + 16),
    "file data checksum": lambda rom: _flip(rom, VOLUME_OFFSET + 120 + 17),
    "compressed data damaged": lambda rom: _flip(rom, VOLUME_OFFSET + 120 + 48 + 400),
    "second file": lambda rom: bios_image.image(outer_files=[_outer_file(_payload()), bios_image.driver(1)]),
    "file attributes": lambda rom: bios_image.image(outer_files=[_outer_file(_payload(), attributes=0x40)]),
    "file state": lambda rom: bios_image.image(outer_files=[_outer_file(_payload(), state=0xFC)]),
    "end marker": lambda rom: bios_image.image(outer_files=[bios_image.ffs(
        bios_image.DXE_FILE, 0x0B, bios_image.lzma_section(_payload(), compress=_with_eopm))]),
    "payload start": lambda rom: bios_image.image(outer_files=[_outer_file(b"\x0c\x00\x00\x19" + b"\x01" * 8 + _payload()[12:])]),
    "not a volume file": lambda rom: bios_image.image(outer_files=[
        bios_image.ffs(bios_image.DXE_FILE, 0x02, bios_image.lzma_section(_payload()))]),
}


@pytest.mark.parametrize("damage", list(REFUSALS), ids=list(REFUSALS))
def test_anything_but_the_reviewed_layout_is_refused(base, pictures, damage):
    with pytest.raises(BootLogoError, match="not one a logo can be added to"):
        replace_logo(REFUSALS[damage](base), pictures["blue"], **CODEC)


def _image_with_dxe_files(files: list[bytes]) -> bytes:
    payload = bytes.fromhex("0c000019") + bytes(8) + bios_image.section(
        0x17, bios_image.volume(files, bios_image.DXE_NAME)
    )
    return bios_image.image(outer_files=[_outer_file(payload)])


@pytest.mark.parametrize(
    "files, reason",
    [
        ([bios_image.driver(1), bios_image.driver(2)], "not exactly one boot logo file"),
        ([bios_image.logo(b"a"), bios_image.driver(2), bios_image.logo(b"b")], "not exactly one boot logo file"),
        ([bios_image.ffs(bios_image.LOGO_FILE, 0x07, bios_image.lzma_section(b"x" * 10))], "unexpected file type"),
        ([bios_image.ffs(bios_image.LOGO_FILE, 0x02, bios_image.lzma_section(
            bios_image.section(0x19, b"\xff\xd8xy")))], "name section is missing"),
        ([bios_image.ffs(bios_image.LOGO_FILE, 0x02, bios_image.section(0x19, b"\xff\xd8" + b"x" * 40))],
         "not one compressed section"),
        ([bios_image.driver(1), bios_image.ffs(bios_image.guid("11111111-2222-4333-8444-555555555555"), 0x07,
                                               b"x" * 40, attributes=0x38), bios_image.logo(b"a")],
         "a file has attributes"),
    ],
    ids=["no logo", "two logos", "logo of another type", "no name", "uncompressed logo", "aligned file"],
)
def test_a_dxe_volume_that_is_not_the_reviewed_one_is_refused(pictures, files, reason):
    with pytest.raises(BootLogoError, match=reason):
        replace_logo(_image_with_dxe_files(files), pictures["blue"], **CODEC)


# --------------------------------------------------------------- verifying

def test_verification_catches_a_change_anywhere_else(base, pictures):
    built = replace_logo(base, pictures["blue"], **CODEC)
    verify_replaced_logo(base, built, pictures["blue"], decompress=lzma1.decompress)
    with pytest.raises(BootLogoError, match="outside the DXE region"):
        verify_replaced_logo(base, _flip(built, 0x1000), pictures["blue"], decompress=lzma1.decompress)
    with pytest.raises(BootLogoError, match="not the one chosen"):
        verify_replaced_logo(base, built, pictures["orange"], decompress=lzma1.decompress)
    with pytest.raises(BootLogoError, match="size of the original"):
        verify_replaced_logo(base, built[:-1], pictures["blue"], decompress=lzma1.decompress)


def test_verification_catches_another_file_changing(base, pictures):
    """A tampered driver inside an otherwise valid, rebuilt DXE volume."""
    tampered_driver = bytearray(bios_image.driver(2))
    tampered_driver[200] ^= 0xFF
    files = [bios_image.driver(0), bios_image.driver(1), bytes(tampered_driver), bios_image.driver(3),
             bios_image.driver(4), bios_image.logo(pictures["blue"])] + [bios_image.driver(100 + i) for i in range(3)]
    # The data checksum of a file without FFS_ATTRIB_CHECKSUM is a constant,
    # so the tampered driver still reads as a valid file.
    built = _image_with_dxe_files(files)
    with pytest.raises(BootLogoError, match="other than the logo changed"):
        verify_replaced_logo(base, built, pictures["blue"], decompress=lzma1.decompress)


def test_verification_catches_a_renamed_logo(base, pictures):
    renamed = bios_image.image(pictures["blue"], name="Other.jpg")
    with pytest.raises(BootLogoError, match="name section changed"):
        verify_replaced_logo(base, renamed, pictures["blue"], decompress=lzma1.decompress)


# ---------------------------------------------------------------- pictures

def test_the_picture_profile_accepts_what_qt_writes_up_to_quality_90(qapp):
    for quality in (30, 60, 90):
        check_logo_jpeg(_jpeg(quality=quality))


def _patched(data: bytes, marker: bytes, offset: int, value: bytes) -> bytes:
    at = data.index(marker)
    return data[:at + offset] + value + data[at + offset + len(value):]


PICTURE_REFUSALS = {
    "wrong size": (lambda: _jpeg(LOGO_WIDTH - 2, LOGO_HEIGHT), "672 × 378 colour JPEG"),
    "grey": (lambda: _jpeg(grey=True), "unexpected frame"),
    "4:4:4": (lambda: _patched(_jpeg(), b"\xff\xc0", 11, b"\x11"), "672 × 378 colour JPEG"),
    "progressive": (lambda: _jpeg(progressive=True), "progressive"),
    "cut short": (lambda: _jpeg()[:-200], "not a complete JPEG"),
    "trailing bytes": (lambda: _jpeg() + b"\xff\xd9", "does not end after its one scan"),
    "restart interval": (lambda: _jpeg()[:2] + b"\xff\xdd\x00\x04\x00\x10" + _jpeg()[2:], "restart markers"),
    "not a JPEG": (lambda: b"\x89PNG\r\n\x1a\n" + bytes(100) + b"\xff\xd9", "not a complete JPEG"),
    "too large": (lambda: _jpeg()[:2] + (b"\xff\xfe\xff\xfe" + bytes(0xFFFC)) * 2 + _jpeg()[2:], "fit"),
    "arithmetic": (lambda: _patched(_jpeg(), b"\xff\xc0", 1, b"\xc9"), "not progressive|baseline"),
}


@pytest.mark.parametrize("case", list(PICTURE_REFUSALS), ids=list(PICTURE_REFUSALS))
def test_a_picture_outside_the_profile_is_refused(qapp, case):
    make, reason = PICTURE_REFUSALS[case]
    with pytest.raises(BootLogoError, match=reason):
        check_logo_jpeg(make())


def test_the_size_cap_keeps_every_result_inside_the_largest_known_volume():
    """MeiMeiDXE's DXE volume without its logo is the largest base in the catalog
    (0x431B4E bytes used); a capped logo still fits the largest known volume."""
    largest_file = 24 + 24 + 13 + (MAX_LOGO_BYTES + 4 + 4 + 64) * 102 // 100
    assert ((0x431B4E + 8 + largest_file + 0xFFF) & ~0xFFF) <= boot_logo.LARGEST_KNOWN_VOLUME
