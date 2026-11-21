"""A new installation starts in the standard look; nothing forces formal."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from frontends.desktop.core.preferences import UiPreferences


def _settings(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_a_new_installation_starts_standard(tmp_path):
    preferences = UiPreferences(_settings(tmp_path))
    preferences.initialize()
    assert preferences.style() == "standard"


def test_a_formal_look_chosen_in_settings_is_kept(tmp_path):
    settings = _settings(tmp_path)
    UiPreferences(settings).initialize()
    settings.setValue("settings/style", "formal")
    UiPreferences(settings).initialize()  # next start
    assert UiPreferences(settings).style() == "formal"


def test_an_existing_standard_choice_is_not_moved_to_formal(tmp_path):
    settings = _settings(tmp_path)
    settings.setValue("settings/style", "standard")
    UiPreferences(settings).initialize()
    assert UiPreferences(settings).style() == "standard"


def test_settings_shows_the_style_the_app_actually_starts_in(tmp_path, qtbot, monkeypatch):
    """2026-11-21: a clean install ran in Standard while Settings showed Formal selected."""
    from frontends.desktop.pages import settings as settings_module
    from frontends.desktop.pages.settings import SettingsPage

    class _Service:
        def read_local_config(self):
            return {}

    class _Activity:
        def clear(self):
            return None

    monkeypatch.setattr(settings_module, "board_bios_version", lambda: "P3.00")
    stored = _settings(tmp_path)
    page = SettingsPage(object(), settings_service=_Service(), activity_service=_Activity(), app_settings=stored)
    qtbot.addWidget(page)
    page._ensure_section("appearance")
    control = page.controls["settings/style"]
    shown = control.currentData() if hasattr(control, "currentData") else control.value()
    assert shown == UiPreferences(stored).style() == "standard"
