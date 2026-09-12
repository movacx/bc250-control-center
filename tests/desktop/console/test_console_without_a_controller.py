"""With a keyboard, the console is a terminal — not a form.

``TerminalView`` was always a complete input path: it handles arrows, Ctrl+C,
function keys, application-cursor mode and bracketed paste, and forwards every
one of them to the pty. The answer row was never needed to type; it was added
because a password prompt shows no characters and looked like a frozen panel.

A controller does need it — a D-pad can produce nothing the grid accepts — so
the row now appears only while one is connected. What this file pins is the
other half: with a keyboard nothing stands between the user and the terminal,
and a hidden prompt still says it is waiting.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from frontends.desktop.console.console_panel import ConsolePanel


@pytest.fixture
def panel(qtbot):
    host = QWidget()
    host.resize(1100, 900)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QWidget(host), 1)
    widget = ConsolePanel(host)
    layout.addWidget(widget)
    qtbot.addWidget(host)
    host.show()
    widget.set_auto_hide(False)
    widget._test_window = host
    yield widget
    widget.shutdown()


# --------------------------------------------------------------- no row at all


def test_a_workflow_with_no_controller_shows_no_answer_row(qtbot, panel):
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    assert panel.input_row.isVisible() is False


def test_the_keyboard_lands_on_the_grid(qtbot, panel):
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    qtbot.waitUntil(lambda: panel.maximumHeight() == panel.panel_height(), timeout=4000)
    assert panel.gamepad_focus_scope() is panel.view
    assert panel.view.hasFocus()


def test_the_grid_keeps_its_own_cursor(qtbot, panel):
    """``set_input_elsewhere`` suppresses it, and nothing is elsewhere."""
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    assert panel.view._input_elsewhere is False


def test_the_grid_gets_the_room_the_row_is_not_using(panel):
    with_row = panel._grid_height(with_input=True)
    without_row = panel._grid_height(with_input=False)
    assert without_row > with_row


# ------------------------------------------------------------ typing reaches it


def test_what_is_typed_into_the_grid_reaches_the_process(qtbot, panel):
    """The path the row was covering: keyPressEvent -> input_ready -> pty."""
    assert panel.run(["/bin/cat"], title="Prueba")
    sent: list[bytes] = []
    panel.view.input_ready.connect(sent.append)
    panel.view.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a")
    )
    assert sent == [b"a"]


def test_enter_reaches_the_process_too(qtbot, panel):
    assert panel.run(["/bin/cat"], title="Prueba")
    sent: list[bytes] = []
    panel.view.input_ready.connect(sent.append)
    panel.view.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier, "\r")
    )
    assert sent == [b"\r"]


# ------------------------------------------------------ a secret still says so


def test_a_hidden_prompt_says_it_is_waiting(qtbot, panel):
    """Otherwise it is indistinguishable from a panel ignoring the keyboard."""
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    panel._set_input_masked(True)
    assert "·" in panel.state_label.text()
    assert panel.state_label.property("tone") == "warning"


def test_the_state_goes_back_when_the_prompt_does(qtbot, panel):
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    panel._set_input_masked(True)
    secret = panel.state_label.text()
    panel._set_input_masked(False)
    assert panel.state_label.text() != secret
    assert panel.state_label.property("tone") == "running"


def test_a_stopping_workflow_is_not_relabelled_as_running(qtbot, panel):
    """The echo watcher polls every 120 ms and must not own the whole label.

    ``_stop_workflow`` sets "Stop" while the process is still running. A
    password prompt ending right afterwards would otherwise quietly relabel a
    stopping workflow as a running one.
    """
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    panel._stop_workflow()
    stopping = panel.state_label.text()
    panel._set_input_masked(False)
    assert panel.state_label.text() == stopping


def test_the_grid_holds_the_keyboard_during_a_secret(qtbot, panel):
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    qtbot.waitUntil(lambda: panel.maximumHeight() == panel.panel_height(), timeout=4000)
    panel._set_input_masked(True)
    assert panel.view.hasFocus()
    assert panel.input_field.hasFocus() is False


# ------------------------------------------------------------------- hot plug


def test_plugging_a_controller_in_mid_workflow_brings_the_row(qtbot, panel):
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    assert panel.input_row.isVisible() is False
    panel.set_gamepad_present(True)
    assert panel.input_row.isVisible() is True
    assert panel.view._input_elsewhere is True
    assert panel.gamepad_focus_scope() is panel.input_field


def test_unplugging_it_gives_the_keyboard_back_to_the_grid(qtbot, panel):
    panel.set_gamepad_present(True)
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    panel.set_gamepad_present(False)
    assert panel.input_row.isVisible() is False
    assert panel.view._input_elsewhere is False
    assert panel.gamepad_focus_scope() is panel.view


def test_a_half_typed_answer_does_not_survive_the_controller_leaving(qtbot, panel):
    """It would be typed into a field nobody can see and nobody will send."""
    panel.set_gamepad_present(True)
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    panel.input_field.setText("a medias")
    panel.set_gamepad_present(False)
    assert panel.input_field.text() == ""


def test_the_grid_is_resized_when_the_row_comes_and_goes(qtbot, panel):
    """The grid is measured against the chrome around it.

    Changing which chrome exists without re-measuring either hides the last
    line behind the row or leaves a dead band where it used to be.
    """
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    panel.set_gamepad_present(True)
    with_row = panel.view._expected_height
    panel.set_gamepad_present(False)
    assert panel.view._expected_height > with_row


def test_the_controller_arriving_before_any_workflow_is_remembered(qtbot, panel):
    panel.set_gamepad_present(True)
    assert panel.input_row.isVisible() is False, "nothing is listening yet"
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    assert panel.input_row.isVisible() is True


# ------------------------------------------------- the window makes the link


def test_the_window_connects_the_controller_to_the_console():
    """Pins the seam: without this the console never learns a controller exists."""
    from pathlib import Path

    source = Path("frontends/desktop/app.py").read_text(encoding="utf-8")
    assert "_follow_controller_into_the_console" in source
    assert "self.gamepad.connection_changed.connect(" in source
    # A controller already plugged in when the window opens emits nothing.
    assert "console.set_gamepad_present(self.gamepad.connected)" in source
