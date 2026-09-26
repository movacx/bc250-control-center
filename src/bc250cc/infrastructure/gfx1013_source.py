"""The GFX1013 compute-queue fix built from source, without MastaG's kernel.

DryhoppedIPA's own installer covers Fedora only, and on Arch/CachyOS the only
automated route so far was MastaG's complete BC-250 kernel and Mesa. That
route works, but it replaces the whole kernel, and users report it does not
bring the performance the fix brings elsewhere. This one builds just the two
pieces upstream publishes -- the V33 amdgpu patches for the *running* kernel
and RADV with the compute-queue patch -- and installs them beside the
distribution's own, never over them.

Bazzite keeps its reviewed release, SteamOS its toolkit and Fedora
DryhoppedIPA's installer; none of them is offered this route. The shell side
lives in ``scripts/system/bc250-gfx1013-source.sh``; see its header for the
boot protection (fallback to the stock module after a failed boot, and
``bc250.gfx1013=0`` at the boot menu).
"""

from __future__ import annotations

import platform
import re
import shlex
from pathlib import Path

from .gfx1013_compute_policy import GFX1013_REVIEWED_COMMIT, GFX1013_UPSTREAM
from .source_checkout import clone_or_update_commit

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "system" / "bc250-gfx1013-source.sh"
LIB_DIR = Path("/usr/lib/bc250cc-gfx1013")
CONF_DIR = Path("/etc/bc250cc-gfx1013")
STATE_DIR = Path("/var/lib/bc250cc-gfx1013")
RUN_DIR = Path("/run/bc250cc-gfx1013")
MARKER = "# Managed by BC250 Control Center: GFX1013 compute-queue fix"
#: Families whose kernel headers and build tools the script knows how to get.
SOURCE_FAMILIES = frozenset({
    "arch", "cachyos", "manjaro", "endeavouros", "garuda",
    "debian", "ubuntu", "linuxmint", "pop",
    "opensuse", "suse",
})
ACTIONS = frozenset({"install", "rebuild", "enable", "disable", "uninstall", "status"})
#: The V33 patches apply from linux 6.14 on (checked against 6.14 to 7.2). On
#: 6.12 (Debian 13), 6.8 (Ubuntu 24.04 before its HWE kernel) or older they do
#: not, so the build is not offered there at all.
MIN_KERNEL = (6, 14)


def kernel_version(kernel: str) -> tuple[int, int] | None:
    """``(major, minor)`` of a ``uname -r`` string, or None when unreadable."""
    match = re.match(r"^(\d+)\.(\d+)", str(kernel or ""))
    return (int(match.group(1)), int(match.group(2))) if match else None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def gfx1013_source_supported(
    *, family: str, distro_id: str = "", kernel: str = "", immutable: bool = False
) -> tuple[bool, str]:
    """Whether this host may use the source build, and why not when it may not."""
    family = str(family or "").strip().lower()
    distro_id = str(distro_id or "").strip().lower()
    if family in {"bazzite"} or distro_id == "bazzite":
        return False, "Bazzite keeps its reviewed async-compute release."
    if family == "steamos":
        return False, "SteamOS keeps its dedicated toolkit."
    if family == "fedora":
        return False, "Fedora uses DryhoppedIPA's own installer."
    if immutable:
        return False, "Image-based systems cannot take an out-of-tree amdgpu this way."
    if "bc250" in str(kernel or "").lower():
        return False, "This BC-250 kernel already carries the fix."
    version = kernel_version(kernel)
    if version is not None and version < MIN_KERNEL:
        return False, "The V33 patches need linux 6.14 or newer."
    if family not in SOURCE_FAMILIES and distro_id not in SOURCE_FAMILIES:
        return False, "This distribution is not covered; the upstream README explains the manual path."
    return True, ""


