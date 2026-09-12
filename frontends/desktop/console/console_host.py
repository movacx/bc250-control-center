"""The bridge between the repositories and the console panel.

Workflows are started from background workers, never from the interface
thread. Qt widgets may only be touched from the thread that owns them, so the
request is handed across with a blocking queued call: the worker waits exactly
as long as it used to wait for a terminal emulator to appear, and every widget
is still created where Qt requires.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import (
    Q_ARG,
    QMetaObject,
    QObject,
    Qt,
    QThread,
    pyqtSlot,
)

from bc250cc.infrastructure.terminal_repository import (
    EmbeddedTerminalRequest,
    TerminalLaunchResult,
    set_embedded_terminal_launcher,
)

logger = logging.getLogger(__name__)

EMBEDDED_TERMINAL_NAME = "bc250-embedded-console"


class ConsoleHost(QObject):
    """Offers one console panel to the repository layer."""

    def __init__(self, panel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._panel = panel
        self._enabled = True
        self._pending: dict | None = None

    # ------------------------------------------------------------- lifecycle

    def install(self) -> None:
        set_embedded_terminal_launcher(self.launch)

    def uninstall(self) -> None:
        set_embedded_terminal_launcher(None)

    def set_enabled(self, enabled: bool) -> None:
        """Turn the panel off without unregistering, so the choice is live."""
        self._enabled = bool(enabled)

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ---------------------------------------------------------------- launch

    def launch(self, request: EmbeddedTerminalRequest) -> TerminalLaunchResult | None:
        """Run a workflow in the panel, or decline so a terminal is opened."""
        if not self._enabled or self._panel is None:
            return None
        box: dict = {"request": request, "result": None, "delivered": False}
        if QThread.currentThread() is self.thread():
            self._run(box)
        else:
            QMetaObject.invokeMethod(
                self,
                "_run",
                Qt.ConnectionType.BlockingQueuedConnection,
                Q_ARG(object, box),
            )
        if not box["delivered"]:
            # The slot itself reports arrival. The return value of
            # invokeMethod cannot: PyQt has returned both a bool and the
            # invoked method's own result across versions, and reading it as
            # success threw away workflows that had in fact started.
            logger.warning("The console panel did not receive the workflow request")
            return None
        return box.get("result")

    @pyqtSlot(object)
    def _run(self, box: dict) -> None:
        box["delivered"] = True
        request = box.get("request")
        if request is None:
            return
        try:
            started = self._panel.run(
                list(request.argv),
                title=request.title,
                log_file=request.log_file,
                launch_path=request.launch_file,
            )
        except Exception:
            logger.exception("The console panel refused a workflow")
            started = False
        if not started:
            # Busy or unable: the caller falls back to a terminal emulator, so
            # a second workflow is never silently dropped.
            return
        box["result"] = TerminalLaunchResult(
            terminal=EMBEDDED_TERMINAL_NAME,
            title=request.title,
            pid=self._panel.session_pid(),
            status_file=request.status_file,
            log_file=request.log_file,
        )
