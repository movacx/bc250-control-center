"""The console has to be dismissable on a machine with only a controller.

SteamOS Game Mode has no pointer. The console's header buttons are
deliberately unfocusable so that typing goes to the workflow rather than to
them, which means a controller cannot reach "Hide" — and the panel that stays
on screen is exactly the one whose workflow failed. Back is the gesture that
gets out of it.

A workflow still running is the deliberate exception: the panel is where it
reports, and a back press must not hide a privileged operation in flight.
"""

from __future__ import annotations

import pytest

from frontends.desktop.console.console_panel import ConsolePanel


@pytest.fixture
def panel(qtbot):
    widget = ConsolePanel()
    qtbot.addWidget(widget)
    widget.resize(900, 300)
    widget.set_auto_hide(False)
    yield widget
    widget.shutdown()


class _Window:
    """The part of the main window the back gesture touches."""

    def __init__(self, console):
        self.console = console
        self.navigated = False

    # Copied in behaviour from ControlCenterWindow.gamepad_back's first step.
    def gamepad_back(self):
        console = getattr(self, "console", None)
        if console is not None and console.is_open and not console.busy:
            console.slide_out()
            return
        self.navigated = True


def test_the_header_buttons_stay_out_of_the_keyboard_path(panel):
    """This is why the back gesture is needed, so pin the reason too."""
    from PyQt6.QtCore import Qt

    for button in (panel.stop_button, panel.copy_button,
                   panel.external_button, panel.hide_button):
        assert button.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_back_dismisses_a_finished_workflow(qtbot, panel):
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        assert panel.run(["/bin/sh", "-c", "echo listo"], title="Prueba")
    qtbot.waitUntil(lambda: panel.is_open, timeout=4000)

    window = _Window(panel)
    window.gamepad_back()
    assert window.navigated is False
    qtbot.waitUntil(lambda: panel.maximumHeight() == 0, timeout=4000)


def test_back_dismisses_a_failed_workflow(qtbot, panel):
    """The failing one stays on screen, so it is the one that traps a user."""
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000) as blocker:
        assert panel.run(["/bin/sh", "-c", "echo roto; exit 9"], title="Prueba")
    assert blocker.args[0] == 9
    qtbot.waitUntil(lambda: panel.is_open, timeout=4000)

    window = _Window(panel)
    window.gamepad_back()
    qtbot.waitUntil(lambda: panel.maximumHeight() == 0, timeout=4000)


def test_back_leaves_a_running_workflow_alone(qtbot, panel):
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    qtbot.waitUntil(lambda: panel.is_open, timeout=4000)

    window = _Window(panel)
    window.gamepad_back()
    assert panel.isVisible()
    assert window.navigated is True, "back must still navigate when the console keeps running"


def test_back_navigates_normally_when_the_console_is_closed(panel):
    window = _Window(panel)
    window.gamepad_back()
    assert window.navigated is True


def test_the_real_window_uses_this_rule(qtbot):
    """Pins that the behaviour above lives in the window, not only in a stub."""
    from pathlib import Path

    source = Path("frontends/desktop/app.py").read_text(encoding="utf-8")
    body = source[source.index("def gamepad_back"):]
    body = body[: body.index("def gamepad_cycle_section")]
    assert "console.is_open" in body
    assert "not console.busy" in body
    assert body.index("console.slide_out()") < body.index("self.stack.currentWidget()")


def test_game_mode_asks_for_a_shorter_panel():
    """280 px is a third of a handheld screen."""
    from pathlib import Path

    source = Path("frontends/desktop/app.py").read_text(encoding="utf-8")
    assert "200 if self._gamemode_session else 280" in source
