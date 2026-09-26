"""What each firmware card says it offers, checked against the images.

The highlights in the catalog are claims about the images: which drivers they
carry, what their menus offer and when they were built. These tests read the
same things out of the images, the way the boot logo tests do, and skip the
images that are not in the firmware cache.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from bc250cc.domain.firmware import boot_logo
from bc250cc.domain.firmware.catalog import FAMILIES_BY_KEY, FIRMWARE_FAMILIES
from bc250cc.infrastructure.firmware import lzma1
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
MEIMEI_DRIVERS = {
    "MeiMeiDXEv3_Menu_Driver", "MeiMeiDXEv3_SMU_Unlock", "MeiMeiDXEv3_SMU_Patch",
    "MeiMeiDXEv3_SMU_Core_Unlock", "MeiMeiDXEv3_ColdBoot", "MeiMeiDXEv3_ACPI_AutoInject",
}
#: The formset of AMD's CBS menu, B04535E3-3004-4946-9EB7-149428983053.
CBS_FORMSET = bytes.fromhex("e33545b0043046499eb7149428983053")
#: AMI writes the build date as MM/DD/YYYY.
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")
_USER_INTERFACE = 0x15


def _cached(image) -> bytes:
    root = Path(os.environ.get("BC250_FIRMWARE_CACHE") or default_cache_root())
    path = FirmwareStore(root).path_for(image.rom)
    if not path.is_file() or sha256_of(path) != image.rom.sha256:
        pytest.skip(f"{image.rom.name} is not in the firmware cache")
    return path.read_bytes()


def _modules(rom: bytes) -> dict[str, bytes]:
    """Every named DXE file of an image, by the name its UI section gives it."""
    volume = boot_logo._dxe_volume(rom, lzma1.decompress)
    named: dict[str, bytes] = {}
    for found in boot_logo._files(volume, "DXE volume"):
        body, offset = found.data[boot_logo._FILE_HEADER:], 0
        while offset + 4 <= len(body):
            size, kind = int.from_bytes(body[offset:offset + 3], "little"), body[offset + 3]
            if size < 4:
                break
            if kind == _USER_INTERFACE:
                named[body[offset + 4:offset + size].decode("utf-16-le").rstrip("\0")] = found.data
            offset = (offset + size + 3) & ~3
    return named


def _strings(data: bytes) -> list[str]:
    return [match.decode("utf-16-le") for match in re.findall(rb"(?:[\x20-\x7e]\x00){2,}", data)]


def _built(family) -> str:
    """The build month a family's highlights give, as the image's date reads it."""
    for line in family.highlights:
        for number, month in enumerate(MONTHS, start=1):
            found = re.search(rf"{month} (20\d\d)", line)
            if found:
                return f"{number:02d}/{found.group(1)}"
    return ""


@pytest.mark.parametrize("family, image", IMAGES)
def test_only_meimeidxe_carries_its_drivers(family, image):
    names = set(_modules(_cached(image)))
    if family.key == "meimeidxe-v3":
        assert MEIMEI_DRIVERS <= names
    else:
        assert not {name for name in names if name.startswith("MeiMeiDXE")}


@pytest.mark.parametrize("image", FAMILIES_BY_KEY["meimeidxe-v3"].images, ids=lambda image: image.key)
def test_the_meimeidxe_menu_offers_what_its_card_says(image):
    modules = _modules(_cached(image))
    menu = _strings(modules["MeiMeiDXEv3_Menu_Driver"])
    for entry in ("MeiMeiDXEv3 Menu", "All Cores", "Custom", "Core 7", "SMU Unlock",
                  "SMU Reporting Patch", "ACPI Patch", "Restore Factory Core Mask"):
        assert entry in menu
    acpi = modules["MeiMeiDXEv3_ACPI_AutoInject"]
    assert b"PSTATE-COMMON" in acpi and b"CSTATE-PAIR" in acpi
    assert "Performing one-time cold reboot to learn factory core mask." in _strings(
        modules["MeiMeiDXEv3_SMU_Core_Unlock"]
    )


@pytest.mark.parametrize("family, image", IMAGES)
def test_the_build_date_is_the_one_the_card_gives(family, image):
    setup = _strings(_modules(_cached(image))["Setup"])
    dates = [text for text in setup if re.fullmatch(r"\d\d/\d\d/20\d\d", text)]
    # The mods keep the date of the ASRock image they are built on.
    base = family if _built(family) else FAMILIES_BY_KEY["p3-stock"]
    month, _day, year = dates[0].split("/")
    assert f"{month}/{year}" == _built(base)


@pytest.mark.parametrize("family, image", IMAGES)
def test_the_vram_menu_is_amd_cbs_from_256_mb_to_12_gb(family, image):
    """The Chipset Menu mod turns one of Setup's links into one to AMD CBS,
    whose UMA frame buffer runs from 256 MB to 12 GB. ASRock's own Setup has
    a UMA option too, from 32 MB to 2 GB, but it never shows it."""
    modules = _modules(_cached(image))
    assert (CBS_FORMSET in modules["Setup"]) == family.vram_menu
    cbs = _strings(modules["CbsSetupDxe"])
    start = cbs.index("UMA Frame buffer Size")
    assert (cbs[start + 2], cbs[start + 12]) == ("256M", "12G")
    assert "VRAM from 256 MB to 12 GB, set in the BIOS" in FAMILIES_BY_KEY["p3-chipset-menu"].highlights


def test_p5_changes_the_smu_and_boot_drivers_over_p3():
    p3 = _modules(_cached(FAMILIES_BY_KEY["p3-stock"].image()))
    p5 = _modules(_cached(FAMILIES_BY_KEY["p5-stock"].image()))
    assert p5["AmdNbioSmuV10Dxe"] != p3["AmdNbioSmuV10Dxe"]
    assert p5["Bds"] != p3["Bds"]
