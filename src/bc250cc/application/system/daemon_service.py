"""The optional user daemon: whether it runs, and the command that turns it on or off."""

from __future__ import annotations

import os
from pathlib import Path

SERVICE = "bc250-control-centerd.service"


def running(runtime: Path | None = None) -> bool:
    """Read from what the user manager leaves on disk while the unit is active; no process is started."""
    base = runtime or Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    return os.path.lexists(base / "systemd/units" / f"invocation:{SERVICE}")


def command(enable: bool) -> str:
    return f"systemctl --user {'enable' if enable else 'disable'} --now {SERVICE}"
