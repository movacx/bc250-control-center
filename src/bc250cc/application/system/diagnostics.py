"""The hardware diagnosis a problem report attaches."""

from __future__ import annotations


def collect_diagnostics() -> str:
    from bc250cc.infrastructure.system_diagnostics import collect_diagnostics as collect

    return collect()


def collect_readonly_attachments() -> list[tuple[str, str]]:
    from bc250cc.infrastructure.report_attachments import (
        collect_readonly_attachments as collect,
    )

    return collect()
