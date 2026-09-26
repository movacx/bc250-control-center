"""Lists the USB drives attached right now, from lsblk.

lsblk reads the kernel's view through sysfs and udev without privileges, is
part of util-linux on every distribution Control Center supports, and prints
JSON, so there is nothing to scrape. Every USB disk is returned, eligible or
not: the interface shows why a drive cannot be used instead of hiding it.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence

from bc250cc.domain.firmware.usb import UsbDrive, UsbPartition

COLUMNS = (
    "NAME", "PATH", "TYPE", "TRAN", "RM", "RO", "SIZE", "VENDOR", "MODEL",
    "SERIAL", "LABEL", "FSTYPE", "FSVER", "MOUNTPOINTS",
)
#: util-linux before 2.37 knows only the singular column.
LEGACY_COLUMNS = tuple("MOUNTPOINT" if column == "MOUNTPOINTS" else column for column in COLUMNS)

Runner = Callable[..., subprocess.CompletedProcess]


def _run_lsblk(columns: Sequence[str], runner: Runner) -> subprocess.CompletedProcess:
    return runner(
        ["lsblk", "--json", "--bytes", "--output", ",".join(columns)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
        env={"LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
    )


def list_usb_drives(runner: Runner = subprocess.run) -> list[UsbDrive]:
    """Every USB disk, in lsblk's order; [] when lsblk cannot answer."""
    try:
        result = _run_lsblk(COLUMNS, runner)
        if result.returncode != 0:
            result = _run_lsblk(LEGACY_COLUMNS, runner)
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    try:
        return parse_lsblk(json.loads(result.stdout or "{}"))
    except ValueError:
        return []


def parse_lsblk(payload: object) -> list[UsbDrive]:
    devices = payload.get("blockdevices") if isinstance(payload, dict) else None
    drives: list[UsbDrive] = []
    for device in devices if isinstance(devices, list) else ():
        if not isinstance(device, dict) or device.get("type") != "disk":
            continue
        if _text(device.get("tran")) != "usb":
            continue
        drives.append(_drive(device))
    return drives


def _drive(device: dict) -> UsbDrive:
    partitions = tuple(
        UsbPartition(
            name=_text(child.get("name")),
            path=_text(child.get("path")),
            size=_integer(child.get("size")),
            label=_text(child.get("label")),
            fstype=_text(child.get("fstype")),
            fsver=_text(child.get("fsver")),
            mountpoints=_mountpoints(child),
        )
        for child in device.get("children") or ()
        if isinstance(child, dict)
    )
    return UsbDrive(
        name=_text(device.get("name")),
        path=_text(device.get("path")) or f"/dev/{_text(device.get('name'))}",
        size=_integer(device.get("size")),
        vendor=_text(device.get("vendor")),
        model=_text(device.get("model")),
        serial=_text(device.get("serial")),
        transport=_text(device.get("tran")),
        removable=_flag(device.get("rm")),
        read_only=_flag(device.get("ro")),
        fstype=_text(device.get("fstype")),
        label=_text(device.get("label")),
        mountpoints=_mountpoints(device),
        partitions=partitions,
    )


def _mountpoints(device: dict) -> tuple[str, ...]:
    points = device.get("mountpoints")
    if points is None:
        points = [device.get("mountpoint")]
    return tuple(_text(point) for point in points if point)


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _integer(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _flag(value: object) -> bool:
    """lsblk prints booleans since 2.33 and "0"/"1" before that."""
    if isinstance(value, bool):
        return value
    return _text(value) in {"1", "true"}
