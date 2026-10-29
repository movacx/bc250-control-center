"""The console pane: a job's output, commands on a pty, and workflows that never leave the screen."""

import threading
import time

import pytest

from frontends.tui.console import Console


def text(console):
    return "\n".join("".join(run[0] for run in line) for line in console.view(1000)[0])


def wait_for(predicate, seconds=5.0):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.02)
    return predicate()


def test_progress_redraws_colours_and_print_output_read_like_a_terminal():
    console = Console("x", 10, 40)
    console._feed("progress 10%\rprogress 90%\r\n\x1b[1;32mOK\x1b[0m next\tcol\r\n")
    print("from python", file=console)
    lines = console.view(1000)[0]
    assert "".join(r[0] for r in lines[0]).rstrip() == "progress 90%"
    assert lines[1][0] == ("OK", "ok", True)  # green and bold survive as a tone
    assert "from python" in text(console) and "\x1b" not in text(console)


def test_a_command_runs_on_a_pty_and_writes_the_workflow_log(tmp_path):
    console = Console("cmd")
    log = tmp_path / "workflow.log"
    status = console.run(["bash", "-c", "echo hello; echo oops >&2; exit 3"], str(log))
    assert status == 3 and "hello" in text(console) and "oops" in text(console)
    assert "hello" in log.read_text()


def test_the_keyboard_reaches_a_command_that_asks_a_question():
    console = Console("ask")
    result = {}
    thread = threading.Thread(target=lambda: result.update(
        status=console.run(["bash", "-c", 'read -p "name? " n; echo "hi $n"'])))
    thread.start()
    assert wait_for(lambda: "name?" in text(console))
    console.send(b"bob\r")
    thread.join(5)
    assert result["status"] == 0 and "hi bob" in text(console)


def test_ctrl_c_interrupts_the_running_command_not_the_interface():
    console = Console("long")
    result = {}
    thread = threading.Thread(target=lambda: result.update(status=console.run(["bash", "-c", "echo go; sleep 30"])))
    thread.start()
    assert wait_for(lambda: "go" in text(console))
    console.interrupt()
    thread.join(5)
    assert not thread.is_alive() and result["status"] != 0


class Patient:
    """A curses window that idles until the console job is done, then closes it with Esc."""

    def __init__(self):
        from .test_screen import FakeWindow

        self.window = FakeWindow()
        self.screen = None

    def __getattr__(self, name):
        return getattr(self.window, name)

    def getch(self):
        time.sleep(0.02)
        console = self.screen.active_console
        if console is None or not console.done.is_set():
            return -1
        self.seen = getattr(self, "seen", 0) + 1  # one redraw after the end, as a person would see it
        return 27 if self.seen > 1 else -1


@pytest.fixture
def screen():
    from frontends.tui.pages import build_pages
    from frontends.tui.screen import Screen

    from .fakes import make_context

    window = Patient()
    window.screen = Screen(window, make_context(), build_pages(), None)
    return window.screen


def test_a_repository_workflow_runs_inside_the_screen_never_in_a_terminal_emulator(screen, tmp_path, monkeypatch):
    from bc250cc.application.system.workflow_console import (
        set_embedded_terminal_launcher,
    )
    from bc250cc.infrastructure.terminal_repository import TerminalRepository

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    launched = []
    monkeypatch.setattr(TerminalRepository, "_launch_terminal_candidates",
                        staticmethod(lambda candidates: launched.append(candidates) or ("", None, [])))
    set_embedded_terminal_launcher(screen.launch_workflow)
    try:
        ok, result = screen.run("Prepare", lambda: TerminalRepository()._abrir_terminal("echo from-the-workflow", "Prepare"))
    finally:
        set_embedded_terminal_launcher(None)
    assert ok and not launched
    assert result.terminal == "bc250-tui-console"
    assert "from-the-workflow" in screen.stdscr.window.text()
    assert (tmp_path / "bc250-control-center" / "terminal").exists()
    assert "0" in open(result.status_file).read()


def test_a_failing_workflow_marks_the_job_failed_and_keeps_its_output(screen):
    from types import SimpleNamespace

    request = SimpleNamespace(argv=("bash", "-c", "echo broken; exit 4"), title="x", status_file="", log_file="")
    ok, _result = screen.run("Broken", lambda: screen.launch_workflow(request))
    assert not ok and "broken" in screen.stdscr.window.text()


def test_without_a_console_on_screen_the_launcher_declines():
    from types import SimpleNamespace

    from frontends.tui.pages import build_pages
    from frontends.tui.screen import Screen

    from .fakes import make_context
    from .test_screen import FakeWindow

    screen = Screen(FakeWindow(), make_context(), build_pages(), None)
    assert screen.launch_workflow(SimpleNamespace(argv=("true",), title="", status_file="", log_file="")) is None
