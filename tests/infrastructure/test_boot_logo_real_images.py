"""The boot logo builder against the catalog's real images, when they are cached.

The images are not in the repository: they are downloaded, by hash, from the
projects that publish them. These tests look for them in the firmware cache
(``BC250_FIRMWARE_CACHE`` when set, the application's own cache otherwise)
and skip the ones that are not there, so they cost nothing on a machine that
never prepared a USB and prove the most on one that did.

Three properties, each for every image in the catalog:

* repacking an image's own DXE files reproduces its DXE volume byte for byte:
  the packing is the one ASRock's and MeiMeiDXE's tools use;
* a new logo changes the logo file and nothing else, and reads back;
* the largest logo allowed still leaves the image inside the largest DXE
  volume known to start on a BC-250.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import pytest
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QImage, QImageWriter

from bc250cc.domain.firmware import boot_logo
from bc250cc.domain.firmware.boot_logo import LOGO_HEIGHT, LOGO_WIDTH, MAX_LOGO_BYTES
from bc250cc.domain.firmware.catalog import FIRMWARE_FAMILIES
from bc250cc.infrastructure.firmware import lzma1
from bc250cc.infrastructure.firmware.preparation import build_logo_image
from bc250cc.infrastructure.firmware.store import (
    FirmwareStore,
    default_cache_root,
    sha256_of,
)

pytestmark = pytest.mark.skipif(bool(lzma1.available()), reason=lzma1.available() or "liblzma ready")

IMAGES = [
    pytest.param(family, image, id=f"{family.key}/{image.key}")
    for family in FIRMWARE_FAMILIES
    for image in family.images
]


def _cached(image) -> bytes:
    root = Path(os.environ.get("BC250_FIRMWARE_CACHE") or default_cache_root())
    path = FirmwareStore(root).path_for(image.rom)
    if not path.is_file() or sha256_of(path) != image.rom.sha256:
        pytest.skip(f"{image.rom.name} is not in the firmware cache")
    return path.read_bytes()


def _jpeg(image: QImage, quality: int) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QImageWriter(buffer, b"jpeg")
    writer.setQuality(quality)
    assert writer.write(image)
    buffer.close()
    return bytes(data)


@pytest.fixture(scope="module")
def logos(qapp):
    """A plain logo, and noise encoded as close under the size cap as it gets."""
    plain = QImage(LOGO_WIDTH, LOGO_HEIGHT, QImage.Format.Format_RGB888)
    plain.fill(0)
    noise = QImage(LOGO_WIDTH, LOGO_HEIGHT, QImage.Format.Format_RGB888)
    generator = random.Random(250)
    for y in range(LOGO_HEIGHT):
        row = noise.scanLine(y)
        row.setsize(LOGO_WIDTH * 3)
        row[:] = bytes(generator.getrandbits(8) for _ in range(LOGO_WIDTH * 3))
    largest = max(
        (data for data in (_jpeg(noise, quality) for quality in range(5, 91)) if len(data) <= MAX_LOGO_BYTES),
        key=len,
    )
    assert len(largest) > MAX_LOGO_BYTES * 0.95
    return {"plain": _jpeg(plain, 90), "largest": largest}


@pytest.mark.parametrize("family, image", IMAGES)
def test_the_packing_reproduces_every_catalog_volume(family, image):
    assert family.logo_replaceable
    slot = boot_logo.read_logo(_cached(image), decompress=lzma1.decompress)
    repacked = boot_logo._volume(slot.volume[:boot_logo._FIRST_FILE], [found.data for found in slot.files])
    assert repacked == slot.volume


@pytest.mark.parametrize("family, image", IMAGES)
def test_a_new_logo_changes_nothing_else(family, image, logos):
    base = _cached(image)
    built = build_logo_image(base, logos["plain"])
    boot_logo.verify_replaced_logo(base, built, logos["plain"], decompress=lzma1.decompress)
    assert len(built) == len(base)
    assert boot_logo.read_logo(built, decompress=lzma1.decompress).picture == logos["plain"]


@pytest.mark.parametrize("family, image", IMAGES)
def test_the_largest_logo_allowed_stays_inside_the_largest_known_volume(family, image, logos):
    built = build_logo_image(_cached(image), logos["largest"])
    volume = boot_logo.read_logo(built, decompress=lzma1.decompress).volume
    assert len(volume) <= boot_logo.LARGEST_KNOWN_VOLUME
