"""What was tried to unlock the CPU cores from here, for a problem report.

A core unlock restarts the computer, so its terminal is gone when the owner
asks why it did not work (R-643035c1): the mask the board reported, the one
that was chosen and how it ended are kept, the last few only.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from bc250cc.shared.paths import state_root

KEPT = 12
_ACCEPT = re.compile(r"--accept-mask[= ]+(0x[0-9A-Fa-f]{1,2})\b")
#: The helper's own switch, always its last argument (a shell step before it
#: may say ``rm -f``).
_FORCE = re.compile(r"\-\-ignore\-core\-mask['\"]?\s*$")


def attempts_path() -> Path:
    return state_root() / "bc250-control-center" / "core-unlock-attempts.jsonl"


def chosen_mask(command) -> str:
    """The mask check a command asks for, in words a report can carry."""
    text = " ".join(str(part) for part in command or ())
    accepted = _ACCEPT.search(text)
    if accepted:
        return f"only 0x{int(accepted[1], 16):02X}"
    return "any (check skipped)" if _FORCE.search(text) else "standard 0x77"


def record_attempt(operation: str, *, chosen: str = "", reported: int | None = None, result: str = "") -> None:
    """Add one line. Never raises: a full disk must not stop the unlock."""
    entry = {
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "operation": str(operation)[:80], "chosen": chosen,
        "reported": "" if reported is None else f"0x{reported:02X}", "result": str(result)[:80],
    }
    path = attempts_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        lines = [*lines, json.dumps(entry)][-KEPT:]
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".tmp")
        partial.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(partial, path)
    except (OSError, UnicodeError):
        pass


def recent_attempts() -> list[str]:
    """The kept attempts, one readable line each, newest last."""
    try:
        lines = attempts_path().read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    rows = []
    for line in lines[-KEPT:]:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            rows.append(" · ".join(filter(None, (
                str(entry.get("at", "")), str(entry.get("operation", "")),
                f"mask chosen: {entry['chosen']}" if entry.get("chosen") else "",
                f"mask read: {entry['reported']}" if entry.get("reported") else "",
                str(entry.get("result", "")),
            ))))
    return rows
