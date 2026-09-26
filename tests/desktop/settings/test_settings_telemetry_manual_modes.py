"""Settings › Telemetry: the two manual switches and what each can lift.

* Power delivery can be shown by hand while the I2C mod is being wired, with
  what automatic detection sees right now next to the switch.
* Manual GDDR6 monitoring lifts the SMU channel check only; on a board that
  is not on P3.00 the page now says so beside the switch.
"""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from frontends.desktop.pages import settings as settings_module
from frontends.desktop.pages.settings import SettingsPage


class _SettingsService:
    def read_local_config(self):
        return {}


class _ActivityService:
    def clear(self):
        return None


def _page(qtbot, tmp_path, monkeypatch, *, bios="P3.00", probe=None):
    monkeypatch.setattr(settings_module, "board_bios_version", lambda: bios)
    monkeypatch.setattr(settings_module, "sondear_telemetria_vrm", lambda: dict(probe or {"daemon": "missing"}))
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    page = SettingsPage(object(), settings_service=_SettingsService(),
                        activity_service=_ActivityService(), app_settings=settings)
    qtbot.addWidget(page)
    page._ensure_section("telemetry")
    return page, settings


def test_the_power_delivery_switch_is_stored_and_announced(qtbot, tmp_path, monkeypatch):
    page, settings = _page(qtbot, tmp_path, monkeypatch)
    seen = []
    page.vrm_manual_changed.connect(seen.append)

    page.vrm_manual_switch.setChecked(True)

    assert seen == [True]
    assert settings.value("settings/vrm_manual") == "true"
    assert page.vrm_detection_label.text() == "Not detected: BC250-Telemetry is not running"


def test_detection_says_what_the_daemon_gets_from_the_pmic(qtbot, tmp_path, monkeypatch):
    page, _settings = _page(qtbot, tmp_path, monkeypatch, probe={
        "daemon": "running", "rails": {"cpu": {"valid": False}, "gpu": {"valid": False}},
    })
    assert page.vrm_detection_label.text() == "Not detected: BC250-Telemetry gets no answer from the PMIC"
    describe = SettingsPage.describe_vrm_detection
    assert describe({"daemon": "running", "rails": {"cpu": {"valid": True}}}) == "Detected: the PMIC answers over I2C"
    assert describe({"daemon": "stale", "age_s": 12.4}) == "Not detected: its snapshot is 12 s old"


def test_a_board_that_is_not_on_p3_is_told_beside_the_gddr6_switch(qtbot, tmp_path, monkeypatch):
    page, _settings = _page(qtbot, tmp_path, monkeypatch, bios="P2.00")
    note = page.gddr6_firmware_note
    assert not note.isHidden()
    assert "P2.00" in note.text() and "P3.00" in note.text()

    supported, _settings = _page(qtbot, tmp_path / "p3", monkeypatch, bios="P3.00")
    assert supported.gddr6_firmware_note.isHidden()
