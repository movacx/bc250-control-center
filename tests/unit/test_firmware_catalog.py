"""The firmware catalog and the rules that decide which USB drive may be erased.

Both are pure data and pure functions, so they are pinned here without any
hardware: a catalog entry that is not pinned to a commit and a SHA-256, or a
drive rule that lets the system disk through, must never reach a user.
"""

from __future__ import annotations

import pytest

from bc250cc.domain.firmware.catalog import (
    ASROCK_AFU,
    DEFAULT_FAMILY,
    FAMILIES_BY_KEY,
    FIRMWARE_FAMILIES,
    MEIMEIDXE_AFU,
    ROM_BYTES,
    UEFI_SHELL,
    ArchivedFile,
    RemoteFile,
    archives_of,
    catalog_problems,
    sources_for,
)
from bc250cc.domain.firmware.usb import (
    LARGE_BYTES,
    MINIMUM_BYTES,
    UsbDrive,
    UsbPartition,
    format_size,
)

GB = 1000 ** 3


def test_the_catalog_has_no_problems():
    assert catalog_problems() == []


def test_the_recommended_default_is_the_chipset_menu_bios():
    assert DEFAULT_FAMILY.key == "p3-chipset-menu"
    assert DEFAULT_FAMILY.recommended
    assert [family.key for family in FIRMWARE_FAMILIES if family.recommended] == ["p3-chipset-menu"]
    assert FIRMWARE_FAMILIES[0] is DEFAULT_FAMILY


def test_the_catalog_offers_the_versions_people_ask_for():
    assert set(FAMILIES_BY_KEY) == {
        "p3-chipset-menu", "meimeidxe-v3", "p5-stock", "p3-stock", "p2-stock",
    }
    assert FAMILIES_BY_KEY["p5-stock"].version.startswith("P5")
    assert FAMILIES_BY_KEY["p2-stock"].version.startswith("P2")
    assert {family.origin for family in FIRMWARE_FAMILIES} == {"modded", "stock"}


def test_every_image_is_one_full_spi_dump():
    for family in FIRMWARE_FAMILIES:
        for image in family.images:
            assert image.rom.size == ROM_BYTES, (family.key, image.key)


def test_every_download_is_pinned_to_a_commit_and_a_hash():
    for family in FIRMWARE_FAMILIES:
        for image in family.images:
            for source in sources_for(family, image):
                remote = archives_of(source)
                assert remote.url.startswith("https://")
                assert len(source.sha256) == 64 and len(remote.sha256) == 64
                assert "/raw/" in remote.url or "raw.githubusercontent.com" in remote.url


def test_the_usb_boots_the_same_shell_whatever_is_flashed():
    for family in FIRMWARE_FAMILIES:
        for image in family.images:
            sources = sources_for(family, image)
            assert sources[0] is UEFI_SHELL
            assert sources[1] is family.tool.binary
            assert sources[2] is image.rom


def test_each_image_is_flashed_with_its_own_publishers_tool_and_flags():
    meimei = FAMILIES_BY_KEY["meimeidxe-v3"]
    assert meimei.tool is MEIMEIDXE_AFU
    assert meimei.tool.clears_settings
    assert "/CLRCFG" in meimei.tool.arguments
    for key in ("p3-chipset-menu", "p5-stock", "p3-stock", "p2-stock"):
        family = FAMILIES_BY_KEY[key]
        assert family.tool is ASROCK_AFU, key
        assert not family.tool.clears_settings
        assert family.tool.arguments == "/p /b /n /k /x /rlc:e"


def test_the_meimeidxe_variants_keep_a_default_and_unique_keys():
    family = FAMILIES_BY_KEY["meimeidxe-v3"]
    assert family.has_variants
    assert len(family.images) == 16
    assert family.variant_title == "Boot logo"
    keys = [image.key for image in family.images]
    assert len(set(keys)) == len(keys)
    assert family.image().key == family.default_image
    assert family.image("no-such-variant").key == family.images[0].key
    assert all(isinstance(image.rom, ArchivedFile) for image in family.images)
    assert {image.rom.archive_format for image in family.images} == {"7z"}


def test_single_image_families_ignore_the_variant_key():
    family = FAMILIES_BY_KEY["p3-stock"]
    assert not family.has_variants
    assert family.image("anything") is family.images[0]


def test_archives_of_returns_the_published_file():
    rom = FAMILIES_BY_KEY["p5-stock"].image().rom
    assert isinstance(rom, ArchivedFile)
    assert archives_of(rom) is rom.archive
    assert rom.archive_format == "zip"
    assert archives_of(UEFI_SHELL) is UEFI_SHELL


def test_a_broken_entry_is_reported(monkeypatch):
    from bc250cc.domain.firmware import catalog

    broken = RemoteFile(url="http://example.com/latest/x.rom", sha256="nope", size=0, name="a/b")
    family = catalog.FIRMWARE_FAMILIES[2]
    image = catalog.FirmwareImage(key="x", label="x", rom=broken)
    monkeypatch.setattr(
        catalog,
        "FIRMWARE_FAMILIES",
        (*catalog.FIRMWARE_FAMILIES, catalog.FirmwareFamily(
            key=family.key, title="t", version="v", origin="other", summary="",
            caution="", tool=family.tool, images=(image,), project="p",
            project_url="http://example.com", recommended=True, cpu_cores=12, boot_logos=3,
        )),
    )
    problems = "\n".join(catalog.catalog_problems())
    assert "duplicate family key" in problems
    assert "unknown origin" in problems
    assert "project URL is not https" in problems
    assert "SHA-256 is malformed" in problems
    assert "not pinned to a commit" in problems
    assert "size must be positive" in problems
    assert "is not a plain name" in problems
    assert "exactly one family must be recommended" in problems
    assert "six to eight CPU cores" in problems
    assert "boot logo count does not match" in problems
    assert "highlights, none of them empty" in problems


