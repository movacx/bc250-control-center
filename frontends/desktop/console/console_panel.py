"""The console that slides up from the foot of the window.

Workflows used to open a terminal emulator of the user's desktop, which meant
a separate window, a different theme, and on some systems no terminal at all.
The panel keeps the workflow inside the application: it appears when a workflow
starts, shows exactly what the shell is printing, takes the password ``sudo``
asks for, and withdraws on its own once the workflow succeeded. A failure keeps
it open, because a failure is the case where the output has to be read.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr, tr_format
from .pty_session import PtySession
from .terminal_view import TerminalView

logger = logging.getLogger(__name__)


class _PromptGlyph(QWidget):
    """A small ``>_`` drawn rather than shipped as an asset.

    The icon set has no terminal mark, and a panel that only says a workflow
    name reads like any other card. One glyph is enough to say what this strip
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

DEFAULT_HEIGHT = 280
MINIMUM_HEIGHT = 140
# The panel may be dragged up to half the window and no further; past that the
# page it covers stops being usable and the grid grows without anyone reading
# it. The fallback applies only before the window has a size of its own.
MAXIMUM_HEIGHT_RATIO = 0.5
MAXIMUM_HEIGHT_FALLBACK = 400
ANIMATION_MS = 210
# Long enough to read "finished", short enough not to sit in the way.
AUTO_HIDE_DELAY_MS = 2200


