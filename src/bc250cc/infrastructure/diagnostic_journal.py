"""Every error Control Center explained to the owner, with when and why.

A diagnostic code used to exist only in the window or terminal that showed
it: once closed, a problem report had to be written from memory. Each one is
now appended here (window errors and failed terminal workflows alike), and
Settings › Diagnostics lists them for the report.

Texts are stored as the English catalogue keys, so the history follows the
interface language. The file is small and bounded, and writing to it never
raises: losing a history line must never break the action that failed.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

JOURNAL_NAME = "diagnostics.jsonl"
MAX_ENTRIES = 300
#: Detail kept per entry; the terminal log keeps the rest.
MAX_DETAIL = 1500
#: The end of a traceback is where it failed; the start is kept out.
MAX_RAW = 4000
#: The same error shown twice this close together is one event.
DUPLICATE_WINDOW_S = 5.0


@dataclass(frozen=True)
class DiagnosticEntry:
    #: Seconds since the epoch.
    at: float
    code: str
    #: "window" or "terminal".
    source: str
    #: What the owner was doing: the dialog or workflow title.
    title: str
    summary: str
    cause: str
    action: str
    detail: str = ""
    #: The screen action that showed it: "GPU-0142 · gpu_governor.py:812 · Page.run".
    origin: str = ""
    #: The function of ours that raised, in the same form.
    raised: str = ""
    #: The exception as Python printed it, bounded.
    raw: str = ""


def journal_path(env: dict | None = None) -> Path:
    env = os.environ if env is None else env
    state = str(env.get("XDG_STATE_HOME") or "").strip()
    root = Path(state) if state else Path.home() / ".local" / "state"
    return root / "bc250-control-center" / JOURNAL_NAME


def read(limit: int = MAX_ENTRIES, path: Path | None = None) -> list[DiagnosticEntry]:
    """The newest ``limit`` entries, newest first."""
    path = path or journal_path()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    entries: list[DiagnosticEntry] = []
    for line in reversed(lines):
        try:
            data = json.loads(line)
            entries.append(DiagnosticEntry(
                at=float(data["at"]),
                code=str(data["code"]),
                source=str(data.get("source") or "window"),
                title=str(data.get("title") or ""),
                summary=str(data.get("summary") or ""),
                cause=str(data.get("cause") or ""),
                action=str(data.get("action") or ""),
                detail=str(data.get("detail") or ""),
                origin=str(data.get("origin") or ""),
                raised=str(data.get("raised") or ""),
                raw=str(data.get("raw") or ""),
            ))
        except (ValueError, KeyError, TypeError):
            continue
        if len(entries) >= limit:
            break
    return entries


def record(
    *,
    code: str,
    source: str,
    title: str,
    summary: str,
    cause: str,
    action: str,
    detail: str = "",
    origin: str = "",
    raised: str = "",
    raw: str = "",
    path: Path | None = None,
    now: float | None = None,
) -> DiagnosticEntry | None:
    """Append one entry; ``None`` when it was a repeat or could not be saved."""
    path = path or journal_path()
    entry = DiagnosticEntry(
        at=time.time() if now is None else now,
        code=str(code),
        source=str(source),
        title=str(title)[:200],
        summary=str(summary),
        cause=str(cause),
        action=str(action),
        detail=str(detail)[:MAX_DETAIL],
        origin=str(origin)[:300],
        raised=str(raised)[:300],
        raw=str(raw)[-MAX_RAW:],
    )
    latest = read(1, path)
    if latest and (
        latest[0].code == entry.code
        and latest[0].detail == entry.detail
        and abs(entry.at - latest[0].at) < DUPLICATE_WINDOW_S
    ):
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        _trim(path)
    except OSError:
        logger.debug("Could not record diagnostic %s", entry.code, exc_info=True)
        return None
    return entry


def _trim(path: Path) -> None:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    # Rewritten only once it is well past the cap, not on every entry.
    if len(lines) <= MAX_ENTRIES + MAX_ENTRIES // 5:
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_text("\n".join(lines[-MAX_ENTRIES:]) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def clear(path: Path | None = None) -> None:
    try:
        (path or journal_path()).unlink(missing_ok=True)
    except OSError:
        logger.debug("Could not clear the diagnostic history", exc_info=True)
