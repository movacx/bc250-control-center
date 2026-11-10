from __future__ import annotations

from pathlib import Path

BC250_GPU_DEVICE_ID = "0x13fe"


def is_bc250_platform() -> bool:
    identity_files = (
        Path("/proc/cpuinfo"),
        Path("/sys/class/dmi/id/board_name"),
        Path("/sys/class/dmi/id/product_name"),
        Path("/sys/class/dmi/id/product_version"),
    )
    for path in identity_files:
        try:
            if "bc-250" in path.read_text(encoding="utf-8", errors="ignore").lower():
                return True
        except OSError:
            continue
    for device in Path("/sys/class/drm").glob("card*/device"):
        try:
            vendor = (device / "vendor").read_text().strip().lower()
            device_id = (device / "device").read_text().strip().lower()
        except OSError:
            continue
        if vendor == "0x1002" and device_id == BC250_GPU_DEVICE_ID:
            return True
    return False


#: The AMD BC-250's GPU on the PCI bus.
_BC250_PCI = ("0x1002", "0x13fe")


def bc250_identity(pci_root: Path = Path("/sys/bus/pci/devices")) -> str:
    """``present``, ``absent`` or ``unknown``: is a BC-250 GPU on the PCI bus?

    ``absent`` only when every device could be read and none is the BC-250,
    so a container, a sandbox or an unreadable sysfs never locks a real
    BC-250 out of the fixes it may need (its kernel may not even bind the
    GPU): those report ``unknown`` and the workflows' own checks decide.
    """
    try:
        devices = list(pci_root.iterdir())
    except OSError:
        return "unknown"
    if not devices:
        return "unknown"
    complete = True
    for device in devices:
        try:
            vendor = (device / "vendor").read_text().strip().lower()
            device_id = (device / "device").read_text().strip().lower()
        except OSError:
            complete = False
            continue
        if (vendor, device_id) == _BC250_PCI:
            return "present"
    return "absent" if complete else "unknown"


def require_bc250_hardware() -> None:
    """Stop a hardware workflow before sudo, a clone or an install when this
    computer has no BC-250 (R-ffde613d and 11 more reports from one PC)."""
    if bc250_identity() == "absent":
        from bc250cc.shared.error_catalog import HARDWARE_GATE_MESSAGE
        from bc250cc.shared.errors import ActionNeeded

        raise ActionNeeded(HARDWARE_GATE_MESSAGE)
