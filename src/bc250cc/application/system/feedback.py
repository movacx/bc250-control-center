"""The problem report, as the interface sees it.

The report itself (its document, the service it goes to, the copy kept when
it cannot be sent) is in ``bc250cc.infrastructure.problem_report``; the
desktop goes through here, like every other use case, so it never imports
infrastructure directly.
"""

from __future__ import annotations

from bc250cc.infrastructure import problem_report as reports
from bc250cc.infrastructure.firmware.board import (
    read_board_firmware,
    read_installed_bios,
)
from bc250cc.infrastructure.report_attachments import collect_attachments
from bc250cc.infrastructure.system_diagnostics import kernel_log_needs_password
from bc250cc.infrastructure.system_snapshot import _os_release as os_release
from bc250cc.infrastructure.system_snapshot import system_snapshot

__all__ = [
    "collect_attachments", "kernel_log_needs_password", "os_release", "read_board_firmware",
    "read_installed_bios", "reports", "system_snapshot",
]
