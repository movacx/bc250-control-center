"""The hardware diagnosis a problem report attaches."""

from __future__ import annotations


def collect_diagnostics() -> str:
    from bc250cc.infrastructure.system_diagnostics import collect_diagnostics as collect

    return collect()


def system_rows() -> list[tuple[str, str]]:
    """The facts a support thread asks first, as (label, value)."""
    from bc250cc.infrastructure.system_snapshot import system_snapshot

    return system_snapshot()


def collect_readonly_attachments() -> list[tuple[str, str]]:
    from bc250cc.infrastructure.report_attachments import (
        collect_readonly_attachments as collect,
    )

    return collect()
