"""An output pane inside the interface, for work that used to take the terminal over.

A service call, or a reviewed workflow command, runs on a worker thread while
the screen shows what it prints. Commands run on a pseudo-terminal, so a
``sudo`` or Polkit prompt appears in the pane and the person answers it there
with the keyboard; nothing leaves the interface.
"""

from __future__ import annotations

import errno
import fcntl
import os
import re
import select
import signal
import struct
import subprocess  # nosec B404 - the argv is the repository's reviewed workflow
import termios
import threading
import time

MAX_LINES = 5000
#: CSI, OSC and charset-select sequences: colours and titles mean nothing in this pane.
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][A-Za-z0-9]|\x1b[=>]")


class Console:
    """Text a running job prints, plus the pty its command (if any) listens on."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.lines: list[str] = [""]
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.ok = True
        self.result: object = None
        self.input_fd: int | None = None
        self.process: subprocess.Popen | None = None
        self.started = time.monotonic()
        self.revision = 0
        self._column = 0

    # -- a file-like object, so print() can target it ----------------------

    def write(self, text: str) -> int:
        text = ANSI.sub("", text)
        with self.lock:
            for char in text:
                if char == "\n":
                    self.lines.append("")
                    self._column = 0
                elif char == "\r":
                    self._column = 0
                elif char == "\b":
                    self._column = max(0, self._column - 1)
                elif char == "\t" or char >= " ":
                    line = self.lines[-1]
                    if char == "\t":
                        char = " " * (8 - self._column % 8)
                    self.lines[-1] = line[:self._column] + char + line[self._column + len(char):]
                    self._column += len(char)
            if len(self.lines) > MAX_LINES:
                del self.lines[:len(self.lines) - MAX_LINES]
            self.revision += 1
        return len(text)

    def flush(self) -> None:
        pass

    def snapshot(self) -> list[str]:
        with self.lock:
            return list(self.lines)

    @property
    def has_output(self) -> bool:
        with self.lock:
            return any(line.strip() for line in self.lines)

    # -- keyboard -> command -------------------------------------------------

    def send(self, data: bytes) -> bool:
        if self.input_fd is None or self.done.is_set():
            return False
        try:
            os.write(self.input_fd, data)
        except OSError:
            return False
        return True

    def interrupt(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGINT)
            except OSError:
                pass

    # -- a command on a pty -----------------------------------------------------

    def run_command(self, command: str, size: tuple[int, int] = (24, 80)) -> int:
        master, slave = os.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", size[0], size[1], 0, 0))

        def become_session_leader() -> None:  # the pty is the command's controlling terminal
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        env = dict(os.environ, TERM="xterm", COLUMNS=str(size[1]), LINES=str(size[0]))
        self.process = subprocess.Popen(  # nosec B603 B607
            ["bash", "-c", command], stdin=slave, stdout=slave, stderr=slave, env=env,
            preexec_fn=become_session_leader, close_fds=True)  # noqa: PLW1509
        os.close(slave)
        self.input_fd = master
        try:
            while True:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError as error:
                        if error.errno == errno.EIO:  # the command closed its side
                            chunk = b""
                        else:
                            raise
                    if not chunk:
                        break
                    self.write(chunk.decode("utf-8", "replace"))
                elif self.process.poll() is not None:
                    break
            return self.process.wait()
        finally:
            self.input_fd = None
            os.close(master)
