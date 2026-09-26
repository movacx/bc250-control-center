"""Async compute for Arch-family systems: the patched RADV alone, kernel 7.2+.

tri3gubki-ops/bc250-async-compute-bazzite runs RADV with the GFX1013
compute-queue patch on Bazzite's OGC 7.2 kernel, whose amdgpu is stock. The
amdgpu of linux 7.2 is the same on CachyOS and on OGC -- gmc_v10_0.c,
gfx_v10_0.c, amdgpu_amdkfd.c and the VM, ring and CS code are byte-identical
in 7.2.7 -- so on an Arch-family kernel 7.2 or newer that driver is all async
compute needs: no patched amdgpu, no initramfs, nothing to rebuild after a
kernel update. Older kernels keep DryhoppedIPA's kernel-side fix
(``gfx1013_source``), without which the patched RADV can hang the GPU.

The driver is built from Mesa's release tarball with the upstream patches, at
a reviewed commit, and installed beside the system Mesa; the shell side lives
in ``scripts/system/bc250-async-compute-radv.sh``. Bazzite keeps its own
release and is never offered this route.
"""

from __future__ import annotations

import os
import platform
import re
import shlex
from collections.abc import Mapping
from pathlib import Path

from .source_checkout import clone_or_update_commit

RADV_ASYNC_UPSTREAM = "https://github.com/tri3gubki-ops/bc250-async-compute-bazzite"
#: 0.3.0 on main: the patches and tests of the v0.2.4 release, unchanged.
RADV_ASYNC_REVIEWED_COMMIT = "56bf06b986f4639c32a669e9cdd31cdf7fba44b6"
#: Must match MESA_VERSION in the shell script.
RADV_ASYNC_MESA_VERSION = "26.2.3"
SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "system" / "bc250-async-compute-radv.sh"
PREFIX_ROOT = Path("/opt/bc250cc-radv")
CONF_DIR = Path("/etc/bc250cc-radv")
GFX1013_RUN_DIR = Path("/run/bc250cc-gfx1013")
MARKER = "# Managed by BC250 Control Center: RADV async compute"
ARCH_FAMILIES = frozenset({"arch", "cachyos", "manjaro", "endeavouros", "garuda", "artix"})
ACTIONS = frozenset({"install", "enable", "disable", "uninstall", "status", "test"})
MIN_KERNEL = (7, 2)


def _kernel_version(kernel: str) -> tuple[int, int] | None:
    match = re.match(r"^(\d+)\.(\d+)", str(kernel or ""))
    return (int(match.group(1)), int(match.group(2))) if match else None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def radv_async_supported(
    *, family: str, distro_id: str = "", kernel: str = "", immutable: bool = False
) -> tuple[bool, str]:
    """Whether this host may use the RADV-only route, and why not when not."""
    family = str(family or "").strip().lower()
    distro_id = str(distro_id or "").strip().lower()
    if family == "bazzite" or distro_id == "bazzite":
        return False, "Bazzite keeps its reviewed async-compute release."
    if family == "steamos":
        return False, "SteamOS keeps its dedicated toolkit."
    if immutable:
        return False, "Image-based systems are not covered by this build."
    if family not in ARCH_FAMILIES and distro_id not in ARCH_FAMILIES:
        return False, "This build covers Arch-family distributions."
    if "bc250" in str(kernel or "").lower():
        return False, "This BC-250 kernel ships its own matching Mesa route."
    version = _kernel_version(kernel)
    if version is None or version < MIN_KERNEL:
        return False, "Kernel 7.2 or newer is needed; older kernels need the kernel-side fix."
    return True, ""


