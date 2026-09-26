"""A finished workflow's output stays on screen unless the user asked otherwise."""

from frontends.desktop.console.console_panel import ConsolePanel


def test_a_successful_workflow_does_not_hide_the_terminal_by_default(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel._on_finished(panel.active_tab, 0)
    assert not panel._auto_hide_timer.isActive()


def test_the_setting_still_hides_it_when_chosen(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.set_auto_hide(True)
    panel._on_finished(panel.active_tab, 0)
    assert panel._auto_hide_timer.isActive()
    panel._auto_hide_timer.stop()
