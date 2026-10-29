"""One reversible rpm-ostree kernel-argument lifecycle for Bazzite, per argument.

``bazzite_boot_messages`` (``loglevel=0``) and ``bazzite_smt`` (``nosmt``) are
this transaction with a different argument; ``bazzite_mitigations`` has the
same shape and is older. The transaction never reboots on its own, saves the
arguments the image had before the first change in a root-owned file, and
puts exactly those back on restore.
"""

from __future__ import annotations

import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

STATE_MARKER = "# Managed by BC250 Control Center"


@dataclass(frozen=True)
class KargSpec:
    #: The argument this lifecycle puts on the command line.
    argument: str
    #: ERE (``grep -E``) for the arguments of the same family, which the image
    #: may already carry in another form and which are taken out first.
    family: str
    #: Bash regex every such argument has to match before it is touched.
    valid: str
    state_file: Path
    #: Words for the messages the workflow prints.
    title: str
    noun: str
    previous: str
    #: The action that puts ``argument`` on the command line.
    enable_action: str
    enabled_label: str
    disabled_label: str
    done_message: str
    restored_message: str

    @property
    def actions(self) -> frozenset[str]:
        return frozenset({self.enable_action, "restore", "status"})


def _tokens(payload: object) -> tuple[str, ...]:
    return tuple(str(payload or "").strip().split())


def probe_karg(
    spec: KargSpec,
    *,
    proc_cmdline: Path = Path("/proc/cmdline"),
    state_file: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    """Compare the running kernel with the default deployment without mutation."""
    state_file = state_file or spec.state_file
    try:
        active = spec.argument in _tokens(
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
        configured = bool(result.returncode == 0 and spec.argument in _tokens(result.stdout))
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
            else spec.enabled_label if active
            else spec.disabled_label
        ),
    }


