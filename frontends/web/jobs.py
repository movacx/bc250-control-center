"""One hardware job at a time, on the terminal interface's own console.

``Console`` is the pty the TUI runs workflows on: sudo and pkexec ask for the
password on it (pkttyagent answers Polkit there), so the web needs no password
logic of its own. What the person types goes to the pty's stdin and nowhere
else: it is not stored, logged or echoed.
"""

from __future__ import annotations

import contextlib
import logging
import threading

from bc250cc.application.system.workflow_console import (
    TerminalLaunchResult,
    set_embedded_terminal_launcher,
)
from bc250cc.application.system.privacy import redact_machine
from bc250cc.shared.failure_text import describe_failure
from frontends.tui.console import Console
from frontends.tui.i18n import tr
from frontends.tui.runtime import describe_error, describe_result

logger = logging.getLogger(__name__)
ROWS, COLUMNS = 24, 100


class Busy(RuntimeError):
    """Another job is still running."""


class Jobs:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counter = 0
        self.console: Console | None = None
        self.label = ""
        self.id = 0
        set_embedded_terminal_launcher(self._launch)

    @property
    def running(self) -> bool:
        return self.console is not None and not self.console.done.is_set()

    def start(self, label: str, work) -> int:
        with self._lock:
            if self.running:
                raise Busy(label)
            self._counter += 1
            self.id, self.label = self._counter, label
            console = self.console = Console(label, ROWS, COLUMNS)
        threading.Thread(target=self._run, args=(console, work), name="bc250-web-job", daemon=True).start()
        return self.id

    def _run(self, console: Console, work) -> None:
        try:
            with console.password_agent(), contextlib.redirect_stdout(console):
                shell = lambda command: self._shell(console, command)
                try:
                    result = work(shell)
                except TypeError:
                    result = work()
            console.finish(True, result)
        except Exception as error:  # said in the console: never an empty failure
            logger.debug("job failed", exc_info=True)
            console.write(f"\n{describe_error(error)}\n")
            console.finish(False, error)

    def shell(self, command: str) -> str:
        """A reviewed command line the service layer built, on the job's pty."""
        status = self.console.run(["bash", "-c", command])
        if status:
            raise RuntimeError(describe_failure(status, "", "", translate=tr))
        return ""

    def _launch(self, request):
        """The repositories' embedded launcher: their workflows run on this job's pty."""
        console = self.console
        if console is None or console.done.is_set():
            return None
        status = console.run(list(request.argv), request.log_file)
        console.failed = console.failed or status != 0
        return TerminalLaunchResult(terminal="bc250-web", title=request.title, pid=None,
                                    status_file=request.status_file, log_file=request.log_file)

    def view(self) -> dict | None:
        console = self.console
        if console is None:
            return None
        lines = console.view(ROWS * 10)[0]
        text = "\n".join("".join(run[0] for run in line).rstrip() for line in lines)
        return {"id": self.id, "label": self.label, "done": console.done.is_set(),
                "ok": console.succeeded if console.done.is_set() else None,
                "message": describe_result(console.result) if console.done.is_set() and console.succeeded else "",
                "text": redact_machine(text), "waiting": console.master is not None}

    def send(self, text: str) -> bool:
        return self.console is not None and self.console.send(text.encode() + b"\n")

    def interrupt(self) -> None:
        if self.running:
            self.console.interrupt()
