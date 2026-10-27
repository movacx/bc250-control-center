"""What the accessory integrations have in common.

Both follow the same rules as the other third-party tools: a pinned release,
its published SHA-256 checked before anything is installed, the work done in
the application's terminal, and state read without privileges.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Iterable
from pathlib import Path

#: Where user units live, as the shell sees it.
UNIT_DIRECTORY = "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
USB_DEVICES = Path("/sys/bus/usb/devices")
QUERY_TIMEOUT_S = 5.0


def command_output(argv: list[str], *, timeout: float = QUERY_TIMEOUT_S) -> str:
    """A bounded, read-only query; ``""`` for anything but a clean answer."""
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _usb_ids(root: Path) -> set[str]:
    found = set()
    try:
        devices = list(root.iterdir())
    except OSError:
        return found
    for device in devices:
        try:
            vendor = (device / "idVendor").read_text(encoding="ascii").strip().lower()
            product = (device / "idProduct").read_text(encoding="ascii").strip().lower()
        except (OSError, UnicodeDecodeError):
            continue
        found.add(f"{vendor}:{product}")
    return found


def present_usb_ids(wanted: Iterable[str], root: Path = USB_DEVICES) -> list[str]:
    """The ``vid:pid`` pairs from ``wanted`` that are plugged in, sorted."""
    return sorted(_usb_ids(root) & {item.lower() for item in wanted})


def present_usb_vendor(vendor: str, root: Path = USB_DEVICES) -> bool:
    return any(item.startswith(f"{vendor.lower()}:") for item in _usb_ids(root))


def user_unit_path(unit: str) -> Path:
    config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config) / "systemd" / "user" / unit


def user_service_state(unit: str) -> str:
    """``missing``, ``disabled``, ``enabled`` or ``active``."""
    if not user_unit_path(unit).is_file():
        return "missing"
    if command_output(["systemctl", "--user", "is-active", unit]) == "active":
        return "active"
    enabled = command_output(["systemctl", "--user", "is-enabled", unit])
    return "enabled" if enabled == "enabled" else "disabled"


def shell_header(title: str) -> list[str]:
    return [
        "set -Eeuo pipefail",
        "export LC_ALL=C LANG=C",
        f"echo {shlex.quote(f'== BC250 Control Center: {title} ==')}",
    ]


def download_and_verify(url: str, asset: str, sha256: str) -> list[str]:
    """Download one release asset into a private folder and prove it.

    Nothing after these lines runs unless the file matches the checksum
    pinned in the source, so a re-cut release under the same tag stops here.
    """
    return [
        "for bc250_command in curl sha256sum; do",
        '  command -v "$bc250_command" >/dev/null 2>&1 || { echo "ERROR: $bc250_command is required. Run Prepare dependencies on the Dashboard, or install it with the package manager."; exit 69; }',
        "done",
        'bc250_stage="$(mktemp -d /tmp/bc250-accessory.XXXXXX)"',
        # apt fetches a local package as its own _apt user: a private folder
        # makes it warn and fall back to root.
        'chmod 755 "$bc250_stage"',
        "trap 'rm -rf -- \"$bc250_stage\"' EXIT",
        f'curl --fail --location --proto "=https" --retry 2 --output "$bc250_stage/{asset}" {shlex.quote(url)}',
        f"printf '%s  %s\\n' {sha256} \"$bc250_stage/{asset}\" | sha256sum --check --status "
        '|| { echo "ERROR: the downloaded file does not match its published SHA-256."; exit 29; }',
    ]
