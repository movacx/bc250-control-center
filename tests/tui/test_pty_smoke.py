"""Start the real program on a pseudo-terminal, look at the first frame, quit."""

import os
import select
import sys
import time
from pathlib import Path

import pytest

pty = pytest.importorskip("pty")
ROOT = Path(__file__).resolve().parents[2]


def _read_until(fd, needle: bytes, timeout: float) -> bytes:
    seen, deadline = b"", time.monotonic() + timeout
    while time.monotonic() < deadline and needle not in seen:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if ready:
            try:
                seen += os.read(fd, 65536)
            except OSError:
                break
    return seen


def test_the_program_draws_its_sidebar_on_a_real_terminal_and_quits_with_q(tmp_path):
    pid, fd = pty.fork()
    if pid == 0:  # child
        os.environ.update(TERM="xterm-256color", LANG="C.UTF-8", HOME=str(tmp_path),
                          XDG_CONFIG_HOME=str(tmp_path / "config"), XDG_STATE_HOME=str(tmp_path / "state"),
                          PYTHONPATH=f"{ROOT}/src:{ROOT}", COLUMNS="100", LINES="30")
        os.chdir(ROOT)
        os.execv(sys.executable, [sys.executable, "-m", "frontends.tui", "--lang", "en"])
    import fcntl
    import struct
    import termios

    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
    try:
        screen = _read_until(fd, b"Dashboard", 25)
        assert b"BC250 Control Center" in screen and b"Dashboard" in screen
        os.write(fd, b"q")
        deadline = time.monotonic() + 10
        status = None
        while time.monotonic() < deadline:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                break
            _read_until(fd, b"\x00", 0.2)
        else:
            pytest.fail("the program did not quit after q")
        assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    finally:
        try:
            os.kill(pid, 9)
        except OSError:
            pass
