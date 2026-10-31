"""The console pane: a job's output and the pty its workflows run on.

Workflows draw progress with carriage returns and cursor moves, and ``sudo`` or
pkexec ask for a password on the controlling terminal, so commands get a real
pseudo-terminal and their bytes go through the desktop console's own terminal
emulator and transcript log. Nothing leaves the interface.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import select
import shutil
import signal
import struct
import subprocess  # nosec B404 - the argv is the repository's reviewed workflow
import sys
import termios
import threading
import time

from bc250cc.application.system.workflow_console import (
    TERMINAL_AGENT_READY,
    TranscriptLog,
)
from frontends.desktop.console.terminal_screen import TerminalScreen

SCROLLBACK = 5000
#: ANSI colour (0-15) -> interface tone; anything else keeps the default colour.
TONES = {1: "bad", 9: "bad", 2: "ok", 10: "ok", 3: "warn", 11: "warn", 4: "accent", 12: "accent", 6: "accent",
         14: "accent"}


class Console:
    """Output of one job. ``print`` may target it; commands run on its pty."""

    def __init__(self, label: str, rows: int = 24, columns: int = 80) -> None:
        self.label = label
        self.term = TerminalScreen(columns, rows, scrollback=SCROLLBACK)
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.ok = True
        self.failed = False  # a workflow it ran exited non-zero
        self.printed = False
        self.log_file = ""  # the last workflow's full log, named in the pane's header
        self.result: object = None
        self.process: subprocess.Popen | None = None
        self.master: int | None = None
        self.started = time.monotonic()
        self.finished_at: float | None = None

    # -- output ---------------------------------------------------------------

    def write(self, text: str) -> int:
        """File-like, for ``print``: a newline returns the carriage as a tty would."""
        self._feed(text.replace("\r\n", "\n").replace("\n", "\r\n"))
        return len(text)

    def flush(self) -> None:
        pass

    def _feed(self, data: bytes | str) -> None:
        self.printed = self.printed or bool(data.strip())
        with self.lock:
            self.term.feed(data)
            answer = self.term.take_response()  # cursor-position queries and the like
        if answer and self.master is not None:
            self.send(answer.encode())

    def view(self, rows: int, scroll: int = 0) -> tuple[list[list[tuple[str, str, bool]]], int]:
        """The ``rows`` lines ending ``scroll`` lines above the last printed one, as
        (text, tone, bold) runs, and the scroll actually used. Only those lines
        are converted: a redraw costs the same with 5000 lines of history."""
        with self.lock:
            grid = self.term.scrollback + self.term.lines
            end = len(grid)
            while end and not any(cell.text.strip() for cell in grid[end - 1]):
                end -= 1
            scroll = max(0, min(scroll, end - rows))
            return [self._runs(row) for row in grid[max(0, end - scroll - rows):end - scroll]], scroll

    def line_count(self) -> int:
        """Printed extent for scrollbar geometry, without formatting scrollback."""
        with self.lock:
            grid = self.term.scrollback + self.term.lines
            end = len(grid)
            while end and not any(cell.text.strip() for cell in grid[end - 1]):
                end -= 1
            return end

    @staticmethod
    def _runs(row) -> list[tuple[str, str, bool]]:
        runs: list[tuple[str, str, bool]] = []
        for cell in row:
            if cell.placeholder:
                continue
            style = cell.style
            key = (TONES.get(style.foreground, "") if isinstance(style.foreground, int) else "", style.bold or style.inverse)
            if runs and runs[-1][1:] == key:
                runs[-1] = (runs[-1][0] + cell.text, *key)
            else:
                runs.append((cell.text, *key))
        return runs

    @property
    def has_output(self) -> bool:
        return self.printed

    @property
    def succeeded(self) -> bool:
        return self.ok and not self.failed

    def finish(self, ok: bool, result: object) -> None:
        self.ok, self.result, self.finished_at = ok, result, time.monotonic()
        self.done.set()

    # -- keyboard -------------------------------------------------------------

    def send(self, data: bytes) -> bool:
        if self.master is None:
            return False
        try:
            os.write(self.master, data)
        except OSError:
            return False
        return True

    def interrupt(self) -> None:
        """Ctrl+C for whatever is waiting on the console (a command, or a password prompt)."""
        if self.send(b"\x03"):  # the pty turns it into SIGINT for its foreground group
            return
        process = self.process
        if process is not None and process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGINT)
            except OSError:
                pass

    def resize(self, rows: int, columns: int) -> None:
        with self.lock:
            if (rows, columns) == (self.term.rows, self.term.columns):
                return
            self.term.resize(columns, rows)
        if self.master is not None:
            try:
                fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
            except OSError as error:
                if error.errno not in (errno.EBADF, errno.EIO):
                    raise

    # -- commands -------------------------------------------------------------

    def _spawn(self, argv: list[str], pass_fds: tuple[int, ...] = ()) -> tuple[subprocess.Popen, int]:
        """Start ``argv`` with a pty of this console as its controlling terminal."""
        master, slave = os.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", self.term.rows, self.term.columns, 0, 0))

        # No pager: "systemctl status" would open less inside the pane and never end; the pane scrolls itself.
        env = dict(os.environ, TERM="xterm-256color", COLUMNS=str(self.term.columns), LINES=str(self.term.rows),
                   PAGER="cat", SYSTEMD_PAGER="cat", GIT_PAGER="cat", SYSTEMD_LESS="")
        for name in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "SSH_ASKPASS", "SUDO_ASKPASS"):
            env.pop(name, None)
        env["SSH_ASKPASS_REQUIRE"] = "never"
        try:
            process = subprocess.Popen(  # nosec B603
                [sys.executable, "-m", "frontends.tui.pty_exec", *argv],
                stdin=slave, stdout=slave, stderr=slave, env=env, pass_fds=pass_fds,
                start_new_session=True, close_fds=True)
        except BaseException:
            os.close(master)
            raise
        finally:
            os.close(slave)
        return process, master

    def _pump(self, process: subprocess.Popen, master: int, log: TranscriptLog | None = None) -> int:
        """Show what ``process`` prints until it exits. The keyboard goes to whoever printed last."""
        try:
            while True:
                ready, _, _ = select.select([master], [], [], 0.1)
                if not ready:
                    if process.poll() is not None:
                        break
                    continue
                try:
                    chunk = os.read(master, 65536)
                except OSError as error:
                    if error.errno != errno.EIO:  # EIO: the command closed its side
                        raise
                    chunk = b""
                if not chunk:
                    break
                self.master = master
                self._feed(chunk)
                if log is not None:
                    log.write(chunk)  # also answers the wrapper's log-sync request
            return process.wait()
        finally:
            if self.master == master:
                self.master = None
            os.close(master)
            if log is not None:
                log.close()

    def run(self, argv: list[str], log_file: str = "") -> int:
        """Run ``argv`` until it exits; its output lands here and in ``log_file``."""
        self.process, self.master = self._spawn(argv)
        return self._pump(self.process, self.master, TranscriptLog(log_file) if log_file else None)

    @contextlib.contextmanager
    def password_agent(self):
        """While the job runs, Polkit asks for the password here, not in a desktop window.

        pkexec authenticates its parent process, which for the helpers the
        services call directly is this interface. A textual agent registered
        for exactly this process (pkttyagent, part of polkit) takes those
        requests on a pty of this console; the desktop's own agent keeps
        serving the rest of the session, and a bare TTY, which has none,
        works the same way.
        """
        agent = shutil.which("pkttyagent")
        if agent is None:
            yield
            return
        ready, notify = os.pipe()
        process, master = self._spawn([agent, "--process", str(os.getpid()), "--notify-fd", str(notify)],
                                      pass_fds=(notify,))
        os.close(notify)
        pump = threading.Thread(target=self._pump, args=(process, master), name="bc250-tui-polkit", daemon=True)
        pump.start()
        readable, _, _ = select.select([ready], [], [], 5)
        os.close(ready)
        registered = bool(readable) and process.poll() is None
        token = TERMINAL_AGENT_READY.set(registered)
        try:
            yield
        finally:
            TERMINAL_AGENT_READY.reset(token)
            if process.poll() is None:
                process.terminate()
            pump.join(2)
