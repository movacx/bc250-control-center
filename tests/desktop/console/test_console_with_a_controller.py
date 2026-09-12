"""Using the console with a controller, and staying out of its way.

Three separate faults showed up the first time a workflow ran in Game Mode:
the floating controller legend sat on top of the answer row and covered the
Send button, the grid was offered as a navigation stop even though a D-pad
cannot type into one, and the panel showed two places to type for a single
prompt — its own cursor and the answer row's.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

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
    widget.set_gamepad_present(True)
    widget._test_window = host
    yield widget
    widget.shutdown()


# ------------------------------------------------------------- where to land


def test_the_grid_is_not_offered_as_a_navigation_stop(panel):
    """A D-pad produces nothing the grid accepts; landing there is a dead end."""
    assert bool(panel.view.property("gamepadSkip"))


def test_a_running_workflow_puts_the_controller_on_the_answer_row(qtbot, panel):
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    assert panel.gamepad_focus_scope() is panel.input_field


def test_captured_text_puts_it_on_the_grid_instead(panel):
    """There is nothing to answer, so scrolling is the only thing left."""
    panel.show_text("solo lectura", title="Estado")
    assert panel.gamepad_focus_scope() is panel.view


def test_the_panel_takes_focus_where_it_can_be_used(qtbot, panel):
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    qtbot.waitUntil(lambda: panel.maximumHeight() == panel.panel_height(), timeout=4000)
    assert panel.input_field.hasFocus()


# ------------------------------------------------------------- one cursor only


def test_the_grid_stops_drawing_a_cursor_while_the_row_holds_the_keyboard(qtbot, panel):
    """Two cursors for one prompt, and one of them takes no input."""
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    qtbot.waitUntil(lambda: panel.input_field.hasFocus(), timeout=4000)
    assert panel.view._input_elsewhere is True
    assert panel.view.hasFocus() is False


def test_the_grid_gets_its_cursor_back_when_the_workflow_ends(qtbot, panel):
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        assert panel.run(["/bin/sh", "-c", "exit 0"], title="Prueba")
    assert panel.view._input_elsewhere is False


def test_clicking_into_the_grid_returns_its_cursor(qtbot, panel):
    """Suppression is about who holds the keyboard, not about hiding forever."""
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    qtbot.waitUntil(lambda: panel.input_field.hasFocus(), timeout=4000)
    panel.view.setFocus()
    qtbot.waitUntil(lambda: panel.view.hasFocus(), timeout=2000)
    # With focus the grid draws its own cursor again, suppressed or not.
    assert panel.view._input_elsewhere is True
    assert panel.view.hasFocus() is True


# ----------------------------------------------------------- the legend above


def test_the_window_reports_the_room_the_console_takes(qtbot):
    """The legend floats at a fixed offset from the bottom of the window."""
    from frontends.desktop.app import ControlCenterWindow

    inset = ControlCenterWindow.gamepad_bottom_inset

    class _Window:
        console = None

    assert inset(_Window()) == 0


def test_a_closed_console_reserves_nothing(qtbot, panel):
    from frontends.desktop.app import ControlCenterWindow

    class _Window:
        pass

    _Window.console = panel
    assert ControlCenterWindow.gamepad_bottom_inset(_Window()) == 0


def test_an_open_console_reserves_its_own_height(qtbot, panel):
    from frontends.desktop.app import ControlCenterWindow

    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    # ``is_open`` turns true on the first frame of the slide, when the panel
    # has a maximum height but the layout has not given it a real one yet —
    # reserving nothing at that instant is correct. What this pins is the
    # open panel, so wait for the animation the way its sibling above does.
    qtbot.waitUntil(lambda: panel.maximumHeight() == panel.panel_height(), timeout=4000)
    qtbot.waitUntil(lambda: panel.height() > 0, timeout=4000)

    class _Window:
        pass

    _Window.console = panel
    reserved = ControlCenterWindow.gamepad_bottom_inset(_Window())
    assert reserved == panel.height()
    assert reserved > 0


def test_the_navigation_asks_the_window_instead_of_assuming(qtbot):
    """Pins the seam: the legend must consult, not hard-code, the bottom edge."""
    from pathlib import Path

    source = Path("frontends/desktop/core/gamepad.py").read_text(encoding="utf-8")
    assert 'getattr(top, "gamepad_bottom_inset", None)' in source
    assert "- 18 - inset" in source


# --------------------------------------------------------------- the keypad


def test_the_answer_row_is_what_the_onscreen_keypad_can_open_for(panel):
    from PyQt6.QtWidgets import QAbstractSpinBox

    assert isinstance(panel.input_field, (QLineEdit, QAbstractSpinBox))
