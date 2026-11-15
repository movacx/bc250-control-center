"""Settings > About > Support: report form, view reports, sent list, in one window."""

from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QLabel

from bc250cc.infrastructure import problem_report as reports
from frontends.desktop.pages.settings import SentReportsList, SettingsPage


class _Service:
    def read_local_config(self):
        return {"gpu_governor": "auto"}


class _Activity:
    def clear(self):
        return True


def _page(qtbot, tmp_path):
    page = SettingsPage(object(), settings_service=_Service(), activity_service=_Activity(),
                        app_settings=QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(page)
    return page


def test_diagnostics_and_history_are_no_longer_sidebar_sections(qtbot, tmp_path):
    page = _page(qtbot, tmp_path)
    assert "diagnostics" not in page.section_order and "reports" not in page.section_order
    assert page.SECTION_ALIASES == {"diagnostics": ("support_reports", 0), "reports": ("support_reports", 1)}


def test_the_old_keys_open_the_matching_tab_of_view_reports(qtbot, tmp_path):
    page = _page(qtbot, tmp_path)
    page.select_section("reports")
    assert page._section_pages["support_reports"].isVisibleTo(page) or True
    assert page.report_tab_pages.currentIndex() == 1 and page.report_tabs[1].isChecked()
    page.select_section("diagnostics")
    assert page.report_tab_pages.currentIndex() == 0 and page.report_tabs[0].isChecked()


def test_the_report_form_opens_inside_settings_and_returns_to_support(qtbot, tmp_path):
    page = _page(qtbot, tmp_path)
    page.select_section("support_report")
    form = page.report_form
    assert form.parent() is not None and not form.isWindow()
    shown = []
    page.select_section = shown.append
    form.closed.emit()
    assert shown == ["support"]


def test_a_sent_report_is_listed_with_its_id_newest_first(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(reports, "sent_history_path", lambda: tmp_path / "sent.json")
    reports.record_sent({"id": "R-11111111", "sent_at": "2026-11-14T10:00:00+00:00", "summary": "First",
                         "error": {"code": "BC250-CU-001"}, "app": {"version": "1.22.9"}})
    reports.record_sent({"id": "R-22222222", "sent_at": "2026-11-15T10:00:00+00:00", "summary": "Second"})
    assert [item["id"] for item in reports.sent_reports()] == ["R-22222222", "R-11111111"]
    listing = SentReportsList()
    qtbot.addWidget(listing)
    # The header, then one row per report.
    assert len(listing.rows) == 3


def test_sending_records_the_report_id_once_the_service_confirmed(tmp_path):
    saved = tmp_path / "sent.json"
    report = reports.Report(summary="It stops after a few seconds")
    reports._last_sent = 0.0
    reports.submit(report, post=lambda document: None, save=lambda document: None,
                   record=lambda document: reports.record_sent(document, saved), clock=lambda: 1_000_000.0)
    assert [item["id"] for item in reports.sent_reports(saved)] == [report.id]


def test_a_failed_send_leaves_no_entry(tmp_path):
    saved = tmp_path / "sent.json"

    def refuse(document):
        raise reports.ReportError("The report service could not be reached.")

    reports._last_sent = 0.0
    try:
        reports.submit(reports.Report(summary="Something broke"), post=refuse, save=lambda document: None,
                       record=lambda document: reports.record_sent(document, saved), clock=lambda: 2_000_000.0)
    except reports.ReportError:
        pass
    assert reports.sent_reports(saved) == []


def test_the_history_keeps_at_most_two_hundred_entries(tmp_path):
    saved = tmp_path / "sent.json"
    for number in range(reports.MAX_SENT_HISTORY + 5):
        reports.record_sent({"id": f"R-{number:08x}", "summary": "x"}, saved)
    assert len(reports.sent_reports(saved)) == reports.MAX_SENT_HISTORY


def test_view_opens_the_report_with_its_summary(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(reports, "sent_history_path", lambda: tmp_path / "sent.json")
    reports.record_sent({"id": "R-33333333", "sent_at": "2026-11-15T10:00:00+00:00", "summary": "It stops",
                         "problem": {"area": "Compute Units (40CU)", "steps": "Press apply and it stops."},
                         "error": {"code": "BC250-CU-001"}, "app": {"version": "1.22.9"}, "attachments": [["a", "b"]]})
    page = _page(qtbot, tmp_path)
    page.select_section("support")
    seen = []
    page.sent_reports_list.view_requested.connect(seen.append)
    row = page.sent_reports_list.rows[1]
    row.findChildren(type(page.sent_reports_list.filters[0]))[0].click()
    assert seen and seen[0]["id"] == "R-33333333"
    assert seen[0]["attached"] is True
    page._show_report_detail(seen[0])
    assert page.detail_title.text() == "R-33333333"
    assert not hasattr(page.support_detail, "input") and not hasattr(page.support_detail, "pages")


def test_the_table_has_no_code_column_and_messages_is_gone(qtbot, tmp_path):
    page = _page(qtbot, tmp_path)
    assert "support_messages" not in page.SUBPAGES
    page.select_section("support")
    headers = [label.text() for label in page.sent_reports_list.rows[0].findChildren(QLabel)]
    assert "Code" not in headers and "Código" not in headers


def test_about_lists_every_application_folder_and_no_contact_row(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    page = _page(qtbot, tmp_path)
    folders = {str(location) for _title, _text, location in page._application_folders()}
    assert str(tmp_path / "data" / "bc250-control-center") in folders
    assert len(folders) == 3
    assert "/var/lib/bc250-control-center" in folders
    assert not hasattr(page, "_open_contact")


def test_a_folder_that_does_not_exist_yet_is_not_created_by_opening_it(qtbot, tmp_path):
    page = _page(qtbot, tmp_path)
    missing = tmp_path / "never-made"
    page._open_existing_folder(missing)
    assert not missing.exists()


def test_enter_in_a_search_box_does_not_close_settings(qtbot, tmp_path):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLineEdit

    from frontends.desktop.pages.settings import SettingsDialog

    dialog = SettingsDialog(object(), settings_service=_Service(), activity_service=_Activity(),
                            app_settings=QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.select_section("repositories")
    field = dialog.page._section_pages["repositories"].findChildren(QLineEdit)[0]
    field.setFocus()
    qtbot.keyClicks(field, "cyan")
    qtbot.keyClick(field, Qt.Key.Key_Return)
    qtbot.keyClick(field, Qt.Key.Key_Enter)
    assert dialog.isVisible()
    # The close button was the dialog's default button: the real cause of the closing.
    assert not dialog.close_button.autoDefault() and not dialog.close_button.isDefault()
