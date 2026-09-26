"""F4 shows and hides the console, the way it does Dolphin's terminal panel.

Opening an empty panel gives the user their own shell rather than a blank
box. That shell belongs to the user, not to a workflow: it must never make
the panel "busy", never ask for confirmation when the window closes, never
be handed a workflow, and ``exit`` in it closes the panel.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from frontends.desktop.console.console_panel import ConsolePanel
from frontends.desktop.console.user_shell import shell_environment, user_shell


@pytest.fixture
def panel(qtbot, monkeypatch):
    # A predictable, quiet shell: no user rc files, no prompt theme.
    monkeypatch.setenv("SHELL", "/bin/sh")
    monkeypatch.setenv("ENV", "")
    host = QWidget()
    host.resize(1100, 900)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QWidget(host), 1)
    widget = ConsolePanel(host)
    layout.addWidget(widget)
    qtbot.addWidget(host)
    host.show()
    yield widget
    widget.shutdown()


def test_f4_on_an_empty_panel_opens_the_users_shell(qtbot, panel):
    panel.toggle()

    assert panel.shown
    tab = panel.active_tab
    assert tab.interactive and tab.running
    # The shell is the user's, not a workflow in progress.
    assert panel.busy is False
    assert panel.running_count() == 0
    assert panel.stop_button.isEnabled() is False
    assert tab.close_button.isVisibleTo(tab)


def test_f4_again_hides_it_and_keeps_the_shell_for_next_time(qtbot, panel):
    panel.toggle()
    shell_tab = panel.active_tab
    qtbot.waitUntil(lambda: panel.is_open, timeout=2000)

    panel.toggle()
    assert panel.shown is False
    qtbot.waitUntil(lambda: not panel.isVisible(), timeout=2000)
    assert shell_tab.running

    panel.toggle()
    assert panel.shown
    assert panel.active_tab is shell_tab


def test_a_quick_double_press_closes_what_it_opened(qtbot, panel):
    """The slide is animated; intent, not the live height, decides."""
    panel.toggle()
    panel.toggle()
    assert panel.shown is False


def test_exit_in_the_shell_closes_the_panel_and_empties_the_tab(qtbot, panel):
    panel.toggle()
    tab = panel.active_tab
    qtbot.waitUntil(lambda: panel.is_open, timeout=2000)

    with qtbot.waitSignal(tab.shell_exited, timeout=10000):
        tab.send_input(b"exit\n")

    assert panel.shown is False
    assert tab.is_empty()
    assert tab.interactive is False


def test_a_workflow_never_takes_over_the_users_shell(qtbot, panel):
    panel.set_auto_hide(False)
    panel.toggle()
    shell_tab = panel.active_tab

    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        assert panel.run(["/bin/sh", "-c", "echo hecho"], title="Prueba")

    assert panel.active_tab is not shell_tab
    assert shell_tab.running and shell_tab.interactive
    assert panel.tab_count() == 2


def test_f4_shows_a_finished_workflow_instead_of_replacing_it(qtbot, panel):
    """Output that was just produced is what F4 should bring back."""
    panel.set_auto_hide(False)
    with qtbot.waitSignal(panel.workflow_finished, timeout=15000):
        assert panel.run(["/bin/sh", "-c", "exit 3"], title="Fallo")
    panel.slide_out()

    panel.toggle()

    assert panel.active_tab.title == "Fallo"
    assert panel.active_tab.interactive is False


def test_the_shell_environment_drops_what_the_launcher_added():
    root = Path("/opt/bc250-control-center")
    env = {
        "PYTHONPATH": os.pathsep.join([str(root / "src"), "/home/u/lib"]),
        "HOME": "/home/u",
    }
    cleaned = shell_environment(env, application_root=root)
    assert cleaned["PYTHONPATH"] == "/home/u/lib"
    assert cleaned["HOME"] == "/home/u"

    only_ours = shell_environment({"PYTHONPATH": str(root / "src")}, application_root=root)
    assert "PYTHONPATH" not in only_ours


def test_a_shell_variable_that_is_not_a_listed_shell_is_ignored(tmp_path):
    shells = tmp_path / "shells"
    shells.write_text("/bin/sh\n# comment\n", encoding="utf-8")
    fake = tmp_path / "evil"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)

    chosen = user_shell({"SHELL": str(fake)}, shells_file=shells)

    assert chosen != str(fake)
    assert os.path.isabs(chosen)


def test_a_shell_line_editor_is_not_announced_as_a_password_prompt(qtbot, panel):
    """zsh, fish and readline clear ECHO while editing; that is no password."""
    panel.toggle()
    tab = panel.active_tab

    panel._on_input_mode_changed(tab, True)

    assert panel._masked is False
    assert "·" not in tab.state_label.text()
