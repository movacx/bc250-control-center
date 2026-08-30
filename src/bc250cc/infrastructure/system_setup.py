"""Desktop bridge to the root-owned optional setup helper."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

HELPER = Path("/usr/libexec/bc250-control-center/bc250-system-setup-helper")
POLICIES = {"preserve", "restore", "swap-16", "swap-32", "zram", "zswap-16", "zswap-32"}


def inventory() -> dict:
    if not HELPER.is_file():
        return {"helper_available": False, "memory": {}, "acpi": {},
                "reason": "Install or update Control Center's system setup helper first"}
    try:
        info = HELPER.stat()
        if info.st_uid != 0 or info.st_mode & 0o022 or HELPER.is_symlink():
            raise ValueError("System setup helper must be root-owned")
        result = subprocess.run(["/usr/bin/python3", "-I", str(HELPER), "status"],
                                capture_output=True, text=True, timeout=8, check=True)
        data = json.loads(result.stdout)
        if data.get("protocol") != 1:
            raise ValueError("Unsupported system setup protocol")
        return {**data, "helper_available": True}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {"helper_available": False, "memory": {}, "acpi": {}, "reason": str(exc)}


def command(action: str, policy: str = "preserve", ttm_gib: int = 0) -> str:
    if action not in {"memory-apply", "acpi-install", "acpi-uninstall", "acpi-check"}:
        raise ValueError("Unsupported system setup action")
    if policy not in POLICIES or type(ttm_gib) is not int or ttm_gib not in {-1, 0, 8, 10, 12}:
        raise ValueError("Invalid memory setup request")
    args = f" --policy {policy} --ttm {ttm_gib}" if action == "memory-apply" else ""
    return ("set -euo pipefail\n"
            "echo '== BC250 optional system setup (testing) =='\n"
            f"test -x {HELPER} || {{ echo 'Update/reinstall Control Center to install the protected system setup helper.'; exit 69; }}\n"
            f"sudo {HELPER} {action}{args}\n")
