"""Remote access: is the SSH server up, and at which address is this board.

Reading is free. Switching it on is one systemd action behind the polkit
password, the same ``systemctl enable --now`` anyone would type; the unit is
``sshd`` on Fedora, Arch and Bazzite and ``ssh`` on Debian and Ubuntu.
"""

from __future__ import annotations

import getpass
import re
import shutil
import subprocess
from pathlib import Path

from bc250cc.infrastructure.polkit_session import normalize_polkit_error, pkexec_argv

UNITS = ("sshd.service", "ssh.service")
#: Virtual links of containers and VMs: nobody connects to those from a phone.
_VIRTUAL_LINKS = ("lo", "docker", "podman", "veth", "virbr", "br-", "cni", "flannel", "tailscale")
_PORT = re.compile(r"(?im)^\s*Port\s+(\d{1,5})\s*$")


def _systemctl(*arguments: str) -> str:
    try:
        done = subprocess.run(
            ["systemctl", *arguments], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout


def _unit() -> str:
    """The installed SSH server unit, or '' when there is none."""
    for unit in UNITS:
        if "LoadState=loaded" in _systemctl("show", "-p", "LoadState", unit):
            return unit
    return ""


def _port() -> int:
    for path in (*sorted(Path("/etc/ssh/sshd_config.d").glob("*.conf")), Path("/etc/ssh/sshd_config")):
        try:
            found = _PORT.search(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if found:
            return int(found.group(1))
    return 22


def addresses() -> list[str]:
    """IPv4 addresses of the real network links, the ones a phone can reach."""
    try:
        listing = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            capture_output=True, text=True, timeout=4, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in listing.splitlines():
        fields = line.split()
        if len(fields) > 3 and not fields[1].startswith(_VIRTUAL_LINKS):
            found.append(fields[3].split("/", 1)[0])
    return found


def status() -> dict:
    """What the page shows: unit, installed, active, enabled at boot, port, user, addresses."""
    unit = _unit()
    states = dict(
        line.split("=", 1)
        for line in _systemctl("show", "-p", "ActiveState,UnitFileState", unit).splitlines()
        if "=" in line
    ) if unit else {}
    return {
        "systemd": Path("/run/systemd/system").exists() and bool(shutil.which("systemctl")),
        "unit": unit,
        "active": states.get("ActiveState") == "active",
        "enabled": states.get("UnitFileState") in {"enabled", "enabled-runtime", "static"},
        "port": _port(),
        "user": getpass.getuser(),
        "addresses": addresses(),
    }


def set_enabled(enable: bool) -> None:
    """Start the SSH server now and at every boot (or stop it and forget it)."""
    unit = _unit()
    if not unit:
        raise RuntimeError("The SSH server is not installed.")
    command = pkexec_argv(
        "pkexec", shutil.which("systemctl") or "/usr/bin/systemctl",
        "enable" if enable else "disable", "--now", unit,
    )
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    except FileNotFoundError as error:
        raise RuntimeError("pkexec is not available on this system.") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("The privileged SSH operation timed out.") from error
    if done.returncode != 0:
        raise RuntimeError(normalize_polkit_error(command, done.stderr).strip() or "The SSH service was not changed.")
