"""Turn a failed process into text a user can act on.

Repositories used to build their failure message as
``err or out or f'exit code {rc}'``. When a helper failed without writing to
stderr, that produced a bare "exit code 43" with no cause, no fix and nothing
to quote to support. This module is the single place that decision is made.
"""

from __future__ import annotations

from . import error_catalog


def describe_failure(
    returncode: object,
    stdout: object = "",
    stderr: object = "",
    *,
    translate=str,
) -> str:
    """Return the clearest available explanation of a failed process.

    Real output from the process is preferred, because it is specific. A code
    identifier is always appended so the same failure is quotable and
    searchable, and so a silent failure still says something useful.
    """
    detail = (str(stderr or "").strip() or str(stdout or "").strip())
    entry = error_catalog.for_marker(detail) if detail else None
    if entry is None:
        entry = error_catalog.for_exit_status(returncode)

    if entry is None:
        if detail:
            # Unrecognised but non-empty: the process explained itself.
            return detail
        entry = error_catalog.GENERAL_FAILURE

    summary = translate(entry.summary)
    action = translate(entry.action)
    parts = [summary, action] if not detail else [detail, summary, action]
    # De-duplicate when the helper already printed the catalog wording.
    rendered = " ".join(dict.fromkeys(part for part in parts if part))
    return f"{rendered} [{entry.code}]"


def failure_code(returncode: object, stdout: object = "", stderr: object = "") -> str:
    """Return only the stable identifier for a failed process."""
    detail = (str(stderr or "").strip() or str(stdout or "").strip())
    entry = error_catalog.for_marker(detail) if detail else None
    if entry is None:
        entry = error_catalog.for_exit_status(returncode)
    return (entry or error_catalog.GENERAL_FAILURE).code
