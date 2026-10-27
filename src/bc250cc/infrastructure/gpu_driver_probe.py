"""Whether the BC-250's GPU has a driver in this boot.

Two reports of the first week came from boards whose amdgpu failed to start
("get invalid ip discovery binary signature ... Fatal error during GPU init"):
every GPU page then failed with D-Bus, UMR or Cyan errors that hid the real
cause. Read-only, from /sys, no privileges.
"""

from __future__ import annotations

from pathlib import Path

BC250_PCI = ("0x1002", "0x13fe")


def gpu_driver_state(root: Path = Path("/sys/bus/pci/devices")) -> dict[str, object]:
    """``{"present": bool, "bound": bool, "driver": str}`` for the BC-250 GPU."""
    for device in sorted(root.glob("*")):
        try:
            vendor = (device / "vendor").read_text().strip()
            model = (device / "device").read_text().strip()
        except OSError:
            continue
        if (vendor, model) != BC250_PCI:
            continue
        driver = device / "driver"
        name = driver.resolve().name if driver.exists() else ""
        return {"present": True, "bound": name == "amdgpu", "driver": name}
    return {"present": False, "bound": False, "driver": ""}
