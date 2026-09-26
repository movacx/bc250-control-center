"""Knowing when a terminal workflow has ended.

Installers, removals and repairs run in a terminal, and the call that starts
one returns as soon as the terminal is up. Whatever shows what is installed
then learned about the change only on its next poll, through two caches, which
is why a button could keep saying "Install" for twenty seconds after the
installer finished.

Every workflow writes its exit status to a file as its last step, whether it
ran in the embedded console or in a desktop terminal. This watcher is told
about each launch and checks those files, cheaply and only while one is
pending, so the window can refresh the moment a workflow ends.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from bc250cc.infrastructure.terminal_repository import (
    TerminalLaunchResult,
    add_workflow_observer,
    remove_workflow_observer,
)

logger = logging.getLogger(__name__)

#: How the console host names itself in a launch result (console_host.py).
EMBEDDED_TERMINAL_NAME = "bc250-embedded-console"


def read_exit_status(status_file: str) -> int | None:
    """The code a workflow wrote on its way out, or None while it runs."""
    try:
        text = Path(status_file).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    if not text:
        return None
    try:
        return int(text.splitlines()[0].strip())
    except ValueError:
        # Written but unreadable still means finished; report a failure.
        return 1


class WorkflowCompletionWatcher(QObject):
    """Emits ``finished`` once for every workflow that ends."""

    finished = pyqtSignal(object, int)
    #: Launches arrive on worker threads; this signal carries them over to the
    #: thread that owns the timer.
    _arrived = pyqtSignal(object)

    POLL_MS = 600
    #: A workflow left waiting at a sudo prompt overnight is not coming back.
    GIVE_UP_AFTER_S = 12 * 3600

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pending: dict[str, tuple[TerminalLaunchResult, float]] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_MS)
        self._timer.timeout.connect(self.check_now)
        self._arrived.connect(self._track)
        self._installed = False

    def install(self) -> None:
        if not self._installed:
            add_workflow_observer(self._observe)
            self._installed = True

    def uninstall(self) -> None:
        if self._installed:
            remove_workflow_observer(self._observe)
            self._installed = False
        self._timer.stop()
        self._pending.clear()

    @property
    def pending(self) -> int:
        return len(self._pending)

    def _observe(self, result: TerminalLaunchResult) -> None:
        # Called from whichever thread launched the workflow.
        self._arrived.emit(result)

    @pyqtSlot(object)
    def _track(self, result: object) -> None:
        status_file = str(getattr(result, "status_file", "") or "")
        if not status_file:
            return
        self._pending[status_file] = (result, time.monotonic())
        if not self._timer.isActive():
            self._timer.start()

    @pyqtSlot(str, int)
    def embedded_finished(self, log_file: str, code: int) -> None:
        """A console tab's process ended; its workflow has ended too.

        A workflow stopped from the console never reaches the line that
        writes its status file, so the tab's word is taken for it. The log
        file is what ties the tab to the launch.
        """
        self.check_now()
        for status_file, (result, _started) in list(self._pending.items()):
            if getattr(result, "terminal", "") != EMBEDDED_TERMINAL_NAME:
                continue
            if str(getattr(result, "log_file", "") or "") != str(log_file or ""):
                continue
            self._pending.pop(status_file, None)
            self.finished.emit(result, int(code))
        if not self._pending:
            self._timer.stop()

    @pyqtSlot()
    def check_now(self) -> None:
        now = time.monotonic()
        for status_file, (result, started) in list(self._pending.items()):
            code = read_exit_status(status_file)
            if code is None:
                if now - started > self.GIVE_UP_AFTER_S:
                    self._pending.pop(status_file, None)
                continue
            self._pending.pop(status_file, None)
            try:
                self.finished.emit(result, code)
            except Exception:
                logger.exception("Handling the end of a workflow failed")
        if not self._pending:
            self._timer.stop()