def radv_async_state(
    *,
    family: str,
    distro_id: str = "",
    kernel: str | None = None,
    immutable: bool = False,
    environ: Mapping[str, str] | None = None,
) -> dict:
    """Read-only: what the installed files and this session say."""
    running = kernel or platform.release()
    supported, blocked_reason = radv_async_supported(
        family=family, distro_id=distro_id, kernel=running, immutable=immutable
    )
    active = _read(CONF_DIR / "active.env")
    installed = MARKER in active
    version = ""
    for line in active.splitlines():
        if line.startswith("VERSION="):
            version = line.partition("=")[2]
    icd = PREFIX_ROOT / version / "share/vulkan/icd.d/radeon_icd.x86_64.json" if version else None
    driver_present = bool(icd and icd.is_file() and (PREFIX_ROOT / version / "lib/libvulkan_radeon.so").is_file())
    enabled = (CONF_DIR / "enabled").exists()
    session_files = str((environ if environ is not None else os.environ).get("VK_DRIVER_FILES") or "")
    session_active = bool(icd) and str(icd) in session_files.split(":")
    deferred = _read(GFX1013_RUN_DIR / "loaded") == "patched"
    if not installed:
        state = "not-installed"
    elif not driver_present:
        state = "invalid"
    elif session_active:
        state = "active"
    elif deferred:
        state = "deferred"
    elif enabled:
        state = "relogin-required"
    else:
        state = "switched-off"
    return {
        "supported": supported,
        "blocked_reason": blocked_reason,
        "installed": installed,
        "enabled": enabled,
        "version": version,
        "expected_version": RADV_ASYNC_MESA_VERSION,
        "outdated": bool(installed and version and version != RADV_ASYNC_MESA_VERSION),
        "kernel": running,
        "session_active": session_active,
        "state": state,
    }


def build_radv_async_command(action: str, checkout: str | Path, *, script: Path = SCRIPT) -> str:
    """One closed shell workflow per action, for the embedded terminal.

    Building runs as the user; installing, switching and removing use sudo
    through a root-owned copy of the reviewed script, so the privileged part
    never executes a file the user can write.
    """
    action = str(action or "").strip().lower()
    if action not in ACTIONS:
        raise ValueError(f"Unsupported async-compute action: {action or '--'}")
    checkout = Path(checkout)
    quoted_script = shlex.quote(str(script))
    quoted_checkout = shlex.quote(str(checkout))
    header = "\n".join((
        "set -Eeuo pipefail",
        'echo; echo "=========================================================================="',
        'echo "  BC-250 async compute · patched RADV beside the system Mesa"',
        f'echo "  tri3gubki-ops patches · Mesa {RADV_ASYNC_MESA_VERSION} · no kernel module (linux 7.2+)"',
        'echo "=========================================================================="; echo',
        f"test -f {quoted_script} || {{ echo 'ERROR: the async-compute script is missing; reinstall Control Center.'; exit 29; }}",
    ))
    if action == "status":
        return f"{header}\nbash {quoted_script} status"
    if action == "test":
        return "\n".join((
            header,
            "command -v bc250cc-async-compute >/dev/null || { echo 'ERROR: async compute is not installed.'; exit 29; }",
            "bc250cc-async-compute status",
            "echo",
            "bc250cc-async-compute test",
        ))
    root_copy = (
        'bc250_root_script="$(sudo mktemp /run/bc250cc-radv-async.XXXXXX)"\n'
        f'sudo install -m 0755 {quoted_script} "$bc250_root_script"\n'
        "trap 'kill \"${bc250_sudo_keepalive:-}\" 2>/dev/null || true; "
        "sudo rm -f -- \"$bc250_root_script\"' EXIT"
    )
    if action in {"enable", "disable", "uninstall"}:
        return f'{header}\n{root_copy}\nsudo bash "$bc250_root_script" {action}'
    keep_sudo = "\n".join((
        'echo "[INFO] Your password is asked once now; the install at the end reuses it."',
        "sudo -v",
        "( while sleep 50; do sudo -n -v 2>/dev/null || exit 0; done ) &",
        "bc250_sudo_keepalive=$!",
        "trap 'kill \"$bc250_sudo_keepalive\" 2>/dev/null || true' EXIT",
    ))
    verify = (
        f'test "$(git -C {quoted_checkout} rev-parse HEAD)" = {RADV_ASYNC_REVIEWED_COMMIT} || '
        "{ echo 'ERROR: the reviewed upstream revision was not checked out.'; exit 29; }"
    )
    stage = '"${XDG_CACHE_HOME:-$HOME/.cache}/bc250-control-center/radv-async/stage"'
    return "\n".join((
        header,
        'echo "[INFO] Building RADV takes 10-20 minutes on a BC-250. Nothing is installed until it built."',
        keep_sudo,
        clone_or_update_commit(RADV_ASYNC_UPSTREAM, checkout, RADV_ASYNC_REVIEWED_COMMIT),
        verify,
        f"bash {quoted_script} deps",
        f"bash {quoted_script} build --source {quoted_checkout} --stage {stage}",
        root_copy,
        f'sudo bash "$bc250_root_script" install --stage {stage}',
    ))
