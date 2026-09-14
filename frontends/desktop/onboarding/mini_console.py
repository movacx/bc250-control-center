"""A terminal inside the first-run panel.

Preparing the board is the first thing anyone has to do, and until now it was
also the first thing nobody was told about: the welcome screen set a language
and a theme and then handed over an application that could not do most of its
job yet. So it offers to do it here.

It has to be a real terminal rather than a progress bar. The work runs under
``sudo``, which reads its password from ``/dev/tty`` and not from standard
input, and package managers draw progress with carriage returns — the two
reasons the docked console exists at all. This is the same machinery: one
:class:`~frontends.desktop.console.console_tab.ConsoleTab`, which already owns
a pseudo-terminal, a grid and a session, shown without its chip.

It answers ``run`` and ``session_pid`` because that is the whole contract
:class:`~frontends.desktop.console.console_host.ConsoleHost` asks of a console.
Pointing a host at one of these is what sends a workflow here instead of to the
docked panel, with no second code path for starting privileged work.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..console.console_tab import ConsoleTab
from ..i18n import tr, tr_format


class MiniConsole(QFrame):
    """One workflow's terminal, sized for a panel rather than a window."""

    workflow_started = pyqtSignal()
    workflow_finished = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("onboardingConsole")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget(self)
        header.setObjectName("onboardingConsoleHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 7, 12, 7)
        header_layout.setSpacing(8)
        self.title = QLabel(tr("Terminal"), header)
        self.title.setObjectName("onboardingConsoleTitle")
        self.state = QLabel("", header)
        self.state.setObjectName("onboardingConsoleState")
        header_layout.addWidget(self.title)
        header_layout.addStretch(1)
        header_layout.addWidget(self.state)
        layout.addWidget(header)

        # The chip belongs to a tab bar this panel does not have; the tab is
        # kept for its terminal, its session and its lifecycle.
        self._tab = ConsoleTab(self)
        self._tab.hide()
        self._tab.finished.connect(self._on_finished)
        self._tab.failed.connect(self._on_failed)
        self.view = self._tab.view
        self.view.setParent(self)
        self.view.setObjectName("onboardingConsoleView")
        layout.addWidget(self.view, 1)

    # ------------------------------------------------------- the host contract

    def run(
        self,
        argv: list[str],
        *,
        title: str = "",
        log_file: str = "",
        launch_path: str = "",
    ) -> bool:
        """Start a workflow here. The signature a console host expects."""
        if self._tab.running:
            return False
        started = self._tab.run(
            list(argv), title=title, log_file=log_file, launch_path=launch_path
        )
        if not started:
            return False
        self.title.setText(self._tab.title)
        self._set_state(tr("Running"), "running")
        self.view.setFocus()
        self.workflow_started.emit()
        return True

    def session_pid(self) -> int | None:
        return self._tab.session_pid()

    # --------------------------------------------------------------- lifecycle

    @property
    def busy(self) -> bool:
        return self._tab.running

    def release_session(self):
        """Hand the running session out, so closing this does not kill it.

        A dependency install takes minutes. Someone who finishes the setup
        while one is halfway through should not lose it — the docked console
        adopts it and carries on.
        """
        return self._tab.release_session()

    def shutdown(self) -> None:
        self._tab.shutdown()

    def retranslate(self) -> None:
        if not self._tab.title:
            self.title.setText(tr("Terminal"))

    # ------------------------------------------------------------------ state

    def _set_state(self, text: str, tone: str) -> None:
        self.state.setText(text)
        self.state.setProperty("tone", tone)
        style = self.state.style()
        if style is not None:
            style.unpolish(self.state)
            style.polish(self.state)

    def _on_failed(self, _message: str) -> None:
        self._set_state(tr("Failed"), "failed")

    def _on_finished(self, code: int) -> None:
        if code == 0:
            self._set_state(tr("Completed"), "ok")
        else:
            self._set_state(tr_format("Exit code {code}", code=code), "failed")
        self.workflow_finished.emit(int(code))
