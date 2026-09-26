"""Settings, one subject per section, with switches that read as switches.

The General section had grown into everything at once: startup behaviour,
the GPU governor backend, the guided tour, the game controller and the
embedded terminal. Each now has its own section, and the keys of the
sections that already existed did not move, so other pages' links still land.
"""

from __future__ import annotations

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QLabel

from frontends.desktop.components.toggle_switch import ToggleSwitch
from frontends.desktop.pages.settings import SettingsPage


class _SettingsService:
    def read_local_config(self):
        return {"gpu_governor": "auto"}


class _ActivityService:
    def clear(self):
        return True


def _page(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    page = SettingsPage(object(), settings_service=_SettingsService(),
                        activity_service=_ActivityService(), app_settings=settings)
    qtbot.addWidget(page)
    return page, settings


def _labels(page, key):
    widget = page._ensure_section(key)
    return {label.text() for label in widget.findChildren(QLabel)}


def test_sections_keep_their_old_keys_and_gain_hardware_and_console(qtbot, tmp_path):
    page, _settings = _page(qtbot, tmp_path)
    assert page.section_order == [
        "general", "appearance", "hardware", "console",
        "telemetry", "security", "reports", "about",
    ]


def test_each_subject_lives_in_its_own_section(qtbot, tmp_path):
    page, _settings = _page(qtbot, tmp_path)
    general = _labels(page, "general")
    assert "Start page" in general and "Guided tour" in general
    assert "GPU governor backend" not in general
    assert "Gamepad navigation" not in general
    assert "Terminal inside the window" not in general

    assert "GPU governor backend" in _labels(page, "hardware")
    console = _labels(page, "console")
    assert {"Terminal inside the window", "Gamepad navigation",
            "Show or hide the terminal", "F4"} <= console


def test_settings_switches_are_real_switches_with_a_knob(qtbot, tmp_path):
    page, settings = _page(qtbot, tmp_path)
    page._ensure_section("general")
    switch = page.controls["settings/reopen_last_module"]
    assert isinstance(switch, ToggleSwitch)
    page.resize(900, 600)
    page.show()
    qtbot.waitUntil(switch.isVisible, timeout=2000)

    switch.setChecked(False)
    # Let the slide to "off" finish before measuring where "off" is.
    qtbot.waitUntil(lambda: switch._position == 0.0, timeout=2000)
    off = switch.knob_center().x()
    qtbot.mouseClick(switch, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: switch.knob_center().x() > off + 10, timeout=2000)

    assert switch.isChecked()
    assert settings.value("settings/reopen_last_module") == "true"
