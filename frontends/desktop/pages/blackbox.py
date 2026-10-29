"""The black box: the last seconds of the GPU, from the window.

A hard freeze leaves nothing in the kernel log, so the recorder writes the GPU
clock, its load, the temperatures, the GFX voltage, power, fans, the CPU clock
and the free memory four times a second and flushes every line. This page
starts and stops it, shows what it wrote last as a table (newest row first, in
the same look as Processes) and says how that recording ended: a restart or a
freeze that cut it off is the one that matters. The next problem report
attaches the end of it.
"""

from __future__ import annotations

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..components.async_tools import BackgroundExecutor
from ..components.buttons import WrappingButton as QPushButton
from ..components.page_widgets import SectionCard
from ..components.responsive import configure_responsive_scroll_area
from ..components.toast import show_toast
from ..components.toggle_switch import ToggleSwitch
from ..components.widgets import InfoDialog
from ..i18n import tr, tr_format
from ..theme import COLORS, scale_stylesheet
from .processes import process_stylesheet

REFRESH_INTERVAL_MS = 1000
#: (heading, key of the row, aligned to the right). Units are in the heading.
COLUMNS = (
    ("Time", "time", False),
    ("GPU clock", "clock", False),
    ("GPU load", "busy", True),
    ("GPU °C", "t_gpu", True),
    ("CPU °C", "t_cpu", True),
    ("GFX mV", "volts", True),
    ("Power W", "watts", True),
    ("Fans rpm", "rpm", False),
    ("CPU MHz", "cpu", True),
    ("Free RAM MiB", "mem", True),
)
#: How the last recording ended, said in words (the keys are blackbox.read_session's).
STATE_TEXT = {
    "none": "Nothing was recorded yet. Start the black box before playing to catch a freeze.",
    "recording": "Recording now. The newest row is at the top.",
    "stopped": "Stopped. These are the last rows it recorded.",
    "stopped-before-restart": "It was stopped normally before the last restart. These are the last rows it recorded.",
    "cut-off": "Cut off by a restart or a freeze. The top rows are the board's last seconds.",
}


class SampleModel(QAbstractTableModel):
    """Every row of the recording. A view draws the few on screen, so thousands cost nothing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 - Qt API name
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 - Qt API name
        return 0 if parent.isValid() else len(COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        _heading, key, right = COLUMNS[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            text = str(self._rows[index.row()].get(key, "-"))
            return "–" if text in {"-", ""} else text
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft))
        return None

    def headerData(self, section: int, orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return tr(COLUMNS[section][0]).upper()
        return None


class BlackBoxPage(QWidget):
    """Start, stop and read the black box."""

    @staticmethod
    def _stylesheet() -> str:
        # The Processes sheet styles a QTableWidget; this page draws a QTableView.
        c = COLORS
        back = scale_stylesheet(f"""
