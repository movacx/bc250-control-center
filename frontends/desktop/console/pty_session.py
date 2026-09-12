"""A child process attached to a real pseudo-terminal.

``sudo`` reads its password from ``/dev/tty``, not from standard input, and
package managers only draw progress when ``isatty`` is true. Both facts make a
pipe-backed process useless for the workflows this application runs, so the
child is given a genuine pty and the master side is pumped into the widget.

The reader is a ``QSocketNotifier`` rather than a thread: the master file
descriptor is edge-driven by the kernel, so the event loop already has exactly
the wake-up we need and no cross-thread queue is required.
"""

from __future__ import annotations

import errno
import fcntl
import logging
import os
import pty
import shutil
import signal
import struct
import termios
from collections.abc import Mapping, Sequence

from PyQt6.QtCore import QObject, QSocketNotifier, QTimer, pyqtSignal

logger = logging.getLogger(__name__)

# One read per notification is enough for interactive output, but an installer
# writing megabytes benefits from draining the buffer before returning to the
# event loop. The cap keeps one noisy process from starving the interface.
READ_CHUNK = 65536
MAX_READS_PER_WAKEUP = 16

# How long a terminated child is given to exit before it is killed outright.
TERMINATE_GRACE_MS = 4000
REAP_INTERVAL_MS = 50
# Often enough that the field changes before anyone finishes reading the
# prompt, cheap enough to be irrelevant: one ioctl per tick.
ECHO_POLL_MS = 120


def set_window_size(descriptor: int, columns: int, rows: int) -> None:
    """Tell the pty its dimensions so the child receives SIGWINCH."""
    packed = struct.pack("HHHH", max(1, int(rows)), max(1, int(columns)), 0, 0)
    try:
        fcntl.ioctl(descriptor, termios.TIOCSWINSZ, packed)
    except OSError:
        logger.debug("Could not set the terminal window size", exc_info=True)


