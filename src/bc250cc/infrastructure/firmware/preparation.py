"""Turns a USB drive into a BIOS update kit, one checked step at a time.

download  every pinned file, hash-verified into the cache
logo      only with a custom boot logo: put it into the image and prove that
          nothing else in the image changed
check     the drive is still the one the user chose, and still safe to erase
erase     unmount it and give it an empty MBR partition table
format    one FAT32 partition over the whole drive, labelled BC250BIOS
copy      the UEFI shell, the flash tool, the image and the kit's scripts
verify    unmount, mount again and hash every file back from the drive
eject     unmount and power the drive off so it can be pulled out

Cancelling is honoured until the drive is touched. After that the steps run
to the end, because stopping between "erase" and "copy" would leave a stick
that is neither what it was nor a working kit.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from bc250cc.domain.firmware.boot_logo import BootLogoError, replace_logo
from bc250cc.domain.firmware.catalog import archives_of
from bc250cc.domain.firmware.usb import UsbDrive
from bc250cc.domain.firmware.usb_kit import VOLUME_LABEL, KitFile, KitPlan

from . import lzma1
from .store import CHUNK_BYTES, DownloadCancelled, FirmwareStore
from .udisks import UDisksClient, UDisksError
from .usb_devices import list_usb_drives

STEPS = ("download", "logo", "check", "erase", "format", "copy", "verify", "eject")
#: How long a freshly created partition may take to show up formatted.
SETTLE_SECONDS = 15.0

#: (step, fraction of that step done, detail)
Progress = Callable[[str, float, str], None]
#: (published image, JPEG) -> the image with that JPEG as its boot logo.
LogoBuilder = Callable[[bytes, bytes], bytes]


def steps_for(plan: KitPlan) -> tuple[str, ...]:
    """The steps a run of ``plan`` goes through: "logo" only when it has one."""
    return STEPS if plan.logo is not None else tuple(step for step in STEPS if step != "logo")


def build_logo_image(rom: bytes, jpeg: bytes) -> bytes:
    """The real builder: the firmware's own LZMA format, through liblzma."""
    return replace_logo(rom, jpeg, compress=lzma1.compress, decompress=lzma1.decompress)


class PreparationError(RuntimeError):
    def __init__(self, step: str, message: str) -> None:
        super().__init__(message)
        self.step = step


class PreparationCancelled(Exception):
    """Stopped before the drive was touched; it is exactly as it was."""


@dataclass(frozen=True)
class PreparationReport:
    partition: str
    files: int
    bytes_written: int
    ejected: bool


def _expected_sha256(item: KitFile) -> str:
    if item.content is not None:
        return hashlib.sha256(item.content).hexdigest()
    return item.source.sha256  # type: ignore[union-attr]


