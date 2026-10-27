"""The workflow log, written from the bytes of a pty rather than by ``tee``.

The log used to be written by ``tee`` inside the workflow. That put a pipe
between every program and the terminal, and a program writing to a pipe
behaves as if nobody is watching: ``git`` prints no transfer progress, APT
draws no progress bar, ``cargo`` drops its build bar and ``make`` holds its
output in a 4 KiB stdio buffer. A long build then showed one frozen line for
minutes and looked hung. The programs now write to a pty, and the log is
written here from the same bytes the user sees:

* the embedded console feeds ``TranscriptLog`` from its own ``PtySession``;
* a terminal emulator runs the workflow through ``run_logged`` (this file,
  executed as a script), which puts a pty between the two.

A terminal stream is not a text file, so it is reduced to one: colour and
cursor sequences are dropped, a carriage-return redraw keeps only its final
state, and a status bar painted elsewhere on the screen (APT's "Progress:",
between a cursor save and restore) is not glued onto the line it interrupted.

Standard library only: the wrapper runs this file directly with ``python3``,
outside the application and without its import path.
"""

from __future__ import annotations

import codecs
import errno
import fcntl
import logging
import os
import pty
import select
import signal
import sys
import termios
import tty
from pathlib import Path

logger = logging.getLogger(__name__)

# When the console writes the log itself, the wrapper prints this OSC string
# before reading the log back and waits for ``log_sync_path`` to appear. The
# screen ignores OSC 777.
LOG_SYNC_OSC = "777;bc250-log-sync"

# A runaway redraw with no newline must not grow without bound.
MAX_LINE_CHARACTERS = 16384


def log_sync_path(log_path: object) -> Path:
    return Path(f"{log_path}.sync")


class TranscriptLog:
    """Appends the readable text of a terminal stream to a log file."""

    def __init__(self, path: str | Path, *, truncate: bool = False) -> None:
        self.path = Path(path)
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._line: list[str] = []
        self._state = "ground"
        self._string = ""
        self._pending_cr = False
        # Between a cursor save and restore the program is drawing somewhere
        # else on the screen, not continuing the current line.
        self._detached = False
        self._lines: list[str] = []
        try:
            self._file = open(self.path, "w" if truncate else "a", encoding="utf-8")  # noqa: SIM115
        except OSError:
            logger.warning("The workflow log %s could not be opened", self.path, exc_info=True)
            self._file = None

    # ------------------------------------------------------------------ input

    def write(self, data: bytes) -> None:
        if self._file is None:
            return
        for character in self._decoder.decode(data):
            self._feed(character)
        self._flush_lines()

    def close(self) -> None:
        """Write the unterminated last line, if any, and release the file."""
        if self._file is None:
            return
        self._end_partial_line()
        self._flush_lines()
        try:
            self._file.close()
        except OSError:
            pass
        self._file = None

    # -------------------------------------------------------------- the parse

    def _feed(self, character: str) -> None:
        state = self._state
        if state == "escape":
            self._escape(character)
        elif state == "csi":
            if not 0x20 <= ord(character) <= 0x3F:
                self._state = "ground"
                if character in "su":
                    self._detached = character == "s"
        elif state == "string":
            self._string_sequence(character)
        elif state == "charset":
            self._state = "ground"
        else:
            self._ground(character)

    def _ground(self, character: str) -> None:
        code = ord(character)
        if self._pending_cr:
            self._pending_cr = False
            if code != 0x0A:
                # A bare carriage return: the line is being redrawn.
                self._line.clear()
        if code == 0x1B:
            self._state = "escape"
            return
        if code == 0x0D:
            self._pending_cr = True
            return
        if self._detached:
            if code != 0x0A:
                return
            # A cursor save that was never restored: a program printing whole
            # lines is not drawing a status somewhere else any more.
            self._detached = False
            self._line.clear()
            return
        if code == 0x0A:
            self._end_line()
        elif code == 0x08:
            if self._line:
                self._line.pop()
        elif code == 0x09 or code >= 0x20 and code != 0x7F:
            if len(self._line) < MAX_LINE_CHARACTERS:
                self._line.append(character)

    def _escape(self, character: str) -> None:
        if character == "[":
            self._state = "csi"
        elif character in "]P^_X":
            self._state = "string"
            self._string = ""
        elif character in "()*+-./":
            self._state = "charset"
        else:
            self._state = "ground"
            if character == "7":
                self._detached = True
            elif character == "8":
                self._detached = False

    def _string_sequence(self, character: str) -> None:
        if character in "\n\x18\x1a":
            # A sequence nobody closed. Left open, it swallowed every later
            # line until the wrapper's own BEL: two reports lost the lines
            # after the sudo prompt, the failure included. A line feed never
            # belongs to a title or a status string; CAN and SUB cancel.
            self._string = ""
            self._state = "ground"
            if character == "\n":
                self._ground(character)
            return
        if character in "\x07\x9c" or (character == "\\" and self._string.endswith("\x1b")):
            payload = self._string.rstrip("\x1b")
            self._string = ""
            self._state = "ground"
            if payload == LOG_SYNC_OSC:
                self._sync()
            return
        if len(self._string) < 256:
            self._string += character

    # ---------------------------------------------------------------- output

    def _end_line(self) -> None:
        self._lines.append("".join(self._line).rstrip())
        self._line.clear()

    def _end_partial_line(self) -> None:
        if self._line:
            self._end_line()

    def _flush_lines(self) -> None:
        if self._file is None or not self._lines:
            return
        try:
            self._file.write("\n".join(self._lines) + "\n")
            self._file.flush()
        except OSError:
            logger.warning("The workflow log %s could not be written", self.path, exc_info=True)
            self._file = None
        self._lines.clear()

    def _sync(self) -> None:
        """The workflow asked for the log to be complete before reading it."""
        self._end_partial_line()
        self._flush_lines()
        try:
            log_sync_path(self.path).touch()
        except OSError:
            logger.debug("The workflow log sync marker could not be written", exc_info=True)


