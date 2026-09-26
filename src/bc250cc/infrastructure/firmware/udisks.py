"""Partitions, formats, mounts and ejects a USB drive through UDisks2.

UDisks2 is the service KDE's and GNOME's own disk tools use. Going through it
rather than a root helper means Polkit decides who may modify which drive,
with the policy the desktop already ships: the active user may modify a
removable device without a password, while anything UDisks itself flags as a
system device needs an administrator. Nothing here runs as root.

The calls go through ``busctl``, part of systemd, which prints typed JSON and
already carries the rest of the application's D-Bus traffic.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable

BUS = "org.freedesktop.UDisks2"
BLOCK_ROOT = "/org/freedesktop/UDisks2/block_devices"
MANAGER = "/org/freedesktop/UDisks2/Manager"
BLOCK = "org.freedesktop.UDisks2.Block"
DRIVE = "org.freedesktop.UDisks2.Drive"
FILESYSTEM = "org.freedesktop.UDisks2.Filesystem"
PARTITION_TABLE = "org.freedesktop.UDisks2.PartitionTable"

#: One MiB in: the alignment every partitioning tool uses today.
PARTITION_OFFSET = 1024 * 1024
#: MBR type 0x0C, "W95 FAT32 (LBA)": what a FAT32 boot stick is expected to say.
FAT32_LBA = "0x0c"
#: Formatting tears down mounts and writes a new table; slow sticks need time.
SLOW_CALL_SECONDS = 300

_KERNEL_NAME = re.compile(r"^[a-z][a-z0-9]*$")

Runner = Callable[..., subprocess.CompletedProcess]


class UDisksError(RuntimeError):
    """A UDisks2 call failed; the message is the service's own."""


def available(runner: Runner = subprocess.run) -> bool:
    """UDisks2 is reachable and busctl exists to talk to it."""
    if not shutil.which("busctl"):
        return False
    try:
        UDisksClient(runner).property(MANAGER, "org.freedesktop.UDisks2.Manager", "Version")
    except (UDisksError, OSError, subprocess.SubprocessError):
        return False
    return True


def block_path(name: str) -> str:
    if not _KERNEL_NAME.match(name):
        raise UDisksError(f"Not a kernel block device name: {name!r}")
    return f"{BLOCK_ROOT}/{name}"


def _decode_bytes(values: object) -> str:
    """UDisks sends paths as NUL-terminated byte arrays (D-Bus "ay")."""
    if not isinstance(values, list):
        return ""
    raw = bytes(int(value) & 0xFF for value in values)
    return raw.split(b"\0", 1)[0].decode("utf-8", "replace")


class UDisksClient:
    def __init__(self, runner: Runner = subprocess.run) -> None:
        self._runner = runner

    # -------------------------------------------------------------- plumbing

    def _busctl(self, arguments: list[str], *, timeout: int) -> object:
        command = [
            "busctl", "--system", "--json=short", f"--timeout={timeout}", *arguments,
        ]
        result = self._runner(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout + 15,
            env={"LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "").strip()
            raise UDisksError(message.removeprefix("Call failed: ") or "UDisks2 call failed.")
        text = (result.stdout or "").strip()
        if not text:
            return None
        try:
            return json.loads(text).get("data")
        except (ValueError, AttributeError) as error:
            raise UDisksError(f"Unexpected answer from UDisks2: {text[:200]}") from error

    def property(self, path: str, interface: str, name: str) -> object:
        return self._busctl(["get-property", BUS, path, interface, name], timeout=10)

    def _call(
        self, path: str, interface: str, method: str, signature: str, *arguments: str,
        timeout: int = 30,
    ) -> object:
        return self._busctl(
            ["call", BUS, path, interface, method, signature, *arguments], timeout=timeout
        )

    # --------------------------------------------------------------- queries

    def is_system_device(self, name: str) -> bool:
        """UDisks' own verdict, independent of our lsblk reading."""
        return bool(self.property(block_path(name), BLOCK, "HintSystem"))

    def connection_bus(self, name: str) -> str:
        drive = self.property(block_path(name), BLOCK, "Drive")
        if not isinstance(drive, str) or drive in {"", "/"}:
            return ""
        return str(self.property(drive, DRIVE, "ConnectionBus") or "")

    def mount_points(self, name: str) -> list[str]:
        try:
            values = self.property(block_path(name), FILESYSTEM, "MountPoints")
        except UDisksError:
            # Not a filesystem (yet): nothing is mounted from it.
            return []
        return [point for point in map(_decode_bytes, values or []) if point]

    # --------------------------------------------------------------- actions

    def unmount(self, name: str) -> None:
        self._call(block_path(name), FILESYSTEM, "Unmount", "a{sv}", "0", timeout=60)

    def erase_to_empty_mbr(self, name: str) -> None:
        """Replace everything on the disk with an empty MBR partition table.

        MBR rather than GPT: it is what every AMI UEFI of this generation
        boots removable media from without question.
        """
        self._call(
            block_path(name), BLOCK, "Format", "sa{sv}",
            "dos", "1", "tear-down", "b", "true",
            timeout=SLOW_CALL_SECONDS,
        )

    def create_fat32_partition(self, name: str, label: str) -> str:
        """One partition over the whole disk, formatted FAT; its kernel name."""
        created = self._call(
            block_path(name), PARTITION_TABLE, "CreatePartitionAndFormat", "ttssa{sv}sa{sv}",
            str(PARTITION_OFFSET), "0", FAT32_LBA, "", "0",
            "vfat", "2", "label", "s", label, "update-partition-type", "b", "true",
            timeout=SLOW_CALL_SECONDS,
        )
        path = created[0] if isinstance(created, list) and created else created
        if not isinstance(path, str) or not path.startswith(BLOCK_ROOT + "/"):
            raise UDisksError("UDisks2 did not report the new partition.")
        return path.rsplit("/", 1)[1]

    def mount(self, name: str) -> str:
        """Mount point of ``name``, mounting it where the desktop would."""
        points = self.mount_points(name)
        if points:
            return points[0]
        try:
            mounted = self._call(block_path(name), FILESYSTEM, "Mount", "a{sv}", "0", timeout=60)
        except UDisksError:
            # A desktop automounter can win the race to the new partition.
            points = self.mount_points(name)
            if points:
                return points[0]
            raise
        point = mounted[0] if isinstance(mounted, list) and mounted else mounted
        if not isinstance(point, str) or not point:
            raise UDisksError("UDisks2 did not report where the USB was mounted.")
        return point

    def power_off(self, name: str) -> None:
        """Eject: the drive can be pulled out once this returns."""
        drive = self.property(block_path(name), BLOCK, "Drive")
        if isinstance(drive, str) and drive not in {"", "/"}:
            self._call(drive, DRIVE, "PowerOff", "a{sv}", "0", timeout=60)