def _usb_path(mount_point: str, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if not parts or any(part in {"", ".", ".."} for part in parts) or relative.startswith("/"):
        raise PreparationError("copy", f"Refusing an unsafe kit path: {relative!r}")
    return Path(mount_point).joinpath(*parts)


class UsbPreparation:
    def __init__(
        self,
        store: FirmwareStore,
        udisks: UDisksClient,
        *,
        list_drives: Callable[[], list[UsbDrive]] = list_usb_drives,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        build_logo: LogoBuilder = build_logo_image,
    ) -> None:
        self.store = store
        self.udisks = udisks
        self._list_drives = list_drives
        self._sleep = sleep
        self._clock = clock
        self._build_logo = build_logo

    # ----------------------------------------------------------------- run

    def run(
        self,
        plan: KitPlan,
        drive: UsbDrive,
        *,
        progress: Progress,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> PreparationReport:
        local = self._download(plan, progress, cancelled)
        plan = self._add_logo(plan, local, progress)
        if plan.logo_pending:
            raise PreparationError("logo", "The custom boot logo was not added. The USB was not touched.")
        drive = self._check(drive, progress)
        if cancelled():
            raise PreparationCancelled()
        # Past this point the drive is being changed and nothing stops halfway.
        self._erase(drive, progress)
        partition = self._format(drive, progress)
        written = self._copy(plan, local, partition, progress)
        self._verify(plan, partition, progress)
        ejected = self._eject(drive, partition, progress)
        return PreparationReport(
            partition=partition,
            files=len(plan.files),
            bytes_written=written,
            ejected=ejected,
        )

    # --------------------------------------------------------------- steps

    def _download(
        self, plan: KitPlan, progress: Progress, cancelled: Callable[[], bool]
    ) -> dict[str, Path]:
        sources = plan.downloads
        total = sum(archives_of(source).size for source in sources) or 1
        done = 0
        local: dict[str, Path] = {}
        for source in sources:
            weight = archives_of(source).size

            def report(received: int, expected: int, *, base=done, weight=weight, name=source.name):
                share = weight * (received / expected if expected else 1.0)
                progress("download", min(1.0, (base + share) / total), name)

            try:
                local[source.sha256] = self.store.ensure(
                    source, progress=report, cancelled=cancelled
                )
            except DownloadCancelled as cancelled_error:
                raise PreparationCancelled() from cancelled_error
            except Exception as error:  # noqa: BLE001 - reported with its step
                raise PreparationError("download", str(error)) from error
            done += weight
        progress("download", 1.0, "")
        return local

    def _add_logo(self, plan: KitPlan, local: dict[str, Path], progress: Progress) -> KitPlan:
        """Put the custom logo into the downloaded image, before the drive is touched."""
        if plan.logo is None:
            return plan
        progress("logo", 0.0, plan.image.rom.name)
        try:
            base = local[plan.image.rom.sha256].read_bytes()
        except OSError as error:
            raise PreparationError("logo", f"Could not read the downloaded firmware: {error}") from error
        # The cache hashed the file a moment ago; the bytes in hand are what
        # the logo goes into, so they are the ones checked.
        if hashlib.sha256(base).hexdigest() != plan.image.rom.sha256:
            raise PreparationError(
                "logo", f"{plan.image.rom.name} does not match the reviewed file (SHA-256 mismatch)."
            )
        try:
            finished = plan.with_logo_rom(self._build_logo(base, plan.logo))
        except (BootLogoError, lzma1.Lzma1Error) as error:
            raise PreparationError("logo", f"Custom boot logo: {error}") from error
        except Exception as error:  # noqa: BLE001 - still before the drive is touched
            raise PreparationError("logo", f"Custom boot logo could not be built: {error}") from error
        progress("logo", 1.0, "")
        return finished

    def _check(self, chosen: UsbDrive, progress: Progress) -> UsbDrive:
        """Re-read the drive right before erasing it; trust nothing from earlier."""
        progress("check", 0.0, chosen.path)
        current = next(
            (drive for drive in self._list_drives() if drive.name == chosen.name), None
        )
        if current is None:
            raise PreparationError("check", "The USB drive is no longer connected.")
        if current.identity != chosen.identity:
            raise PreparationError(
                "check",
                "A different drive is now connected in its place. Choose the USB again.",
            )
        if not current.eligible:
            raise PreparationError("check", current.blocker())
        try:
            system = self.udisks.is_system_device(current.name)
            bus = self.udisks.connection_bus(current.name)
        except UDisksError as error:
            raise PreparationError("check", str(error)) from error
        if system or bus != "usb":
            raise PreparationError(
                "check", "UDisks2 reports this drive as part of the system. It was not touched."
            )
        progress("check", 1.0, "")
        return current

    def _erase(self, drive: UsbDrive, progress: Progress) -> None:
        progress("erase", 0.0, drive.path)
        try:
            for name in [partition.name for partition in drive.partitions] + [drive.name]:
                if self.udisks.mount_points(name):
                    self.udisks.unmount(name)
            self.udisks.erase_to_empty_mbr(drive.name)
        except UDisksError as error:
            raise PreparationError("erase", str(error)) from error
        progress("erase", 1.0, "")

    def _format(self, drive: UsbDrive, progress: Progress) -> str:
        progress("format", 0.0, VOLUME_LABEL)
        try:
            partition = self.udisks.create_fat32_partition(drive.name, VOLUME_LABEL)
        except UDisksError as error:
            raise PreparationError("format", str(error)) from error
        deadline = self._clock() + SETTLE_SECONDS
        while True:
            fat = self._fat_version(drive.name, partition)
            if fat == "FAT32":
                break
            if fat and fat != "FAT32":
                raise PreparationError(
                    "format", f"The USB was formatted {fat}, not FAT32. Nothing was copied."
                )
            if self._clock() >= deadline:
                raise PreparationError("format", "The new FAT32 partition did not appear.")
            self._sleep(0.5)
        progress("format", 1.0, "FAT32")
        return partition

    def _fat_version(self, disk: str, partition: str) -> str:
        """"FAT32" once udev has probed the new partition, "" until then."""
        for drive in self._list_drives():
            if drive.name != disk:
                continue
            for child in drive.partitions:
                if child.name == partition and child.fstype == "vfat":
                    return child.fsver.upper()
        return ""

    def _mount(self, partition: str, step: str) -> str:
        try:
            return self.udisks.mount(partition)
        except UDisksError as error:
            raise PreparationError(step, str(error)) from error

    def _unmount(self, partition: str, step: str) -> None:
        try:
            if self.udisks.mount_points(partition):
                self.udisks.unmount(partition)
        except UDisksError as error:
            raise PreparationError(step, str(error)) from error

    def _copy(
        self, plan: KitPlan, local: dict[str, Path], partition: str, progress: Progress
    ) -> int:
        mount_point = self._mount(partition, "copy")
        total = plan.total_bytes or 1
        written = 0
        try:
            for folder in plan.folders:
                _usb_path(mount_point, folder).mkdir(parents=True, exist_ok=True)
            for item in plan.files:
                target = _usb_path(mount_point, item.path)
                target.parent.mkdir(parents=True, exist_ok=True)
                progress("copy", written / total, item.path)
                with open(target, "wb") as output:
                    if item.content is not None:
                        output.write(item.content)
                    else:
                        with open(local[item.source.sha256], "rb") as stream:  # type: ignore[union-attr]
                            for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
                                output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                written += item.size
        except OSError as error:
            raise PreparationError("copy", f"Could not write to the USB: {error}") from error
        progress("copy", 1.0, "")
        return written

    def _verify(self, plan: KitPlan, partition: str, progress: Progress) -> None:
        """Hash every file back from the stick itself.

        Unmounting drops the page cache for the filesystem, so the second
        mount reads what the flash cells hold, not what Linux remembers
        writing.
        """
        self._unmount(partition, "verify")
        mount_point = self._mount(partition, "verify")
        total = plan.total_bytes or 1
        checked = 0
        for item in plan.files:
            progress("verify", checked / total, item.path)
            try:
                digest = hashlib.sha256()
                with open(_usb_path(mount_point, item.path), "rb") as stream:
                    for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
                        digest.update(chunk)
            except OSError as error:
                raise PreparationError("verify", f"Could not read back {item.path}: {error}") from error
            if digest.hexdigest() != _expected_sha256(item):
                raise PreparationError(
                    "verify",
                    f"{item.path} on the USB does not match what was written. "
                    "The drive may be failing; try another one.",
                )
            checked += item.size
        progress("verify", 1.0, "")

    def _eject(self, drive: UsbDrive, partition: str, progress: Progress) -> bool:
        progress("eject", 0.0, drive.path)
        self._unmount(partition, "eject")
        try:
            self.udisks.power_off(drive.name)
        except UDisksError:
            # Unmounted is already safe to unplug; powering off is a courtesy.
            progress("eject", 1.0, "")
            return False
        progress("eject", 1.0, "")
        return True
