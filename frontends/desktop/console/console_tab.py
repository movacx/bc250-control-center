"""One workflow's terminal, and the chip in the header that selects it.

The console used to be a single terminal. A second workflow started while the
first was still running was declined, and the caller fell back to a terminal
emulator of the desktop — a separate window, with a different theme, outside
the application the user was working in. This is the other half of the answer:
the panel holds a strip of these the way an editor holds a strip of terminals,
so a concurrent workflow gets a tab rather than a window.

A tab owns its pseudo-terminal, its grid and its state. The workflows never
see each other's output, and switching between them is only a question of
which grid is on top.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ..components.widgets import icon
from ..i18n import tr, tr_format, translate_workflow_title
from .pty_session import PtySession
from .terminal_view import TerminalView


class _PromptGlyph(QWidget):
    """A small ``>_`` drawn rather than shipped as an asset.

    The icon set has no terminal mark, and a tab that only says a workflow
    name reads like any other chip. One glyph is enough to say what this strip
    is before a word of it is read.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        from ..theme import COLORS

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(COLORS["blue"]))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        # The chevron of a prompt, then the underscore of its cursor.
        painter.drawPolyline(QPolygonF([QPointF(4, 4), QPointF(8, 8), QPointF(4, 12)]))
        painter.drawLine(QPointF(9.5, 12), QPointF(13, 12))
        painter.end()


