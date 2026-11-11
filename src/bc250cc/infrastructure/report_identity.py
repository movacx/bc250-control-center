"""Local provenance included with optional report diagnostics."""

import os
import re
import secrets
import subprocess
import tempfile
from pathlib import Path

from bc250cc.infrastructure.install_source import detect_install_source
from bc250cc.shared.paths import state_root


def _installation_id() -> str:
    path = state_root() / "bc250-control-center" / "report-installation-id"
    try:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, mode="w") as temp:
                temp.write(secrets.token_hex(16))
                temp.flush()
                try:
                    os.link(temp.name, path)
                except FileExistsError:
                    pass
        value = path.read_text().strip()
        return value if re.fullmatch(r"[0-9a-f]{32}", value) else ""
    except (OSError, UnicodeError):
        return ""


def report_identity() -> dict[str, object]:
    root = next((p for p in Path(__file__).resolve().parents if (p / "VERSION").is_file()), None)
    revision = ""
    channel = detect_install_source().channel.value
    if channel == "release":
        channel = "source-or-release"
    working_tree = {}
    if root:
        try:
            if (root / ".git").exists():
                channel = "git"
                revision = subprocess.check_output(
                    ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, timeout=2,
                    stderr=subprocess.DEVNULL,
                ).strip()
                status = subprocess.run(
                    ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
                    capture_output=True, text=True, timeout=2,
                )
                if status.returncode == 0:
                    working_tree["modified_checkout"] = bool(status.stdout)
            else:
                revision = (root / "BUILD_REVISION").read_text().strip()
                if channel == "source-or-release":
                    stamp = root / "BUILD_TYPE"
                    if stamp.is_file():
                        origin = stamp.read_text().strip()
                        if origin in {"git", "local", "release"}:
                            channel = origin
                    elif re.fullmatch(r"[0-9a-f]{40,64}", revision):
                        channel = "release"
        except (OSError, UnicodeError, subprocess.SubprocessError):
            pass
    container = ""
    if Path("/.flatpak-info").exists():
        container = "flatpak"
    elif os.environ.get("CONTAINER_ID") and os.environ.get("DISTROBOX_ENTER_PATH"):
        container = "distrobox"
    elif Path("/run/.toolboxenv").exists():
        container = "toolbx"
    elif Path("/run/.containerenv").exists() or Path("/.dockerenv").exists():
        container = "container"
    return {
        **working_tree,
        "installation_id": _installation_id(),
        "build_type": channel,
        "commit": revision if re.fullmatch(r"[a-f0-9]{7,64}", revision) else "",
        "container": container,
    }
