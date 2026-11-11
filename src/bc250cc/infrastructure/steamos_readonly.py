"""SteamOS' read-only root, shown and switched on request.

SteamOS mounts its root filesystem read-only so an OS update can replace it
whole. Installing packages (the application's own, its dependencies, drivers)
needs it writable, which is ``steamos-readonly disable``. Workflows that need
it already unlock and restore it themselves; this is the explicit switch a
person asked for, the SteamOS counterpart of Bazzite's ``mitigations=off``
card.

Nothing here runs as root. The probe reads ``steamos-readonly status`` as the
desktop user, and the command is a closed terminal workflow.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Callable

_ACTIONS = frozenset({"disable", "enable", "status", "free-var"})

# Before the first sudo on SteamOS: the deck account has no password until the
# owner sets one, and sudo then fails every prompt without saying why. An
# account that sudo already trusts without a password passes straight through.
STEAMOS_PASSWORD_GUARD = r"""bc250_require_password() {
  sudo -n true 2>/dev/null && return 0
  bc250_account="$(id -un 2>/dev/null || true)"
  case "$(passwd -S "$bc250_account" 2>/dev/null | awk '{print $2}')" in
    NP|L|LK|NL)
      echo "ERROR: The $bc250_account account has no password yet, so sudo cannot authorize this change."
      echo "Set one first: open Konsole in Desktop Mode, run passwd, then try again."
      exit 77 ;;
  esac
}"""


# SteamOS' /var is a small partition (about 230 MB) that also backs the overlay of
# /etc. When it fills up, pacman dies half way and blames "/etc too full". This
# stops before anything is written, names what takes the room, gives the command
# that frees each part, and says how much the work needs. Package downloads go
# to a temporary cache (STEAMOS_PACMAN_INSTALL), so the work itself needs little.
# ``bc250_require_var_space MEGABYTES`` is the call.
STEAMOS_VAR_SPACE_GUARD = r"""bc250_require_var_space() {
  bc250_need="${1:-40}"
  bc250_free="$(df -Pm /var 2>/dev/null | awk 'NR==2 {print $4}')"
  case "$bc250_free" in ''|*[!0-9]*) return 0 ;; esac
  if [ "$bc250_free" -lt "$bc250_need" ]; then
    echo "ERROR: /var has only ${bc250_free} MB free and this needs about ${bc250_need} MB."
    echo "SteamOS keeps /var small, and a full /var breaks package installs half way. What takes the room:"
    du -xh --max-depth=2 /var 2>/dev/null | sort -rh | head -6
    echo "To free space:"
    echo "  sudo pacman -Scc                     # downloaded packages; answer y"
    echo "  sudo rm -rf /var/cache/fwupd/*       # firmware metadata; fwupd downloads it again"
    echo "  sudo journalctl --vacuum-size=20M    # system logs"
    echo "/var/lib/umr is UMR, which Compute Units tools use; keep it."
    echo "Control Center does the same with Free /var space, under SteamOS read-only mode in Preparation. Then try again."
    exit 75
  fi
  if [ "$bc250_free" -lt 250 ]; then
    echo "[WARN] /var has only ${bc250_free} MB free; it works now, but keep an eye on it."
  fi
}"""

# Signed SteamOS packages, the way every workflow that needs one does it: the
# read-only protection is lifted for the install and put back whatever happens
# (an interrupted run included); the keyring is initialised, because an update
# resets it. ``bc250_pacman_install PACKAGE...`` is the call; it runs in a
# subshell so its traps do not replace the caller's.
STEAMOS_PACMAN_INSTALL = r"""bc250_pacman_install() (
  bc250_readonly_was=0
  bc250_restore_readonly() {
    bc250_rc=${1:-$?}
    trap - EXIT INT TERM HUP
    if [ "$bc250_readonly_was" -eq 1 ]; then sudo steamos-readonly enable || bc250_rc=1; fi
    exit "$bc250_rc"
  }
  trap bc250_restore_readonly EXIT
  trap 'bc250_restore_readonly 130' INT
  trap 'bc250_restore_readonly 143' TERM
  trap 'bc250_restore_readonly 129' HUP
  for bc250_tool in steamos-readonly pacman pacman-key; do
    command -v "$bc250_tool" >/dev/null 2>&1 || { echo "ERROR: $bc250_tool is required to install signed SteamOS packages."; exit 69; }
  done
  if steamos-readonly status 2>/dev/null | grep -qi enabled; then
    sudo steamos-readonly disable
    bc250_readonly_was=1
  fi
  sudo pacman-key --init
  sudo pacman-key --populate archlinux holo 2>/dev/null || sudo pacman-key --populate
  # Downloads go to a temporary cache, not SteamOS' small /var.
  bc250_cache="$(mktemp -d "${TMPDIR:-/tmp}/bc250-pacman-cache.XXXXXX")" || exit 73
  bc250_pacman_status=0
  sudo pacman --cachedir "$bc250_cache" -S "$@" || { echo "[INFO] Refreshing the package databases (a SteamOS update resets them) and trying once more."; sudo pacman -Syy --noconfirm && sudo pacman --cachedir "$bc250_cache" -S "$@"; } || bc250_pacman_status=$?
  sudo rm -rf -- "$bc250_cache" 2>/dev/null || rm -rf -- "$bc250_cache" 2>/dev/null || true
  exit "$bc250_pacman_status"
)"""


def _state_from(output: str) -> str:
    text = str(output or "")
    if re.search(r"(^|[^A-Za-z])disabled([^A-Za-z]|$)", text, re.IGNORECASE):
        return "disabled"
    if re.search(r"(^|[^A-Za-z])enabled([^A-Za-z]|$)", text, re.IGNORECASE):
        return "enabled"
    return "unknown"


def _var_free_mb(statvfs: Callable[[str], os.statvfs_result]) -> int | None:
    try:
        stats = statvfs("/var")
    except OSError:
        return None
    return int(stats.f_bavail * stats.f_frsize // (1024 * 1024))


def probe_steamos_readonly(
    *,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    statvfs: Callable[[str], os.statvfs_result] = os.statvfs,
) -> dict[str, object]:
    """``enabled`` (protected), ``disabled`` (writable) or ``unknown``, and the
    free space on SteamOS' small /var (``var_free_mb``, None when unreadable)."""
    if not which("steamos-readonly"):
        return {"available": False, "state": "unavailable"}
    var_free_mb = _var_free_mb(statvfs)
    try:
        result = runner(
            ("steamos-readonly", "status"),
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
            env={**os.environ, "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        return {"available": True, "state": "unknown", "var_free_mb": var_free_mb}
    return {
        "available": True,
        "state": _state_from(f"{result.stdout}\n{result.stderr}"),
        "var_free_mb": var_free_mb,
    }


def build_steamos_readonly_command(action: str) -> str:
    """A closed workflow around ``steamos-readonly``; it never reboots."""
    action = str(action or "").strip().lower()
    if action not in _ACTIONS:
        raise ValueError("Unsupported SteamOS read-only action.")
    commands = [
        "set -u",
        'command -v steamos-readonly >/dev/null 2>&1 || { echo "ERROR: steamos-readonly was not found; this workflow is for SteamOS."; exit 64; }',
    ]
    if action == "status":
        commands.append("steamos-readonly status")
        return "\n".join(commands)
    commands.append(STEAMOS_PASSWORD_GUARD)
    commands.append("bc250_require_password")
    if action == "free-var":
        # Caches only: pacman's downloads, fwupd's metadata (it downloads it
        # again) and the journal beyond 20 MB. UMR's data in /var/lib/umr is
        # what Compute Units tools use and is left alone. The read-only switch
        # is not touched: /var is writable either way.
        commands.extend((
            'echo "Before:"; df -h /var',
            "sudo find /var/cache/pacman/pkg -mindepth 1 -delete 2>/dev/null || true",
            "sudo find /var/cache/fwupd -mindepth 1 -delete 2>/dev/null || true",
            "sudo journalctl --vacuum-size=20M || true",
            'echo "After:"; df -h /var',
            'echo "OK: /var caches were cleared. /var/lib/umr is UMR, which Compute Units tools use, and was kept."',
        ))
        return "\n".join(commands)
    if action == "disable":
        commands.extend((
            "sudo steamos-readonly disable || exit $?",
            "steamos-readonly status",
            'echo "OK: the SteamOS root filesystem is writable. A SteamOS update turns the protection back on and replaces what was installed into it."',
        ))
    else:
        commands.extend((
            "sudo steamos-readonly enable || exit $?",
            "steamos-readonly status",
            'echo "OK: SteamOS read-only protection is on again."',
        ))
    return "\n".join(commands)
