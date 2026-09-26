"""USB drives, and which of them may be erased for a BIOS update kit.

Preparing the kit erases the whole drive, so the rules here err on the side
of refusing: a drive is offered only when it is attached over USB, writable,
large enough to be formatted FAT32, and holds no part of the running system.
The rules are pure so they can be tested without hardware; the helpers that
enumerate real drives and erase them re-check them right before any write.
"""

from __future__ import annotations

from dataclasses import dataclass

#: mkfs.fat picks FAT32 on its own from 512 MiB up; 1 GiB leaves room for the
#: kit (about 20 MB) and for the backup of the current BIOS (16 MiB), and keeps
#: every drive we accept in FAT32 territory, which is what the board's UEFI
#: reads most reliably.
MINIMUM_BYTES = 1024 ** 3
#: Bigger than any thumb drive a BC-250 owner is likely to sacrifice: most
#: likely an external disk. Still allowed, never silently.
LARGE_BYTES = 128 * 1024 ** 3

#: Mount points that mean "this drive is part of the running system".
SYSTEM_MOUNTS = frozenset({
    "/", "/boot", "/boot/efi", "/efi", "/home", "/usr", "/var", "/opt",
    "/srv", "/nix", "/sysroot", "/var/home", "/var/lib", "/recovery",
    "[SWAP]",
})


@dataclass(frozen=True)
class UsbPartition:
    name: str
    path: str
    size: int
    label: str = ""
    fstype: str = ""
    fsver: str = ""
    mountpoints: tuple[str, ...] = ()


@dataclass(frozen=True)
class UsbDrive:
    name: str
    path: str
    size: int
    vendor: str = ""
    model: str = ""
    serial: str = ""
    transport: str = ""
    removable: bool = False
    read_only: bool = False
    fstype: str = ""
    label: str = ""
    mountpoints: tuple[str, ...] = ()
    partitions: tuple[UsbPartition, ...] = ()

    @property
    def display_name(self) -> str:
        """"SanDisk Ultra"; never empty, never the vendor twice."""
        vendor = " ".join(self.vendor.split())
        model = " ".join(self.model.split())
        if vendor and model.lower().startswith(vendor.lower()):
            vendor = ""
        name = " ".join(part for part in (vendor, model) if part)
        return name or "USB drive"

    @property
    def identity(self) -> tuple[str, str, int, str]:
        """What must still match right before the drive is erased.

        A kernel name is reused as soon as a drive is unplugged, so the name
        alone would let a different stick plugged into the same slot be
        erased in its place.
        """
        return (self.name, self.serial, self.size, self.model.strip())

    @property
    def all_mountpoints(self) -> tuple[str, ...]:
        points = list(self.mountpoints)
        for partition in self.partitions:
            points.extend(partition.mountpoints)
        return tuple(point for point in points if point)

    @property
    def volume_labels(self) -> tuple[str, ...]:
        labels = [self.label] + [partition.label for partition in self.partitions]
        return tuple(label for label in labels if label)

    @property
    def holds_system(self) -> bool:
        return any(_is_system_mount(point) for point in self.all_mountpoints)

    def blocker(self) -> str:
        """Why this drive cannot be used, or "" when it can."""
        if self.transport != "usb":
            return "Not connected over USB."
        if self.holds_system:
            return "This drive holds part of the running system."
        if self.read_only:
            return "This drive is write-protected."
        if self.size < MINIMUM_BYTES:
            return "Too small: the kit needs a USB drive of at least 1 GB."
        return ""

    @property
    def eligible(self) -> bool:
        return not self.blocker()

    def warning(self) -> str:
        """Something the user should read before erasing, or ""."""
        if self.size >= LARGE_BYTES:
            return (
                "Larger than a typical USB stick. Make sure this is the drive "
                "you want to erase."
            )
        return ""


#: Trees whose every mount belongs to the running system. /home is not one:
#: a USB stick mounted by hand at ~/usb is exactly what this page is for.
SYSTEM_TREES = ("/boot/", "/sysroot/", "/usr/")


def _is_system_mount(point: str) -> bool:
    return point in SYSTEM_MOUNTS or point.startswith(SYSTEM_TREES)


def format_size(size: int) -> str:
    """Drive sizes the way they are sold: decimal gigabytes."""
    gigabytes = size / 1000 ** 3
    if gigabytes >= 1000:
        return f"{gigabytes / 1000:.1f} TB"
    if gigabytes >= 10:
        return f"{gigabytes:.0f} GB"
    if gigabytes >= 1:
        return f"{gigabytes:.1f} GB"
    return f"{size / 1000 ** 2:.0f} MB"
