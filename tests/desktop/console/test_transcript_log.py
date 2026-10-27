"""The console writes the workflow log, so the workflow keeps a real terminal.

Behind the old ``| tee`` pipe git hid its progress, APT and cargo dropped
their bars and make buffered its output: a UMR build on Ubuntu 26.04 showed
one frozen line for minutes. These tests pin both halves of the fix: the
workflow's stdout is the terminal, and the log is still clean, complete text.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from bc250cc.infrastructure.terminal_plan import (
    LOG_SYNC_OSC,
    log_sync_path,
    workflow_wrapper,
)
from bc250cc.infrastructure.terminal_transcript import TranscriptLog
from frontends.desktop.console.pty_session import PtySession


def transcript(tmp_path, *chunks: bytes) -> str:
    log = TranscriptLog(tmp_path / "workflow.log")
    for chunk in chunks:
        log.write(chunk)
    log.close()
    return (tmp_path / "workflow.log").read_text(encoding="utf-8")


def test_colour_and_crlf_are_reduced_to_plain_lines(tmp_path):
    text = transcript(tmp_path, b"\x1b[1;32m[ 12%]\x1b[0m Building C object\r\n[INFO] done\r\n")
    assert text == "[ 12%] Building C object\n[INFO] done\n"


def test_a_carriage_return_redraw_keeps_only_its_final_state(tmp_path):
    text = transcript(
        tmp_path,
        b"Receiving objects:  10% (1/10)\rReceiving objects:  50% (5/10)\r",
        b"\x1b[KReceiving objects: 100% (10/10), done.\n",
    )
    assert text == "Receiving objects: 100% (10/10), done.\n"


def test_apt_status_bar_is_not_glued_onto_the_line_it_interrupted(tmp_path):
    text = transcript(
        tmp_path,
        b"Setting up cmake (4.2.3) ...\r\n",
        b"\x1b7\x1b[24;0f\x1b[42m\x1b[30mProgress: [ 45%]\x1b[49m\x1b[39m [####....]\x1b8",
        b"Setting up llvm-21 (1:21.1.8) ...\r\n",
    )
    assert text == "Setting up cmake (4.2.3) ...\nSetting up llvm-21 (1:21.1.8) ...\n"


def test_an_unclosed_sequence_does_not_swallow_the_rest_of_the_log(tmp_path):
    # Two reports lost every line after the sudo prompt, the failure too: a
    # sequence that was never closed kept the log from reading anything.
    text = transcript(
        tmp_path,
        b"[sudo] password for user: \x1b]0;title never closed\r\n",
        b"error: Transaction in progress: upgrade\r\n",
    )
    assert text.endswith("error: Transaction in progress: upgrade\n")


def test_a_cursor_save_never_restored_does_not_swallow_later_lines(tmp_path):
    text = transcript(tmp_path, b"\x1b7status drawn elsewhere\r\n", b"ERROR: what failed\r\n")
    assert text == "ERROR: what failed\n"


def test_the_sync_request_still_works_after_an_unclosed_sequence(tmp_path):
    path = tmp_path / "workflow.log"
    log = TranscriptLog(path)
    log.write(b"\x1bPdcs never closed\nlast line\n" + f"\x1b]{LOG_SYNC_OSC}\x07".encode())
    assert path.read_text(encoding="utf-8").strip() == "last line"
    assert log_sync_path(path).exists()
    log.close()


def test_a_utf8_character_split_across_reads_survives(tmp_path):
    encoded = "Qué ocurrió\n".encode()
    assert transcript(tmp_path, encoded[:3], encoded[3:]) == "Qué ocurrió\n"


def test_sync_request_flushes_the_partial_line_and_answers(tmp_path):
    path = tmp_path / "workflow.log"
    log = TranscriptLog(path)
    log.write(b"no newline yet" + f"\x1b]{LOG_SYNC_OSC}\x07".encode())
    assert path.read_text(encoding="utf-8") == "no newline yet\n"
    assert log_sync_path(path).exists()
    log.close()


def test_the_host_logged_wrapper_does_not_pipe_the_workflow():
    wrapped = workflow_wrapper("make", "/tmp/s", "/tmp/l", hold=False, host_logs=True)
    assert "tee" not in wrapped
    assert "pipefail" not in wrapped


def test_the_host_logged_wrapper_still_reports_without_a_console(tmp_path):
    """No console answering the sync must cost a short wait, never the result."""
    status, log = tmp_path / "status", tmp_path / "log"
    log.write_text("[ERROR] headers do not match\n", encoding="utf-8")
    wrapped = workflow_wrapper("exit 21", status, log, hold=False, host_logs=True)
    result = subprocess.run(["bash", "-c", wrapped], capture_output=True, text=True, timeout=30)
    assert result.returncode == 21
    assert status.read_text(encoding="utf-8") == "21\n"
    assert "headers do not match" in result.stdout


@pytest.mark.skipif(not hasattr(os, "fork"), reason="a pseudo-terminal needs fork()")
def test_the_workflow_sees_a_terminal_and_the_console_writes_its_log(qtbot, tmp_path):
    status, log = tmp_path / "status", tmp_path / "workflow.log"
    wrapped = workflow_wrapper(
        "if [ -t 1 ]; then echo stdout-is-a-tty; else echo stdout-is-a-pipe; fi; exit 3",
        status, log, hold=False, host_logs=True,
    )
    session = PtySession()
    with qtbot.waitSignal(session.finished, timeout=20000) as blocker:
        assert session.start(["bash", "-c", wrapped], log_file=str(log))
    assert blocker.args[0] == 3
    text = log.read_text(encoding="utf-8")
    assert "stdout-is-a-tty" in text
    assert "stdout-is-a-pipe" not in text
    # The summary is written after the sync, from the evidence in the log.
    assert "Diagnostic code:" in text
    assert status.read_text(encoding="utf-8") == "3\n"
    assert not log_sync_path(log).exists()


# ------------------------------------------------ the terminal-emulator path


def run_in_a_terminal(script: str, keys: bytes = b"", timeout: float = 30.0) -> tuple[bytes, int]:
    """Run a shell script the way a terminal emulator would: on a pty."""
    import pty
    import select
    import time

    pid, master = pty.fork()
    if pid == 0:  # pragma: no cover - replaced by exec
        os.execvp("bash", ["bash", "-c", script])
    output = b""
    deadline = time.monotonic() + timeout
    sent = False
    while time.monotonic() < deadline:
        readable, _, _ = select.select([master], [], [], 0.2)
        if not sent and keys and b"PROMPT" in output:
            os.write(master, keys)
            sent = True
        if not readable:
            continue
        try:
            chunk = os.read(master, 65536)
        except OSError:
            break
        if not chunk:
            break
        output += chunk
    _, status = os.waitpid(pid, 0)
    os.close(master)
    return output, os.waitstatus_to_exitcode(status)


def test_a_terminal_emulator_workflow_also_writes_to_a_terminal(tmp_path):
    status, log = tmp_path / "status", tmp_path / "workflow.log"
    wrapped = workflow_wrapper(
        "if [ -t 1 ]; then echo stdout-is-a-tty; else echo stdout-is-a-pipe; fi; "
        "printf 'Receiving 10%%\\rReceiving 100%%, done.\\n'; exit 5",
        status, log, hold=False,
    )
    output, code = run_in_a_terminal(wrapped)
    assert code == 5
    # The emulator gets the live redraw; the log keeps its final state.
    assert b"Receiving 10%\r" in output
    text = log.read_text(encoding="utf-8")
    assert "stdout-is-a-tty" in text and "stdout-is-a-pipe" not in text
    assert "Receiving 100%, done." in text and "Receiving 10%" not in text
    assert "Diagnostic code:" in text
    assert status.read_text(encoding="utf-8") == "5\n"


def test_a_password_typed_in_a_terminal_emulator_is_not_echoed(tmp_path):
    """sudo turns echo off on its own terminal; the runner must honour that."""
    wrapped = workflow_wrapper(
        "echo PROMPT; IFS= read -rs secret; echo \"length=${#secret}\"",
        tmp_path / "status", tmp_path / "log", hold=False,
    )
    output, code = run_in_a_terminal(wrapped, keys=b"hunter2\r")
    assert code == 0
    assert b"length=7" in output
    assert b"hunter2" not in output
    assert "hunter2" not in (tmp_path / "log").read_text(encoding="utf-8")