class ConsolePanel(QFrame):
    """A dockable pseudo-terminal pinned to the bottom of the main window."""

    workflow_finished = pyqtSignal(int)
    visibility_changed = pyqtSignal(bool)
    external_terminal_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("consolePanel")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._session: PtySession | None = None
        self._title = ""
        self._launch_path = ""
        self._log_file = ""
        self._panel_height = DEFAULT_HEIGHT
        self._drag_origin: int | None = None
        self._drag_height = 0
        self._auto_hide = True
        # A controller cannot type into the grid, so it needs a field. A
        # keyboard can, and putting a field in front of it turns a terminal
        # into a form. Set from the navigation controller; see
        # ``set_gamepad_present``.
        self._gamepad_present = False
        self._masked = False
        self._prompt_owns_state = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QWidget(self)
        self.header.setObjectName("consoleHeader")
        self.header.setCursor(Qt.CursorShape.SizeVerCursor)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(14, 7, 8, 7)
        header_layout.setSpacing(8)

        # The left half behaves like the active tab of a docked panel: a mark,
        # the workflow's name, and a rule underneath that carries its state.
        self.tab = QWidget(self.header)
        self.tab.setObjectName("consoleTab")
        tab_layout = QHBoxLayout(self.tab)
        tab_layout.setContentsMargins(0, 2, 10, 4)
        tab_layout.setSpacing(8)
        self.glyph = _PromptGlyph(self.tab)
        self.title_label = QLabel(tr("Terminal"), self.tab)
        self.title_label.setObjectName("consoleTitle")
        self.state_label = QLabel("", self.tab)
        self.state_label.setObjectName("consoleState")
        tab_layout.addWidget(self.glyph)
        tab_layout.addWidget(self.title_label)
        tab_layout.addWidget(self.state_label)
        header_layout.addWidget(self.tab)
        header_layout.addStretch(1)

        self.stop_button = self._header_button(tr("Stop"), header_layout)
        self.stop_button.clicked.connect(self._stop_workflow)
        self.copy_button = self._header_button(tr("Copy"), header_layout)
        self.copy_button.clicked.connect(self._copy_everything)
        self.external_button = self._header_button(tr("Open terminal"), header_layout)
        self.external_button.clicked.connect(self._open_external_terminal)
        self.hide_button = self._header_button(tr("Hide"), header_layout)
        self.hide_button.clicked.connect(self.slide_out)

        self.view = TerminalView(self)
        self.view.input_ready.connect(self._send_input)

        # A place to answer from *for a controller*. The grid already takes
        # every keystroke a terminal understands, so with a keyboard this row
        # would only put a form in front of a terminal. A D-pad produces
        # nothing the grid accepts, though, and this is a real text field, so
        # the on-screen keypad Game Mode brings up can reach it. It is
        # therefore shown only while a controller is connected.
        self.input_row = QWidget(self)
        self.input_row.setObjectName("consoleInputRow")
        input_layout = QHBoxLayout(self.input_row)
        input_layout.setContentsMargins(12, 8, 10, 10)
        input_layout.setSpacing(8)
        self.input_label = QLabel(tr("Input"), self.input_row)
        self.input_label.setObjectName("consoleInputLabel")
        self.input_field = QLineEdit(self.input_row)
        self.input_field.setObjectName("consoleInput")
        self.input_field.setPlaceholderText(tr("Type here and press Enter"))
        self.input_field.returnPressed.connect(self._send_typed_input)
        self.send_button = QPushButton(tr("Send"), self.input_row)
        self.send_button.setObjectName("consoleSendButton")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self._send_typed_input)
        input_layout.addWidget(self.input_label)
        input_layout.addWidget(self.input_field, 1)
        input_layout.addWidget(self.send_button)
        self.input_row.setVisible(False)

        layout.addWidget(self.header)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.input_row)

        self._animation = QPropertyAnimation(self, b"maximumHeight", self)
        self._animation.setDuration(ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.finished.connect(self._animation_finished)

        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.slide_out)

        self.setMaximumHeight(0)
        self.setMinimumHeight(0)
        super().setVisible(False)

    @staticmethod
    def _header_button(text: str, layout: QHBoxLayout) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("consoleHeaderButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(button)
        return button

    # ------------------------------------------------------------------ state

    @property
    def busy(self) -> bool:
        return self._session is not None and self._session.running

    def session_pid(self) -> int | None:
        return self._session.pid if self._session is not None else None

    @property
    def is_open(self) -> bool:
        return self.isVisible() and self.maximumHeight() > 0

    def gamepad_focus_scope(self) -> QWidget:
        """Where the keyboard and the controller should land in this panel.

        The answer row while a controller is driving a listening workflow,
        because a D-pad can reach nothing else; the grid otherwise, which is
        both the terminal's own input and the thing a pointer scrolls.
        """
        if self.input_row.isVisible() and self.input_field.isEnabled():
            return self.input_field
        return self.view

    def set_gamepad_present(self, present: bool) -> None:
        """Follow the controller in and out, including mid-workflow.

        A controller can be plugged in while a workflow is already asking for
        something, and unplugged while the user is halfway through an answer.
        Both directions have to end with exactly one place to type: the row
        takes the keyboard when it appears, and gives it back to the grid when
        it goes. The grid keeps working either way — it is the terminal.
        """
        present = bool(present)
        if present == self._gamepad_present:
            return
        self._gamepad_present = present
        if not self.busy:
            # Nothing is listening; ``run`` will size itself when one starts.
            return
        self._apply_input_surface()

    def _apply_input_surface(self) -> None:
        """Put the answer row, the grid size and the focus in agreement."""
        show_row = self._gamepad_present
        self.input_row.setVisible(show_row)
        # The grid is measured against the chrome above and below it. Changing
        # which chrome exists without re-measuring hides the last line behind
        # the row, or leaves a band of dead pixels where it used to be.
        self.view.set_expected_height(self._grid_height(with_input=show_row))
        self.view.set_input_elsewhere(show_row)
        if not show_row:
            self.input_field.clear()
        self._announce_masked_state()
        target = self.gamepad_focus_scope()
        if self.is_open:
            target.setFocus(Qt.FocusReason.OtherFocusReason)

    def set_auto_hide(self, enabled: bool) -> None:
        self._auto_hide = bool(enabled)

    def set_panel_height(self, height: int) -> None:
        """Set the open height, never past what the window can spare.

        The clamp used to live only in the drag handler, so a stored height or
        a programmatic one went straight through: asking for more than the
        window had squeezed the page above it down to a few pixels while the
        grid grew to hundreds of rows. Clamping here covers every caller.
        """
        self._panel_height = max(MINIMUM_HEIGHT, min(int(height), self._available_height()))
        if self.is_open:
            self.setMaximumHeight(self._panel_height)
            self.setMinimumHeight(self._panel_height)

    def panel_height(self) -> int:
        return self._panel_height

    # ------------------------------------------------------------- animation

    def slide_in(self) -> None:
        self._auto_hide_timer.stop()
        was_open = self.is_open
        super().setVisible(True)
        self.setMinimumHeight(0)
        self._animation.stop()
        self._animation.setStartValue(self.maximumHeight())
        self._animation.setEndValue(self._panel_height)
        self._animation.start()
        if not was_open:
            self.visibility_changed.emit(True)

    def slide_out(self) -> None:
        self._auto_hide_timer.stop()
        if not self.isVisible():
            return
        self._animation.stop()
        self.setMinimumHeight(0)
        self._animation.setStartValue(self.maximumHeight())
        self._animation.setEndValue(0)
        self._animation.start()
        self.visibility_changed.emit(False)

    def _animation_finished(self) -> None:
        if self.maximumHeight() <= 0:
            super().setVisible(False)
            return
        # Pin the height so the panel does not creep when the window resizes.
        self.setMinimumHeight(self._panel_height)
        # The panel has its real geometry now, so the estimate that carried the
        # grid through the animation has done its job. Dropping it here means a
        # wrong estimate can never outlive the slide.
        self.view.set_expected_height(0)
        self.gamepad_focus_scope().setFocus(Qt.FocusReason.OtherFocusReason)
        self.view.scroll_to_bottom()

    # --------------------------------------------------- dragging the divider

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._on_header(event) and event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = int(event.globalPosition().y())
            self._drag_height = self.height()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._drag_origin is None:
            super().mouseMoveEvent(event)
            return
        delta = self._drag_origin - int(event.globalPosition().y())
        ceiling = self._available_height()
        self.set_panel_height(max(MINIMUM_HEIGHT, min(self._drag_height + delta, ceiling)))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def _on_header(self, event) -> bool:
        return self.header.geometry().contains(event.position().toPoint())

    def _grid_height(self, *, with_input: bool) -> int:
        """How much of the open panel the terminal grid will actually get.

        Everything that is not the grid has to come off first. Subtracting the
        header alone left the grid a few rows taller than the space it had, so
        the last lines of a workflow were drawn underneath the answer row —
        and because the guess stayed permanently larger than the real
        viewport, it never corrected itself either.
        """
        chrome = self.header.sizeHint().height()
        if with_input:
            chrome += self.input_row.sizeHint().height()
        return max(1, self._panel_height - chrome)

    def _available_height(self) -> int:
        """Half the window, which is as far as the panel may ever come up.

        The page it covers has to stay usable: the console is where a workflow
        reports, not a replacement for the screen behind it.
        """
        window = self.window()
        if window is None or window.height() <= 0:
            return MAXIMUM_HEIGHT_FALLBACK
        return max(MINIMUM_HEIGHT, int(window.height() * MAXIMUM_HEIGHT_RATIO))

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        """Shrink with the window instead of overflowing it."""
        super().resizeEvent(event)
        ceiling = self._available_height()
        if self._panel_height > ceiling:
            self.set_panel_height(ceiling)

    # ------------------------------------------------------------------- run

    def run(
        self,
        argv: list[str],
        *,
        title: str = "",
        log_file: str = "",
        launch_path: str = "",
    ) -> bool:
        """Start a workflow in the panel. Returns False when it cannot be shown."""
        if self.busy:
            return False
        self._release_previous_session()
        self._title = str(title or tr("Terminal"))
        self._log_file = str(log_file or "")
        self._launch_path = str(launch_path or "")
        self.title_label.setText(self._title)
        # Size the grid for the open panel, not for the closed one it still is.
        self.view.set_expected_height(self._grid_height(with_input=self._gamepad_present))
        self.view.clear()
        self._set_state(tr("Running"), "running")
        self.stop_button.setEnabled(True)
        self.slide_in()

        session = PtySession(self)
        session.output.connect(self.view.feed)
        session.finished.connect(self._on_finished)
        session.failed.connect(self._on_failed)
        session.input_mode_changed.connect(self._set_input_masked)
        started = session.start(
            argv,
            columns=self.view.columns,
            rows=self.view.rows,
            # No directory of our own. A terminal emulator inherited the
            # application's, and some generated workflows still name their
            # scripts relative to it; moving the child to the home directory
            # made those workflows fail to find a file that was there.
            cwd=None,
        )
        if not started:
            session.deleteLater()
            return False
        self._session = session
        self.view.size_changed.connect(self._resize_session)
        self._set_input_masked(False)
        self._apply_input_surface()
        return True

    def _release_previous_session(self) -> None:
        """Let go of the finished session before starting another one.

        Each workflow gets its own session object parented to the panel. Left
        alone they accumulate for the life of the window, one per workflow,
        each still holding its timers.
        """
        previous, self._session = self._session, None
        if previous is None:
            return
        try:
            self.view.size_changed.disconnect(self._resize_session)
        except TypeError:
            pass
        previous.shutdown()
        previous.deleteLater()

    def show_text(self, text: str, *, title: str = "") -> bool:
        """Display captured output without running anything.

        Some output is read once and shown afterwards — a raw status, a saved
        report. It used to open a modal window with its own monospace box,
        which meant the application had two different places that show command
        output and only one of them could be scrolled, searched or copied the
        same way. This is the same panel, with nothing listening: the answer
        row stays hidden because there is no process to answer.
        """
        if self.busy:
            return False
        self._release_previous_session()
        self._title = str(title or tr("Terminal"))
        self.title_label.setText(self._title)
        self._log_file = ""
        self._launch_path = ""
        self.view.set_expected_height(self._grid_height(with_input=False))
        self.view.clear()
        self.input_row.setVisible(False)
        self.view.set_input_elsewhere(False)
        self.stop_button.setEnabled(False)
        # No state word: the title already says what this is, and every state
        # this panel has means something about a running workflow.
        self._set_state("", "plain")
        self.slide_in()
        # A captured log has its own line endings; a terminal needs both halves.
        self.view.feed(str(text).replace("\r\n", "\n").replace("\n", "\r\n").encode())
        # Nothing is listening, so nothing should look like it is waiting for
        # a keystroke.
        self.view.screen.cursor_visible = False
        self.view.viewport().update()
        return True

    def _resize_session(self, columns: int, rows: int) -> None:
        if self._session is not None:
            self._session.resize(columns, rows)

    def _send_input(self, payload: bytes) -> None:
        if self._session is not None:
            self._session.write(payload)

    def _send_typed_input(self) -> None:
        """Send what the field holds, exactly as if it had been typed."""
        if self._session is None or not self._session.running:
            return
        text = self.input_field.text()
        self.input_field.clear()
        self._session.write(text.encode("utf-8") + b"\r")
        self.view.scroll_to_bottom()

    def _set_input_masked(self, masked: bool) -> None:
        """Follow the workflow: a prompt that hides its input gets a hidden field."""
        masked = bool(masked)
        self._masked = masked
        self.input_field.setEchoMode(
            QLineEdit.EchoMode.Password if masked else QLineEdit.EchoMode.Normal
        )
        self.input_field.setPlaceholderText(
            tr("Nothing you type here is shown") if masked
            else tr("Type here and press Enter")
        )
        self.input_label.setText(
            tr("Administrator password") if masked else tr("Input")
        )
        self.input_row.setProperty("mode", "secret" if masked else "plain")
        for widget in (self.input_row, self.input_label):
            style = widget.style()
            if style is not None:
                style.unpolish(widget)
                style.polish(widget)
        self._announce_masked_state()
        if masked and self.input_row.isVisible():
            # The prompt is the reason the panel is on screen right now.
            self.input_field.setFocus(Qt.FocusReason.OtherFocusReason)

    def _announce_masked_state(self) -> None:
        """Say that a hidden prompt is waiting, when nothing else can say it.

        A password prompt shows no characters even while it is working, which
        looks exactly like a panel ignoring the keyboard. The answer row used
        to carry that message in its label and its secret styling. With a
        keyboard the row is gone, so the state beside the title carries it
        instead, and the grid keeps the caret so there is somewhere to type.
        """
        if not self.busy:
            return
        if self._masked and not self.input_row.isVisible():
            self._prompt_owns_state = True
            self._set_state(tr("Administrator password"), "warning")
            if self.is_open:
                self.view.setFocus(Qt.FocusReason.OtherFocusReason)
        elif self._prompt_owns_state:
            # Only take back the word this method put there. "Stop" and
            # "Failed" are set while the process is still running, and the
            # echo watcher polls every 120 ms — without this guard it would
            # quietly relabel a stopping workflow as a running one.
            self._prompt_owns_state = False
            self._set_state(tr("Running"), "running")

    def _stop_workflow(self) -> None:
        if self._session is None or not self._session.running:
            return
        self._set_state(tr("Stop"), "warning")
        self.stop_button.setEnabled(False)
        self._session.terminate()

    def _on_failed(self, message: str) -> None:
        self.view.feed(f"\r\n{message}\r\n".encode())
        self._set_state(tr("Failed"), "failed")
        self.stop_button.setEnabled(False)

    def _on_finished(self, code: int) -> None:
        self.stop_button.setEnabled(False)
        # Nothing is listening any more; leaving the field would invite typing
        # into a process that has already gone.
        self.input_row.setVisible(False)
        self.input_field.clear()
        self.view.set_input_elsewhere(False)
        try:
            self.view.size_changed.disconnect(self._resize_session)
        except TypeError:
            pass
        if code == 0:
            self._set_state(tr("Completed"), "ok")
            self.view.feed(b"\r\n")
            if self._auto_hide:
                self._auto_hide_timer.start(AUTO_HIDE_DELAY_MS)
        else:
            # A failed workflow is exactly the one whose output matters, so the
            # panel stays open and says what the exit code was.
            self._set_state(tr_format("Exit code {code}", code=code), "failed")
        self.workflow_finished.emit(code)

    def _set_state(self, text: str, tone: str) -> None:
        self.state_label.setText(f"· {text}" if text else "")
        for widget in (self.state_label, self.tab):
            widget.setProperty("tone", tone)
            style = widget.style()
            if style is not None:
                style.unpolish(widget)
                style.polish(widget)

    # --------------------------------------------------------------- actions

    def _copy_everything(self) -> None:
        if self.view.copy_everything():
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and self._log_file:
            clipboard.setText(self._log_file)

    def _open_external_terminal(self) -> None:
        if self._launch_path:
            self.external_terminal_requested.emit(self._launch_path)

    def retranslate(self) -> None:
        self._set_input_masked(
            self._session.input_is_masked if self._session is not None else False
        )
        self.send_button.setText(tr("Send"))
        self.stop_button.setText(tr("Stop"))
        self.copy_button.setText(tr("Copy"))
        self.external_button.setText(tr("Open terminal"))
        self.hide_button.setText(tr("Hide"))
        if not self._title:
            self.title_label.setText(tr("Terminal"))

    def apply_theme(self) -> None:
        self.view.apply_theme()

    def shutdown(self) -> None:
        """Stop everything, for application close."""
        self._auto_hide_timer.stop()
        self._animation.stop()
        self.view.shutdown()
        if self._session is not None:
            self._session.shutdown()
            self._session = None