class ConsoleTab(QWidget):
    """A workflow's terminal: the chip in the strip, the grid behind it."""

    #: The chip was clicked and wants to be the one on screen.
    activated = pyqtSignal()
    #: The ✕ was pressed. Only ever reachable while nothing is running here.
    close_requested = pyqtSignal()
    finished = pyqtSignal(int)
    failed = pyqtSignal(str)
    input_mode_changed = pyqtSignal(bool)
    #: The user's own shell ended (``exit`` or Ctrl+D). Not a workflow result.
    shell_exited = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("consoleTab")
        # A plain QWidget ignores a stylesheet background without this, and the
        # selected tab is exactly the one that has to carry the grid's ground.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.title = ""
        self.log_file = ""
        self.launch_path = ""
        self.exit_code: int | None = None
        #: The user's own shell, opened with F4 the way Dolphin opens its
        #: terminal panel. It is not a workflow: it never makes the panel
        #: "busy", never holds the window open on close, and is never handed
        #: a workflow of its own.
        self.interactive = False
        self._session: PtySession | None = None
        self._active = False
        self._in_a_strip = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 6, 4)
        layout.setSpacing(8)
        self.glyph = _PromptGlyph(self)
        self.title_label = QLabel(tr("Terminal"), self)
        self.title_label.setObjectName("consoleTitle")
        self.state_label = QLabel("", self)
        self.state_label.setObjectName("consoleState")
        self.close_button = QPushButton(self)
        self.close_button.setObjectName("consoleTabClose")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setIcon(icon("close_gray"))
        self.close_button.setIconSize(QSize(11, 11))
        self.close_button.setFixedSize(QSize(18, 18))
        self.close_button.setToolTip(tr("Close"))
        self.close_button.clicked.connect(self.close_requested)
        layout.addWidget(self.glyph)
        layout.addWidget(self.title_label)
        layout.addWidget(self.state_label)
        layout.addWidget(self.close_button)

        # The grid is parented by whoever stacks it, not by the chip.
        self.view = TerminalView()
        self.view.input_ready.connect(self._send_input)
        self.view.size_changed.connect(self._resize_session)

        self.set_state("", "plain")
        self._sync_close_button()

    # ------------------------------------------------------------------ state

    @property
    def running(self) -> bool:
        return self._session is not None and self._session.running

    @property
    def session(self) -> PtySession | None:
        return self._session

    def session_pid(self) -> int | None:
        return self._session.pid if self._session is not None else None

    def input_is_masked(self) -> bool:
        return bool(self._session is not None and self._session.input_is_masked)

    @property
    def running_workflow(self) -> bool:
        """A workflow is running here — the user's own shell does not count."""
        return self.running and not self.interactive

    def is_empty(self) -> bool:
        """Nothing has ever been shown here, so there is nothing to read."""
        return not self.running and self.exit_code is None and not self.title

    def is_reusable(self) -> bool:
        """Whether the next workflow may take this tab over.

        A tab that never ran, or whose workflow succeeded, has nothing left to
        read. A failed one is exactly the tab whose output explains what
        happened, so it keeps its place until it is closed. A shell the user
        is typing into is theirs, never taken over by a workflow.
        """
        if self.interactive and self.running:
            return False
        return not self.running and self.exit_code in (None, 0)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self.setProperty("active", self._active)
        # A descendant selector on the chip would not reach the label: Qt
        # resolves an ID rule on the label itself first, so the label carries
        # the flag directly.
        self.title_label.setProperty("dim", not self._active and self._in_a_strip)
        self.repolish_tree()

    def set_among_others(self, among_others: bool) -> None:
        """Whether this chip is one of several, or the whole header.

        Alone it is not a choice, so it does not dress as one.
        """
        self._in_a_strip = bool(among_others)
        self.set_active(self._active)

    def set_title(self, title: str) -> None:
        self.title = translate_workflow_title(title)
        self.title_label.setText(self.title)

    def set_state(self, text: str, tone: str) -> None:
        self.state_label.setText(f"· {text}" if text else "")
        self.state_label.setProperty("tone", tone)
        self.setProperty("tone", tone)
        self.repolish_tree()

    def repolish_tree(self) -> None:
        """Re-read the stylesheet for this chip and everything inside it.

        The title's colour depends on whether its tab is the selected one, and
        Qt only re-evaluates the widget it is told about: repolishing the chip
        alone left the label styled for the state it used to be in.
        """
        for widget in (self, self.title_label, self.state_label, self.close_button):
            self._repolish(widget)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        style = widget.style()
        if style is not None:
            style.unpolish(widget)
            style.polish(widget)

    def _sync_close_button(self) -> None:
        """Only offer ✕ when pressing it cannot end a privileged workflow.

        Stop is the control that ends a running workflow, and it says so. A
        tab close that silently killed a half-applied patch would be the same
        action wearing a much smaller glyph.
        """
        self.close_button.setVisible(not self.running_workflow)

    # -------------------------------------------------------------------- run

    def run(
        self,
        argv: list[str],
        *,
        title: str = "",
        log_file: str = "",
        launch_path: str = "",
        grid_height: int = 0,
        interactive: bool = False,
        cwd: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> bool:
        if self.running:
            return False
        self._release_session()
        self.set_title(title)
        self.log_file = str(log_file or "")
        self.launch_path = str(launch_path or "")
        self.exit_code = None
        self.interactive = bool(interactive)
        if grid_height > 0:
            # Size the grid for the open panel, not for the closed one it
            # still is while the slide runs.
            self.view.set_expected_height(grid_height)
        self.view.clear()
        # A shell is not "running" in the sense a workflow is: it waits for
        # the user, so its chip carries no state word at all.
        if self.interactive:
            self.set_state("", "plain")
        else:
            self.set_state(tr("Running"), "running")

        session = PtySession(self)
        session.output.connect(self.view.feed)
        session.finished.connect(self._on_finished)
        session.failed.connect(self._on_failed)
        session.input_mode_changed.connect(self.input_mode_changed)
        started = session.start(
            argv,
            columns=self.view.columns,
            rows=self.view.rows,
            # Workflows get no directory of our own. A terminal emulator
            # inherited the application's, and some generated workflows still
            # name their scripts relative to it; moving the child to the home
            # directory made those workflows fail to find a file that was
            # there. Only the user's shell asks for one.
            cwd=cwd,
            environment=environment,
        )
        if not started:
            session.deleteLater()
            self.set_state("", "plain")
            self.interactive = False
            return False
        self._session = session
        self._sync_close_button()
        return True

    def show_text(self, text: str, *, title: str = "", grid_height: int = 0) -> None:
        """Display captured output with nothing listening behind it."""
        self._release_session()
        self.interactive = False
        self.set_title(title)
        self.log_file = ""
        self.launch_path = ""
        self.exit_code = None
        if grid_height > 0:
            self.view.set_expected_height(grid_height)
        self.view.clear()
        self.view.set_input_elsewhere(False)
        # No state word: the title already says what this is, and every state
        # this tab has means something about a running workflow.
        self.set_state("", "plain")
        # A captured log has its own line endings; a terminal needs both halves.
        self.view.feed(str(text).replace("\r\n", "\n").replace("\n", "\r\n").encode())
        # Nothing is listening, so nothing should look like it is waiting for
        # a keystroke.
        self.view.screen.cursor_visible = False
        self.view.viewport().update()
        self._sync_close_button()

    def release_session(self) -> PtySession | None:
        """Give up the running session without stopping it.

        Used when a workflow has to outlive the widget it started in: the
        first-run panel runs a dependency install in a terminal of its own,
        and closing that panel must not kill a package manager halfway
        through. The session is detached from this tab's grid and handed to
        whoever adopts it next.
        """
        session, self._session = self._session, None
        if session is None:
            return None
        for signal, slot in (
            (session.output, self.view.feed),
            (session.finished, self._on_finished),
            (session.failed, self._on_failed),
            (session.input_mode_changed, self.input_mode_changed),
        ):
            try:
                signal.disconnect(slot)
            except TypeError:
                pass
        self._sync_close_button()
        return session

    def adopt(self, session: PtySession, *, title: str = "", transcript: str = "") -> None:
        """Take over a session someone else started, output and all.

        The transcript is what the workflow had already printed in the
        terminal it is leaving. Without it the adopted tab opens blank, and
        the half of the install the user just watched is gone.
        """
        self._release_session()
        self.interactive = False
        self.set_title(title)
        self.exit_code = None
        self.view.clear()
        if transcript:
            self.view.feed(
                transcript.replace("\r\n", "\n").replace("\n", "\r\n").encode()
            )
        session.setParent(self)
        session.output.connect(self.view.feed)
        session.finished.connect(self._on_finished)
        session.failed.connect(self._on_failed)
        session.input_mode_changed.connect(self.input_mode_changed)
        self._session = session
        self.set_state(tr("Running") if session.running else tr("Completed"),
                       "running" if session.running else "ok")
        self._sync_close_button()
        self._resize_session(self.view.columns, self.view.rows)

    def stop(self) -> None:
        if self._session is None or not self._session.running:
            return
        self.set_state(tr("Stop"), "warning")
        self._session.terminate()

    def send_input(self, payload: bytes) -> None:
        if self._session is not None:
            self._session.write(payload)

    def _send_input(self, payload: bytes) -> None:
        self.send_input(payload)

    def _resize_session(self, columns: int, rows: int) -> None:
        if self._session is not None:
            self._session.resize(columns, rows)

    def _on_failed(self, message: str) -> None:
        self.view.feed(f"\r\n{message}\r\n".encode())
        self.set_state(tr("Failed"), "failed")
        self.exit_code = self.exit_code if self.exit_code not in (None, 0) else 1
        self._sync_close_button()
        self.failed.emit(message)

    def _on_finished(self, code: int) -> None:
        if self.interactive:
            # ``exit`` in the user's shell is a way of closing it, not a
            # result anyone has to read: the tab goes back to the empty state
            # it started in, ready for the next shell or workflow.
            self.interactive = False
            self.exit_code = None
            self.title = ""
            self.title_label.setText(tr("Terminal"))
            self.view.clear()
            self.set_state("", "plain")
            self._sync_close_button()
            self.shell_exited.emit()
            return
        self.exit_code = int(code)
        if code == 0:
            self.set_state(tr("Completed"), "ok")
            self.view.feed(b"\r\n")
        else:
            # A failed workflow is exactly the one whose output matters, so
            # the tab says what the exit code was and keeps it on screen.
            self.set_state(tr_format("Exit code {code}", code=code), "failed")
        self._sync_close_button()
        self.finished.emit(int(code))

    # ------------------------------------------------------------- lifecycle

    def _release_session(self) -> None:
        """Let go of the finished session before starting another one.

        Each workflow gets its own session object. Left alone they accumulate
        for the life of the window, one per workflow, each still holding its
        timers.
        """
        previous, self._session = self._session, None
        if previous is None:
            return
        previous.shutdown()
        previous.deleteLater()

    def shutdown(self) -> None:
        self.view.shutdown()
        if self._session is not None:
            self._session.shutdown()
            self._session = None

    def retranslate(self) -> None:
        self.close_button.setToolTip(tr("Close"))
        if not self.title:
            self.title_label.setText(tr("Terminal"))

    # ----------------------------------------------------------- interaction

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        # Not accepted: the header above this strip is also the drag handle
        # that resizes the panel, and swallowing the press here would make the
        # tabs a dead zone for that.
        super().mousePressEvent(event)
