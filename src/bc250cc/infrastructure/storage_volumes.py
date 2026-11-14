"""Which mounted filesystems are disks a person would call theirs.

``psutil.disk_partitions(all=False)`` still lists far more than the drives a
user plugged in: the read-only image an immutable system boots from (SteamOS
``/``, the composefs ``/`` and ``/sysroot`` of Bazzite), the EFI and boot
partitions, and the same btrfs device mounted again at ``/etc``, ``/var`` or a
dozen SteamOS offload binds. This module keeps one entry per real device, with
a name people recognise, so an external USB or eSATA drive shows up as its own
row and disappears again once it is unmounted.

Everything here is pure: the caller hands in the partition list, a usage
reader and the volume labels, which keeps the rules testable with the layouts
of each distribution.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

#: Filesystems that never hold a user's files: kernel interfaces, RAM disks,
#: compressed system images and optical media.
PSEUDO_FSTYPES = frozenset({
    "autofs", "binfmt_misc", "bpf", "cgroup", "cgroup2", "composefs", "configfs",
    "debugfs", "devpts", "devtmpfs", "efivarfs", "erofs", "fusectl", "hugetlbfs",
    "iso9660", "mqueue", "nsfs", "overlay", "proc", "pstore", "ramfs", "rpc_pipefs",
    "securityfs", "squashfs", "sysfs", "tmpfs", "tracefs", "udf",
})

#: Block devices that are images or memory, not drives.
VIRTUAL_DEVICE_PREFIXES = ("/dev/loop", "/dev/zram", "/dev/ram", "/dev/sr", "/dev/fd")

#: Mount points that belong to the operating system rather than its user.
SYSTEM_MOUNTPOINTS = frozenset({
    "/boot", "/boot/efi", "/efi", "/esp", "/etc", "/frzr_root", "/recovery",
    "/sysroot", "/usr",
})
SYSTEM_PREFIXES = (
    "/boot/", "/efi/", "/sysroot/", "/usr/", "/snap/", "/proc/", "/sys/", "/dev/",
    "/var/lib/", "/tmp",
)

#: Where desktops and people mount drives that come and go.
EXTERNAL_PREFIXES = ("/run/media/", "/media/", "/mnt/", "/var/mnt/", "/var/media/", "/var/run/media/")

#: Which mount point names a device, best first.
PREFERRED_MOUNTPOINTS = ("/", "/home", "/var/home", "/var")
HOME_MOUNTPOINTS = frozenset({"/home", "/var/home"})

#: Below this an internal partition is plumbing (SteamOS keeps a 256 MiB
#: ``/var`` per slot), not a disk worth a row. External media keep any size.
MIN_INTERNAL_BYTES = 1 << 30

_HEX_ESCAPE = re.compile(rb"\\x([0-9a-fA-F]{2})")


def is_external_mountpoint(mountpoint: str) -> bool:
    return any(mountpoint.startswith(prefix) for prefix in EXTERNAL_PREFIXES)


def _is_system_mountpoint(mountpoint: str) -> bool:
    if mountpoint in SYSTEM_MOUNTPOINTS:
        return True
    if mountpoint.startswith("/run/") and not mountpoint.startswith("/run/media/"):
        return True
    return any(mountpoint.startswith(prefix) for prefix in SYSTEM_PREFIXES)


def _is_real_filesystem(device: str, fstype: str) -> bool:
    fstype = fstype.lower()
    if fstype in PSEUDO_FSTYPES:
        return False
    if fstype == "zfs":
        return bool(device)
    # Network shares (nfs, cifs, sshfs) can hang a statvfs when the server
    # is gone, and are not a drive of this board.
    if not device.startswith("/dev/"):
        return False
    return not device.startswith(VIRTUAL_DEVICE_PREFIXES)


def _device_key(device: str, fstype: str) -> str:
    # ZFS datasets share their pool's free space: one row per pool.
    return device.split("/", 1)[0] if fstype.lower() == "zfs" else device


def _is_read_only(options: str) -> bool:
    return "ro" in str(options or "").split(",")


def _mountpoint_rank(mountpoint: str) -> tuple:
    if mountpoint in PREFERRED_MOUNTPOINTS:
        return (0, PREFERRED_MOUNTPOINTS.index(mountpoint), "")
    return (1 if is_external_mountpoint(mountpoint) else 2, len(mountpoint), mountpoint)


def decode_udev_label(name: str) -> str:
    """``My\\x20Disk`` from ``/dev/disk/by-label`` back to ``My Disk``."""
    raw = _HEX_ESCAPE.sub(lambda match: bytes([int(match.group(1), 16)]), os.fsencode(name))
    return raw.decode("utf-8", "replace")


def _kind(mountpoint: str, system: bool, external: bool) -> str:
    if system:
        return "system"
    if mountpoint in HOME_MOUNTPOINTS:
        return "home"
    return "external" if external else "volume"


def _label(kind: str, mountpoint: str, volume_label: str, device: str) -> str:
    if kind == "system":
        return "System"
    if kind == "home":
        return "Home"
    return volume_label or Path(mountpoint).name or Path(device).name or mountpoint


_KIND_ORDER = {"system": 0, "home": 1, "volume": 2, "external": 3}


def list_real_disks(
    partitions: Iterable[object],
    usage: Callable[[str], object],
    labels: Mapping[str, str] | None = None,
) -> list[dict]:
    """One usage entry per real disk, system first, then home, then the rest.

    ``partitions`` are ``psutil.disk_partitions(all=False)`` entries (any
    object with ``device``, ``mountpoint``, ``fstype`` and ``opts``),
    ``usage`` is ``psutil.disk_usage`` and ``labels`` maps a device to its
    volume label. A mount that cannot be read is left out rather than shown
    as an error: the next sample tries again.
    """
    labels = labels or {}
    groups: dict[str, list] = {}
    for partition in partitions:
        device = str(getattr(partition, "device", "") or "")
        mountpoint = str(getattr(partition, "mountpoint", "") or "")
        fstype = str(getattr(partition, "fstype", "") or "")
        if not mountpoint or not _is_real_filesystem(device, fstype):
            continue
        groups.setdefault(_device_key(device, fstype), []).append(partition)

    disks = []
    for key, entries in groups.items():
        mountpoints = {str(entry.mountpoint) for entry in entries}
        system = bool(mountpoints & {"/", "/sysroot"})
        visible = [
            entry for entry in entries
            if not _is_system_mountpoint(str(entry.mountpoint))
            and (not _is_read_only(getattr(entry, "opts", "")) or is_external_mountpoint(str(entry.mountpoint)))
        ]
        if not visible:
            # A read-only system image, or only boot and EFI partitions.
            continue
        chosen = min(visible, key=lambda entry: _mountpoint_rank(str(entry.mountpoint)))
        mountpoint = str(chosen.mountpoint)
        external = is_external_mountpoint(mountpoint)
        try:
            reading = usage(mountpoint)
            total = int(getattr(reading, "total", 0) or 0)
            used = int(getattr(reading, "used", 0) or 0)
            free = int(getattr(reading, "free", 0) or 0)
            percent = float(getattr(reading, "percent", 0.0) or 0.0)
        except (OSError, TypeError, ValueError):
            continue
        if total <= 0 or (not external and not system and total < MIN_INTERNAL_BYTES):
            continue
        device = str(chosen.device)
        kind = _kind(mountpoint, system, external)
        disks.append({
            "label": _label(kind, mountpoint, str(labels.get(device) or "").strip(), device),
            "kind": kind,
            "mountpoint": mountpoint,
            "device": device if key == device else key,
            "fstype": str(chosen.fstype),
            "external": external,
            "total": total,
            "used": used,
            "free": free,
            "percent": max(0.0, min(100.0, percent)),
        })

    disks.sort(key=lambda disk: (_KIND_ORDER[disk["kind"]], disk["mountpoint"]))
    seen: dict[str, int] = {}
    for disk in disks:
        seen[disk["label"]] = seen.get(disk["label"], 0) + 1
    for disk in disks:
        if seen[disk["label"]] > 1 and disk["kind"] not in ("system", "home"):
            disk["label"] = f"{disk['label']} ({Path(disk['device']).name})"
    return disks
