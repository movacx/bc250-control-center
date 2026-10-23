"""The report button glows softly by default, rests when hidden, and obeys Settings."""

from __future__ import annotations

from PyQt6.QtCore import QAbstractAnimation

from frontends.desktop.components.dashboard_widgets import DashboardFooter


def test_the_glow_runs_while_shown_and_stops_with_the_switch(qtbot):
    footer = DashboardFooter()
    qtbot.addWidget(footer)
    button = footer.report_button
    footer.set_report_glow(True)
    footer.show()
    qtbot.waitExposed(footer)
    assert button.glowing()
    assert button._glow.state() == QAbstractAnimation.State.Running

    footer.hide()
    assert button._glow.state() == QAbstractAnimation.State.Stopped
    footer.show()
    assert button._glow.state() == QAbstractAnimation.State.Running

    footer.set_report_glow(False)
    assert not button.glowing()
    assert button._glow.state() == QAbstractAnimation.State.Stopped
    assert button._level == 0.0


def test_the_glow_is_on_unless_settings_switch_it_off(monkeypatch):
    from frontends.desktop.core import preferences

    class Stored:
        def __init__(self, value=None):
            self.value_ = value

        def value(self, _key, default):
            return default if self.value_ is None else self.value_

    monkeypatch.setattr(preferences, "application_settings", lambda: Stored())
    assert preferences.report_glow_enabled()
    monkeypatch.setattr(preferences, "application_settings", lambda: Stored("false"))
    assert not preferences.report_glow_enabled()


def test_an_error_window_glows_like_the_dashboard_and_stops_once_pressed(qtbot, monkeypatch):
    from frontends.desktop.components import widgets
    from frontends.desktop.components.outline_glow import OutlineGlow

    monkeypatch.setattr(widgets, "report_glow_enabled", lambda: True)
    button = widgets.ReportButton("Report this problem")
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)
    assert button.glowing()
    assert isinstance(button._outline, OutlineGlow)
    assert button._outline.cycle.state() == QAbstractAnimation.State.Running

    button.click()
    assert not button.glowing()
    assert button._outline.cycle.state() == QAbstractAnimation.State.Stopped


def test_the_settings_switch_also_quiets_error_windows(qtbot, monkeypatch):
    from frontends.desktop.components import widgets

    monkeypatch.setattr(widgets, "report_glow_enabled", lambda: False)
    button = widgets.ReportButton("Report this problem")
    qtbot.addWidget(button)
    button.show()
    assert not button.glowing()
