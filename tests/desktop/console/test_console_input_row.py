"""Answering a workflow with a controller, and saying when a secret is asked.

A D-pad produces nothing a terminal grid accepts, so Game Mode needs a real
text field to answer from — and it needs to say what is being asked, because a
password prompt shows no characters even while it is receiving them. That is
what this row is for, and why it appears only while a controller is connected.
The keyboard case is in ``test_console_without_a_controller``.

The mode is not guessed from the output. A program that wants a secret clears
the terminal's ECHO flag, and the master side of the pty can be asked, so the
field follows the program rather than the wording of a prompt in one language.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QLineEdit, QVBoxLayout, QWidget


@pytest.fixture
def panel(qtbot):
    from frontends.desktop.console.console_panel import ConsolePanel

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
    # This file is about the row, and the row is what a controller answers
    # from. Without one there is no row — see test_console_without_a_controller.
    widget.set_gamepad_present(True)
    yield widget
    widget.shutdown()


# ------------------------------------------------------------------ presence


def test_the_row_is_hidden_until_something_is_listening(panel):
    assert panel.input_row.isVisible() is False


def test_the_row_appears_while_a_workflow_runs(qtbot, panel):
    assert panel.run(["/bin/sleep", "300"], title="Prueba")
    assert panel.input_row.isVisible()
    assert panel.input_field.isEnabled()


def test_the_row_goes_away_when_the_workflow_ends(qtbot, panel):
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        assert panel.run(["/bin/sh", "-c", "exit 0"], title="Prueba")
    assert panel.input_row.isVisible() is False


def test_the_field_is_emptied_when_the_workflow_ends(qtbot, panel):
    assert panel.run(["/bin/sleep", "300"])
    panel.input_field.setText("a medio escribir")
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        panel.stop_button.click()
    assert panel.input_field.text() == ""


# -------------------------------------------------------------------- typing


def test_what_the_field_sends_reaches_the_process(qtbot, panel):
    program = "read -r value; printf 'recibido:%s\\n' \"$value\""
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        assert panel.run(["/bin/sh", "-c", program], title="Prueba")
        qtbot.wait(250)
        panel.input_field.setText("cyan")
        panel.send_button.click()
    assert "recibido:cyan" in panel.view.screen.full_text()


def test_enter_sends_the_same_as_the_button(qtbot, panel):
    program = "read -r value; printf 'recibido:%s\\n' \"$value\""
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        assert panel.run(["/bin/sh", "-c", program], title="Prueba")
        qtbot.wait(250)
        panel.input_field.setText("oberon")
        panel.input_field.returnPressed.emit()
    assert "recibido:oberon" in panel.view.screen.full_text()


def test_the_field_clears_after_sending(qtbot, panel):
    assert panel.run(["/bin/sh", "-c", "read -r a; sleep 300"])
    qtbot.wait(250)
    panel.input_field.setText("algo")
    panel.send_button.click()
    assert panel.input_field.text() == ""


def test_sending_with_nothing_running_does_nothing(panel):
    panel.input_field.setText("al vacio")
    panel._send_typed_input()  # must not raise


# ------------------------------------------------------------ password prompts


def test_the_field_hides_what_a_password_prompt_asks_for(qtbot, panel):
    """The real shape of a sudo prompt: echo off, then a read."""
    program = (
        "printf 'normal: '; read -r a; "
        "stty -echo; printf 'contrasena: '; read -r b; stty echo; "
        "printf '\\nrecibido:%s\\n' \"$b\"; sleep 300"
    )
    assert panel.run(["/bin/sh", "-c", program], title="Prueba")
    qtbot.waitUntil(lambda: "normal:" in panel.view.screen.full_text(), timeout=8000)
    assert panel.input_field.echoMode() == QLineEdit.EchoMode.Normal

    panel.input_field.setText("visible")
    panel.send_button.click()

    qtbot.waitUntil(lambda: panel.input_field.echoMode() == QLineEdit.EchoMode.Password,
                    timeout=8000)
    assert panel.input_row.property("mode") == "secret"


def test_the_label_says_which_password_is_being_asked_for(qtbot, panel):
    program = "stty -echo; printf 'clave: '; read -r b; stty echo; sleep 300"
    assert panel.run(["/bin/sh", "-c", program], title="Prueba")
    qtbot.waitUntil(
        lambda: panel.input_field.echoMode() == QLineEdit.EchoMode.Password, timeout=8000
    )
    assert panel.input_label.text().strip()
    assert panel.input_field.placeholderText().strip()


def test_a_secret_reaches_the_process_unaltered(qtbot, panel):
    program = (
        "stty -echo; read -r secreto; stty echo; "
        "printf 'largo:%s\\n' \"${#secreto}\"; printf 'valor:%s\\n' \"$secreto\""
    )
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        assert panel.run(["/bin/sh", "-c", program], title="Prueba")
        qtbot.waitUntil(
            lambda: panel.input_field.echoMode() == QLineEdit.EchoMode.Password,
            timeout=8000,
        )
        panel.input_field.setText("cláve-ñ-42")
        panel.send_button.click()
    text = panel.view.screen.full_text()
    assert "valor:cláve-ñ-42" in text
    assert "largo:10" in text


def test_the_field_returns_to_plain_text_when_the_prompt_is_over(qtbot, panel):
    program = (
        "stty -echo; read -r b; stty echo; printf 'de nuevo: '; read -r c; sleep 300"
    )
    assert panel.run(["/bin/sh", "-c", program], title="Prueba")
    qtbot.waitUntil(
        lambda: panel.input_field.echoMode() == QLineEdit.EchoMode.Password, timeout=8000
    )
    panel.input_field.setText("secreto")
    panel.send_button.click()
    qtbot.waitUntil(
        lambda: panel.input_field.echoMode() == QLineEdit.EchoMode.Normal, timeout=8000
    )
    assert panel.input_row.property("mode") == "plain"


def test_a_workflow_that_never_asks_stays_in_plain_mode(qtbot, panel):
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        assert panel.run(["/bin/sh", "-c", "echo hola"], title="Prueba")
    assert panel.input_field.echoMode() == QLineEdit.EchoMode.Normal


def test_a_new_workflow_starts_from_plain_mode(qtbot, panel):
    """A leftover masked field would hide input the next workflow does show."""
    program = "stty -echo; read -r b; stty echo"
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        assert panel.run(["/bin/sh", "-c", program], title="Primera")
        qtbot.waitUntil(
            lambda: panel.input_field.echoMode() == QLineEdit.EchoMode.Password,
            timeout=8000,
        )
        panel.input_field.setText("x")
        panel.send_button.click()
    assert panel.run(["/bin/sleep", "300"], title="Segunda")
    assert panel.input_field.echoMode() == QLineEdit.EchoMode.Normal


# --------------------------------------------------------------- a controller


def test_the_field_is_the_kind_of_widget_the_onscreen_keypad_opens_for(panel):
    """Game Mode has no keyboard; the keypad only triggers on a text field.

    The terminal grid is a scroll area, so typing into it directly is
    unreachable with a controller. This row is what makes the console usable
    there at all.
    """
    from PyQt6.QtWidgets import QAbstractSpinBox

    assert isinstance(panel.input_field, (QLineEdit, QAbstractSpinBox))
    assert panel.input_field.focusPolicy() != panel.input_field.focusPolicy().NoFocus


# ------------------------------------------------------- captured output only


def test_captured_text_shows_without_anything_listening(qtbot, panel):
    assert panel.show_text("linea uno\nlinea dos\n", title="Estado")
    # The panel slides; it is open once the animation has run, not before.
    qtbot.waitUntil(lambda: panel.is_open, timeout=4000)
    assert panel.busy is False
    assert "linea uno" in panel.view.screen.full_text()
    assert "linea dos" in panel.view.screen.full_text()


def test_captured_text_offers_no_place_to_type(panel):
    """There is no process on the other side, so the row must stay away."""
    panel.show_text("solo lectura", title="Estado")
    assert panel.input_row.isVisible() is False
    assert panel.view.screen.cursor_visible is False
    assert panel.stop_button.isEnabled() is False


def test_captured_text_keeps_its_line_breaks(panel):
    panel.show_text("a\r\nb\nc", title="Estado")
    visible = [line for line in panel.view.screen.full_text().splitlines() if line]
    assert visible == ["a", "b", "c"]


def test_captured_text_never_lands_on_a_running_workflow(qtbot, panel):
    """A running workflow owns its grid; its output must not be replaced.

    It used to be refused outright, because there was one terminal. With a
    strip it gets a tab of its own instead, and the workflow keeps both its
    output and its place.
    """
    assert panel.run(["/bin/sh", "-c", "echo del-flujo; sleep 300"], title="Prueba")
    running = panel.active_tab
    qtbot.waitUntil(
        lambda: "del-flujo" in running.view.screen.full_text(), timeout=8000
    )

    assert panel.show_text("otra cosa", title="Estado")

    assert panel.active_tab is not running
    assert running.title == "Prueba"
    assert "del-flujo" in running.view.screen.full_text()
    assert "otra cosa" not in running.view.screen.full_text()
    panel.shutdown()


def test_a_workflow_after_captured_text_gets_its_cursor_back(qtbot, panel):
    panel.show_text("estado previo", title="Estado")
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        assert panel.run(["/bin/sh", "-c", "echo nuevo"], title="Prueba")
    assert panel.view.screen.cursor_visible is True
    assert "estado previo" not in panel.view.screen.full_text()
