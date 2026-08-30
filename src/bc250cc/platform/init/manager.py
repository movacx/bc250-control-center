"""Init-system detection based on runtime markers and executable support."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path


class InitSystem(StrEnum):
    SYSTEMD = "systemd"
    OPENRC = "openrc"
    UNKNOWN = "unknown"


def detect_init_system(run_root: Path = Path("/run")) -> InitSystem:
    if (run_root / "openrc" / "softlevel").exists():
        return InitSystem.OPENRC
    if (run_root / "systemd" / "system").exists():
        return InitSystem.SYSTEMD
    return InitSystem.UNKNOWN
