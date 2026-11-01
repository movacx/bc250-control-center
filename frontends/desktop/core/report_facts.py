"""What a problem report says about this system, read without Qt.

The desktop's report form and the terminal interface fill the same report
from here, so both send the same facts.
"""

from __future__ import annotations

from bc250cc.application.system.feedback import reports as form

from .diagnostic_history import history_entries


def read_report_facts() -> dict[str, object]:
    """Everything the app knows about this system, read off the UI thread.

    Every read fails to a blank rather than raising: a system without one of
    the files still sends the rest.
    """
    from bc250cc.application.system.feedback import (
        collect_attachments,
        os_release,
        read_board_firmware,
        read_installed_bios,
        system_snapshot,
    )

    rows = system_snapshot()
    facts = dict(rows)
    cores = 0
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as handle:
            cores = len({
                line.split(":", 1)[1].strip()
                for line in handle if line.startswith("core id")
            })
    except OSError:
        pass
    release = os_release()
    firmware: dict[str, str] = {}
    try:
        board = read_board_firmware()
        installed = read_installed_bios()
        firmware = {
            "board": board.board, "vendor": board.vendor, "version": board.version, "date": board.date,
            "variant": installed.variant, "evidence": installed.evidence,
        }
    except Exception:  # noqa: BLE001 - the report goes without it
        firmware = {}
    return {
        # The version is the report's own, and the BIOS is in ``firmware``.
        "system": {str(label): str(value) for label, value in rows if label not in ("Control Center", "BIOS")},
        "os_release": form.os_release_subset(release),
        "firmware": firmware,
        "history": history_entries(),
        # The diagnosis, one entry per section: the unfiltered kernel log,
        # service journals, configuration, storage, the last workflow logs.
        "attachments": _attachments_or_none(collect_attachments),
        "version": str(facts.get("Control Center", "")),
        "install": form.suggested_install(str(facts.get("Installation", ""))),
        "distribution": form.suggested_distribution(release),
        "bios": form.suggested_bios(firmware.get("variant", "")),
        "cores": form.suggested_cores(cores),
    }


def _attachments_or_none(collect) -> list[tuple[str, str]]:
    try:
        return list(collect())
    except Exception:  # noqa: BLE001 - the report goes without them
        return []
