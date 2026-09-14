"""The console is offered to code that runs on a worker thread.

Every privileged workflow in this application is started from a background
worker so the interface stays responsive. Qt forbids touching widgets from
another thread, and the seam has to return a launch result synchronously
because thirty-seven call sites expect one. These tests hold that contract.
"""

from __future__ import annotations

import os
import time

import pytest
from PyQt6.QtCore import QThread

from bc250cc.infrastructure.terminal_repository import (
    EmbeddedTerminalRequest,
    TerminalRepository,
    embedded_terminal_launcher,
    set_embedded_terminal_launcher,
)
from frontends.desktop.console.console_host import EMBEDDED_TERMINAL_NAME, ConsoleHost
from frontends.desktop.console.console_panel import ConsolePanel


@pytest.fixture(autouse=True)
def _no_leftover_launcher():
    """A registry is global state; never let one test's host reach another."""
    set_embedded_terminal_launcher(None)
    yield
    set_embedded_terminal_launcher(None)


@pytest.fixture
def host(qtbot):
    panel = ConsolePanel()
    qtbot.addWidget(panel)
    panel.resize(900, 300)
    panel.set_auto_hide(False)
    bridge = ConsoleHost(panel)
    yield bridge
    bridge.uninstall()
    panel.shutdown()


def request(**overrides) -> EmbeddedTerminalRequest:
    values = dict(
        argv=("/bin/sh", "-c", "echo listo"),
        title="Instalar Cyan",
        status_file="/tmp/bc250-status",
        log_file="/tmp/bc250-log",
        launch_file="/tmp/bc250-launch.sh",
    )
    values.update(overrides)
    return EmbeddedTerminalRequest(**values)


# ------------------------------------------------------------------ registry


def test_installing_makes_the_repositories_reach_the_panel(host):
    assert embedded_terminal_launcher() is None
    host.install()
    assert embedded_terminal_launcher() is not None
    host.uninstall()
    assert embedded_terminal_launcher() is None


def test_a_launch_returns_the_same_evidence_a_terminal_window_would(qtbot, host):
    result = host.launch(request())
    assert result is not None
    assert result.terminal == EMBEDDED_TERMINAL_NAME
    assert result.title == "Instalar Cyan"
    assert result.status_file == "/tmp/bc250-status"
    assert result.log_file == "/tmp/bc250-log"
    assert isinstance(result.pid, int)


def test_a_disabled_console_declines_so_a_terminal_window_opens(host):
    host.set_enabled(False)
    assert host.enabled is False
    assert host.launch(request()) is None


def test_a_second_workflow_gets_a_tab_instead_of_a_terminal_window(qtbot, host):
    """This is what the tabs are for.

    Preparing dependencies and then opening something else used to put a
    terminal emulator of the desktop on top of the application, because the
    one embedded terminal was taken. Both workflows belong inside the window.
    """
    assert host.launch(request(argv=("/bin/sleep", "300"))) is not None
    assert host.launch(request(argv=("/bin/sleep", "300"), title="segunda")) is not None
    assert host._panel.tab_count() == 2
    assert host._panel.running_count() == 2


def test_the_console_still_declines_once_every_tab_is_taken(qtbot, host):
    """The terminal-window fallback is the floor, not the first answer.

    Each tab holds a pseudo-terminal of its own, so the strip has a ceiling.
    Past it the request is declined exactly as the whole console used to be,
    and the caller opens a window rather than losing the workflow.
    """
    from frontends.desktop.console.console_panel import MAXIMUM_TABS

    for index in range(MAXIMUM_TABS):
        assert host.launch(
            request(argv=("/bin/sleep", "300"), title=f"w{index}")
        ) is not None
    assert host.launch(request(argv=("/bin/sleep", "300"), title="extra")) is None


def test_a_panel_that_raises_declines_instead_of_losing_the_workflow(host):
    class _Broken:
        def run(self, *args, **kwargs):
            raise RuntimeError("the panel is broken")

        def session_pid(self):
            return None

    broken = ConsoleHost(_Broken())
    assert broken.launch(request()) is None


def test_a_host_without_a_panel_declines(host):
    assert ConsoleHost(None).launch(request()) is None


# -------------------------------------------------------------------- threads


class _WorkerLaunch(QThread):
    """Exactly what a repository does: call the seam off the interface thread."""

    def __init__(self, host, payload):
        super().__init__()
        self.host = host
        self.payload = payload
        self.result = None
        self.error = None
        self.worker_thread_id = None

    def run(self):  # noqa: D102 - QThread entry point
        self.worker_thread_id = int(QThread.currentThreadId())
        try:
            self.result = self.host.launch(self.payload)
        except Exception as error:  # pragma: no cover - a failure is the report
            self.error = error


