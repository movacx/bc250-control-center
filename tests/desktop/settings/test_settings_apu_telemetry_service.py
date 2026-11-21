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
        "blocked_reason": "SteamOS resets /usr on every update; install BC250-Telemetry with its own installer.",
    })
    assert not page.apu_telemetry_button.isEnabled()
    assert "SteamOS" in page.apu_telemetry_button.toolTip()


def test_the_gddr6_warning_is_one_short_note(qtbot, tmp_path, monkeypatch):
    """The four-paragraph explanation was too much; one short note stays."""
    page, _controller = _page(qtbot, tmp_path, monkeypatch, {"state": "not-installed", "supported": True})
    assert not hasattr(page, "gddr6_help_toggle")
    assert len(page.GDDR6_NOTE) < 220 and "freeze" in page.GDDR6_NOTE


def test_the_sources_come_first_and_the_daemon_last(qtbot, tmp_path, monkeypatch):
    from frontends.desktop.pages.settings import SettingsGroup

    page, _controller = _page(qtbot, tmp_path, monkeypatch, {"state": "not-installed", "supported": True})
    host = page.apu_telemetry_button.window()
    groups = [group for group in host.findChildren(SettingsGroup) if group.isAncestorOf(page.apu_telemetry_button)
              or group.isAncestorOf(page.daemon_status_label)]
    assert groups[0].isAncestorOf(page.apu_telemetry_button)
    assert groups[-1].isAncestorOf(page.daemon_status_label)


def test_the_service_row_says_where_it_stands(qtbot, tmp_path, monkeypatch):
    page, _controller = _page(qtbot, tmp_path, monkeypatch, {"state": "publishing", "supported": True, "managed": True})
    assert page.apu_telemetry_state_label.text() in {"Running", "En marcha"}


def test_kernel_drivers_offer_the_action_their_state_needs(qtbot, tmp_path, monkeypatch):
    from frontends.desktop.pages import dashboard

    monkeypatch.setattr(dashboard, "kernel_sensor_drivers", lambda: {
        "vrm_sensor": {"state": "update-available", "device": True},
        "vram_sensor": {"state": "managed-elsewhere", "device": True},
    })
    page, _controller = _page(qtbot, tmp_path, monkeypatch, {"state": "not-installed", "supported": True})
    page.refresh_kernel_sensor_drivers()
    vrm, vram = page.kernel_sensor_buttons["vrm_sensor"], page.kernel_sensor_buttons["vram_sensor"]
    assert not vrm.isHidden() and vrm.property("sensorAction") == "update"
    assert vram.isHidden() and page.kernel_sensor_states["vram_sensor"].text() in {"Built into this kernel", "Integrado en este kernel"}
    emitted = []
    page.driver_support_requested.connect(emitted.append)
    vrm.click()
    assert emitted == ["vrm_sensor:install"]


def test_kernel_driver_states_in_words():
    describe = SettingsPage.describe_kernel_sensor
    assert describe("vrm_sensor", {"state": "active", "reading": 47.2})[1:] == ("remove", True)
    assert describe("vram_sensor", {"state": "unsupported", "device": True, "bios_supported": False})[0] == "Needs BIOS P3.00"
    assert describe("vrm_sensor", {"state": "unsupported", "device": True})[0] == "Arch-based systems only"
