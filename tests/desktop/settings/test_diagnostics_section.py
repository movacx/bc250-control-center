"""Settings › Diagnostics: the system sheet and every error the owner was shown.

A diagnostic code used to live only in the window or terminal that printed it,
so a problem report was written from memory. Each one is now kept with its
time and probable cause, and the page copies the lot for the report.
"""

from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from bc250cc.infrastructure import diagnostic_journal as journal
from bc250cc.infrastructure import system_snapshot as snapshot_module
from bc250cc.infrastructure.terminal_repository import TerminalLaunchResult
from frontends.desktop.components.widgets import InfoDialog
from frontends.desktop.core import diagnostic_history
from frontends.desktop.core.diagnostic_history import (
    diagnostic_report,
    record_terminal_failure,
    record_window_error,
)
from frontends.desktop.core.error_diagnostics import explain_code
from frontends.desktop.pages import settings as settings_module
from frontends.desktop.pages.settings import SettingsPage


@pytest.fixture
def journal_file(tmp_path, monkeypatch):
    path = tmp_path / "state" / "diagnostics.jsonl"
    monkeypatch.setattr(journal, "journal_path", lambda env=None: path)
    # Never the real Decky history of the machine running the tests.
    monkeypatch.setattr(diagnostic_history, "DECKY_DIAGNOSTICS", tmp_path / "decky" / "diagnostics.jsonl")
    return path


def _entry(code="BC250-GPU-003", at=1_000.0, **extra):
    diagnosis = explain_code(code)
    return journal.record(
        code=code, source=extra.get("source", "window"), title=extra.get("title", "GPU"),
        summary=diagnosis.summary, cause=diagnosis.cause, action=diagnosis.action,
        detail=extra.get("detail", ""), now=at,
    )


# ------------------------------------------------------------------ journal


def test_entries_come_back_newest_first(journal_file):
    _entry("BC250-GPU-003", at=1_000)
    _entry("BC250-CMD-001", at=2_000)
    assert [entry.code for entry in journal.read()] == ["BC250-CMD-001", "BC250-GPU-003"]


def test_the_same_error_shown_twice_at_once_is_one_entry(journal_file):
    assert _entry(at=1_000, detail="x") is not None
    assert _entry(at=1_002, detail="x") is None
    assert _entry(at=1_100, detail="x") is not None
    assert len(journal.read()) == 2


def test_the_history_stays_bounded(journal_file, monkeypatch):
    monkeypatch.setattr(journal, "MAX_ENTRIES", 10)
    for index in range(20):
        _entry(at=1_000 + index * 60, detail=str(index))
    entries = journal.read(limit=100)
    assert len(entries) <= 12 and entries[0].detail == "19"


def test_a_broken_line_is_skipped_and_clear_empties_it(journal_file):
    _entry()
    with open(journal_file, "a", encoding="utf-8") as handle:
        handle.write("not json\n")
    assert len(journal.read()) == 1
    journal.clear()
    assert journal.read() == []


