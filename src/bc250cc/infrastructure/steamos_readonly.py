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

_ACTIONS = frozenset({"disable", "enable", "status"})

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
# stops before anything is written, names what takes the room, and says how much
# the work needs. ``bc250_require_var_space MEGABYTES`` is the call.
STEAMOS_VAR_SPACE_GUARD = r"""bc250_require_var_space() {
  bc250_need="${1:-100}"
  bc250_free="$(df -Pm /var 2>/dev/null | awk 'NR==2 {print $4}')"
  case "$bc250_free" in ''|*[!0-9]*) return 0 ;; esac
  if [ "$bc250_free" -lt "$bc250_need" ]; then
    echo "ERROR: /var has only ${bc250_free} MB free and this needs about ${bc250_need} MB."
    echo "SteamOS keeps /var small, and a full /var breaks package installs half way. What takes the room:"
    du -xh --max-depth=2 /var 2>/dev/null | sort -rh | head -6
    echo "Free some space (journalctl --vacuum-size=50M, pacman -Sc) and try again."
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
  sudo pacman -S "$@" || { echo "[INFO] Refreshing the package databases (a SteamOS update resets them) and trying once more."; sudo pacman -Syy --noconfirm && sudo pacman -S "$@"; }
)"""


def _state_from(output: str) -> str:
    text = str(output or "")
    if re.search(r"(^|[^A-Za-z])disabled([^A-Za-z]|$)", text, re.IGNORECASE):
        return "disabled"
    if re.search(r"(^|[^A-Za-z])enabled([^A-Za-z]|$)", text, re.IGNORECASE):
        return "enabled"
    return "unknown"


def probe_steamos_readonly(
    *,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    """``enabled`` (protected), ``disabled`` (writable) or ``unknown``."""
    if not which("steamos-readonly"):
        return {"available": False, "state": "unavailable"}
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
        return {"available": True, "state": "unknown"}
    return {"available": True, "state": _state_from(f"{result.stdout}\n{result.stderr}")}


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