# ------------------------------------------------ terminal-emulator runner


def _window_size(descriptor: int) -> bytes | None:
    try:
        return fcntl.ioctl(descriptor, termios.TIOCGWINSZ, b"\0" * 8)
    except OSError:
        return None


def _write_all(descriptor: int, data: bytes) -> None:
    while data:
        try:
            written = os.write(descriptor, data)
        except InterruptedError:
            continue
        data = data[written:]


def run_logged(log_path: str, argv: list[str]) -> int:
    """Run ``argv`` on a pty of its own, showing and logging its output.

    Used when the workflow runs in a terminal emulator: the program sees a
    terminal, as it would without logging, and the log is the same text the
    embedded console writes.
    """
    size = _window_size(sys.stdin.fileno()) if sys.stdin.isatty() else None
    pid, master = pty.fork()
    if pid == 0:  # pragma: no cover - replaced by exec
        try:
            if size is not None:
                fcntl.ioctl(0, termios.TIOCSWINSZ, size)
            os.execvp(argv[0], argv)
        finally:
            os._exit(127)

    def resized(_signum, _frame) -> None:
        current = _window_size(sys.stdin.fileno())
        if current is not None:
            try:
                fcntl.ioctl(master, termios.TIOCSWINSZ, current)
            except OSError:
                pass

    transcript = TranscriptLog(log_path, truncate=True)
    stdin = sys.stdin.fileno()
    stdout = sys.stdout.fileno()
    saved = None
    if sys.stdin.isatty():
        saved = termios.tcgetattr(stdin)
        # Keys go to the child's terminal untouched: its line discipline
        # echoes, edits and turns Ctrl+C into SIGINT, and hides a password.
        tty.setraw(stdin)
        signal.signal(signal.SIGWINCH, resized)
    sources = [master, stdin]
    try:
        while master in sources:
            try:
                readable, _, _ = select.select(sources, [], [])
            except InterruptedError:
                continue
            if master in readable:
                try:
                    data = os.read(master, 65536)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    data = b""
                if not data:
                    sources.remove(master)
                else:
                    _write_all(stdout, data)
                    transcript.write(data)
            if stdin in readable:
                data = os.read(stdin, 1024)
                if data:
                    _write_all(master, data)
                else:
                    sources.remove(stdin)
    finally:
        if saved is not None:
            termios.tcsetattr(stdin, termios.TCSAFLUSH, saved)
        transcript.close()
        os.close(master)
    _, status = os.waitpid(pid, 0)
    code = os.waitstatus_to_exitcode(status)
    return 128 - code if code < 0 else code


def main(arguments: list[str]) -> int:
    if len(arguments) < 3 or arguments[1] != "--":
        print("usage: terminal_transcript.py LOG -- COMMAND [ARGS...]", file=sys.stderr)
        return 64
    return run_logged(arguments[0], arguments[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