@pytest.mark.parametrize(
    "key, vram, cores, logos",
    [
        ("p3-chipset-menu", True, 6, 0),
        ("meimeidxe-v3", True, 8, 16),
        ("p5-stock", False, 6, 0),
        ("p3-stock", False, 6, 0),
        ("p2-stock", False, 6, 0),
    ],
)
def test_what_each_image_unlocks(key, vram, cores, logos):
    """Read from the images: MeiMeiDXE v3 carries the Chipset Menu's Setup module."""
    family = FAMILIES_BY_KEY[key]
    assert (family.vram_menu, family.cpu_cores, family.boot_logos) == (vram, cores, logos)


def test_only_meimeidxe_resets_its_own_settings():
    assert [family.key for family in FIRMWARE_FAMILIES if family.tool.clears_settings] == ["meimeidxe-v3"]


# ----------------------------------------------------------------- drives

def _drive(**changes) -> UsbDrive:
    values = dict(
        name="sdb", path="/dev/sdb", size=16 * GB, vendor="Kingston", model="DataTraveler 3.0",
        serial="0019E06B", transport="usb", removable=True,
    )
    values.update(changes)
    return UsbDrive(**values)


def test_a_plain_usb_stick_is_eligible():
    drive = _drive()
    assert drive.blocker() == ""
    assert drive.eligible
    assert drive.warning() == ""


@pytest.mark.parametrize(
    "changes, reason",
    [
        ({"transport": "sata"}, "Not connected over USB."),
        ({"transport": "nvme"}, "Not connected over USB."),
        ({"mountpoints": ("/",)}, "This drive holds part of the running system."),
        ({"read_only": True}, "This drive is write-protected."),
        ({"size": MINIMUM_BYTES - 1}, "Too small: the kit needs a USB drive of at least 1 GB."),
    ],
)
def test_drives_that_must_not_be_erased_say_why(changes, reason):
    drive = _drive(**changes)
    assert drive.blocker() == reason
    assert not drive.eligible


@pytest.mark.parametrize(
    "mount_point",
    ["/", "/boot", "/boot/efi", "/efi", "/home", "/var/home", "/sysroot/ostree", "/usr/local", "[SWAP]"],
)
def test_a_usb_disk_carrying_the_system_is_refused(mount_point):
    drive = _drive(partitions=(UsbPartition("sdb2", "/dev/sdb2", 8 * GB, mountpoints=(mount_point,)),))
    assert drive.holds_system
    assert not drive.eligible


@pytest.mark.parametrize(
    "mount_point",
    ["/run/media/user/VENTOY", "/media/usb", "/home/user/usb", "/mnt/stick"],
)
def test_a_stick_mounted_by_the_desktop_or_by_hand_is_still_usable(mount_point):
    drive = _drive(partitions=(UsbPartition("sdb1", "/dev/sdb1", 8 * GB, mountpoints=(mount_point,)),))
    assert not drive.holds_system
    assert drive.eligible


def test_a_large_disk_is_allowed_but_warned_about():
    drive = _drive(size=LARGE_BYTES)
    assert drive.eligible
    assert "Make sure this is the drive" in drive.warning()


def test_identity_includes_what_a_different_stick_would_change():
    drive = _drive()
    assert drive.identity == ("sdb", "0019E06B", 16 * GB, "DataTraveler 3.0")
    assert _drive(serial="OTHER").identity != drive.identity
    assert _drive(size=8 * GB).identity != drive.identity


def test_display_name_never_repeats_the_vendor_and_is_never_empty():
    assert _drive(vendor="SanDisk", model="SanDisk Ultra").display_name == "SanDisk Ultra"
    assert _drive(vendor="  Kingston ", model=" DataTraveler  3.0 ").display_name == "Kingston DataTraveler 3.0"
    assert _drive(vendor="", model="").display_name == "USB drive"


def test_volume_labels_and_mountpoints_cover_every_partition():
    drive = _drive(
        label="WHOLE",
        mountpoints=("/run/media/u/WHOLE",),
        partitions=(
            UsbPartition("sdb1", "/dev/sdb1", GB, label="Ventoy", mountpoints=("/run/media/u/Ventoy",)),
            UsbPartition("sdb2", "/dev/sdb2", GB, label="VTOYEFI"),
        ),
    )
    assert drive.volume_labels == ("WHOLE", "Ventoy", "VTOYEFI")
    assert drive.all_mountpoints == ("/run/media/u/WHOLE", "/run/media/u/Ventoy")


@pytest.mark.parametrize(
    "size, text",
    [(500 * 1000 ** 2, "500 MB"), (int(1.2 * GB), "1.2 GB"), (16 * GB, "16 GB"),
     (int(124.78 * GB), "125 GB"), (2 * 1000 * GB, "2.0 TB")],
)
def test_sizes_read_the_way_drives_are_sold(size, text):
    assert format_size(size) == text


def test_every_image_in_the_catalog_can_take_a_custom_logo():
    """Checked against the real images in test_boot_logo_real_images.py."""
    assert all(family.logo_replaceable for family in FIRMWARE_FAMILIES)
