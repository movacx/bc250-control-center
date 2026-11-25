"""Whether the CPU, CU, GPU and fan helpers may run without the password."""
from __future__ import annotations

import getpass
import json
from pathlib import Path

from bc250cc.infrastructure.system_setup import HELPER

STATE = Path("/var/lib/bc250-control-center/system-setup/quick-auth.json")


def enabled() -> bool:
    """The rules are in folders only root can list; the helper leaves this note beside its own state."""
    try:
        return str(json.loads(STATE.read_text(encoding="utf-8")).get("user") or "") == getpass.getuser()
    except (OSError, ValueError, AttributeError, KeyError):
        return False


def available() -> bool:
    try:
        return '"quick-auth-enable"' in HELPER.read_text(encoding="utf-8")
    except OSError:
        return False
