"""The embedded console must be a terminal, not a pipe with a nice font.

The application runs 312 privileged steps that call plain ``sudo``. ``sudo``
reads the password from ``/dev/tty``; a pipe-backed process fails every one of
them. These tests run real child processes and assert the properties that make
the difference: a controlling tty, a window size, signal delivery to the whole
process group, and input that arrives.
"""

from __future__ import annotations

import os
import shutil
import sys

import pytest

from frontends.desktop.console.pty_session import PtySession

pytestmark = pytest.mark.skipif(
    not hasattr(os, "fork"), reason="a pseudo-terminal needs fork()"
)

PYTHON = sys.executable


def run(qtbot, argv, *, columns=80, rows=24, timeout=15000):
    """Start a command and return (collected output, exit code)."""
    session = PtySession()
    chunks: list[bytes] = []
    session.output.connect(chunks.append)
    with qtbot.waitSignal(session.finished, timeout=timeout) as blocker:
        assert session.start(argv, columns=columns, rows=rows)
    return b"".join(chunks).decode("utf-8", "replace"), blocker.args[0]


# ------------------------------------------------------------------- basics


def test_a_command_runs_and_its_output_arrives(qtbot):
    text, code = run(qtbot, ["/bin/echo", "governor ready"])
    assert "governor ready" in text
    assert code == 0


def test_the_exit_code_of_a_failing_command_is_reported(qtbot):
    _text, code = run(qtbot, ["/bin/sh", "-c", "exit 7"])
    assert code == 7


def test_a_command_that_does_not_exist_is_refused_before_anything_is_forked(qtbot):
    """Resolving the program in the parent turns exit 127 into a plain message."""
    session = PtySession()
    reports: list[str] = []
    session.failed.connect(reports.append)
    assert session.start(["/nonexistent/bc250-not-a-command"]) is False
    assert reports and "was not found" in reports[0]
    assert session.running is False


def test_a_program_on_PATH_is_found_without_an_absolute_path(qtbot):
    text, code = run(qtbot, ["echo", "sin ruta absoluta"])
    assert code == 0
    assert "sin ruta absoluta" in text


def test_starting_with_an_empty_command_reports_instead_of_raising(qtbot):
    session = PtySession()
    with qtbot.waitSignal(session.failed, timeout=2000):
        assert session.start([]) is False


def test_a_session_refuses_to_run_two_commands_at_once(qtbot):
    session = PtySession()
    assert session.start(["/bin/sleep", "5"])
    try:
        with pytest.raises(RuntimeError):
            session.start(["/bin/echo", "second"])
    finally:
        session.shutdown()


# ------------------------------------------------------- the terminal itself


def test_the_child_really_has_a_terminal_on_all_three_descriptors(qtbot):
    """This is the property that makes sudo and progress bars work at all."""
    program = (
        "import sys;"
        "print('tty', sys.stdin.isatty(), sys.stdout.isatty(), sys.stderr.isatty())"
    )
    text, code = run(qtbot, [PYTHON, "-c", program])
    assert "tty True True True" in text
    assert code == 0


def test_the_child_has_a_controlling_terminal_it_can_open(qtbot):
    """sudo opens /dev/tty directly; without a controlling terminal it fails."""
    program = "open('/dev/tty').close(); print('controlling terminal present')"
    text, code = run(qtbot, [PYTHON, "-c", program])
    assert "controlling terminal present" in text
    assert code == 0


def test_the_child_runs_in_its_own_session(qtbot):
    program = "import os; print('sid', os.getsid(0) == os.getpid())"
    text, _code = run(qtbot, [PYTHON, "-c", program])
    assert "sid True" in text


def test_the_requested_window_size_is_visible_to_the_child_from_the_start(qtbot):
    """Set before the fork, so nothing redraws itself at 80x24 first."""
    program = "import os; size = os.get_terminal_size(); print('size', size.columns, size.lines)"
    text, _code = run(qtbot, [PYTHON, "-c", program], columns=132, rows=43)
    assert "size 132 43" in text


def test_term_declares_the_capabilities_this_screen_implements(qtbot):
    program = "import os; print('term', os.environ['TERM'], os.environ.get('COLORTERM'))"
    text, _code = run(qtbot, [PYTHON, "-c", program])
    assert "term xterm-256color truecolor" in text