class PtySession(QObject):
    """Runs one command on a pseudo-terminal for the lifetime of one workflow."""

    output = pyqtSignal(bytes)
    finished = pyqtSignal(int)
    failed = pyqtSignal(str)
    # True when the program turned the terminal's echo off, which is how
    # ``sudo`` and every other password prompt says "do not show this".
    input_mode_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._master: int | None = None
        self._pid: int | None = None
        self._notifier: QSocketNotifier | None = None
        self._reaper: QTimer | None = None
        self._killer: QTimer | None = None
        self._exit_code: int | None = None
        self._closing = False
        self._masked = False
        self._echo_watch: QTimer | None = None

    # ----------------------------------------------------------------- status

    @property
    def running(self) -> bool:
        return self._pid is not None

    @property
    def echo_enabled(self) -> bool:
        """Whether the child is echoing what it is sent.

        The master and the slave of a pty share one termios state, so asking
        the master answers for the program on the other side. A program that
        clears ECHO is asking for something it does not want displayed.
        """
        if self._master is None:
            return True
        try:
            return bool(termios.tcgetattr(self._master)[3] & termios.ECHO)
        except OSError:
            return True

    @property
    def input_is_masked(self) -> bool:
        return self._masked

    def _watch_echo(self) -> None:
        masked = self.running and not self.echo_enabled
        if masked != self._masked:
            self._masked = masked
            self.input_mode_changed.emit(masked)

    @property
    def exit_code(self) -> int | None:
        return self._exit_code

    @property
    def pid(self) -> int | None:
        return self._pid

    # ------------------------------------------------------------------ start

    def start(
        self,
        argv: Sequence[str],
        *,
        columns: int = 100,
        rows: int = 24,
        cwd: str | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> bool:
        """Fork the child onto a new pty. Returns False and reports why on error."""
        if self.running:
            raise RuntimeError("This terminal session is already running a command.")
        command = [str(part) for part in argv if part is not None]
        if not command:
            self.failed.emit("No command was given to the terminal.")
            return False
        try:
            master, slave = pty.openpty()
        except OSError as error:
            self.failed.emit(f"A pseudo-terminal could not be opened: {error}")
            return False

        # The size is set before the fork so the child never observes the
        # default 80x24 and redraws itself a moment later.
        set_window_size(master, columns, rows)

        # Everything the child needs is prepared here, in the parent. This
        # application has worker threads, and only the forking thread survives
        # into the child: any lock another thread happened to hold is held
        # forever there. Python-level work between fork and exec is what could
        # take such a lock, so the child below does nothing but system calls.
        program = shutil.which(command[0])
        if program is None:
            os.close(master)
            os.close(slave)
            self.failed.emit(f"{command[0]} was not found on this system.")
            return False
        child_environment = self._child_environment(environment, columns, rows)
        signals_to_restore = [
            number
            for number in (
                getattr(signal, name, None)
                for name in ("SIGINT", "SIGQUIT", "SIGTERM", "SIGPIPE", "SIGHUP")
            )
            if number is not None
        ]
        working_directory = str(cwd) if cwd else ""

        try:
            pid = os.fork()
        except OSError as error:
            os.close(master)
            os.close(slave)
            self.failed.emit(f"The terminal process could not be created: {error}")
            return False

        if pid == 0:  # pragma: no cover - the child never returns to pytest
            self._become_child(
                master,
                slave,
                program,
                command,
                working_directory,
                child_environment,
                signals_to_restore,
            )

        os.close(slave)
        self._master = master
        self._pid = pid
        self._exit_code = None
        self._closing = False
        flags = fcntl.fcntl(master, fcntl.F_GETFL)
        fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self._notifier = QSocketNotifier(master, QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._on_readable)
        # One ioctl on a timer. A prompt appears and disappears between reads,
        # so watching the flag is more reliable than parsing the output for
        # something that looks like the word "password" in some language.
        self._echo_watch = QTimer(self)
        self._echo_watch.setInterval(ECHO_POLL_MS)
        self._echo_watch.timeout.connect(self._watch_echo)
        self._echo_watch.start()
        return True

    @staticmethod
    def _child_environment(
        environment: Mapping[str, str] | None, columns: int, rows: int
    ) -> dict[str, str]:
        child = dict(os.environ if environment is None else environment)
        # Declare what this screen actually implements. Claiming a richer
        # terminal would invite sequences the interpreter does not render.
        child["TERM"] = "xterm-256color"
        child["COLORTERM"] = "truecolor"
        child["COLUMNS"] = str(columns)
        child["LINES"] = str(rows)
        # The workflows are read by people, so a pager that waits for a key
        # would look like the process hung inside a panel with no pager keys.
        child.setdefault("SYSTEMD_PAGER", "")
        child.setdefault("PAGER", "cat")
        child.pop("LD_PRELOAD", None)
        return child

    @staticmethod
    def _become_child(
        master: int,
        slave: int,
        program: str,
        command: list[str],
        cwd: str,
        environment: dict[str, str],
        signals_to_restore: list[int],
    ) -> None:  # pragma: no cover - runs only in the forked child
        """Turn this forked copy into the workflow. Only system calls here.

        Every argument arrives already built. ``execve`` is used rather than
        ``execvpe`` because the latter searches PATH in Python; the search
        happens in the parent instead, so the child does as little as the
        interpreter allows before handing the process over.
        """
        try:
            os.close(master)
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
            os.dup2(slave, 0)
            os.dup2(slave, 1)
            os.dup2(slave, 2)
            if slave > 2:
                os.close(slave)
            # Restore the default disposition of everything Qt may have
            # ignored, or the child inherits an ignored SIGINT and Ctrl+C
            # silently does nothing.
            for number in signals_to_restore:
                signal.signal(number, signal.SIG_DFL)
            if cwd:
                try:
                    os.chdir(cwd)
                except OSError:
                    pass
            os.execve(program, command, environment)
        except BaseException:
            # A failed exec must not unwind into a second copy of the
            # application; report on the pty and leave immediately.
            try:
                os.write(2, b"BC250: the workflow command could not be started.\r\n")
            except OSError:
                pass
            os._exit(127)

    # ------------------------------------------------------------------- read

    def _on_readable(self) -> None:
        if self._master is None:
            return
        for _ in range(MAX_READS_PER_WAKEUP):
            try:
                data = os.read(self._master, READ_CHUNK)
            except BlockingIOError:
                return
            except OSError as error:
                if error.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    return
                # EIO is the normal end of a pty: the last slave has closed.
                self._on_hangup()
                return
            if not data:
                self._on_hangup()
                return
            self.output.emit(data)

    def _on_hangup(self) -> None:
        if self._notifier is not None:
            self._notifier.setEnabled(False)
        self._start_reaping()

    # ------------------------------------------------------------------ write

    def write(self, data: bytes | str) -> None:
        """Send keystrokes or a pasted block to the child."""
        if self._master is None or not self.running:
            return
        payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        while payload:
            try:
                written = os.write(self._master, payload)
            except BlockingIOError:
                # The child is not draining. Dropping the tail is better than
                # blocking the interface; interactive input is never this big.
                logger.debug("The terminal input buffer is full; input was dropped")
                return
            except OSError:
                return
            payload = payload[written:]

    def resize(self, columns: int, rows: int) -> None:
        if self._master is None:
            return
        set_window_size(self._master, columns, rows)

    # -------------------------------------------------------------- finishing

    def interrupt(self) -> None:
        """Deliver Ctrl+C to the whole foreground group, as a terminal would."""
        self._signal_group(signal.SIGINT)

    def terminate(self) -> None:
        """Ask the workflow to stop, and insist if it does not."""
        if not self.running:
            return
        self._closing = True
        self._signal_group(signal.SIGTERM)
        self._start_reaping()
        if self._killer is None:
            self._killer = QTimer(self)
            self._killer.setSingleShot(True)
            self._killer.timeout.connect(self.kill)
        self._killer.start(TERMINATE_GRACE_MS)

    def kill(self) -> None:
        if not self.running:
            return
        self._closing = True
        self._signal_group(signal.SIGKILL)
        self._start_reaping()

    def _signal_group(self, number: int) -> None:
        """Signal the workflow, and never anything outside it.

        The child calls ``setsid`` right after the fork, which makes its
        process group id equal to its pid. Addressing the group by that pid is
        therefore exact. Asking the kernel instead — ``killpg(getpgid(pid))``
        — is not: in the window between the fork and ``setsid`` the child is
        still in *this* application's process group, and the signal would go
        to the application itself. Pressing Stop quickly enough killed the
        whole program.
        """
        pid = self._pid
        if pid is None:
            return
        own_group = os.getpgrp()
        if pid != own_group:
            try:
                os.killpg(pid, number)
                return
            except OSError:
                # No such group yet: setsid has not run. Fall through to the
                # single process, which is all that exists at this point.
                pass
        try:
            os.kill(pid, number)
        except OSError:
            logger.debug("The terminal process could not be signalled", exc_info=True)

    def _start_reaping(self) -> None:
        if self._pid is None:
            return
        if self._reaper is None:
            self._reaper = QTimer(self)
            self._reaper.setInterval(REAP_INTERVAL_MS)
            self._reaper.timeout.connect(self._reap)
        self._reaper.start()
        self._reap()

    def _reap(self) -> None:
        pid = self._pid
        if pid is None:
            return
        try:
            waited, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            # Something else already reaped it; report a clean finish rather
            # than leaving the panel claiming the workflow is still running.
            self._complete(0)
            return
        except OSError:
            self._complete(-1)
            return
        if waited == 0:
            return
        self._complete(os.waitstatus_to_exitcode(status))

    def _complete(self, code: int) -> None:
        if self._pid is None:
            return
        self._pid = None
        self._exit_code = code
        if self._reaper is not None:
            self._reaper.stop()
        if self._killer is not None:
            self._killer.stop()
        if self._echo_watch is not None:
            self._echo_watch.stop()
        if self._masked:
            self._masked = False
            self.input_mode_changed.emit(False)
        self._drain_remaining()
        self.close()
        self.finished.emit(code)

    def _drain_remaining(self) -> None:
        """Emit whatever the child wrote just before exiting.

        Without this the last lines of a workflow — which are exactly the ones
        that say whether it worked — can be lost between the final read and
        the process being reaped.
        """
        if self._master is None:
            return
        for _ in range(MAX_READS_PER_WAKEUP):
            try:
                data = os.read(self._master, READ_CHUNK)
            except OSError:
                return
            if not data:
                return
            self.output.emit(data)

    def close(self) -> None:
        """Release the pty. Safe to call more than once."""
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier.deleteLater()
            self._notifier = None
        if self._master is not None:
            try:
                os.close(self._master)
            except OSError:
                pass
            self._master = None

    def shutdown(self) -> None:
        """Stop a running workflow and release everything, for window close."""
        if self.running:
            self.kill()
            pid = self._pid
            if pid is not None:
                try:
                    os.waitpid(pid, 0)
                except OSError:
                    pass
                self._pid = None
        if self._reaper is not None:
            self._reaper.stop()
        if self._killer is not None:
            self._killer.stop()
        self.close()