def build_karg_command(spec: KargSpec, action: str) -> str:
    """Return a closed rpm-ostree transaction and never reboot automatically."""
    action = str(action or "").strip().lower()
    if action not in spec.actions:
        raise ValueError(f"Unsupported Bazzite {spec.noun} action.")
    state = str(spec.state_file)
    argument = spec.argument
    noun = spec.noun
    lines = [
        "set -Eeuo pipefail",
        "export LANG=C LC_ALL=C",
        "test \"$(id -u)\" -ne 0 || { echo 'ERROR: run this workflow as the Desktop Mode user, not root'; exit 60; }",
        "grep -Eqi \"^ID=['\\\"]?bazzite['\\\"]?$\" /etc/os-release || { echo 'ERROR: this workflow is available only on Bazzite'; exit 61; }",
        "test -e /run/ostree-booted || { echo 'ERROR: the Bazzite image deployment was not detected'; exit 61; }",
        "command -v rpm-ostree >/dev/null 2>&1 || { echo 'ERROR: rpm-ostree is required on Bazzite'; exit 62; }",
        f"echo '== {spec.title} =='",
        f"bc250_active=0; tr ' ' '\\n' < /proc/cmdline | grep -Fxq '{argument}' && bc250_active=1 || true",
        f"mapfile -t bc250_current < <(rpm-ostree kargs | tr ' ' '\\n' | grep -E '{spec.family}' || true)",
        f"for bc250_arg in \"${{bc250_current[@]}}\"; do [[ \"$bc250_arg\" =~ {spec.valid} ]] || {{ echo 'ERROR: malformed existing {noun} argument'; exit 65; }}; done",
    ]
    if action == "status":
        lines.extend((
            f"bc250_configured=0; printf '%s\\n' \"${{bc250_current[@]}}\" | grep -Fxq '{argument}' && bc250_configured=1 || true",
            f"echo \"Running kernel: $([ \"$bc250_active\" = 1 ] && echo {spec.enabled_label} || echo {spec.disabled_label})\"",
            f"echo \"Next boot: $([ \"$bc250_configured\" = 1 ] && echo {spec.enabled_label} || echo {spec.disabled_label})\"",
        ))
        return "\n".join(lines)

    lines.append("sudo -v")
    if action == spec.enable_action:
        lines.extend((
            f"if printf '%s\\n' \"${{bc250_current[@]}}\" | grep -Fxq '{argument}'; then echo 'OK: {argument} is already configured for the next boot.'; exit 0; fi",
            f"bc250_state='{state}'",
            "sudo install -d -m 0755 /etc/bc250-control-center",
            "if sudo test -e \"$bc250_state\"; then",
            f"  sudo test ! -L \"$bc250_state\" && sudo test -f \"$bc250_state\" || {{ echo 'ERROR: unsafe {noun} restoration state'; exit 66; }}",
            f"  test \"$(sudo stat -c %u \"$bc250_state\")\" -eq 0 && test \"$(sudo stat -c %a \"$bc250_state\")\" = 600 || {{ echo 'ERROR: unprotected {noun} restoration state'; exit 66; }}",
            f"  sudo head -n 1 \"$bc250_state\" | grep -Fqx '{STATE_MARKER}' || {{ echo 'ERROR: foreign {noun} restoration state'; exit 66; }}",
            "else",
            f"  {{ printf '%s\\n' '{STATE_MARKER}' \"${{bc250_current[@]}}\"; }} | sudo tee \"$bc250_state\" >/dev/null",
            "  sudo chmod 0600 \"$bc250_state\"",
            "fi",
            "bc250_args=()",
            "for bc250_arg in \"${bc250_current[@]}\"; do bc250_args+=(\"--delete-if-present=$bc250_arg\"); done",
            f"bc250_args+=(\"--append-if-missing={argument}\")",
            "sudo rpm-ostree kargs \"${bc250_args[@]}\"",
            f"rpm-ostree kargs | tr ' ' '\\n' | grep -Fxq '{argument}' || {{ echo 'ERROR: {argument} was not staged'; exit 74; }}",
            f"echo 'OK: {spec.done_message}'",
        ))
    else:
        lines.extend((
            f"bc250_state='{state}'",
            f"sudo test ! -L \"$bc250_state\" && sudo test -f \"$bc250_state\" || {{ echo 'ERROR: no BC250-owned {noun} state is available to restore'; exit 66; }}",
            f"test \"$(sudo stat -c %u \"$bc250_state\")\" -eq 0 && test \"$(sudo stat -c %a \"$bc250_state\")\" = 600 || {{ echo 'ERROR: unprotected {noun} restoration state'; exit 66; }}",
            f"sudo head -n 1 \"$bc250_state\" | grep -Fqx '{STATE_MARKER}' || {{ echo 'ERROR: foreign {noun} restoration state'; exit 66; }}",
            "mapfile -t bc250_original < <(sudo tail -n +2 \"$bc250_state\")",
            f"for bc250_arg in \"${{bc250_original[@]}}\"; do [[ \"$bc250_arg\" =~ {spec.valid} ]] || {{ echo 'ERROR: invalid saved {noun} argument'; exit 66; }}; done",
            "bc250_args=()",
            "for bc250_arg in \"${bc250_current[@]}\"; do bc250_args+=(\"--delete-if-present=$bc250_arg\"); done",
            "for bc250_arg in \"${bc250_original[@]}\"; do bc250_args+=(\"--append-if-missing=$bc250_arg\"); done",
            "if ((${#bc250_args[@]})); then sudo rpm-ostree kargs \"${bc250_args[@]}\"; fi",
            f"mapfile -t bc250_staged < <(rpm-ostree kargs | tr ' ' '\\n' | grep -E '{spec.family}' || true)",
            f"((${{#bc250_staged[@]}} == ${{#bc250_original[@]}})) || {{ echo 'ERROR: the {spec.previous} was not restored exactly'; exit 74; }}",
            f"for bc250_arg in \"${{bc250_original[@]}}\"; do printf '%s\\n' \"${{bc250_staged[@]}}\" | grep -Fxq -- \"$bc250_arg\" || {{ echo 'ERROR: the {spec.previous} was not restored exactly'; exit 74; }}; done",
            "sudo unlink \"$bc250_state\"",
            f"echo 'OK: {spec.restored_message}'",
        ))
    lines.append("echo 'No automatic reboot was performed.'")
    return "\n".join(lines)
