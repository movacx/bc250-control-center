"""Put every diagnostic the owner is shown into the diagnostic journal.

Two places show one: a red dialog (and the few pages that render their own
diagnosis) and a terminal workflow that failed, whose wrapper prints the code.
Both land in ``diagnostic_journal`` with the time, what was being done and the
probable cause, for Settings › Diagnostics. Recording never raises.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from bc250cc.infrastructure import diagnostic_journal

from .error_diagnostics import ErrorDiagnosis, diagnose_error, explain_code

logger = logging.getLogger(__name__)

CODE_PATTERN = re.compile(r"\bBC250-[A-Z0-9]+-\d{3}\b")
#: Enough of a terminal log to hold the explanation block and what led to it.
LOG_TAIL_BYTES = 64 * 1024
LOG_DETAIL_LINES = 25


def current_wording(entry) -> ErrorDiagnosis:
    """The explanation a code has today, so older entries follow text fixes.

    The stored words are the fallback, for a code this version no longer has.
    """
    return explain_code(entry.code) or ErrorDiagnosis(entry.code, entry.summary, entry.cause, entry.action)


def record_diagnosis(diagnosis: ErrorDiagnosis, *, source: str, title: str, detail: str = "") -> None:
    try:
        diagnostic_journal.record(
            code=diagnosis.code,
            source=source,
            title=title,
            summary=diagnosis.summary,
            cause=diagnosis.cause,
            action=diagnosis.action,
            detail=detail,
        )
    except Exception:  # noqa: BLE001 - history must never break the failing action
        logger.debug("Could not record diagnostic %s", diagnosis.code, exc_info=True)


def record_window_error(message: object, *, context: str, title: str) -> None:
    """A red dialog: the same diagnosis it renders, from the same text."""
    detail = str(message or "").strip()
    codes = CODE_PATTERN.findall(detail)
    # A message that already carries its explanation names its own code.
    diagnosis = explain_code(codes[-1]) if codes else None
    if diagnosis is None:
        diagnosis = diagnose_error(detail, context=context)
    record_diagnosis(diagnosis, source="window", title=title, detail=detail)


def record_terminal_failure(result: object, exit_code: int) -> None:
    """A workflow that ended badly and printed a diagnostic code.

    A workflow closed by hand prints none and is not recorded: stopping one
    is a choice, not a fault.
    """
    if not exit_code:
        return
    log_file = str(getattr(result, "log_file", "") or "")
    try:
        with open(log_file, "rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - LOG_TAIL_BYTES))
            text = handle.read().decode("utf-8", "replace")
    except OSError:
        return
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text).replace("\r", "\n")
    codes = CODE_PATTERN.findall(text)
    if not codes:
        return
    diagnosis = explain_code(codes[-1])
    if diagnosis is None:
        return
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    detail = "\n".join(lines[-LOG_DETAIL_LINES:])
    if log_file:
        detail += f"\n\nLog: {log_file}"
    record_diagnosis(
        diagnosis,
        source="terminal",
        title=str(getattr(result, "title", "") or "Terminal"),
        detail=detail,
    )


#: Written by the Decky Quick Access backend (root) beside its settings; read
#: here only.  See ``Plugin._record_diagnostic`` in the plugin's main.py.
DECKY_DIAGNOSTICS = Path.home() / "homebrew" / "settings" / "bc250-quick-access" / "diagnostics.jsonl"
#: The Decky file is root-owned, so "Clear" cannot delete it: entries older
#: than this mark are hidden instead.
DECKY_CLEARED_MARK = "decky-diagnostics-cleared-at"
DECKY_MODULES = {
    "gpu": "GPU", "cu": "Compute Units", "cpu": "CPU", "fan": "Fan", "vram": "VRAM",
}


def _decky_cleared_path() -> Path:
    return diagnostic_journal.journal_path().with_name(DECKY_CLEARED_MARK)


def _decky_cleared_at() -> float:
    try:
        return float(_decky_cleared_path().read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return 0.0


def read_decky_entries(path: Path | None = None, *, cleared_at: float | None = None) -> list:
    """Decky Quick Access failures as journal entries, newest first.

    Each is classified with the same rules as a desktop error, so a Game Mode
    failure gets the same code, cause and fix as the desktop would show.
    """
    path = path or DECKY_DIAGNOSTICS
    cleared_at = _decky_cleared_at() if cleared_at is None else cleared_at
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    entries = []
    for line in reversed(lines[-diagnostic_journal.MAX_ENTRIES:]):
        try:
            data = json.loads(line)
            at = float(data["at"])
            module = str(data.get("module") or "")
            target = str(data.get("target") or "")
            detail = str(data.get("error") or "").strip()[: diagnostic_journal.MAX_DETAIL]
        except (ValueError, KeyError, TypeError):
            continue
        if at <= cleared_at:
            continue
        codes = CODE_PATTERN.findall(detail)
        diagnosis = (explain_code(codes[-1]) if codes else None) or diagnose_error(detail, context=module)
        entries.append(diagnostic_journal.DiagnosticEntry(
            at=at,
            code=diagnosis.code,
            source="decky",
            title=f"Decky Quick Access · {DECKY_MODULES.get(module, module)} · {target}",
            summary=diagnosis.summary,
            cause=diagnosis.cause,
            action=diagnosis.action,
            detail=detail,
        ))
    return entries


def history_entries(limit: int = diagnostic_journal.MAX_ENTRIES) -> list:
    """Desktop and Decky Quick Access errors together, newest first."""
    merged = diagnostic_journal.read(limit) + read_decky_entries()
    return sorted(merged, key=lambda entry: entry.at, reverse=True)[:limit]


def clear_history() -> None:
    diagnostic_journal.clear()
    try:
        mark = _decky_cleared_path()
        mark.parent.mkdir(parents=True, exist_ok=True)
        mark.write_text(f"{time.time():.3f}\n", encoding="ascii")
    except OSError:
        logger.debug("Could not hide the Decky diagnostic history", exc_info=True)


#: Errors a copied report carries; the newest are the ones asked about.
REPORT_ENTRIES = 15


def diagnostic_report(system_rows, entries, *, now: float | None = None) -> str:
    """Plain text for a problem report: the system sheet, then recent errors.

    Always English, whatever the interface language, so the maintainer reads
    the same words and codes from every reporter.
    """
    stamp = datetime.fromtimestamp(time.time() if now is None else now).strftime("%Y-%m-%d %H:%M")
    width = max((len(label) for label, _value in system_rows), default=0)
    lines = [f"BC250 Control Center diagnostic report ({stamp})", "", "== System =="]
    lines += [f"{label.ljust(width)}  {value}" for label, value in system_rows] or ["(not read yet)"]
    lines += ["", f"== Recent errors ({min(len(entries), REPORT_ENTRIES)} of {len(entries)}) =="]
    if not entries:
        lines.append("None recorded.")
    for entry in list(entries)[:REPORT_ENTRIES]:
        when = datetime.fromtimestamp(entry.at).strftime("%Y-%m-%d %H:%M:%S")
        lines += [
            "",
            f"{when} · {entry.code} · {entry.source} · {entry.title}",
            f"  What happened: {current_wording(entry).summary}",
            f"  Likely cause: {current_wording(entry).cause}",
        ]
        if entry.detail:
            detail = entry.detail if len(entry.detail) <= 600 else entry.detail[:597] + "..."
            lines += ["  Detail:"] + [f"    {line}" for line in detail.splitlines()]
    return "\n".join(lines) + "\n"
