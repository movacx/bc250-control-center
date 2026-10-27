"""Formal is the default look from 1.21.3, applied once to upgrades too."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from frontends.desktop.core.preferences import UiPreferences


def _settings(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_a_new_installation_starts_formal(tmp_path):
    preferences = UiPreferences(_settings(tmp_path))
    preferences.initialize()
    assert preferences.style() == "formal"


def test_an_upgrade_from_the_standard_look_is_moved_to_formal_once(tmp_path):
    settings = _settings(tmp_path)
    settings.setValue("settings/style", "standard")
    UiPreferences(settings).initialize()
    assert UiPreferences(settings).style() == "formal"


def test_a_standard_look_chosen_after_the_move_is_kept(tmp_path):
    settings = _settings(tmp_path)
    UiPreferences(settings).initialize()
    settings.setValue("settings/style", "standard")  # chosen in Settings
    UiPreferences(settings).initialize()  # next start
    assert UiPreferences(settings).style() == "standard"