def gfx1013_source_state(
    *, family: str, distro_id: str = "", kernel: str | None = None, immutable: bool = False
) -> dict:
    """Read-only: what the boot service and the installed files say."""
    running = kernel or platform.release()
    supported, blocked_reason = gfx1013_source_supported(
        family=family, distro_id=distro_id, kernel=running, immutable=immutable
    )
    active = _read(CONF_DIR / "active.env")
    installed = MARKER in active
    version = ""
    for line in active.splitlines():
        if line.startswith("VERSION="):
            version = line.partition("=")[2]
    module = (LIB_DIR / running / "amdgpu.ko").is_file()
    loaded = _read(RUN_DIR / "loaded")
    enabled = (CONF_DIR / "enabled").exists()
    fallback = (STATE_DIR / "last-fallback").exists()
    if not installed:
        state = "not-installed"
    elif loaded == "patched":
        state = "active"
    elif not module:
        state = "rebuild-needed"
    elif fallback and not enabled:
        state = "fell-back"
    elif not enabled:
        state = "switched-off"
    elif loaded == "early":
        state = "blocked-early-load"
    else:
        state = "reboot-required"
    return {
        "supported": supported,
        "blocked_reason": blocked_reason,
        "installed": installed,
        "enabled": enabled,
        "version": version,
        "kernel": running,
        "module_for_kernel": module,
        "loaded": loaded or "unknown",
        "reason": _read(RUN_DIR / "reason"),
        "last_fallback": fallback,
        "last_good": _read(STATE_DIR / "last-good"),
        "state": state,
    }


def build_gfx1013_source_command(action: str, checkout: str | Path, *, script: Path = SCRIPT) -> str:
    """One closed shell workflow per action, for the embedded terminal.

    Building runs as the user; only installing, switching and removing use
    sudo, and those steps copy the reviewed script to a root-owned temporary
    file first so the privileged part never executes a user-writable file.
    """
    action = str(action or "").strip().lower()
    if action not in ACTIONS:
        raise ValueError(f"Unsupported GFX1013 source-build action: {action or '--'}")
    checkout = Path(checkout)
    quoted_script = shlex.quote(str(script))
    quoted_checkout = shlex.quote(str(checkout))
    root_copy = (
        'bc250_root_script="$(sudo mktemp /run/bc250cc-gfx1013-source.XXXXXX)"\n'
        f'sudo install -m 0755 {quoted_script} "$bc250_root_script"\n'
        "trap 'kill \"${bc250_sudo_keepalive:-}\" 2>/dev/null || true; "
        "sudo rm -f -- \"$bc250_root_script\"' EXIT"
    )
    # The build takes 15-30 minutes and sudo forgets the password long before
    # it ends: the install at the end then asked again and timed out while the
    # user was away. Ask once at the start and keep it fresh until the end.
    keep_sudo = "\n".join((
        'echo "[INFO] Your password is asked once now; the install at the end reuses it."',
        "sudo -v",
        "( while sleep 50; do sudo -n -v 2>/dev/null || exit 0; done ) &",
        "bc250_sudo_keepalive=$!",
        "trap 'kill \"$bc250_sudo_keepalive\" 2>/dev/null || true' EXIT",
    ))
    header = "\n".join((
        "set -Eeuo pipefail",
        'echo; echo "=========================================================================="',
        'echo "  BC-250 GFX1013 compute-queue fix · built for this kernel"',
        'echo "  DryhoppedIPA V33 kernel patches + RADV compute-queue patch"',
        'echo "=========================================================================="; echo',
        f"test -x {quoted_script} || test -f {quoted_script} || {{ echo 'ERROR: the GFX1013 build script is missing; reinstall Control Center.'; exit 29; }}",
    ))
    if action == "status":
        return f"{header}\nbash {quoted_script} status"
    if action in {"enable", "disable", "uninstall"}:
        return f'{header}\n{root_copy}\nsudo bash "$bc250_root_script" {action}'
    checkout_step = clone_or_update_commit(GFX1013_UPSTREAM, checkout, GFX1013_REVIEWED_COMMIT)
    verify = (
        f"test \"$(git -C {quoted_checkout} rev-parse HEAD)\" = {GFX1013_REVIEWED_COMMIT} || "
        "{ echo 'ERROR: the reviewed upstream revision was not checked out.'; exit 29; }"
    )
    stage = '"${XDG_CACHE_HOME:-$HOME/.cache}/bc250-control-center/gfx1013/stage"'
    if action == "install":
        steps = (
            f"bash {quoted_script} deps",
            f"bash {quoted_script} build --source {quoted_checkout} --stage {stage}",
        )
    else:  # rebuild: only the module follows a kernel update
        steps = (f"bash {quoted_script} build --kernel-only --source {quoted_checkout} --stage {stage}",)
    return "\n".join((
        header,
        'echo "[INFO] Building takes 15-30 minutes on a BC-250. Nothing is installed until both halves built."',
        keep_sudo,
        checkout_step,
        verify,
        *steps,
        root_copy,
        f'sudo bash "$bc250_root_script" install --stage {stage}',
    ))
