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
