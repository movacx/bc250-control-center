"""A theme, accent or density change restyles the window once, and only when needed.

Restyling means Qt re-applying a 96 KB style sheet to about 2 500 widgets:
over a second, longer with a game running. It used to run inside the click
-- the chosen option did not look selected until it finished -- once per
click, and again when the choice did not change anything on screen.
"""

from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QMainWindow

from frontends.desktop.app import ControlCenterWindow
from frontends.desktop.core.preferences import UiPreferences


class ThemedWindow(ControlCenterWindow):
    def __init__(self, settings: QSettings):
        QMainWindow.__init__(self)
        self.gamepad = None
        self._gamemode_session = False
        self.settings = settings
        self.preferences = UiPreferences(settings)
        self.pages = {}
        self.restyles = []

    def _system_theme(self) -> str:
        return "dark"

    def _save_backend_preference(self, key, value) -> None:
        pass

    def setStyleSheet(self, sheet: str) -> None:  # noqa: N802 - Qt API
        self.restyles.append(sheet)
        super().setStyleSheet(sheet)


def _window(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    window = ThemedWindow(settings)
    qtbot.addWidget(window)
    return window


def test_a_choice_that_changes_nothing_is_not_restyled(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._apply_appearance("dark", "blue", "comfortable")
    assert len(window.restyles) == 1

    window._apply_appearance("dark", "blue", "comfortable")
    # "System" resolving to the dark theme already shown is no change either,
    # but it is still remembered as the user's choice.
    window._apply_appearance("system", "blue", "comfortable")
    assert len(window.restyles) == 1
    assert window.settings.value("settings/appearance") == "system"

    window._apply_appearance("light", "blue", "comfortable")
    assert len(window.restyles) == 2


def test_quick_clicks_apply_once_after_the_click_has_painted(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._apply_appearance("dark", "blue", "comfortable")
    window.restyles.clear()

    window._queue_appearance("light", "blue", "comfortable")
    window._queue_appearance("light", "violet", "comfortable")
    window._queue_appearance("light", "violet", "compact")
    assert window.restyles == []  # nothing inside the click

    qtbot.waitUntil(lambda: len(window.restyles) == 1, timeout=2000)
    qtbot.wait(150)
    assert len(window.restyles) == 1
    assert window.settings.value("settings/density") == "compact"
    assert window.settings.value("settings/accent") == "violet"