def test_a_pager_never_swallows_a_workflow(qtbot):
    program = "import os; print('pager', repr(os.environ.get('SYSTEMD_PAGER')), os.environ.get('PAGER'))"
    text, _code = run(qtbot, [PYTHON, "-c", program])
    assert "pager '' cat" in text


def test_the_environment_of_the_application_reaches_the_child(qtbot):
    session = PtySession()
    chunks: list[bytes] = []
    session.output.connect(chunks.append)
    environment = dict(os.environ, BC250_TEST_MARKER="present")
    program = "import os; print('marker', os.environ.get('BC250_TEST_MARKER'))"
    with qtbot.waitSignal(session.finished, timeout=15000):
        session.start([PYTHON, "-c", program], environment=environment)
    assert "marker present" in b"".join(chunks).decode()


# -------------------------------------------------------------------- input


def test_what_the_user_types_reaches_the_process(qtbot):
    session = PtySession()
    chunks: list[bytes] = []
    session.output.connect(chunks.append)
    program = "value = input('prompt: '); print('got', value.strip())"
    assert session.start([PYTHON, "-u", "-c", program])
    qtbot.waitUntil(lambda: b"prompt: " in b"".join(chunks), timeout=15000)
    with qtbot.waitSignal(session.finished, timeout=15000):
        session.write("cyan\r")
    assert "got cyan" in b"".join(chunks).decode()


def test_writing_to_a_finished_session_is_ignored(qtbot):
    session = PtySession()
    with qtbot.waitSignal(session.finished, timeout=15000):
        session.start(["/bin/true"])
    session.write("this goes nowhere")  # must not raise


# ------------------------------------------------------------------ resizing


def test_a_resize_reaches_the_running_child(qtbot):
    session = PtySession()
    chunks: list[bytes] = []
    session.output.connect(chunks.append)
    program = (
        "import os, signal, sys\n"
        "def report(*_):\n"
        "    size = os.get_terminal_size()\n"
        "    print('resized', size.columns, size.lines, flush=True)\n"
        "    sys.exit(0)\n"
        "signal.signal(signal.SIGWINCH, report)\n"
        "print('ready', flush=True)\n"
        "signal.pause()\n"
    )
    assert session.start([PYTHON, "-u", "-c", program], columns=80, rows=24)
    qtbot.waitUntil(lambda: b"ready" in b"".join(chunks), timeout=15000)
    with qtbot.waitSignal(session.finished, timeout=15000):
        session.resize(120, 40)
    assert "resized 120 40" in b"".join(chunks).decode()


def test_resizing_a_closed_session_does_nothing(qtbot):
    session = PtySession()
    session.resize(100, 30)  # must not raise


# ---------------------------------------------------------------- finishing


def test_terminate_stops_a_workflow_that_would_otherwise_never_end(qtbot):
    session = PtySession()
    assert session.start(["/bin/sleep", "300"])
    with qtbot.waitSignal(session.finished, timeout=15000) as blocker:
        session.terminate()
    assert blocker.args[0] < 0  # reported as a signal, not a clean exit
    assert session.running is False


def test_a_workflow_that_ignores_sigterm_is_still_stopped(qtbot):
    program = (
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "print('ignoring', flush=True)\n"
        "time.sleep(300)\n"
    )
    session = PtySession()
    chunks: list[bytes] = []
    session.output.connect(chunks.append)
    assert session.start([PYTHON, "-u", "-c", program])
    qtbot.waitUntil(lambda: b"ignoring" in b"".join(chunks), timeout=15000)
    with qtbot.waitSignal(session.finished, timeout=15000):
        session.kill()
    assert session.running is False


