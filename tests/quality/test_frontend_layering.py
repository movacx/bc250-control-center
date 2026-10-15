"""Layering ratchet: the interface reaches the system through ``application``.

``docs/ARQUITECTURA_MVC.md`` describes Desktop -> application -> infrastructure,
but older pages import ``bc250cc.infrastructure`` directly. Those files are
listed below so they can be migrated one by one; a new file may not join them,
and a migrated one must leave the list.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMPORT = re.compile(r"^\s*(?:from|import) bc250cc\.infrastructure", re.MULTILINE)

LEGACY = frozenset({
    "frontends/cli.py",
    "frontends/desktop/app.py",
    "frontends/desktop/components/dashboard_widgets.py",
    "frontends/desktop/components/preparation_pages.py",
    "frontends/desktop/components/system_setup_controls.py",
    "frontends/desktop/components/update_dialog.py",
    "frontends/desktop/console/console_host.py",
    "frontends/desktop/console/pty_session.py",
    "frontends/desktop/core/diagnostic_history.py",
    "frontends/desktop/core/firmware_session.py",
    "frontends/desktop/core/performance_views.py",
    "frontends/desktop/core/preferences.py",
    "frontends/desktop/core/sensor_log.py",
    "frontends/desktop/core/state.py",
    "frontends/desktop/core/workflow_watch.py",
    "frontends/desktop/main.py",
    "frontends/desktop/pages/dashboard.py",
    "frontends/desktop/pages/fans.py",
    "frontends/desktop/pages/firmware.py",
    "frontends/desktop/pages/gpu_governor.py",
    "frontends/desktop/pages/gpu_governor_state.py",
    "frontends/desktop/pages/gpu_governor_widgets.py",
    "frontends/desktop/pages/performance.py",
    "frontends/desktop/pages/performance_sensors.py",
    "frontends/desktop/pages/settings.py",
})


def _importers() -> set[str]:
    return {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "frontends").rglob("*.py")
        if IMPORT.search(path.read_text(encoding="utf-8"))
    }


def test_no_new_frontend_file_imports_infrastructure_directly():
    new = sorted(_importers() - LEGACY)
    assert not new, f"Go through bc250cc.application instead of infrastructure: {new}"


def test_migrated_files_leave_the_legacy_list():
    stale = sorted(LEGACY - _importers())
    assert not stale, f"No longer import infrastructure, remove from LEGACY: {stale}"


def test_domain_and_application_do_not_import_the_interface():
    offenders = [
        path.relative_to(ROOT).as_posix()
        for layer in ("domain", "application")
        for path in (ROOT / "src" / "bc250cc" / layer).rglob("*.py")
        if re.search(r"^\s*(?:from|import) (?:frontends|PyQt6)", path.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert not offenders, offenders
