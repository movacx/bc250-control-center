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