def test_a_helper_started_by_the_workflow_is_not_left_behind(qtbot):
    """Workflows start background helpers; the signal goes to the group."""
    session = PtySession()
    chunks: list[bytes] = []
    session.output.connect(chunks.append)
    script = "/bin/sleep 300 & echo helper $!; wait"
    assert session.start(["/bin/sh", "-c", script])
    qtbot.waitUntil(lambda: b"helper" in b"".join(chunks), timeout=15000)
    helper_pid = int(b"".join(chunks).decode().split("helper", 1)[1].split()[0])
    with qtbot.waitSignal(session.finished, timeout=15000):
        session.kill()
    qtbot.waitUntil(lambda: not _process_alive(helper_pid), timeout=5000)


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_interrupt_reaches_the_foreground_process(qtbot):
    session = PtySession()
    chunks: list[bytes] = []
    session.output.connect(chunks.append)
    program = (
        "import time\n"
        "print('waiting', flush=True)\n"
        "try:\n"
        "    time.sleep(300)\n"
        "except KeyboardInterrupt:\n"
        "    print('interrupted', flush=True)\n"
    )
    assert session.start([PYTHON, "-u", "-c", program])
    qtbot.waitUntil(lambda: b"waiting" in b"".join(chunks), timeout=15000)
    with qtbot.waitSignal(session.finished, timeout=15000):
        session.interrupt()
    assert "interrupted" in b"".join(chunks).decode()


def test_the_last_lines_of_a_workflow_are_not_lost(qtbot):
    """The summary is the final thing printed, and the reason to read at all."""
    script = "for i in $(seq 1 400); do echo line $i; done; echo '== Process finished =='"
    text, code = run(qtbot, ["/bin/sh", "-c", script])
    assert code == 0
    assert "== Process finished ==" in text
    assert "line 400" in text


def test_a_large_burst_of_output_arrives_complete(qtbot):
    script = "seq 1 20000"
    text, code = run(qtbot, ["/bin/sh", "-c", script], timeout=30000)
    assert code == 0
    assert "20000" in text
    assert text.count("\n") >= 20000


def test_shutdown_is_safe_on_a_session_that_never_started(qtbot):
    PtySession().shutdown()


def test_shutdown_stops_a_running_workflow(qtbot):
    session = PtySession()
    assert session.start(["/bin/sleep", "300"])
    pid = session.pid
    session.shutdown()
    assert session.running is False
    qtbot.waitUntil(lambda: not _process_alive(pid), timeout=5000)


def test_closing_twice_does_not_raise(qtbot):
    session = PtySession()
    with qtbot.waitSignal(session.finished, timeout=15000):
        session.start(["/bin/true"])
    session.close()
    session.close()


@pytest.mark.skipif(shutil.which("stty") is None, reason="stty is not installed")
def test_stty_agrees_with_the_size_we_asked_for(qtbot):
    text, _code = run(qtbot, ["/bin/sh", "-c", "stty size"], columns=96, rows=30)
    assert "30 96" in text


def test_stopping_a_workflow_never_signals_the_application_itself(qtbot):
    """Regression: Stop pressed before setsid ran killed the whole program.

    ``killpg(getpgid(child))`` looks exact, but between the fork and the
    child's ``setsid`` the kernel still reports this application's own process
    group, so the signal came home. The session now addresses the child's group
    by its pid, which the child owns alone, and falls back to the single
    process while the group does not exist yet.
    """
    own_group = os.getpgrp()
    signalled: list[tuple[int, int]] = []

    session = PtySession()
    assert session.start(["/bin/sleep", "300"])
    try:
        real_killpg, real_kill = os.killpg, os.kill

        def guarded_killpg(group, number):
            signalled.append((group, number))
            assert group != own_group, "the application signalled its own group"
            return real_killpg(group, number)

        def guarded_kill(pid, number):
            assert pid != os.getpid(), "the application signalled itself"
            return real_kill(pid, number)

        os.killpg, os.kill = guarded_killpg, guarded_kill
        try:
            with qtbot.waitSignal(session.finished, timeout=15000):
                session.kill()
        finally:
            os.killpg, os.kill = real_killpg, real_kill
    finally:
        session.shutdown()
    assert signalled, "no group signal was sent"


def test_the_signal_reaches_the_child_group_and_not_ours(qtbot):
    session = PtySession()
    assert session.start(["/bin/sleep", "300"])
    pid = session.pid
    # setsid makes the child its own group leader; that is what we address.
    qtbot.waitUntil(lambda: os.getpgid(pid) == pid, timeout=5000)
    assert os.getpgid(pid) != os.getpgrp()
    with qtbot.waitSignal(session.finished, timeout=15000):
        session.kill()
