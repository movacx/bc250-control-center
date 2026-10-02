"""Desktop bridge to the root-owned optional setup helper."""
from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path

HELPER = Path("/usr/libexec/bc250-control-center/bc250-system-setup-helper")
POLICIES = {"preserve", "restore", "swap-16", "swap-32", "zram", "zswap-16", "zswap-32"}
#: The BC-250 kernel unlocks all 40 compute units itself when amdgpu is given
#: this write mode; it replaces umr and the live CU manager.
CU_UNLOCK_OPTION = "amdgpu.bc250_cc_write_mode=3"
#: The only kernel boot options the helper manages.
KERNEL_OPTIONS = ("mitigations=off", "nosmt", CU_UNLOCK_OPTION)


def inventory() -> dict:
    if not HELPER.is_file():
        return {"helper_available": False, "memory": {}, "acpi": {}, "telemetry": {}, "kernel_options": {}, "vram": {},
                "reason": "Install or update Control Center's system setup helper first"}
    try:
        info = HELPER.stat()
        if info.st_uid != 0 or info.st_mode & 0o022 or HELPER.is_symlink():
            raise ValueError("System setup helper must be root-owned")
        result = subprocess.run(["/usr/bin/python3", "-I", str(HELPER), "status"],
                                capture_output=True, text=True, timeout=8, check=True)
        data = json.loads(result.stdout)
        if data.get("protocol") != 2:
            raise ValueError("Unsupported system setup protocol")
        return {**data, "helper_available": True}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {"helper_available": False, "memory": {}, "acpi": {}, "telemetry": {}, "kernel_options": {}, "vram": {}, "reason": str(exc)}


def command(action: str, policy: str = "preserve", ttm_gib: int = 0, uma_size_mb: int = 0,
            takeover_zram: bool = False, target_mount: str = "",
            kernel_options: tuple[str, ...] = ()) -> str:
    if action not in {
        "memory-apply", "acpi-install", "acpi-uninstall", "acpi-check",
        "telemetry-fix", "telemetry-restore", "vram-read", "vram-apply",
        "kernel-options-set",
    }:
        raise ValueError("Unsupported system setup action")
    kernel_options = tuple(kernel_options or ())
    if any(option not in KERNEL_OPTIONS for option in kernel_options):
        raise ValueError("Invalid kernel option request")
    if policy not in POLICIES or type(ttm_gib) is not int or ttm_gib not in {-1, 0, 8, 10, 12}:
        raise ValueError("Invalid memory setup request")
    if action == "vram-apply" and (type(uma_size_mb) is not int or not (256 <= uma_size_mb < 16384)):
        raise ValueError("Invalid VRAM setup request")
    target_mount = str(target_mount or "")
    if target_mount and not re.fullmatch(r"/[A-Za-z0-9_./-]*", target_mount):
        raise ValueError("Invalid swap target mount")
    if action == "memory-apply":
        args = f" --policy {policy} --ttm {ttm_gib}"
        if takeover_zram:
            args += " --takeover-zram"
        if target_mount:
            args += f" --target-mount {shlex.quote(target_mount)}"
    elif action == "vram-apply":
        args = f" --uma-size {uma_size_mb}"
    elif action == "kernel-options-set":
        wanted = ",".join(option for option in KERNEL_OPTIONS if option in kernel_options)
        args = f" --kernel-options {shlex.quote(wanted)}"
    else:
        args = ""
    return ("set -euo pipefail\n"
            "echo '== BC250 optional system setup (testing) =='\n"
            f"test -x {HELPER} || {{ echo 'Update/reinstall Control Center to install the protected system setup helper.'; exit 69; }}\n"
            f"sudo {HELPER} {action}{args}\n")
