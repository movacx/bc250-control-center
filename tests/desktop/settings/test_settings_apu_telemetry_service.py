"""Settings › Telemetry: the BC250-Telemetry service row installs, removes or steps aside."""

from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QDialog

from frontends.desktop.pages import settings as settings_module
from frontends.desktop.pages.settings import SettingsPage


class _SettingsService:
    def read_local_config(self):
        return {}


class _ActivityService:
    def clear(self):
        return None


class _Controller:
    def __init__(self):
        self.calls = []

    def gestionar_apu_telemetry(self, action):
        self.calls.append(action)
        return "opened"


def _page(qtbot, tmp_path, monkeypatch, state):
    monkeypatch.setattr(settings_module, "board_bios_version", lambda: "P3.00")
    monkeypatch.setattr(settings_module, "sondear_telemetria_vrm", lambda: {"daemon": "missing"})
    monkeypatch.setattr(settings_module, "apu_telemetry_state", lambda **_kw: dict(state))
    controller = _Controller()
    page = SettingsPage(
        controller, settings_service=_SettingsService(), activity_service=_ActivityService(),
        app_settings=QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat),
    )
    qtbot.addWidget(page)
    page._ensure_section("telemetry")
    return page, controller


def _accept(monkeypatch, accepted=True):
    shown = []

    def fake_exec(self):
        shown.append(self)
        return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(settings_module.ConfirmDialog, "exec", fake_exec)
    return shown


def test_a_board_without_the_service_is_offered_the_install(qtbot, tmp_path, monkeypatch):
    page, _controller = _page(qtbot, tmp_path, monkeypatch, {"state": "not-installed", "supported": True})
    assert page.apu_telemetry_button.text() == "Install service"
    assert page.apu_telemetry_button.isEnabled()


def test_the_install_asks_first_and_then_runs_the_workflow(qtbot, tmp_path, monkeypatch):
    page, controller = _page(qtbot, tmp_path, monkeypatch, {"state": "not-installed", "supported": True})
    shown = _accept(monkeypatch)

    page.apu_telemetry_button.click()

    qtbot.waitUntil(lambda: controller.calls == ["install"], timeout=3000)
    assert len(shown) == 1


def test_declining_the_confirmation_runs_nothing(qtbot, tmp_path, monkeypatch):
    page, controller = _page(qtbot, tmp_path, monkeypatch, {"state": "not-installed", "supported": True})
    _accept(monkeypatch, accepted=False)

    page.apu_telemetry_button.click()
    qtbot.wait(150)

    assert controller.calls == []


def test_the_service_control_center_installed_can_be_removed(qtbot, tmp_path, monkeypatch):
    page, controller = _page(qtbot, tmp_path, monkeypatch, {"state": "publishing", "supported": True, "managed": True})
    _accept(monkeypatch)
    assert page.apu_telemetry_button.text() == "Remove service"

    page.apu_telemetry_button.click()

    qtbot.waitUntil(lambda: controller.calls == ["uninstall"], timeout=3000)


def test_a_service_from_upstreams_installer_is_left_alone(qtbot, tmp_path, monkeypatch):
    page, _controller = _page(qtbot, tmp_path, monkeypatch, {"state": "external", "supported": True, "managed": False})
    assert page.apu_telemetry_button.text() == "Installed separately"
    assert not page.apu_telemetry_button.isEnabled()


def test_where_it_is_not_offered_the_button_says_why(qtbot, tmp_path, monkeypatch):
    page, _controller = _page(qtbot, tmp_path, monkeypatch, {
        "state": "not-installed", "supported": False,
        "blocked_reason": "Bazzite is image-based; install BC250-Telemetry with its own installer.",
    })
    assert not page.apu_telemetry_button.isEnabled()
    assert "Bazzite" in page.apu_telemetry_button.toolTip()


def test_the_long_gddr6_explanation_is_folded_until_asked_for(qtbot, tmp_path, monkeypatch):
    page, _controller = _page(qtbot, tmp_path, monkeypatch, {"state": "not-installed", "supported": True})
    page.show()
    qtbot.waitExposed(page)
    page.nav_buttons["telemetry"].click()

    assert not page.gddr6_help_panel.isVisible()
    assert page.gddr6_help_toggle.text().endswith("Details")

    page.gddr6_help_toggle.click()
    assert page.gddr6_help_panel.isVisible()
    assert page.app_settings.value("settings/gddr6_help_open") == "true"

    page.gddr6_help_toggle.click()
    assert not page.gddr6_help_panel.isVisible()


def test_an_opened_explanation_stays_open_next_time(qtbot, tmp_path, monkeypatch):
    first, _controller = _page(qtbot, tmp_path, monkeypatch, {"state": "not-installed", "supported": True})
    first.gddr6_help_toggle.click()

    second, _controller = _page(qtbot, tmp_path, monkeypatch, {"state": "not-installed", "supported": True})
    assert second.gddr6_help_toggle.isChecked()
