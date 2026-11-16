"""Real Settings navigation, distribution help, copy-only commands and error links."""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea

from bc250cc.shared import known_errors
from frontends.desktop.components import known_errors as views
from frontends.desktop.components.known_errors import DistributionSelector
from frontends.desktop.components.widgets import InfoDialog
from frontends.desktop.i18n import current_language, set_language, tr
from frontends.desktop.pages.settings import SettingsPage, SupportCard


@pytest.fixture
def page(qtbot, tmp_path, monkeypatch):
    previous_language = current_language()
    set_language("es")
    monkeypatch.setattr(views, "detect_os_info", lambda: SimpleNamespace(family="bazzite"))
    settings = SimpleNamespace(read_local_config=lambda: {"gpu_governor": "auto"})
    page = SettingsPage(object(), settings_service=settings, activity_service=SimpleNamespace(clear=lambda: True),
                        app_settings=QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(page)
    page.resize(1145, 705)
    page.show()
    yield page
    set_language(previous_language)


def test_third_card_opens_index_with_all_fifteen_modules(page):
    page.select_section("support")
    cards = page._section_pages["support"].findChildren(SupportCard)
    assert [card.findChildren(QLabel)[0].text() for card in cards] == [
        tr("Report a problem"), tr("View reports"), tr("Known errors"),
    ]
    cards[2].click()
    assert page._section_pages["support_errors"].isVisibleTo(page)
    listing = page.known_errors_list
    assert listing.module_combo.count() == 16 and len(listing.rows) == 76
    assert not listing.findChildren(QScrollArea)
    assert not listing.findChildren(DistributionSelector)
    assert not hasattr(listing, "all_distributions")
    listing.module_combo.setCurrentIndex(listing.module_combo.findData("fans"))
    assert {key for key, row in listing.rows.items() if not row.isHidden()} == {"FAN-01", "FAN-02", "FAN-03", "FAN-04"}
    listing.set_query("PKG006")
    assert not listing.rows["PKG-05"].isHidden()
    listing.set_query("qxzxq nothing matches")
    assert not listing.empty.isHidden()


def test_search_debounces_typing_and_explains_the_match(page, qtbot):
    page.select_section("support_errors")
    listing = page.known_errors_list
    listing.search_field.setText("no gira")
    assert listing.search_timer.isActive() and listing.search_timer.interval() == 150
    assert sum(not row.isHidden() for row in listing.rows.values()) == 76
    qtbot.waitUntil(lambda: not listing.search_timer.isActive())
    assert {key for key, row in listing.rows.items() if not row.isHidden()} == {
        "FAN-01", "FAN-02", "FAN-03", "FAN-04"}
    assert "no gira" in listing.subtitles["FAN-01"].text()
    listing.set_query("pkg 6")
    assert "BC250-PKG-006" in listing.subtitles["PKG-05"].text()


def test_empty_search_opens_a_prefilled_report_without_sending(page, monkeypatch):
    from bc250cc.infrastructure import problem_report

    sent = []
    monkeypatch.setattr(problem_report, "submit", lambda *args, **kwargs: sent.append(args))
    page.select_section("support_errors")
    listing = page.known_errors_list
    query = "qxzxq wvwvw xyzxyz"
    listing.set_query(query)
    assert not listing.empty.isHidden()
    assert not listing.report_button.isHidden()
    listing.report_button.click()
    assert page._section_pages["support_report"].isVisibleTo(page)
    assert page.report_form.summary.text() == query
    assert sent == []


def test_empty_search_offers_a_nearby_module(page):
    page.select_section("support_errors")
    listing = page.known_errors_list
    listing.module_combo.setCurrentIndex(listing.module_combo.findData("packages"))
    listing.search_field.setText("ventiladres")
    listing._filter()
    assert not listing.empty.isHidden()
    button = next(button for button in listing.module_suggestions
                  if not button.isHidden() and button.property("module") == "fans")
    button.click()
    assert listing.module == "fans" and listing.search_field.text() == ""
    assert {key for key, row in listing.rows.items() if not row.isHidden()} == {
        "FAN-01", "FAN-02", "FAN-03", "FAN-04"}


def test_enter_searches_without_closing_the_settings_dialog(qtbot, tmp_path):
    from frontends.desktop.pages.settings import SettingsDialog

    dialog = SettingsDialog(object(), settings_service=SimpleNamespace(read_local_config=lambda: {}),
                            activity_service=SimpleNamespace(clear=lambda: True),
                            app_settings=QSettings(str(tmp_path / "enter.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.select_section("support_errors")
    listing = dialog.page.known_errors_list
    listing.search_field.setFocus()
    qtbot.keyClicks(listing.search_field, "pkg 6")
    qtbot.keyClick(listing.search_field, Qt.Key.Key_Return)
    qtbot.keyClick(listing.search_field, Qt.Key.Key_Enter)
    assert dialog.isVisible() and not listing.search_timer.isActive()
    assert not listing.rows["PKG-05"].isHidden()


def test_article_opens_the_solution_for_detected_distro_and_copies_without_running(page, qtbot):
    page.select_section("support_errors:CU-01")
    detail = page.known_error_detail
    assert detail.distro == "bazzite"
    assert detail.distribution_selector.combo.currentData() == "auto"
    assert detail.distribution_selector.isHidden()
    assert detail.active_tab == "solution"
    assert not detail.tab_pages["solution"].isHidden()
    assert set(detail.tab_buttons) == {"solution", "developer"}
    assert detail.tab_buttons["solution"].text() == tr("Solution")
    assert detail.tab_pages["developer"].isHidden()
    assert not hasattr(detail, "step_cards")
    command = known_errors.fix_for(known_errors.for_id("CU-01"), "bazzite")["article"][1]["commands"][0]
    block = next(frame for frame in detail.tab_pages["solution"].findChildren(views.QFrame)
                 if frame.objectName() == "DialogDetail" and
                 any(label.text() == command for label in frame.findChildren(QLabel)))
    copy = next(button for button in block.findChildren(QPushButton) if button.objectName() == "DialogSecondary")
    copy.click()
    assert QApplication.clipboard().text() == command
    assert copy.text() == tr("Copied")
    # The outer settings scroll must accommodate the expanded, wrapped text.
    qtbot.waitUntil(lambda: page.scroll.verticalScrollBar().maximum() > 0)
    assert detail.title.height() >= detail.title.fontMetrics().height()
    detail.tab_buttons["developer"].click()
    assert not detail.tab_pages["developer"].isHidden()
    assert detail.tab_pages["solution"].isHidden()
    qtbot.waitUntil(lambda: detail.article.y() < 100)
    assert detail.article.y() == 0


def test_distribution_choice_updates_commands_and_survives_navigation(page):
    page.select_section("support_errors:CU-01")
    selector = page.known_error_detail.distribution_selector.combo
    selector.setCurrentIndex(selector.findData("debian"))
    page.select_section("support_errors")
    page.known_errors_list.view_buttons["CU-01"].click()
    detail = page.known_error_detail
    assert detail.distro == "debian"
    assert detail.distribution_selector.combo.currentData() == "debian"
    commands = [label.text() for label in detail.tab_pages["solution"].findChildren(QLabel)
                if label.objectName() == "DialogDetailText"]
    assert any("apt install" in command for command in commands)
    assert not any("rpm-ostree" in command for command in commands)
    detail.distribution_selector.combo.setCurrentIndex(0)
    assert detail.distro == "bazzite"
    page.select_section("support_errors")
    page.known_errors_list.view_buttons["CU-01"].click()
    assert selector.currentData() == "auto"


def test_inapplicable_distro_has_no_commands_and_can_be_changed(page):
    page.select_section("support_errors:INST-01")
    detail = page.known_error_detail
    selector = detail.distribution_selector.combo
    selector.setCurrentIndex(selector.findData("debian"))
    assert not detail.tab_pages["solution"].findChildren(QPushButton)
    assert tr("Not applicable") in [label.text() for label in detail.tab_pages["solution"].findChildren(QLabel)]
    selector.setCurrentIndex(selector.findData("bazzite"))
    commands = [label.text() for label in detail.tab_pages["solution"].findChildren(QLabel)
                if label.objectName() == "DialogDetailText"]
    assert "rpm-ostree uninstall coolercontrol" in commands


def test_error_window_link_opens_matching_settings_entry(page, qtbot):
    dialog = InfoDialog("UMR is not installed.", "cannot find the UMR executable", parent=page, tone="red")
    qtbot.addWidget(dialog)
    assert hasattr(dialog, "known_errors_button")
    dialog.known_errors_button.click()
    qtbot.waitUntil(lambda: hasattr(page, "known_error_detail") and page.known_error_detail.identity == "CU-01")


def test_multiple_matches_open_search_instead_of_an_arbitrary_entry(page):
    page.select_section("support_errors:BC250-UMR-001")
    assert page.known_errors_list.search_field.text() == "BC250-UMR-001"
    assert not page.known_errors_list.rows["CU-01"].isHidden()
    assert not page.known_errors_list.rows["CU-02"].isHidden()


def test_protective_warning_can_also_open_the_handbook(page, qtbot):
    dialog = InfoDialog("Warning", "non-0x77 presence mask detected", parent=page, tone="orange")
    qtbot.addWidget(dialog)
    dialog.known_errors_button.click()
    qtbot.waitUntil(lambda: hasattr(page, "known_error_detail") and page.known_error_detail.identity == "CU-03")


def test_update_uses_existing_signal_and_expected_entries_explain_protection(page, monkeypatch):
    monkeypatch.setattr(views, "__version__", "1.22.6")
    page.select_section("support_errors:UPS-01")
    seen = []
    page.update_requested.connect(lambda: seen.append(True))
    button = next(button for button in page.known_error_detail.findChildren(QPushButton)
                  if button.property("primaryAction"))
    button.click()
    assert seen == [True]
    page.select_section("support_errors:CU-03")
    assert tr("A protection, not an error") in [label.text() for label in page.known_error_detail.findChildren(QLabel)]