def test_an_unwritable_history_never_raises(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setattr(journal, "journal_path", lambda env=None: blocker / "diagnostics.jsonl")
    assert _entry() is None


def test_the_journal_lives_in_the_state_folder():
    assert journal.journal_path({"XDG_STATE_HOME": "/s"}).as_posix() == "/s/bc250-control-center/diagnostics.jsonl"


# ------------------------------------------------------------- recording


def test_a_red_dialog_records_the_diagnosis_it_shows(qtbot, journal_file):
    dialog = InfoDialog("Fans", "Permission denied: /dev/hwmon", tone="red", eyebrow="FANS")
    qtbot.addWidget(dialog)
    entry = journal.read()[0]
    assert entry.source == "window" and entry.title == "Fans"
    assert entry.code.startswith("BC250-") and entry.cause
    assert "Permission denied" in entry.detail


def test_an_informative_dialog_records_nothing(qtbot, journal_file):
    qtbot.addWidget(InfoDialog("Done", "All good", tone="blue"))
    assert journal.read() == []


def test_a_message_that_names_its_code_keeps_it(journal_file):
    record_window_error("What happened\n...\nDiagnostic code: BC250-GPU-003", context="", title="GPU")
    assert journal.read()[0].code == "BC250-GPU-003"


def _launch(tmp_path, text: str) -> TerminalLaunchResult:
    log = tmp_path / "workflow.log"
    log.write_text(text, encoding="utf-8")
    return TerminalLaunchResult("bc250-embedded-console", "Prepare dependencies", None, str(tmp_path / "s"), str(log))


def test_a_failed_workflow_records_the_code_its_terminal_printed(tmp_path, journal_file):
    record_terminal_failure(_launch(tmp_path, "pacman: target not found\n\x1b[31mDiagnostic code: BC250-CMD-001\x1b[0m\n"), 127)
    entry = journal.read()[0]
    assert (entry.code, entry.source, entry.title) == ("BC250-CMD-001", "terminal", "Prepare dependencies")
    assert "target not found" in entry.detail and "\x1b" not in entry.detail
    assert entry.detail.rstrip().endswith("workflow.log")


def test_a_workflow_closed_by_hand_or_that_succeeded_is_not_an_error(tmp_path, journal_file):
    record_terminal_failure(_launch(tmp_path, "Diagnostic code: BC250-CMD-001\n"), 0)
    record_terminal_failure(_launch(tmp_path, "interrupted\n"), 130)
    assert journal.read() == []


# ------------------------------------------------------------ snapshot


def test_boot_options_that_identify_disks_are_left_out(monkeypatch):
    monkeypatch.setattr(snapshot_module, "_read", lambda path, limit=65536: (
        "BOOT_IMAGE=/vmlinuz root=UUID=abc rw amdgpu.sg_display=0 resume=/dev/sda2 cryptdevice=x" if path == "/proc/cmdline" else ""
    ))
    assert snapshot_module._kernel_options() == "rw amdgpu.sg_display=0"


def test_every_row_is_there_even_when_a_fact_cannot_be_read(monkeypatch, tmp_path):
    def broken():
        raise OSError("nope")

    monkeypatch.setattr(snapshot_module, "_mesa", broken)
    rows = dict(snapshot_module.system_snapshot(project_root=tmp_path))
    assert list(rows)[:4] == ["Control Center", "Installation", "Operating system", "Kernel"]
    assert rows["Mesa"] == snapshot_module.UNKNOWN


# -------------------------------------------------------------- report


def test_the_report_carries_the_sheet_and_the_newest_errors(journal_file, monkeypatch):
    monkeypatch.setattr(diagnostic_history, "REPORT_ENTRIES", 2)
    for index, code in enumerate(("BC250-GPU-003", "BC250-CMD-001", "BC250-USB-900")):
        _entry(code, at=1_000 + index * 60)
    text = diagnostic_report([("Kernel", "7.2.8"), ("BIOS", "P3.00")], journal.read(), now=0)
    assert "Kernel  7.2.8" in text and "BIOS    P3.00" in text
    assert "Recent errors (2 of 3)" in text
    assert "BC250-USB-900" in text and "BC250-CMD-001" in text and "BC250-GPU-003" not in text
    assert "Likely cause:" in text


# ---------------------------------------------------------------- page


class _SettingsService:
    def read_local_config(self):
        return {"gpu_governor": "auto"}


class _ActivityService:
    def clear(self):
        return True


@pytest.fixture
def page(qtbot, tmp_path, journal_file, monkeypatch):
    monkeypatch.setattr(settings_module, "system_snapshot", lambda: [("Kernel", "7.2.8"), ("GPU governor", "None running")])
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    page = SettingsPage(object(), settings_service=_SettingsService(),
                        activity_service=_ActivityService(), app_settings=settings)
    qtbot.addWidget(page)
    return page


def test_the_page_lists_the_system_and_the_history(qtbot, page):
    _entry("BC250-GPU-003", at=1_000, detail="vddgfx 44587 mV")
    page.select_section("diagnostics")
    qtbot.waitUntil(lambda: page.system_table.rowCount() == 2, timeout=5000)
    assert page.system_table.item(0, 1).text() == "7.2.8"
    assert page.diagnostics_table.rowCount() == 1
    assert page.diagnostics_table.item(0, 1).text() == "BC250-GPU-003"
    page.diagnostics_table.selectRow(0)
    assert "vddgfx 44587 mV" in page.diagnostics_detail.toPlainText()


def test_an_empty_history_says_so(qtbot, page):
    page.select_section("diagnostics")
    assert page.diagnostics_table.isHidden() and not page.diagnostics_empty.isHidden()
    assert not page.diagnostics_clear_button.isEnabled()


def test_copy_puts_the_report_on_the_clipboard_and_clear_empties_it(qtbot, page):
    _entry()
    page.select_section("diagnostics")
    qtbot.waitUntil(lambda: page.system_table.rowCount() == 2, timeout=5000)
    page.diagnostics_copy_button.click()
    copied = QApplication.clipboard().text()
    assert copied.startswith("BC250 Control Center diagnostic report") and "BC250-GPU-003" in copied
    page.diagnostics_clear_button.click()
    assert journal.read() == [] and page.diagnostics_table.rowCount() == 0


def test_the_old_health_section_is_gone(page):
    assert "health" not in page.section_order and not hasattr(page, "health_table")
    assert json.dumps(page.section_order).count("diagnostics") == 1


def test_an_older_entry_shows_the_wording_its_code_has_today(journal_file):
    journal.record(code="BC250-CMD-001", source="terminal", title="x", summary="old", cause="old", action="old", now=1)
    entry = journal.read()[0]
    assert diagnostic_history.current_wording(entry).action == explain_code("BC250-CMD-001").action
    unknown = journal.record(code="BC250-GONE-999", source="window", title="x", summary="s", cause="c", action="a", now=99)
    assert diagnostic_history.current_wording(unknown).action == "a"


# ------------------------------------------------------- Decky Quick Access


def _decky_line(path, **entry):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def test_decky_failures_join_the_history_classified_like_desktop_errors(journal_file):
    _entry("BC250-GPU-003", at=1_000)
    decky = diagnostic_history.DECKY_DIAGNOSTICS
    _decky_line(decky, at=2_000, module="cpu", target="detect-3850:1150",
                error="SMU_IN_USE: Another BC-250 tool kept the SMU busy")
    _decky_line(decky, at=500, module="gpu", target="benchmark",
                error="QUICK_ACCESS_GPU_DBUS: Cyan D-Bus is not ready; no range was changed.")
    decky.open("a").write("not json\n")

    entries = diagnostic_history.history_entries()

    assert [(entry.source, entry.at) for entry in entries] == [
        ("decky", 2_000), ("window", 1_000), ("decky", 500),
    ]
    assert entries[0].title == "Decky Quick Access · CPU · detect-3850:1150"
    assert entries[2].code == "BC250-DBUS-001"


def test_clearing_hides_decky_failures_it_cannot_delete(journal_file):
    decky = diagnostic_history.DECKY_DIAGNOSTICS
    _decky_line(decky, at=1_000, module="fan", target="quiet", error="QUICK_ACCESS_FAN: write failed")
    assert diagnostic_history.history_entries()

    diagnostic_history.clear_history()

    assert diagnostic_history.history_entries() == []
    assert decky.exists()
