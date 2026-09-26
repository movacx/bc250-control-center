"""The preparation, step by step, against a fake UDisks2 and a fake drive list.

The "USB" is a folder under tmp_path and UDisks2 is a recorder, so every
branch that decides whether a real drive gets erased can be exercised without
one: the identity and system checks that come right before the erase, the
cancel that only works until then, the FAT32 check, and the read-back.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from bc250cc.domain.firmware.boot_logo import BootLogoError
from bc250cc.domain.firmware.catalog import FAMILIES_BY_KEY, RemoteFile
from bc250cc.domain.firmware.usb import UsbDrive, UsbPartition
from bc250cc.domain.firmware.usb_kit import KitFile, KitPlan
from bc250cc.infrastructure.firmware import lzma1
from bc250cc.infrastructure.firmware.preparation import (
    STEPS,
    PreparationCancelled,
    PreparationError,
    UsbPreparation,
    steps_for,
)
from bc250cc.infrastructure.firmware.store import DownloadCancelled
from bc250cc.infrastructure.firmware.udisks import UDisksError

GB = 1000 ** 3


def _source(name: str, data: bytes) -> RemoteFile:
    return RemoteFile(url=f"https://example.invalid/{name}", sha256=hashlib.sha256(data).hexdigest(),
                      size=len(data), name=name)


SHELL = _source("BOOTX64.EFI", b"shell" * 1000)
TOOL = _source("AfuEfix64.efi", b"afu" * 1000)
ROM = _source("IMAGE.ROM", b"rom" * 5000)
BLOBS = {SHELL.sha256: b"shell" * 1000, TOOL.sha256: b"afu" * 1000, ROM.sha256: b"rom" * 5000}


def _plan() -> KitPlan:
    family = FAMILIES_BY_KEY["p3-stock"]
    return KitPlan(
        family=family,
        image=family.image(),
        files=(
            KitFile("EFI/BOOT/BOOTX64.EFI", source=SHELL),
            KitFile("startup.nsh", content=b"@echo -off\r\n"),
            KitFile("BC250/MENU.NSH", content=b"echo \"menu\"\r\n"),
            KitFile("BC250/TOOLS/AfuEfix64.efi", source=TOOL),
            KitFile("BC250/FIRMWARE/IMAGE.ROM", source=ROM),
        ),
        folders=("BC250/BACKUP",),
    )


class _Store:
    def __init__(self, tmp_path, *, fail=None, cancel=False):
        self.root = tmp_path / "cache"
        self.root.mkdir()
        self.fail = fail
        self.cancel = cancel
        self.fetched = []

    def ensure(self, source, *, progress=None, cancelled=lambda: False):
        if self.cancel:
            raise DownloadCancelled()
        if self.fail:
            raise self.fail
        path = self.root / source.name
        path.write_bytes(BLOBS[source.sha256])
        self.fetched.append(source.name)
        if progress is not None:
            progress(source.size // 2, source.size)
            progress(source.size, source.size)
        return path


STICK = UsbDrive(
    name="sdz", path="/dev/sdz", size=16 * GB, vendor="Kingston", model="DataTraveler",
    serial="SERIAL1", transport="usb", removable=True,
    partitions=(UsbPartition("sdz1", "/dev/sdz1", 16 * GB, label="OLD", fstype="exfat",
                             mountpoints=("/run/media/user/OLD",)),),
)


class _World:
    """The drive list and UDisks2 as the preparation sees them."""

    def __init__(self, tmp_path, drive=STICK):
        self.drive = drive
        self.mounted = {"sdz1": "/run/media/user/OLD"}
        self.usb = tmp_path / "usb"
        self.calls: list[tuple] = []
        self.system = False
        self.bus = "usb"
        self.new_fat = "FAT32"
        self.fail: dict[str, Exception] = {}
        self.on_unmount = None

    # the drive list -------------------------------------------------------
    def list_drives(self):
        return [self.drive] if self.drive is not None else []

    # UDisksClient ---------------------------------------------------------
    def _maybe_fail(self, name):
        if name in self.fail:
            raise self.fail[name]

    def is_system_device(self, name):
        self.calls.append(("is_system_device", name))
        self._maybe_fail("is_system_device")
        return self.system

    def connection_bus(self, name):
        self.calls.append(("connection_bus", name))
        return self.bus

    def mount_points(self, name):
        point = self.mounted.get(name)
        return [point] if point else []

    def unmount(self, name):
        self.calls.append(("unmount", name))
        self.mounted.pop(name, None)
        if self.on_unmount is not None:
            self.on_unmount(name)

    def erase_to_empty_mbr(self, name):
        self.calls.append(("erase", name))
        self._maybe_fail("erase")
        self.drive = replace(self.drive, partitions=())

    def create_fat32_partition(self, name, label):
        self.calls.append(("format", name, label))
        self._maybe_fail("format")
        self.drive = replace(self.drive, partitions=(
            UsbPartition("sdz1", "/dev/sdz1", 16 * GB, label=label, fstype="vfat", fsver=self.new_fat),
        ))
        return "sdz1"

    def mount(self, name):
        self.calls.append(("mount", name))
        self.usb.mkdir(exist_ok=True)
        self.mounted[name] = str(self.usb)
        return str(self.usb)

    def power_off(self, name):
        self.calls.append(("power_off", name))
        self._maybe_fail("power_off")


def _preparation(tmp_path, world, **store_options):
    return UsbPreparation(
        _Store(tmp_path, **store_options), world, list_drives=world.list_drives,
        sleep=lambda _seconds: None, clock=iter(range(0, 10_000)).__next__,
    )


def test_a_full_run_leaves_a_verified_kit_and_ejects_the_drive(tmp_path):
    world = _World(tmp_path)
    steps = []
    report = _preparation(tmp_path, world).run(
        _plan(), STICK, progress=lambda step, fraction, detail: steps.append((step, fraction))
    )
    assert report.partition == "sdz1"
    assert report.files == 5
    assert report.bytes_written == _plan().total_bytes
    assert report.ejected is True
    assert list(steps_for(_plan())) == list(dict.fromkeys(step for step, _ in steps))
    assert "logo" not in steps_for(_plan()) and "logo" in STEPS
    assert all(0.0 <= fraction <= 1.0 for _step, fraction in steps)
    assert (world.usb / "BC250" / "FIRMWARE" / "IMAGE.ROM").read_bytes() == BLOBS[ROM.sha256]
    assert (world.usb / "startup.nsh").read_bytes() == b"@echo -off\r\n"
    assert (world.usb / "BC250" / "BACKUP").is_dir()
    order = [call[0] for call in world.calls]
    assert order.index("unmount") < order.index("erase") < order.index("format") < order.index("mount")
    assert ("format", "sdz", "BC250BIOS") in world.calls
    assert order[-1] == "power_off"


def test_nothing_is_erased_when_a_download_fails(tmp_path):
    world = _World(tmp_path)
    with pytest.raises(PreparationError) as raised:
        _preparation(tmp_path, world, fail=RuntimeError("network down")).run(
            _plan(), STICK, progress=lambda *_a: None
        )
    assert raised.value.step == "download"
    assert "network down" in str(raised.value)
    assert world.calls == []


def test_cancelling_during_the_download_leaves_the_drive_alone(tmp_path):
    world = _World(tmp_path)
    with pytest.raises(PreparationCancelled):
        _preparation(tmp_path, world, cancel=True).run(_plan(), STICK, progress=lambda *_a: None)
    assert world.calls == []


def test_cancelling_before_the_erase_is_the_last_chance(tmp_path):
    world = _World(tmp_path)
    with pytest.raises(PreparationCancelled):
        _preparation(tmp_path, world).run(
            _plan(), STICK, progress=lambda *_a: None, cancelled=lambda: True
        )
    assert not any(call[0] in {"erase", "format", "unmount"} for call in world.calls)


def test_a_cancel_arriving_after_the_erase_is_ignored(tmp_path):
    world = _World(tmp_path)
    erased = []
    original = world.erase_to_empty_mbr

    def erase(name):
        original(name)
        erased.append(name)

    world.erase_to_empty_mbr = erase
    report = _preparation(tmp_path, world).run(
        _plan(), STICK, progress=lambda *_a: None, cancelled=lambda: bool(erased)
    )
    assert report.ejected


def test_a_drive_that_was_pulled_out_is_not_touched(tmp_path):
    world = _World(tmp_path, drive=None)
    with pytest.raises(PreparationError, match="no longer connected") as raised:
        _preparation(tmp_path, world).run(_plan(), STICK, progress=lambda *_a: None)
    assert raised.value.step == "check"
    assert world.calls == []


def test_a_different_stick_in_the_same_slot_is_not_erased(tmp_path):
    world = _World(tmp_path, drive=replace(STICK, serial="SOMEONE ELSE"))
    with pytest.raises(PreparationError, match="different drive"):
        _preparation(tmp_path, world).run(_plan(), STICK, progress=lambda *_a: None)
    assert not any(call[0] == "erase" for call in world.calls)


def test_a_drive_that_became_ineligible_says_why(tmp_path):
    world = _World(tmp_path, drive=replace(STICK, read_only=True))
    with pytest.raises(PreparationError, match="write-protected"):
        _preparation(tmp_path, world).run(_plan(), STICK, progress=lambda *_a: None)


@pytest.mark.parametrize("system, bus", [(True, "usb"), (False, "sata"), (False, "")])
def test_udisks_gets_the_last_word_on_system_drives(tmp_path, system, bus):
    world = _World(tmp_path)
    world.system, world.bus = system, bus
    with pytest.raises(PreparationError, match="part of the system") as raised:
        _preparation(tmp_path, world).run(_plan(), STICK, progress=lambda *_a: None)
    assert raised.value.step == "check"
    assert not any(call[0] in {"erase", "unmount"} for call in world.calls)


def test_a_udisks_failure_during_the_check_touches_nothing(tmp_path):
    world = _World(tmp_path)
    world.fail["is_system_device"] = UDisksError("The name is not activatable")
    with pytest.raises(PreparationError, match="not activatable"):
        _preparation(tmp_path, world).run(_plan(), STICK, progress=lambda *_a: None)
    assert not any(call[0] == "erase" for call in world.calls)


def test_a_refused_erase_is_reported_on_its_step(tmp_path):
    world = _World(tmp_path)
    world.fail["erase"] = UDisksError("Not authorized to perform operation")
    with pytest.raises(PreparationError, match="Not authorized") as raised:
        _preparation(tmp_path, world).run(_plan(), STICK, progress=lambda *_a: None)
    assert raised.value.step == "erase"


def test_a_partition_formatted_as_something_else_stops_before_copying(tmp_path):
    world = _World(tmp_path)
    world.new_fat = "FAT16"
    with pytest.raises(PreparationError, match="formatted FAT16, not FAT32") as raised:
        _preparation(tmp_path, world).run(_plan(), STICK, progress=lambda *_a: None)
    assert raised.value.step == "format"
    assert not any(call[0] == "mount" for call in world.calls)


def test_a_partition_that_never_shows_up_times_out(tmp_path):
    world = _World(tmp_path)
    world.new_fat = ""
    with pytest.raises(PreparationError, match="did not appear"):
        _preparation(tmp_path, world).run(_plan(), STICK, progress=lambda *_a: None)


def test_a_file_that_reads_back_different_fails_the_verification(tmp_path):
    world = _World(tmp_path)

    def corrupt(name):
        rom = world.usb / "BC250" / "FIRMWARE" / "IMAGE.ROM"
        if name == "sdz1" and rom.exists() and not world.calls.count(("mount", "sdz1")) > 1:
            rom.write_bytes(b"x" * 10)

    world.on_unmount = corrupt
    with pytest.raises(PreparationError, match="does not match what was written") as raised:
        _preparation(tmp_path, world).run(_plan(), STICK, progress=lambda *_a: None)
    assert raised.value.step == "verify"
    assert not any(call[0] == "power_off" for call in world.calls)


def test_a_drive_that_cannot_power_off_is_still_ready(tmp_path):
    world = _World(tmp_path)
    world.fail["power_off"] = UDisksError("Drive is busy")
    report = _preparation(tmp_path, world).run(_plan(), STICK, progress=lambda *_a: None)
    assert report.ejected is False
    assert "sdz1" not in world.mounted


@pytest.mark.parametrize("path", ["../escape", "/etc/passwd", "BC250/../../x", ""])
def test_kit_paths_cannot_leave_the_usb(tmp_path, path):
    world = _World(tmp_path)
    plan = replace(_plan(), files=(KitFile(path, content=b"x"),))
    with pytest.raises(PreparationError, match="unsafe kit path") as raised:
        _preparation(tmp_path, world).run(plan, STICK, progress=lambda *_a: None)
    assert raised.value.step == "copy"


# ------------------------------------------------------- custom boot logo

LOGO = b"\xff\xd8 the user's picture \xff\xd9"


def _logo_plan(monkeypatch, rom_source, blobs):
    """A real plan_kit plan around stand-in downloads."""
    from bc250cc.domain.firmware import usb_kit as usb_kit_module
    from bc250cc.domain.firmware.catalog import FirmwareImage

    monkeypatch.setattr(usb_kit_module, "UEFI_SHELL", SHELL)
    monkeypatch.setitem(BLOBS, rom_source.sha256, blobs)
    stock = FAMILIES_BY_KEY["p3-stock"]
    family = replace(stock, tool=replace(stock.tool, binary=TOOL),
                     images=(FirmwareImage("p3-stock", "P3.00 (ASRock)", rom_source),))
    return usb_kit_module.plan_kit(family, family.image(), prepared="2026-09-25 10:00, test", logo=LOGO)


BASE = bytes(range(256)) * 64
BASE_ROM = _source("BASE.ROM", BASE)


def test_the_logo_goes_in_before_the_drive_is_touched(tmp_path, monkeypatch):
    world = _World(tmp_path)
    built = BASE[::-1]
    calls = []

    def build(base, jpeg):
        calls.append((base, jpeg, list(world.calls)))
        return built

    steps = []
    preparation = UsbPreparation(
        _Store(tmp_path), world, list_drives=world.list_drives, sleep=lambda _s: None,
        clock=iter(range(0, 10_000)).__next__, build_logo=build,
    )
    report = preparation.run(
        _logo_plan(monkeypatch, BASE_ROM, BASE), STICK,
        progress=lambda step, fraction, detail: steps.append(step),
    )
    assert calls == [(BASE, LOGO, [])], "built from the verified download, before any drive call"
    assert list(dict.fromkeys(steps)) == list(STEPS)
    assert report.ejected
    on_usb = world.usb / "BC250" / "FIRMWARE" / "LOGO-BASE.ROM"
    assert on_usb.read_bytes() == built
    assert not (world.usb / "BC250" / "FIRMWARE" / "BASE.ROM").exists()
    menu = (world.usb / "BC250" / "MENU.NSH").read_text(encoding="ascii")
    assert hashlib.sha256(built).hexdigest() in menu and BASE_ROM.sha256 in menu


@pytest.mark.parametrize(
    "failure, message",
    [
        (BootLogoError("DXE volume: a file has attributes. This firmware image is not one a logo can be added to."),
         "Custom boot logo: DXE volume"),
        (lzma1.Lzma1Error("liblzma 5.2.5 is too old; 5.4 or newer is needed."), "Custom boot logo: liblzma"),
        (MemoryError("out of memory"), "could not be built: out of memory"),
    ],
)
def test_a_logo_that_cannot_be_added_leaves_the_drive_alone(tmp_path, monkeypatch, failure, message):
    world = _World(tmp_path)

    def build(_base, _jpeg):
        raise failure

    preparation = UsbPreparation(
        _Store(tmp_path), world, list_drives=world.list_drives, sleep=lambda _s: None,
        clock=iter(range(0, 10_000)).__next__, build_logo=build,
    )
    with pytest.raises(PreparationError, match=message) as raised:
        preparation.run(_logo_plan(monkeypatch, BASE_ROM, BASE), STICK, progress=lambda *_a: None)
    assert raised.value.step == "logo"
    assert world.calls == []


def test_a_download_that_changed_on_disk_is_not_given_a_logo(tmp_path, monkeypatch):
    world = _World(tmp_path)
    built = []
    preparation = UsbPreparation(
        _Store(tmp_path), world, list_drives=world.list_drives, sleep=lambda _s: None,
        clock=iter(range(0, 10_000)).__next__, build_logo=lambda base, jpeg: built.append(base) or base,
    )
    with pytest.raises(PreparationError, match="does not match the reviewed file") as raised:
        preparation.run(_logo_plan(monkeypatch, BASE_ROM, BASE[:-1] + b"X"), STICK, progress=lambda *_a: None)
    assert raised.value.step == "logo"
    assert built == [] and world.calls == []


def test_the_real_builder_writes_a_verified_image_to_the_usb(tmp_path, monkeypatch, qapp):
    """End to end on the synthetic image: download, logo, erase, copy, read back."""
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
    from PyQt6.QtGui import QImage, QImageWriter

    from bc250cc.domain.firmware.boot_logo import read_logo
    from tests.fixtures import bios_image

    if lzma1.available():
        pytest.skip(lzma1.available())
    picture = QImage(672, 378, QImage.Format.Format_RGB888)
    picture.fill(0x3366CC)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QImageWriter(buffer, b"jpeg")
    writer.setQuality(85)
    assert writer.write(picture)
    buffer.close()
    jpeg = bytes(data)
    base = bios_image.image()
    source = _source("SYNTH.ROM", base)
    world = _World(tmp_path)
    plan = _logo_plan(monkeypatch, source, base)
    plan = replace(plan, logo=jpeg, files=tuple(
        replace(item, logo=jpeg) if item.logo is not None else item for item in plan.files
    ))
    report = _preparation(tmp_path, world).run(plan, STICK, progress=lambda *_a: None)
    assert report.ejected
    written = (world.usb / "BC250" / "FIRMWARE" / "LOGO-SYNTH.ROM").read_bytes()
    assert written == bios_image.image(jpeg)
    assert read_logo(written, decompress=lzma1.decompress).picture == jpeg
