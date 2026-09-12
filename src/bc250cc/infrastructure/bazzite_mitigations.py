"""Explicit, reversible Bazzite lifecycle for ``mitigations=off``."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Callable

MITIGATIONS_ARGUMENT = "mitigations=off"
MITIGATIONS_STATE_FILE = Path(
    "/etc/bc250-control-center/mitigations-kargs.original"
)
_ACTIONS = frozenset({"disable", "restore", "status"})


def _tokens(payload: object) -> tuple[str, ...]:
    return tuple(str(payload or "").strip().split())


def probe_bazzite_mitigations(
    *,
    proc_cmdline: Path = Path("/proc/cmdline"),
    state_file: Path = MITIGATIONS_STATE_FILE,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    """Compare the running kernel with the default deployment without mutation."""
    try:
        active = MITIGATIONS_ARGUMENT in _tokens(
            proc_cmdline.read_text(encoding="ascii", errors="replace")
        )
    except OSError:
        active = False
    try:
        result = runner(
            ("rpm-ostree", "kargs"),
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
            env={**os.environ, "LANG": "C", "LC_ALL": "C"},
        )
        configured = bool(
            result.returncode == 0
            and MITIGATIONS_ARGUMENT in _tokens(result.stdout)
        )
        query_available = result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        configured = False
        query_available = False
    try:
        metadata = state_file.lstat()
        managed = bool(
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_uid == 0
            and metadata.st_mode & 0o077 == 0
        )
    except OSError:
        managed = False
    return {
        "available": query_available,
        "active": active,
        "configured": configured,
        "managed": managed,
        "reboot_required": active != configured,
        "state": (
            "reboot-required" if active != configured
            else "disabled" if active
            else "protected"
        ),
    }


def build_bazzite_mitigations_command(action: str) -> str:
    """Return a closed rpm-ostree transaction and never reboot automatically."""
    action = str(action or "").strip().lower()
    if action not in _ACTIONS:
        raise ValueError("Unsupported Bazzite CPU-mitigation action.")
    state = str(MITIGATIONS_STATE_FILE)
    lines = [
        "set -Eeuo pipefail",
        "export LANG=C LC_ALL=C",
        "test \"$(id -u)\" -ne 0 || { echo 'ERROR: run this workflow as the Desktop Mode user, not root'; exit 60; }",
        "grep -Eqi \"^ID=['\\\"]?bazzite['\\\"]?$\" /etc/os-release || { echo 'ERROR: this workflow is available only on Bazzite'; exit 61; }",
        "test -e /run/ostree-booted || { echo 'ERROR: the Bazzite image deployment was not detected'; exit 61; }",
        "command -v rpm-ostree >/dev/null 2>&1 || { echo 'ERROR: rpm-ostree is required on Bazzite'; exit 62; }",
        "echo '== BC250 Bazzite CPU security mitigations =='",
        "bc250_active=0; tr ' ' '\\n' < /proc/cmdline | grep -Fxq 'mitigations=off' && bc250_active=1 || true",
        "mapfile -t bc250_current < <(rpm-ostree kargs | tr ' ' '\\n' | grep -E '^mitigations=' || true)",
        "for bc250_arg in \"${bc250_current[@]}\"; do [[ \"$bc250_arg\" =~ ^mitigations=[A-Za-z0-9,._-]+$ ]] || { echo 'ERROR: malformed existing mitigations argument'; exit 65; }; done",
    ]
    if action == "status":
        lines.extend((
            "bc250_configured=0; printf '%s\\n' \"${bc250_current[@]}\" | grep -Fxq 'mitigations=off' && bc250_configured=1 || true",
            "echo \"Running kernel: $([ \"$bc250_active\" = 1 ] && echo disabled || echo protected)\"",
            "echo \"Next boot: $([ \"$bc250_configured\" = 1 ] && echo disabled || echo protected)\"",
        ))
        return "\n".join(lines)

    lines.append("sudo -v")
    if action == "disable":
        lines.extend((
            "if printf '%s\\n' \"${bc250_current[@]}\" | grep -Fxq 'mitigations=off'; then echo 'OK: mitigations=off is already configured for the next boot.'; exit 0; fi",
            f"bc250_state='{state}'",
            "sudo install -d -m 0755 /etc/bc250-control-center",
            "if sudo test -e \"$bc250_state\"; then",
            "  sudo test ! -L \"$bc250_state\" && sudo test -f \"$bc250_state\" || { echo 'ERROR: unsafe mitigation restoration state'; exit 66; }",
            "  test \"$(sudo stat -c %u \"$bc250_state\")\" -eq 0 && test \"$(sudo stat -c %a \"$bc250_state\")\" = 600 || { echo 'ERROR: unprotected mitigation restoration state'; exit 66; }",
            "  sudo head -n 1 \"$bc250_state\" | grep -Fqx '# Managed by BC250 Control Center' || { echo 'ERROR: foreign mitigation restoration state'; exit 66; }",
            "else",
            "  { printf '%s\\n' '# Managed by BC250 Control Center' \"${bc250_current[@]}\"; } | sudo tee \"$bc250_state\" >/dev/null",
            "  sudo chmod 0600 \"$bc250_state\"",
            "fi",
            "bc250_args=()",
            "for bc250_arg in \"${bc250_current[@]}\"; do bc250_args+=(\"--delete-if-present=$bc250_arg\"); done",
            "bc250_args+=(\"--append-if-missing=mitigations=off\")",
            "sudo rpm-ostree kargs \"${bc250_args[@]}\"",
            "rpm-ostree kargs | tr ' ' '\\n' | grep -Fxq 'mitigations=off' || { echo 'ERROR: mitigations=off was not staged'; exit 74; }",
            "echo 'OK: CPU security mitigations will be disabled after reboot.'",
        ))
    else:
        lines.extend((
            f"bc250_state='{state}'",
            "sudo test ! -L \"$bc250_state\" && sudo test -f \"$bc250_state\" || { echo 'ERROR: no BC250-owned mitigation state is available to restore'; exit 66; }",
            "test \"$(sudo stat -c %u \"$bc250_state\")\" -eq 0 && test \"$(sudo stat -c %a \"$bc250_state\")\" = 600 || { echo 'ERROR: unprotected mitigation restoration state'; exit 66; }",
            "sudo head -n 1 \"$bc250_state\" | grep -Fqx '# Managed by BC250 Control Center' || { echo 'ERROR: foreign mitigation restoration state'; exit 66; }",
            "mapfile -t bc250_original < <(sudo tail -n +2 \"$bc250_state\")",
            "for bc250_arg in \"${bc250_original[@]}\"; do [[ \"$bc250_arg\" =~ ^mitigations=[A-Za-z0-9,._-]+$ ]] || { echo 'ERROR: invalid saved mitigations argument'; exit 66; }; done",
            "bc250_args=()",
            "for bc250_arg in \"${bc250_current[@]}\"; do bc250_args+=(\"--delete-if-present=$bc250_arg\"); done",
            "for bc250_arg in \"${bc250_original[@]}\"; do bc250_args+=(\"--append-if-missing=$bc250_arg\"); done",
            "if ((${#bc250_args[@]})); then sudo rpm-ostree kargs \"${bc250_args[@]}\"; fi",
            "mapfile -t bc250_staged < <(rpm-ostree kargs | tr ' ' '\\n' | grep -E '^mitigations=' || true)",
            "((${#bc250_staged[@]} == ${#bc250_original[@]})) || { echo 'ERROR: the previous mitigation policy was not restored exactly'; exit 74; }",
            "for bc250_arg in \"${bc250_original[@]}\"; do printf '%s\\n' \"${bc250_staged[@]}\" | grep -Fxq -- \"$bc250_arg\" || { echo 'ERROR: the previous mitigation policy was not restored exactly'; exit 74; }; done",
            "sudo unlink \"$bc250_state\"",
            "echo 'OK: the previous CPU mitigation policy will return after reboot.'",
        ))
    lines.append("echo 'No automatic reboot was performed.'")
    return "\n".join(lines)
