"""The in-screen console: what a job prints, and a command with a keyboard."""

import time

from frontends.tui.console import Console


def test_console_handles_carriage_returns_ansi_and_tabs_like_a_terminal():
    console = Console("x")
    console.write("\x1b[1;32mprogress 10%\x1b[0m\rprogress 90%\nnext\tcol\n")
    lines = console.snapshot()
    assert lines[0] == "progress 90%" and lines[1].startswith("next") and "\x1b" not in "".join(lines)


def test_console_keeps_only_the_latest_lines():
    console = Console("x")
    for index in range(6000):
        console.write(f"line {index}\n")
    assert len(console.snapshot()) <= 5000 and console.snapshot()[-2] == "line 5999"


def test_a_command_runs_on_a_pty_and_its_output_arrives_in_the_console():
    console = Console("cmd")
    status = console.run_command("echo hello; echo oops >&2; exit 3")
    text = "\n".join(console.snapshot())
    assert status == 3 and "hello" in text and "oops" in text


def test_the_keyboard_reaches_a_command_that_asks_a_question():
    console = Console("ask")
    import threading

    result = {}
    thread = threading.Thread(target=lambda: result.update(status=console.run_command('read -p "name? " n; echo "hi $n"')))
    thread.start()
    deadline = time.monotonic() + 5
    while console.input_fd is None and time.monotonic() < deadline:
        time.sleep(0.02)
    while "name?" not in "\n".join(console.snapshot()) and time.monotonic() < deadline:
        time.sleep(0.02)
    console.send(b"bob\n")
    thread.join(5)
    assert result["status"] == 0 and "hi bob" in "\n".join(console.snapshot())


def test_the_interactive_run_shows_workflow_output_in_the_screen_instead_of_leaving_it(monkeypatch):
    from frontends.tui.pages import build_pages
    from frontends.tui.screen import Screen

    from .fakes import make_context
    from .test_screen import FakeWindow

    monkeypatch.setenv("DISPLAY", ":0")
    class Patient(FakeWindow):
        """Idle polls (-1) until the job is done, then the Esc that closes the console."""

        def getch(self):
            time.sleep(0.02)
            if self.screen.active_console is not None and self.screen.active_console.done.is_set():
                return 27
            return -1

    window = Patient()
    screen = Screen(window, make_context(), build_pages(), None)
    window.screen = screen

    def work():
        screen.execute("echo from-the-workflow")
        return "done"

    ok, result = screen.run("Workflow", work)
    assert ok and result == "done"
    assert "from-the-workflow" in window.text()
