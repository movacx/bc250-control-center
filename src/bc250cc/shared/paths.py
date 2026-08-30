"""Path policy shared by application code; no probing on import."""

from __future__ import annotations

import os
from pathlib import Path


def state_root() -> Path:
    configured = os.environ.get("XDG_STATE_HOME", "").strip()
    return Path(configured) if configured else Path.home() / ".local" / "state"
