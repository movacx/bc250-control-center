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