def test_a_worker_thread_can_start_a_workflow_in_the_panel(qtbot, host):
    worker = _WorkerLaunch(host, request())
    with qtbot.waitSignal(worker.finished, timeout=15000):
        worker.start()
    assert worker.error is None
    assert worker.result is not None
    assert worker.result.terminal == EMBEDDED_TERMINAL_NAME


def test_the_worker_really_was_another_thread(qtbot, host):
    worker = _WorkerLaunch(host, request())
    main_thread_id = int(QThread.currentThreadId())
    with qtbot.waitSignal(worker.finished, timeout=15000):
        worker.start()
    assert worker.worker_thread_id != main_thread_id


def test_the_widget_stays_on_the_thread_that_owns_it(qtbot, host):
    """The whole reason for the blocking queued call."""
    worker = _WorkerLaunch(host, request())
    with qtbot.waitSignal(worker.finished, timeout=15000):
        worker.start()
    assert host._panel.thread() is QThread.currentThread()
    assert host._panel.view.thread() is QThread.currentThread()


def test_the_worker_waits_for_the_answer_instead_of_guessing(qtbot, host):
    """A result of None would send the caller to a terminal window by mistake."""
    host.set_enabled(True)
    worker = _WorkerLaunch(host, request(argv=("/bin/sleep", "300")))
    with qtbot.waitSignal(worker.finished, timeout=15000):
        worker.start()
    assert worker.result is not None
    assert host._panel.busy


# ------------------------------------------------------- through the repository


def test_the_repository_routes_a_real_workflow_into_the_panel(qtbot, host, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    host.install()
    panel = host._panel
    with qtbot.waitSignal(panel.workflow_finished, timeout=20000) as blocker:
        result = TerminalRepository()._abrir_terminal("echo desde-el-panel", "Prueba")
    assert result.terminal == EMBEDDED_TERMINAL_NAME
    assert blocker.args[0] == 0
    assert "desde-el-panel" in panel.view.screen.full_text()


def test_the_status_and_log_files_are_written_exactly_as_before(qtbot, host, tmp_path, monkeypatch):
    """Pages poll the status file to know a workflow finished; that must hold."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    host.install()
    panel = host._panel
    with qtbot.waitSignal(panel.workflow_finished, timeout=20000):
        result = TerminalRepository()._abrir_terminal("echo evidencia; exit 5", "Prueba")

    deadline = time.time() + 5
    while time.time() < deadline and not os.path.exists(result.status_file):
        qtbot.wait(50)
    assert os.path.exists(result.status_file)
    assert open(result.status_file).read().strip() == "5"
    assert os.path.exists(result.log_file)
    assert "evidencia" in open(result.log_file).read()


def test_a_docked_workflow_does_not_wait_for_a_key_press(qtbot, host, tmp_path, monkeypatch):
    """In a terminal window a prompt keeps the output readable; here it hangs."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    host.install()
    panel = host._panel
    with qtbot.waitSignal(panel.workflow_finished, timeout=20000):
        TerminalRepository()._abrir_terminal("echo hecho", "Prueba")
    assert "Enter to close" not in panel.view.screen.full_text()


def test_without_a_console_the_repository_still_looks_for_a_terminal(tmp_path, monkeypatch):
    """No host registered means the original behaviour, unchanged."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(
        TerminalRepository, "_launch_terminal_candidates",
        staticmethod(lambda candidates: ("kitty", 4321, [])),
    )
    result = TerminalRepository()._abrir_terminal("echo hola", "Prueba")
    assert result.terminal == "kitty"
    assert result.pid == 4321


def test_a_declining_console_falls_back_to_a_terminal_window(qtbot, host, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(
        TerminalRepository, "_launch_terminal_candidates",
        staticmethod(lambda candidates: ("konsole", 99, [])),
    )
    host.set_enabled(False)
    host.install()
    result = TerminalRepository()._abrir_terminal("echo hola", "Prueba")
    assert result.terminal == "konsole"


def test_the_workflow_script_the_panel_runs_is_the_reviewed_one(qtbot, host, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    seen: list[EmbeddedTerminalRequest] = []

    def capture(payload):
        seen.append(payload)
        return None

    set_embedded_terminal_launcher(capture)
    monkeypatch.setattr(
        TerminalRepository, "_launch_terminal_candidates",
        staticmethod(lambda candidates: ("kitty", 1, [])),
    )
    TerminalRepository()._abrir_terminal("echo revisado", "Prueba")
    assert len(seen) == 1
    assert seen[0].argv[0] == "bash"
    script = open(seen[0].argv[1]).read()
    assert "echo revisado" in script
    assert "tee" in script
    assert os.stat(seen[0].argv[1]).st_mode & 0o777 == 0o700