QWidget[processPage='true'] QPushButton[processButton='back'] {{
    background: {c['blue_soft']}; color: {c['blue']}; border: 1px solid {c['blue_soft']};
    border-radius: 8px; min-height: 0px; padding: 7px 16px; font-size: 11px; font-weight: 700;
}}
QWidget[processPage='true'] QPushButton[processButton='back']:hover {{ border-color: {c['blue']}; }}
""")
        return process_stylesheet().replace("QTableWidget", "QTableView") + back

    def _mark_back_button(self, going_back: bool) -> None:
        """Pale blue with an arrow while the button leads back to the recording."""
        self.diagnosis_button.setProperty("processButton", "back" if going_back else "secondary")
        self.diagnosis_button.style().unpolish(self.diagnosis_button)
        self.diagnosis_button.style().polish(self.diagnosis_button)

    def apply_appearance(self) -> None:
        self.setStyleSheet(self._stylesheet())
        # The diagnosis view keeps its own sheet: without this it kept the colours of the
        # theme it was opened in (pale text on a pale page after switching to light).
        if getattr(self, "diagnosis_view", None) is not None:
            self.diagnosis_view.apply_appearance()
        self.update()

    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        # Same look as Processes: its stylesheet keys off this property.
        self.setProperty("processPage", True)
        self.setStyleSheet(self._stylesheet())
        self._background = BackgroundExecutor(self)
        self._state: dict = {}
        self._pending_rows: list[dict] | None = None
        self._shown_signature: tuple | None = None
        self._updates_active = False
        self._syncing = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea()
        self.content = QWidget()
        configure_responsive_scroll_area(self.scroll, self.content)
        self.content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.content.setProperty("redesignedModule", True)
        root = QVBoxLayout(self.content)
        root.setContentsMargins(18, 8, 18, 20)
        root.setSpacing(14)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll)

        self.card = SectionCard(
            "Black box",
            "Records the GPU clock, load, temperatures, voltage, power, fans, CPU clock and free memory four "
            "times a second, so the next problem report shows the seconds before a freeze.",
            icon_name="",
        )
        self.card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.card, 1)

        # -- controls ---------------------------------------------------------
        self.controls = QGridLayout()
        self.controls.setContentsMargins(0, 0, 0, 0)
        self.controls.setHorizontalSpacing(10)
        self.controls.setVerticalSpacing(8)
        self.record_button = self._button("Start recording", self._toggle_recording, primary=True)
        self.folder_button = self._button("Open folder", self._open_folder)
        self.diagnosis_button = self._button("View full diagnosis", self._view_full_diagnosis)
        self.autostart_switch = ToggleSwitch()
        self.autostart_switch.setAccessibleName(tr("Start with the session"))
        self.autostart_switch.toggled.connect(self._autostart_toggled)
        self.autostart_label = QLabel(tr("Start with the session"))
        self.autostart_label.setProperty("readingLabel", True)
        self.autostart_label.setToolTip(tr("Starts the black box at every login with a systemd user service."))
        self.controls.addWidget(self.record_button, 0, 0)
        self.controls.addWidget(self.folder_button, 0, 1)
        self.controls.addWidget(self.diagnosis_button, 0, 2)
        self.controls.setColumnStretch(3, 1)
        self.controls.addWidget(self.autostart_switch, 0, 4)
        self.controls.addWidget(self.autostart_label, 0, 5)
        self.card.body.addLayout(self.controls)

        self.state_label = QLabel("")
        self.state_label.setWordWrap(True)
        self.state_label.setProperty("sectionSubtitle", True)
        self.card.body.addWidget(self.state_label)

        rule = QFrame()
        rule.setProperty("processRule", True)
        rule.setFixedHeight(1)
        self.card.body.addWidget(rule)

        # -- table ------------------------------------------------------------
        self.model = SampleModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAccessibleName(tr("Black box"))
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setCornerButtonEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        # Same height everywhere: with thousands of rows, measuring each one is the cost.
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setMinimumHeight(260)
        header = self.table.horizontalHeader()
        header.setSectionsClickable(False)
        header.setHighlightSections(False)
        for index in range(len(COLUMNS)):
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalScrollBar().valueChanged.connect(self._scrolled)

        # Reading older rows must not be pulled out from under the reader.
        self.paused_label = QLabel(tr("Paused while you read. Go back to the top to follow the recording."))
        self.paused_label.setProperty("sectionSubtitle", True)
        self.paused_label.setWordWrap(True)
        self.paused_label.hide()

        self.footer = QLabel("")
        self.footer.setProperty("processFooter", True)
        self.footer.setWordWrap(True)
        self.footer.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.recording_page = QWidget()
        recording_layout = QVBoxLayout(self.recording_page)
        recording_layout.setContentsMargins(0, 0, 0, 0)
        recording_layout.setSpacing(8)
        recording_layout.addWidget(self.table, 1)
        recording_layout.addWidget(self.paused_label)
        recording_layout.addWidget(self.footer)
        self.diagnosis_view = None  # built when it is first asked for: collecting it takes seconds
        self.diagnosis_page = QWidget()
        self.diagnosis_layout = QVBoxLayout(self.diagnosis_page)
        self.diagnosis_layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        self.stack.setMinimumHeight(420)
        self.stack.addWidget(self.recording_page)
        self.stack.addWidget(self.diagnosis_page)
        self.card.body.addWidget(self.stack, 1)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(REFRESH_INTERVAL_MS)
        self.refresh_timer.timeout.connect(self.refresh)

    # -- construction --------------------------------------------------------

    def _button(self, text: str, slot, *, primary: bool = False) -> QPushButton:
        button = QPushButton(tr(text))
        button.setProperty("processButton", "secondary")
        if primary:
            button.setProperty("PrimaryAction", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False: slot())
        return button

    # -- updates -------------------------------------------------------------

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if self._updates_active:
            self.refresh()
            if not self.refresh_timer.isActive():
                self.refresh_timer.start()
        else:
            self.refresh_timer.stop()

    def refresh(self) -> None:
        self._background.start(
            "status",
            lambda: self.controller.blackbox_estado(),
            on_success=self._apply_state,
            # A read that fails once a second must not open a window each time.
            on_error=lambda _message: None,
        )

    def _apply_state(self, state: dict) -> None:
        self._state = dict(state or {})
        self._render()

    def retranslate_dynamic_copy(self) -> None:
        self.model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(COLUMNS) - 1)
        self._render()

    # -- drawing -------------------------------------------------------------

    def _render(self) -> None:
        state = self._state
        if not state:
            return
        supported = bool(state.get("supported"))
        running = bool(state.get("running"))
        self.record_button.setText(tr("Stop recording" if running else "Start recording"))
        self.record_button.setProperty("PrimaryAction", not running)
        self.record_button.style().unpolish(self.record_button)
        self.record_button.style().polish(self.record_button)
        self.record_button.setEnabled(supported and not self._background.is_running("action"))

        autostart = state.get("autostart") or {}
        offered = bool(autostart.get("supported"))
        self.autostart_switch.setVisible(offered)
        self.autostart_label.setVisible(offered)
        self._syncing = True
        try:
            self.autostart_switch.setChecked(bool(autostart.get("enabled")))
        finally:
            self._syncing = False
        self.autostart_switch.setEnabled(not autostart.get("foreign") and not self._background.is_running("autostart"))

        key = str(state.get("state") or "none")
        self.state_label.setText(tr(STATE_TEXT.get(key, STATE_TEXT["none"])))
        self.state_label.setStyleSheet(
            f"color: {COLORS['orange']};" if key == "cut-off" else ""
        )
        self._show_rows(list(state.get("rows") or ()))
        header = str(state.get("header") or "")
        details = header.split(" ", 2)[-1] if header.startswith("# boot=") else ""
        self.footer.setText(
            tr_format("{count} rows shown · {path}", count=self.model.rowCount(), path=str(state.get("directory") or ""))
            + (f"\n{details}" if details else "")
        )

    def _following(self) -> bool:
        return self.table.verticalScrollBar().value() == 0

    def _show_rows(self, rows: list[dict]) -> None:
        """Newest row first. While the reader is further down, the rows wait."""
        if not self._following():
            self._pending_rows = rows
            self.paused_label.show()
            return
        self._pending_rows = None
        self.paused_label.hide()
        # A stopped recording does not change: leave the view as it is.
        signature = (len(rows), rows[0].get("time") if rows else None, rows[-1].get("time") if rows else None)
        if signature != self._shown_signature:
            self._shown_signature = signature
            self.model.set_rows(rows)

    def _scrolled(self, value: int) -> None:
        if value == 0 and self._pending_rows is not None:
            self._show_rows(self._pending_rows)

    # -- actions -------------------------------------------------------------

    def _toggle_recording(self) -> None:
        running = bool(self._state.get("running"))
        operation = self.controller.blackbox_detener if running else self.controller.blackbox_iniciar
        self.record_button.setEnabled(False)
        self._background.start(
            "action", operation,
            on_success=lambda _result: self._after_action(),
            on_error=self._action_failed,
            on_finished=self._action_finished,
        )

    def _after_action(self) -> None:
        # The recorder needs a moment to write its pid file.
        QTimer.singleShot(700, self.refresh)

    def _action_finished(self) -> None:
        self._render()

    def _action_failed(self, message: str) -> None:
        self._show_failure(message, tone="red")
        self.refresh()

    def _show_failure(self, message: str, *, tone: str) -> None:
        InfoDialog(
            "Could not change the black box",
            message,
            icon_name="warning_orange",
            eyebrow="Black box",
            button_text="Close",
            notice="No changes were made.",
            tone=tone,
            parent=self,
        ).open()

    def _autostart_toggled(self, checked: bool) -> None:
        if self._syncing:
            return
        self.autostart_switch.setEnabled(False)
        self._background.start(
            "autostart",
            lambda: self.controller.blackbox_con_la_sesion(checked),
            on_success=lambda _state: self._autostart_done(checked),
            on_error=self._autostart_failed,
            on_finished=self.refresh,
        )

    def _autostart_done(self, enabled: bool) -> None:
        show_toast(self, tr("Start with the session"), tr("On" if enabled else "Off"), tone="green")

    def _autostart_failed(self, message: str) -> None:
        self._show_failure(message, tone="orange")

    def _view_full_diagnosis(self) -> None:
        """Swap the recording for the diagnosis a report attaches, in the same place; again to come back."""
        showing = self.stack.currentWidget() is self.diagnosis_page
        if showing:
            self.stack.setCurrentWidget(self.recording_page)
            self.diagnosis_button.setText(tr("View full diagnosis"))
            self._mark_back_button(False)
            self.state_label.show()
            return
        if self.diagnosis_view is None:
            from ..components.full_diagnosis_dialog import FullDiagnosisView

            self.diagnosis_view = FullDiagnosisView(self.diagnosis_page, collect=self.controller.diagnostico_completo)
            self.diagnosis_layout.addWidget(self.diagnosis_view)
        self.stack.setCurrentWidget(self.diagnosis_page)
        self.diagnosis_button.setText("← " + tr("Back to the recording"))
        self._mark_back_button(True)
        # How the recording ended belongs to the table, which is not on screen now.
        self.state_label.hide()

    def _open_folder(self) -> None:
        directory = str(self._state.get("directory") or "")
        if directory:
            QDesktopServices.openUrl(QUrl.fromLocalFile(directory))
