"""The console that slides up from the foot of the window.

Workflows used to open a terminal emulator of the user's desktop, which meant
a separate window, a different theme, and on some systems no terminal at all.
The panel keeps the workflow inside the application: it appears when a workflow
starts, shows exactly what the shell is printing, takes the password ``sudo``
asks for, and withdraws on its own once the workflow succeeded. A failure keeps
it open, because a failure is the case where the output has to be read.

It holds a strip of tabs rather than a single terminal. Preparing dependencies
and then opening something else used to end with a terminal window of the
desktop appearing over the application, because the one terminal was taken;
now the second workflow gets a tab beside the first and both stay inside the
window.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..components.widgets import icon
from ..i18n import tr
from .console_tab import ConsoleTab

logger = logging.getLogger(__name__)

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
# Past this the strip stops reading as a set of tabs and starts reading as a
# list, and each one still holds a pseudo-terminal of its own. A workflow that
# arrives with every tab taken falls back to a terminal window, exactly as the
# whole console did before tabs existed.
MAXIMUM_TABS = 5


class ConsolePanel(QFrame):
    """A dockable pseudo-terminal pinned to the bottom of the main window."""

    workflow_started = pyqtSignal()
    workflow_finished = pyqtSignal(int)
    visibility_changed = pyqtSignal(bool)
    external_terminal_requested = pyqtSignal(str)
    #: How many workflows are running right now, whenever that number moves.
    running_count_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("consolePanel")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._tabs: list[ConsoleTab] = []
        self._active: ConsoleTab | None = None
        self._panel_height = DEFAULT_HEIGHT
        self._drag_origin: int | None = None
        self._drag_height = 0
        self._auto_hide = True
        self._running_count = 0
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
        header_layout.setContentsMargins(8, 7, 8, 7)
        header_layout.setSpacing(8)

        # The tab strip, the way an editor puts its terminals in one corner.
        self.tab_strip = QWidget(self.header)
        self.tab_strip.setObjectName("consoleTabStrip")
        self._strip_layout = QHBoxLayout(self.tab_strip)
        self._strip_layout.setContentsMargins(0, 0, 0, 0)
        self._strip_layout.setSpacing(4)
        header_layout.addWidget(self.tab_strip)
        header_layout.addStretch(1)

        self.stop_button = self._header_button(
            tr("Stop"), header_layout, icon_name="stop_red"
        )
        self.stop_button.clicked.connect(self._stop_workflow)
        self.copy_button = self._header_button(
            tr("Copy"), header_layout, icon_name="copy_gray", icon_only=True
        )
        self.copy_button.clicked.connect(self._copy_everything)
        self.external_button = self._header_button(
            tr("Open terminal"), header_layout,
            icon_name="external_gray", icon_only=True,
        )
        self.external_button.clicked.connect(self._open_external_terminal)
        self.hide_button = self._header_button(
            tr("Hide"), header_layout,
            icon_name="chevron_down_gray", icon_only=True,
        )
        self.hide_button.clicked.connect(self.slide_out)

        self.stack = QStackedWidget(self)
        self.stack.setObjectName("consoleStack")

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
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.input_row)

        self._animation = QPropertyAnimation(self, b"maximumHeight", self)
        self._animation.setDuration(ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.finished.connect(self._animation_finished)

        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.slide_out)

        # One tab from the start, so the panel looks and behaves exactly as it
        # did while nothing concurrent is happening.
        self._activate(self._new_tab())

        self.setMaximumHeight(0)
        self.setMinimumHeight(0)
        super().setVisible(False)

    @staticmethod
    def _header_button(
        text: str,
        layout: QHBoxLayout,
        *,
        icon_name: str = "",
        icon_only: bool = False,
    ) -> QPushButton:
        """A header action, as an icon with a tooltip or an icon beside a label.

        The secondary actions are icon-only: they are the shapes every terminal
        uses, they keep the header from crowding the workflow title, and the
        tooltip still names them. Stop keeps its word — it ends a running
        privileged workflow, and that is not a thing to leave to a glyph.
        """
        button = QPushButton("" if icon_only else text)
        button.setObjectName("consoleHeaderButton")
        button.setProperty("iconOnly", bool(icon_only))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolTip(text)
        if icon_name:
            button.setIcon(icon(icon_name))
            button.setIconSize(QSize(16, 16))
        layout.addWidget(button)
        return button

    # ------------------------------------------------------------------ tabs

    def _new_tab(self) -> ConsoleTab:
        tab = ConsoleTab(self.tab_strip)
        tab.activated.connect(lambda t=tab: self._activate(t))
        tab.close_requested.connect(lambda t=tab: self.close_tab(t))
        tab.finished.connect(lambda code, t=tab: self._on_finished(t, code))
        tab.failed.connect(lambda _message, t=tab: self._on_failed_tab(t))
        tab.input_mode_changed.connect(
            lambda masked, t=tab: self._on_input_mode_changed(t, masked)
        )
        self._strip_layout.addWidget(tab)
        self._tabs.append(tab)
        self.stack.addWidget(tab.view)
        self._sync_strip()
        return tab

    def _activate(self, tab: ConsoleTab) -> None:
        if tab not in self._tabs:
            return
        self._active = tab
        for other in self._tabs:
            other.set_active(other is tab)
        self.stack.setCurrentWidget(tab.view)
        self.stop_button.setEnabled(tab.running)
        self._masked = tab.input_is_masked()
        self._set_input_masked(self._masked)
        self._apply_input_surface()

    def close_tab(self, tab: ConsoleTab) -> None:
        """Dismiss a finished workflow's tab. The last one is only emptied.

        Closing every tab would leave the panel with no grid at all, and the
        next workflow would have to build one before it could print its first
        line. The last tab is reset instead, which is the state the panel
        starts in.
        """
        if tab.running:
            return
        if len(self._tabs) <= 1:
            tab.show_text("", title="")
            return
        self._tabs.remove(tab)
        self.stack.removeWidget(tab.view)
        self._strip_layout.removeWidget(tab)
        tab.shutdown()
        tab.view.deleteLater()
        tab.deleteLater()
        if self._active is tab:
            self._activate(self._tabs[-1])
        self._sync_strip()

    def _sync_strip(self) -> None:
        """Only wear the look of a tab strip when there is more than one."""
        several = len(self._tabs) > 1
        self.tab_strip.setProperty("several", several)
        # Repolishing a container leaves its children with the style they were
        # given under the old property, so the second tab would arrive with
        # the first still wearing the single-tab look.
        style = self.tab_strip.style()
        if style is not None:
            style.unpolish(self.tab_strip)
            style.polish(self.tab_strip)
        for tab in self._tabs:
            tab.set_among_others(several)

    def _tab_for_next_workflow(self) -> ConsoleTab | None:
        """Where the next workflow goes: a spare tab, a new one, or nowhere."""
        for tab in self._tabs:
            if tab.is_reusable():
                return tab
        if len(self._tabs) < MAXIMUM_TABS:
            return self._new_tab()
        # Every tab is either running or holding a failure nobody has read
        # yet. Declining here is what puts the workflow in a terminal window
        # rather than losing it.
        for tab in self._tabs:
            if not tab.running:
                return tab
        return None

    def tab_count(self) -> int:
        return len(self._tabs)

    def running_count(self) -> int:
        return sum(1 for tab in self._tabs if tab.running)

    def _announce_running_count(self) -> None:
        count = self.running_count()
        if count == self._running_count:
            return
        self._running_count = count
        self.running_count_changed.emit(count)

    # ------------------------------------------------------------------ state

    @property
    def active_tab(self) -> ConsoleTab:
        return self._active if self._active is not None else self._tabs[0]

    @property
    def view(self):
        return self.active_tab.view

    @property
    def title_label(self) -> QLabel:
        return self.active_tab.title_label

    @property
    def state_label(self) -> QLabel:
        return self.active_tab.state_label

    @property
    def busy(self) -> bool:
        return any(tab.running for tab in self._tabs)

    def session_pid(self) -> int | None:
        return self.active_tab.session_pid()

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
        show_row = self._gamepad_present and self.active_tab.running
        self.input_row.setVisible(show_row)
        # The grid is measured against the chrome above and below it. Changing
        # which chrome exists without re-measuring hides the last line behind
        # the row, or leaves a band of dead pixels where it used to be.
        height = self._grid_height(with_input=show_row)
        for tab in self._tabs:
            tab.view.set_expected_height(height)
            tab.view.set_input_elsewhere(show_row)
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
        for tab in self._tabs:
            tab.view.set_expected_height(0)
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
        """Start a workflow in a tab. Returns False when it cannot be shown."""
        tab = self._tab_for_next_workflow()
        if tab is None:
            return False
        started = tab.run(
            list(argv),
            title=title,
            log_file=log_file,
            launch_path=launch_path,
            grid_height=self._grid_height(with_input=self._gamepad_present),
        )
        if not started:
            return False
        self._activate(tab)
        self.stop_button.setEnabled(True)
        self.slide_in()
        self._announce_running_count()
        self.workflow_started.emit()
        return True

    def adopt_session(self, session, *, title: str = "", transcript: str = "") -> bool:
        """Take over a workflow another console started, and show it.

        The first-run panel runs the dependency install in a terminal of its
        own, because the shell behind it — this panel included — is not
        accepting input while it is up. Finishing the setup before that
        install is done must not kill it, so it arrives here instead.
        """
        if session is None:
            return False
        tab = self._tab_for_next_workflow()
        if tab is None:
            return False
        tab.adopt(session, title=title, transcript=transcript)
        self._activate(tab)
        self.stop_button.setEnabled(tab.running)
        self.slide_in()
        self._announce_running_count()
        self.workflow_started.emit()
        return True

    def show_text(self, text: str, *, title: str = "") -> bool:
        """Display captured output without running anything.

        Some output is read once and shown afterwards — a raw status, a saved
        report. It used to open a modal window with its own monospace box,
        which meant the application had two different places that show command
        output and only one of them could be scrolled, searched or copied the
        same way. This is the same panel, with nothing listening: the answer
        row stays hidden because there is no process to answer.
        """
        tab = self._tab_for_next_workflow()
        if tab is None:
            return False
        tab.show_text(text, title=title, grid_height=self._grid_height(with_input=False))
        self._activate(tab)
        self.stop_button.setEnabled(False)
        self.slide_in()
        return True

    def _send_typed_input(self) -> None:
        """Send what the field holds, exactly as if it had been typed."""
        tab = self.active_tab
        if not tab.running:
            return
        text = self.input_field.text()
        self.input_field.clear()
        tab.send_input(text.encode("utf-8") + b"\r")
        self.view.scroll_to_bottom()

    def _on_input_mode_changed(self, tab: ConsoleTab, masked: bool) -> None:
        """Only the tab on screen may move the one answer row there is."""
        if tab is not self._active:
            return
        self._set_input_masked(masked)

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
        tab = self.active_tab
        if not tab.running:
            return
        if self._masked and not self.input_row.isVisible():
            self._prompt_owns_state = True
            tab.set_state(tr("Administrator password"), "warning")
            if self.is_open:
                self.view.setFocus(Qt.FocusReason.OtherFocusReason)
        elif self._prompt_owns_state:
            # Only take back the word this method put there. "Stop" and
            # "Failed" are set while the process is still running, and the
            # echo watcher polls every 120 ms — without this guard it would
            # quietly relabel a stopping workflow as a running one.
            self._prompt_owns_state = False
            tab.set_state(tr("Running"), "running")

    def _stop_workflow(self) -> None:
        tab = self.active_tab
        if not tab.running:
            return
        self.stop_button.setEnabled(False)
        tab.stop()

    def _on_failed_tab(self, tab: ConsoleTab) -> None:
        if tab is self._active:
            self.stop_button.setEnabled(False)

    def _on_finished(self, tab: ConsoleTab, code: int) -> None:
        if tab is self._active:
            self.stop_button.setEnabled(False)
            # Nothing is listening any more; leaving the field would invite
            # typing into a process that has already gone.
            self.input_row.setVisible(False)
            self.input_field.clear()
            self.view.set_input_elsewhere(False)
        if code == 0 and self._auto_hide and not self.busy:
            # Only when the last one is done: withdrawing the panel over a
            # workflow that is still printing would hide the running one.
            self._auto_hide_timer.start(AUTO_HIDE_DELAY_MS)
        # A failure in a tab the user is not watching stays where it is. Its
        # chip turns red and says the exit code, which is the whole reason the
        # state lives on the tab rather than in one shared header — pulling
        # the screen out from under whatever they are reading would not make
        # it any easier to find.
        self._announce_running_count()
        self.workflow_finished.emit(code)

    # --------------------------------------------------------------- actions

    def _copy_everything(self) -> None:
        if self.view.copy_everything():
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and self.active_tab.log_file:
            clipboard.setText(self.active_tab.log_file)

    def _open_external_terminal(self) -> None:
        if self.active_tab.launch_path:
            self.external_terminal_requested.emit(self.active_tab.launch_path)

    def retranslate(self) -> None:
        self._set_input_masked(self.active_tab.input_is_masked())
        self.send_button.setText(tr("Send"))
        self.stop_button.setText(tr("Stop"))
        self.stop_button.setToolTip(tr("Stop"))
        for button, label in (
            (self.copy_button, "Copy"),
            (self.external_button, "Open terminal"),
            (self.hide_button, "Hide"),
        ):
            # Icon-only: the word lives in the tooltip, so that is what a
            # language change has to rewrite.
            button.setToolTip(tr(label))
        for tab in self._tabs:
            tab.retranslate()

    def apply_theme(self) -> None:
        for tab in self._tabs:
            tab.view.apply_theme()

    def shutdown(self) -> None:
        """Stop everything, for application close."""
        self._auto_hide_timer.stop()
        self._animation.stop()
        for tab in self._tabs:
            tab.shutdown()
        self._announce_running_count()
