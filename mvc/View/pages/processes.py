from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import time
from typing import Iterable

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..components.async_tools import BackgroundExecutor
from ..i18n import count_label, tr, tr_format
from ..components.page_widgets import ControlPageHeader, ConfirmDialog, SectionCard
from ..components.responsive import configure_responsive_scroll_area, effective_viewport_width
from ..core.state import state_cache_for
from ..theme import COLORS, scale_stylesheet
from ..components.widgets import IconBadge, InfoDialog, PillLabel, icon


def formato_bytes(value: int | float) -> str:
    """Format byte counters locally without importing the retired GUI tree."""
    size = max(0.0, float(value or 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            precision = 0 if unit == "B" else 1
            return f"{size:.{precision}f} {unit}"
        size /= 1024.0
    return "0 B"


@lru_cache(maxsize=256)
def icono_app(name: str, command: str) -> QIcon:
    """Resolve a desktop icon once per application signature."""
    executable = Path(str(command or "").strip().split(maxsplit=1)[0]).name
    normalized_name = str(name or "").strip().lower().replace(" ", "-")
    for candidate in dict.fromkeys((executable, normalized_name)):
        if not candidate:
            continue
        themed = QIcon.fromTheme(candidate)
        if not themed.isNull():
            return themed
    return icon("processes_gray")


def process_stylesheet() -> str:
    c = COLORS
    return scale_stylesheet(f"""
QWidget[processPage='true'] QFrame[processFilterBar='true'],
QWidget[processPage='true'] QFrame[processActionBar='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 12px;
}}
QWidget[processPage='true'] QFrame[processFilterBar='true'] {{ min-height: 48px; }}
QWidget[processPage='true'] QFrame[processActionBar='true'] {{
    background: {c['blue_soft']}; border-color: {c['blue_border']};
}}
QWidget[processPage='true'] QLineEdit[processSearch='true'] {{
    min-height: 40px; background: {c['control']}; border: 1px solid {c['border']};
    border-radius: 10px; padding: 0 13px; color: {c['text']}; font-size: 11px; font-weight: 620;
    selection-background-color: {c['blue']}; selection-color: {c['on_accent']};
}}
QWidget[processPage='true'] QLineEdit[processSearch='true']:focus {{
    border-color: {c['focus']}; background: {c['panel_raised']};
}}
QWidget[processPage='true'] QCheckBox {{ color: {c['muted']}; font-size: 10px; font-weight: 700; spacing: 7px; }}
QWidget[processPage='true'] QTableWidget {{
    background: {c['panel']}; alternate-background-color: {c['panel_alt']};
    border: 1px solid {c['border_soft']}; border-radius: 12px; outline: none;
    gridline-color: transparent; color: {c['text']}; font-size: 10px;
}}
QWidget[processPage='true'] QTableWidget::item {{ border-bottom: 1px solid {c['border_soft']}; padding: 0 10px; }}
QWidget[processPage='true'] QTableWidget::item:selected {{ background: {c['selection']}; color: {c['text']}; }}
QWidget[processPage='true'] QHeaderView::section {{
    background: {c['panel_alt']}; color: {c['muted']}; border: none;
    border-bottom: 1px solid {c['border']}; padding: 9px 10px; font-size: 9px; font-weight: 820;
}}
QWidget[processPage='true'] QLabel[appName='true'] {{ color: {c['text']}; font-size: 11px; font-weight: 790; }}
QWidget[processPage='true'] QLabel[appCommand='true'] {{ color: {c['subtle']}; font-size: 9px; font-weight: 520; }}
QWidget[processPage='true'] QLabel[selectionKicker='true'] {{
    color: {c['blue']}; font-size: 8px; font-weight: 840; letter-spacing: 0.8px;
}}
QWidget[processPage='true'] QLabel[selectedSummary='true'] {{ color: {c['text']}; font-size: 11px; font-weight: 740; }}
QWidget[processPage='true'] QLabel[processFooter='true'] {{ color: {c['subtle']}; font-size: 9px; font-weight: 560; }}
QWidget[processPage='true'] QLabel[memoryValue='true'] {{ color: {c['text']}; font-size: 10px; font-weight: 760; }}
QWidget[processPage='true'] QProgressBar[processMemory='true'] {{
    min-height: 5px; max-height: 5px; background: {c['progress_track']}; border: none; border-radius: 2px; text-align: center;
}}
QWidget[processPage='true'] QProgressBar[processMemory='true']::chunk {{ background: {c['blue']}; border-radius: 2px; }}
QWidget[processPage='true'] QPushButton[processActionButton='true'] {{
    min-height: 40px; min-width: 126px; padding: 0 14px; font-size: 10px; font-weight: 740;
}}
QWidget[processPage='true'] QPushButton[processSecondaryAction='true'] {{
    background: {c['control']}; border: 1px solid {c['border']}; border-radius: 10px; color: {c['text']};
}}
QWidget[processPage='true'] QPushButton[processSecondaryAction='true']:hover {{
    background: {c['control_hover']}; border-color: {c['border_strong']};
}}
""")



APP_NAMES = (
    ("firefox", "Firefox"),
    ("google-chrome", "Google Chrome"),
    ("chrome", "Chrome"),
    ("chromium", "Chromium"),
    ("brave", "Brave"),
    ("vivaldi", "Vivaldi"),
    ("steamwebhelper", "Steam Web Helper"),
    ("steam", "Steam"),
    ("discord", "Discord"),
    ("legcord", "Legcord"),
    ("telegram", "Telegram"),
    ("spotify", "Spotify"),
    ("codium", "VSCodium"),
    ("code", "VS Code"),
    ("dolphin", "Dolphin"),
    ("konsole", "Konsole"),
    ("wine", "Wine / Proton"),
    ("proton", "Wine / Proton"),
    ("lutris", "Lutris"),
    ("heroic", "Heroic"),
    ("java", "Java"),
)


@dataclass
class ProcessEntry:
    key: str
    name: str
    pid_text: str
    memory: int
    command: str
    processes: list
    grouped: bool = False

    @property
    def closable(self) -> list:
        return [process for process in self.processes if not bool(getattr(process, "protegido", False))]

    @property
    def protected_count(self) -> int:
        return len(self.processes) - len(self.closable)

    @property
    def fully_protected(self) -> bool:
        return not self.closable

    @property
    def protection_text(self) -> str:
        if self.fully_protected:
            reasons = sorted({str(getattr(process, "razon", "") or "system") for process in self.processes})
            return tr_format("Protected · {reasons}", reasons=", ".join(reasons[:2]))
        if self.protected_count:
            return tr_format("Partial · {count} protected", count=self.protected_count)
        return tr("Safe to close")

    @property
    def impact_text(self) -> str:
        memory_mb = self.memory / 1024 / 1024
        if memory_mb >= 1024:
            return "High"
        if memory_mb >= 400:
            return "Medium"
        return "Normal"


class ProcessTask(QThread):
    completed = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, controller, operation: str, *, hide_system: bool = True, payload=None, state_cache=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.operation = operation
        self.hide_system = bool(hide_system)
        self.payload = payload
        self.state_cache = state_cache

    @staticmethod
    def _performance_dict(value) -> dict:
        if hasattr(value, "to_dict"):
            return dict(value.to_dict())
        if isinstance(value, dict):
            return dict(value)
        return {}

    def _snapshot(self) -> dict:
        return {
            "processes": list(self.controller.procesos(self.hide_system)),
            "performance": self.state_cache.performance() if self.state_cache is not None else self._performance_dict(self.controller.rendimiento()),
            "refreshed_at": datetime.now().strftime("%H:%M:%S"),
        }

    def run(self) -> None:  # pragma: no cover - thread execution
        try:
            if self.operation == "refresh":
                self.completed.emit(self.operation, self._snapshot())
                return
            if self.operation == "terminate":
                self.controller.cerrar(list(self.payload or []))
                if self.state_cache is not None:
                    self.state_cache.invalidate("performance")
                self.completed.emit(self.operation, self._snapshot())
                return
            if self.operation == "cache":
                result = self.controller.limpiar_cache()
                if self.state_cache is not None:
                    self.state_cache.invalidate("performance")
                self.completed.emit(self.operation, result or {"returncode": 0})
                return
            raise ValueError(f"Unknown process task: {self.operation}")
        except Exception as error:
            self.failed.emit(self.operation, str(error))


class ApplicationCell(QWidget):
    def __init__(self, entry: ProcessEntry, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)
        icon_label = QLabel()
        icon_label.setFixedSize(28, 28)
        icon_label.setPixmap(icono_app(entry.name, entry.command).pixmap(22, 22))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(1)
        name = QLabel(entry.name)
        name.setProperty("appName", True)
        command = QLabel(entry.command)
        command.setProperty("appCommand", True)
        command.setToolTip(entry.command)
        copy.addWidget(name)
        copy.addWidget(command)
        layout.addLayout(copy, 1)


class MemoryCell(QWidget):
    def __init__(self, memory: int, maximum: int, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(6)
        value = QLabel(formato_bytes(memory))
        value.setProperty("memoryValue", True)
        bar = QProgressBar()
        bar.setProperty("processMemory", True)
        bar.setRange(0, 1000)
        ratio = 0 if maximum <= 0 else max(0, min(1000, round(memory / maximum * 1000)))
        bar.setValue(ratio)
        bar.setTextVisible(False)
        layout.addWidget(value)
        layout.addWidget(bar)


class ProcessesPage(QWidget):
    """Task manager backed by the original protected process service."""

    def apply_appearance(self) -> None:
        self.setStyleSheet(process_stylesheet())
        self.update()

    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.setProperty("processPage", True)
        self.setStyleSheet(process_stylesheet())
        self._worker: ProcessTask | None = None
        self._busy = False
        self._workspace_columns = 0
        self._action_layout_mode = ""
        self._processes: list = []
        self._entries: list[ProcessEntry] = []
        self._row_entries: list[ProcessEntry] = []
        self._selected_keys: set[str] = set()
        self._performance: dict = {}
        self._updates_active = False
        self._pending_result: dict | None = None
        self._last_snapshot_at = 0.0
        self._state_cache = state_cache_for(controller)
        self._background = BackgroundExecutor(self)
        self._event_sequence = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea()
        self.content = QWidget()
        configure_responsive_scroll_area(self.scroll, self.content)
        root = QVBoxLayout(self.content)
        root.setContentsMargins(18, 8, 18, 20)
        root.setSpacing(14)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll)

        self.header = ControlPageHeader(
            "TASK MANAGER",
            "Processes",
            "Find user applications, group related subprocesses, and end workloads through the original protected close sequence.",
            mode_text="● LIVE SESSION",
        )
        self.header.refresh_requested.connect(self.refresh)
        root.addWidget(self.header)
        # Hide the introductory task-manager banner and reclaim its full height.
        # The header remains instantiated so the existing refresh connection is
        # unchanged.
        self.header.hide()

        self.workspace = QGridLayout()
        self.workspace.setContentsMargins(0, 0, 0, 0)
        self.workspace.setHorizontalSpacing(14)
        self.workspace.setVerticalSpacing(14)
        self.inventory_card = self._build_inventory_card()
        self.inventory_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addLayout(self.workspace, 1)
        self._reflow(1400)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(5000)
        self.refresh_timer.timeout.connect(self._automatic_refresh)
        self.filter_timer = QTimer(self)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.setInterval(120)
        self.filter_timer.timeout.connect(self._apply_text_filter)

    def _build_inventory_card(self) -> SectionCard:
        card = SectionCard(
            "Application inventory",
            "Current-user workloads sorted by resident memory. Protected desktop and system tasks remain visible, clearly marked, and unavailable for termination.",
            icon_name="processes_blue",
            icon_background=COLORS["blue_soft"],
            status=("Loading", "gray"),
        )

        filter_bar = QFrame()
        filter_bar.setProperty("processFilterBar", True)
        filter_layout = QGridLayout(filter_bar)
        filter_layout.setContentsMargins(12, 9, 12, 9)
        filter_layout.setHorizontalSpacing(11)
        filter_layout.setVerticalSpacing(7)
        self.filter_layout = filter_layout
        self.filter_icon = IconBadge("processes_blue", COLORS["blue_soft"], 32, radius=9)
        filter_layout.addWidget(self.filter_icon, 0, 0)
        self.search = QLineEdit()
        self.search.setProperty("processSearch", True)
        self.search.setPlaceholderText("Search application, PID, or command")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_changed)
        filter_layout.addWidget(self.search, 0, 1)
        filter_layout.setColumnStretch(1, 1)
        self.hide_system = QCheckBox("Hide system")
        self.hide_system.setChecked(True)
        self.hide_system.toggled.connect(self._source_filter_changed)
        filter_layout.addWidget(self.hide_system, 0, 2)
        self.group_apps = QCheckBox("Group apps")
        self.group_apps.setChecked(True)
        self.group_apps.toggled.connect(self._grouping_changed)
        filter_layout.addWidget(self.group_apps, 0, 3)
        card.body.addWidget(filter_bar)

        self.table = QTableWidget(0, 6)
        header_labels = ("", "Application", "PID / instances", "Resident memory", "Impact", "Safety")
        self.table.setHorizontalHeaderLabels(header_labels)
        for column, label in enumerate(header_labels):
            item = self.table.horizontalHeaderItem(column)
            if item is not None:
                alignment = Qt.AlignmentFlag.AlignLeft if column == 1 else Qt.AlignmentFlag.AlignCenter
                item.setTextAlignment(alignment | Qt.AlignmentFlag.AlignVCenter)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setCornerButtonEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(58)
        self.table.horizontalHeader().setFixedHeight(42)
        self.table.horizontalHeader().setMinimumSectionSize(44)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 44)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in ((2, 170), (3, 160), (4, 92), (5, 92)):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        self.table.setMinimumHeight(410)
        self.table.setToolTip("Protected rows cannot be selected")
        self.table.cellClicked.connect(self._row_clicked)
        card.body.addWidget(self.table, 1)

        self.action_bar = QFrame()
        self.action_bar.setProperty("processActionBar", True)
        self.action_layout = QGridLayout(self.action_bar)
        self.action_layout.setContentsMargins(13, 10, 13, 10)
        self.action_layout.setHorizontalSpacing(8)
        self.action_layout.setVerticalSpacing(8)
        self.selection_copy = QWidget()
        selection_copy_layout = QVBoxLayout(self.selection_copy)
        selection_copy_layout.setContentsMargins(0, 0, 0, 0)
        selection_copy_layout.setSpacing(2)
        selection_kicker = QLabel("SELECTION")
        selection_kicker.setProperty("selectionKicker", True)
        self.selected_summary = QLabel("No applications selected")
        self.selected_summary.setProperty("selectedSummary", True)
        self.selected_summary.setMinimumWidth(0)
        self.selected_summary.setWordWrap(True)
        selection_copy_layout.addWidget(selection_kicker)
        selection_copy_layout.addWidget(self.selected_summary)
        self.select_safe_button = QPushButton("Select safe visible")
        self.select_safe_button.setProperty("processSecondaryAction", True)
        self.select_safe_button.setProperty("processActionButton", True)
        self.select_safe_button.setIcon(icon("check_green"))
        self.select_safe_button.clicked.connect(self.select_safe_visible)
        self.clear_button = QPushButton("Clear selection")
        self.clear_button.setProperty("processSecondaryAction", True)
        self.clear_button.setProperty("processActionButton", True)
        self.clear_button.setIcon(icon("close_gray"))
        self.clear_button.clicked.connect(self.clear_selection)
        self.cache_button = QPushButton("Release page cache")
        self.cache_button.setProperty("processSecondaryAction", True)
        self.cache_button.setProperty("processActionButton", True)
        self.cache_button.setIcon(icon("refresh_gray"))
        self.cache_button.clicked.connect(self.release_cache)
        self.terminate_button = QPushButton("End selected tasks")
        self.terminate_button.setProperty("dangerAction", True)
        self.terminate_button.setProperty("processActionButton", True)
        self.terminate_button.setIcon(icon("warning_orange"))
        self.terminate_button.clicked.connect(self.terminate_selected)
        self.action_buttons = (
            self.select_safe_button,
            self.clear_button,
            self.cache_button,
            self.terminate_button,
        )
        card.body.addWidget(self.action_bar)

        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)
        footer.setSpacing(10)
        self.visible_summary = QLabel("Waiting for process inventory")
        self.visible_summary.setProperty("processFooter", True)
        footer.addWidget(self.visible_summary)
        footer.addStretch(1)
        self.last_refresh = QLabel("Last refresh --:--:--")
        self.last_refresh.setProperty("processFooter", True)
        footer.addWidget(self.last_refresh)
        card.body.addLayout(footer)
        return card

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if self._updates_active:
            if not self.refresh_timer.isActive():
                self.refresh_timer.start()
            # Let QStackedWidget paint the selected page before a potentially
            # large process table is populated.
            QTimer.singleShot(16, self._resume_updates)
        else:
            self.refresh_timer.stop()

    def _resume_updates(self) -> None:
        if not self._updates_active:
            return
        if self._pending_result is not None:
            pending = self._pending_result
            self._pending_result = None
            self._apply_snapshot(pending)
            return
        if not self._processes or time.monotonic() - self._last_snapshot_at > 2.5:
            self.refresh()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow(effective_viewport_width(self, self.scroll))

    def _reflow(self, width: int) -> None:
        if self._workspace_columns != 1:
            self._workspace_columns = 1
            while self.workspace.count():
                item = self.workspace.takeAt(0)
                if item.widget() is not None:
                    item.widget().setParent(None)
            self.workspace.addWidget(self.inventory_card, 0, 0)
            self.workspace.setColumnStretch(0, 1)
            self.inventory_card.setMinimumHeight(520)
        self._reflow_filter_bar(width)
        self._resize_table_columns(width)
        self._reflow_action_bar(width)

    def _reflow_action_bar(self, width: int) -> None:
        mode = "wide" if width >= 1180 else "medium" if width >= 760 else "compact" if width >= 460 else "stack"
        if mode == self._action_layout_mode:
            return
        self._action_layout_mode = mode
        while self.action_layout.count():
            self.action_layout.takeAt(0)
        for column in range(5):
            self.action_layout.setColumnStretch(column, 0)
        if mode == "wide":
            self.action_layout.addWidget(self.selection_copy, 0, 0)
            for index, button in enumerate(self.action_buttons, start=1):
                self.action_layout.addWidget(button, 0, index)
            self.action_layout.setColumnStretch(0, 1)
        elif mode == "medium":
            self.action_layout.addWidget(self.selection_copy, 0, 0, 1, 4)
            for index, button in enumerate(self.action_buttons):
                self.action_layout.addWidget(button, 1, index)
                self.action_layout.setColumnStretch(index, 1)
        elif mode == "compact":
            self.action_layout.addWidget(self.selection_copy, 0, 0, 1, 2)
            for index, button in enumerate(self.action_buttons):
                self.action_layout.addWidget(button, 1 + index // 2, index % 2)
            self.action_layout.setColumnStretch(0, 1)
            self.action_layout.setColumnStretch(1, 1)
        else:
            self.action_layout.addWidget(self.selection_copy, 0, 0)
            for index, button in enumerate(self.action_buttons):
                self.action_layout.addWidget(button, index + 1, 0)
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.action_layout.setColumnStretch(0, 1)

    def _reflow_filter_bar(self, width: int) -> None:
        compact = width < 700
        if compact == getattr(self, "_filter_compact", False):
            return
        self._filter_compact = compact
        for widget in (self.filter_icon, self.search, self.hide_system, self.group_apps):
            self.filter_layout.removeWidget(widget)
        if compact:
            self.filter_layout.addWidget(self.filter_icon, 0, 0)
            self.filter_layout.addWidget(self.search, 0, 1, 1, 2)
            self.filter_layout.addWidget(self.hide_system, 1, 1)
            self.filter_layout.addWidget(self.group_apps, 1, 2)
            self.filter_layout.setColumnStretch(0, 0)
            self.filter_layout.setColumnStretch(1, 1)
            self.filter_layout.setColumnStretch(2, 1)
        else:
            self.filter_layout.addWidget(self.filter_icon, 0, 0)
            self.filter_layout.addWidget(self.search, 0, 1)
            self.filter_layout.addWidget(self.hide_system, 0, 2)
            self.filter_layout.addWidget(self.group_apps, 0, 3)
            self.filter_layout.setColumnStretch(0, 0)
            self.filter_layout.setColumnStretch(1, 1)
            self.filter_layout.setColumnStretch(2, 0)
            self.filter_layout.setColumnStretch(3, 0)

    def _resize_table_columns(self, width: int) -> None:
        compact = width < 760
        widths = ((2, 124), (3, 132), (4, 76), (5, 76)) if compact else ((2, 170), (3, 160), (4, 92), (5, 92))
        for column, section_width in widths:
            self.table.setColumnWidth(column, section_width)

    def _automatic_refresh(self) -> None:
        if not self._updates_active or self._busy or self.search.text().strip() or self._selected_entries():
            return
        self.refresh()

    def _source_filter_changed(self, _checked: bool) -> None:
        self.clear_selection()
        self.refresh()

    def _grouping_changed(self, _checked: bool) -> None:
        self.clear_selection()
        self._rebuild_entries()
        self._render_table()

    def _filter_changed(self, _text: str) -> None:
        self.filter_timer.start()

    def _apply_text_filter(self) -> None:
        self.clear_selection(render=False)
        self._render_table()

    def refresh(self) -> None:
        if self._busy or not self._updates_active:
            return
        self._start_task("refresh", hide_system=self.hide_system.isChecked())

    def _start_task(self, operation: str, *, hide_system: bool = True, payload=None) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._set_busy(True, operation)
        worker = ProcessTask(self.controller, operation, hide_system=hide_system, payload=payload, state_cache=self._state_cache, parent=self)
        worker.completed.connect(self._task_completed)
        worker.failed.connect(self._task_failed)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _task_completed(self, operation: str, result) -> None:
        self._worker = None
        if operation in {"refresh", "terminate"}:
            if operation == "terminate":
                self._selected_keys.clear()
            data = dict(result or {})
            if not self._updates_active:
                self._pending_result = data
            else:
                self._apply_snapshot(data)
        self._set_busy(False, operation)
        if operation == "terminate":
            self._record_event("process", "info", "Selected tasks ended", "SIGTERM followed by protected force-close fallback.")
        elif operation == "cache":
            self._record_event("memory", "success", "Page cache released", "The privileged sync/drop_caches workflow completed successfully.")
            InfoDialog(
                "Page cache released",
                "The privileged cache-release workflow completed successfully.",
                icon_name="shield_green",
                parent=self,
                eyebrow="ADVANCED MEMORY ACTION",
                button_text="Close",
                notice="Applications were not closed by this action.",
                tone="green",
            ).exec()
            if self._updates_active:
                self.refresh()

    def _apply_snapshot(self, data: dict) -> None:
        self._last_snapshot_at = time.monotonic()
        self._processes = list(data.get("processes") or [])
        self._performance = dict(data.get("performance") or {})
        self.last_refresh.setText(tr_format("Last refresh {time}", time=data.get("refreshed_at") or datetime.now().strftime("%H:%M:%S")))
        self._rebuild_entries()
        self._render_table()
        self._update_pressure_status()

    def _task_failed(self, operation: str, message: str) -> None:
        self._worker = None
        self._set_busy(False, operation)
        InfoDialog(
            "Process operation failed",
            message,
            icon_name="warning_orange",
            parent=self,
            eyebrow="TASK MANAGER",
            button_text="Close",
            notice="No additional action will be attempted automatically.",
            tone="red",
        ).exec()

    def _set_busy(self, busy: bool, operation: str = "") -> None:
        self._busy = bool(busy)
        if self.inventory_card.status is not None:
            self.inventory_card.status.setText(tr("Working") if busy else tr_format("{count} visible", count=len(self._row_entries)))
            self.inventory_card.status.set_tone("blue" if busy else "gray")
        for widget in (
            self.search,
            self.hide_system,
            self.group_apps,
            self.select_safe_button,
            self.clear_button,
            self.terminate_button,
            self.cache_button,
        ):
            widget.setEnabled(not busy)
        if busy:
            self.visible_summary.setText(tr("Refreshing process inventory…" if operation == "refresh" else "Applying selected action…"))
        self._update_action_availability()

    @staticmethod
    def _app_key(process) -> str:
        text = f"{getattr(process, 'nombre', '')} {getattr(process, 'comando', '')}".lower()
        for needle, name in APP_NAMES:
            if needle in text:
                return name
        raw = str(getattr(process, "nombre", "App") or "App").strip().split()[0]
        return raw[:1].upper() + raw[1:]

    def _rebuild_entries(self) -> None:
        if not self.group_apps.isChecked():
            self._entries = [
                ProcessEntry(
                    key=f"pid:{process.pid}",
                    name=str(process.nombre),
                    pid_text=str(process.pid),
                    memory=int(process.memoria),
                    command=str(process.comando),
                    processes=[process],
                )
                for process in self._processes
            ]
            self._entries.sort(key=lambda entry: entry.memory, reverse=True)
            return

        groups: dict[str, list] = {}
        for process in self._processes:
            groups.setdefault(self._app_key(process), []).append(process)
        entries: list[ProcessEntry] = []
        for name, processes in groups.items():
            processes.sort(key=lambda process: int(process.memoria), reverse=True)
            memory = sum(int(process.memoria) for process in processes)
            if len(processes) == 1:
                process = processes[0]
                entries.append(
                    ProcessEntry(
                        key=f"pid:{process.pid}",
                        name=str(process.nombre),
                        pid_text=str(process.pid),
                        memory=memory,
                        command=str(process.comando),
                        processes=processes,
                    )
                )
                continue
            pid_list = ", ".join(str(process.pid) for process in processes[:12])
            if len(processes) > 12:
                pid_list += f" +{len(processes) - 12}"
            entries.append(
                ProcessEntry(
                    key=f"group:{name.lower()}",
                    name=name,
                    pid_text=f"{len(processes)} instances",
                    memory=memory,
                    command=f"PIDs: {pid_list}",
                    processes=processes,
                    grouped=True,
                )
            )
        entries.sort(key=lambda entry: entry.memory, reverse=True)
        self._entries = entries

    def _filtered_entries(self) -> list[ProcessEntry]:
        query = self.search.text().strip().lower()
        if not query:
            return list(self._entries)
        output = []
        for entry in self._entries:
            text = f"{entry.name} {entry.pid_text} {entry.command}"
            text += " " + " ".join(
                f"{getattr(process, 'nombre', '')} {getattr(process, 'pid', '')} {getattr(process, 'comando', '')}"
                for process in entry.processes
            )
            if query in text.lower():
                output.append(entry)
        return output

    def _render_table(self) -> None:
        entries = self._filtered_entries()
        valid_keys = {entry.key for entry in self._entries}
        self._selected_keys.intersection_update(valid_keys)
        self._row_entries = entries
        max_memory = max((entry.memory for entry in entries), default=1)
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                checkbox = QCheckBox()
                checkbox.setProperty("entryKey", entry.key)
                checkbox.setEnabled(bool(entry.closable))
                checkbox.setChecked(entry.key in self._selected_keys and bool(entry.closable))
                checkbox.stateChanged.connect(lambda state, key=entry.key: self._checkbox_changed(key, state))
                checkbox_wrap = QWidget()
                checkbox_layout = QHBoxLayout(checkbox_wrap)
                checkbox_layout.setContentsMargins(0, 0, 0, 0)
                checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                checkbox_layout.addWidget(checkbox)
                self.table.setCellWidget(row, 0, checkbox_wrap)

                self.table.setCellWidget(row, 1, ApplicationCell(entry))
                pid_item = QTableWidgetItem(entry.pid_text)
                pid_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                pid_item.setToolTip("\n".join(str(getattr(process, "pid", "")) for process in entry.processes[:20]))
                self.table.setItem(row, 2, pid_item)
                self.table.setCellWidget(row, 3, MemoryCell(entry.memory, max_memory))

                impact_tone = "red" if entry.impact_text == "High" else "orange" if entry.impact_text == "Medium" else "gray"
                impact_wrap = QWidget()
                impact_layout = QHBoxLayout(impact_wrap)
                impact_layout.setContentsMargins(5, 0, 5, 0)
                impact_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                impact_layout.addWidget(PillLabel(tr(entry.impact_text), impact_tone))
                self.table.setCellWidget(row, 4, impact_wrap)

                safety_tone = "gray" if entry.fully_protected else "orange" if entry.protected_count else "green"
                safety_text = "Protected" if entry.fully_protected else "Partial" if entry.protected_count else "Safe"
                safety_wrap = QWidget()
                safety_layout = QHBoxLayout(safety_wrap)
                safety_layout.setContentsMargins(5, 0, 5, 0)
                safety_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                pill = PillLabel(tr(safety_text), safety_tone)
                pill.setToolTip(entry.protection_text)
                safety_layout.addWidget(pill)
                self.table.setCellWidget(row, 5, safety_wrap)

                if entry.fully_protected:
                    item = self.table.item(row, 2)
                    if item is not None:
                        item.setForeground(QColor(COLORS["subtle"]))
        finally:
            self.table.setUpdatesEnabled(True)
            self.table.blockSignals(False)

        protected = sum(1 for entry in entries if entry.fully_protected)
        real_count = sum(len(entry.processes) for entry in entries)
        self.visible_summary.setText(tr_format("{rows} · {processes} · {protected} protected", rows=count_label(len(entries), "row"), processes=count_label(real_count, "process"), protected=count_label(protected, "row")))
        if self.inventory_card.status is not None and not self._busy:
            self.inventory_card.status.setText(tr_format("{count} visible", count=len(entries)))
            self.inventory_card.status.set_tone("blue" if entries else "gray")
        self._update_selection_summary()

    def _row_clicked(self, row: int, column: int) -> None:
        if column == 0 or row < 0 or row >= len(self._row_entries) or self._busy:
            return
        entry = self._row_entries[row]
        if not entry.closable:
            return
        if entry.key in self._selected_keys:
            self._selected_keys.discard(entry.key)
        else:
            self._selected_keys.add(entry.key)
        self._sync_selection_checkboxes((row,))
        self._update_selection_summary()

    def _sync_selection_checkboxes(self, rows: Iterable[int] | None = None) -> None:
        target_rows = rows if rows is not None else range(len(self._row_entries))
        for row in target_rows:
            if row < 0 or row >= len(self._row_entries):
                continue
            wrap = self.table.cellWidget(row, 0)
            checkbox = wrap.findChild(QCheckBox) if wrap is not None else None
            if checkbox is None:
                continue
            checkbox.blockSignals(True)
            checkbox.setChecked(self._row_entries[row].key in self._selected_keys)
            checkbox.blockSignals(False)

    def _checkbox_changed(self, key: str, state: int) -> None:
        if state == int(Qt.CheckState.Checked.value):
            self._selected_keys.add(key)
        else:
            self._selected_keys.discard(key)
        self._update_selection_summary()

    def _selected_entries(self) -> list[ProcessEntry]:
        return [entry for entry in self._row_entries if entry.key in self._selected_keys and entry.closable]

    @staticmethod
    def _real_closable(entries: Iterable[ProcessEntry]) -> list:
        output = []
        seen: set[int] = set()
        for entry in entries:
            for process in entry.closable:
                try:
                    pid = int(process.pid)
                except Exception:
                    continue
                if pid in seen:
                    continue
                seen.add(pid)
                output.append(process)
        return output

    def select_safe_visible(self) -> None:
        if self._busy:
            return
        self._selected_keys = {entry.key for entry in self._row_entries if entry.closable}
        self._sync_selection_checkboxes()
        self._update_selection_summary()

    def clear_selection(self, *, render: bool = True) -> None:
        self._selected_keys.clear()
        if render:
            self._sync_selection_checkboxes()
            self._update_selection_summary()
        else:
            self._update_selection_summary()

    def _update_selection_summary(self) -> None:
        entries = self._selected_entries()
        real = self._real_closable(entries)
        memory = sum(int(getattr(process, "memoria", 0) or 0) for process in real)
        if entries:
            self.selected_summary.setText(
                tr_format("{applications} · {processes} · approx. {memory}", applications=count_label(len(entries), "application"), processes=count_label(len(real), "process"), memory=formato_bytes(memory))
            )
        else:
            self.selected_summary.setText(tr("No applications selected"))
        if self.inventory_card.status is not None and not self._busy:
            self.inventory_card.status.setText(
                tr_format("{visible} visible · {selected} selected", visible=len(self._row_entries), selected=len(real)) if self._row_entries else tr("Empty")
            )
            self.inventory_card.status.set_tone("orange" if real else "blue" if self._row_entries else "gray")
        self._update_action_availability()

    def _update_action_availability(self) -> None:
        selected = bool(self._selected_entries())
        ready = not self._busy
        self.terminate_button.setEnabled(ready and selected)
        self.cache_button.setEnabled(ready)
        self.select_safe_button.setEnabled(not self._busy and any(entry.closable for entry in self._row_entries))
        self.clear_button.setEnabled(not self._busy and bool(self._selected_keys))

    def terminate_selected(self) -> None:
        entries = self._selected_entries()
        real = self._real_closable(entries)
        if not entries or not real:
            InfoDialog(
                "Nothing safe is selected",
                "Select one or more unprotected application rows before ending tasks.",
                parent=self,
                eyebrow="TASK MANAGER",
                button_text="Close",
                notice="Protected rows are never sent to the close backend.",
                tone="blue",
            ).exec()
            return
        memory = sum(int(getattr(process, "memoria", 0) or 0) for process in real)
        names = ", ".join(entry.name for entry in entries[:4])
        if len(entries) > 4:
            names += f" and {len(entries) - 4} more"
        dialog = ConfirmDialog(
            "End selected tasks",
            "The original protected workflow will request a graceful SIGTERM first, wait 1.5 seconds, and force-close only remaining unprotected processes.",
            summary=(
                ("Applications", names),
                ("Real processes", str(len(real))),
                ("Approx. memory", formato_bytes(memory)),
                ("Protected processes", "Excluded"),
            ),
            confirm_text="End selected tasks",
            tone="red",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._start_task("terminate", hide_system=self.hide_system.isChecked(), payload=real)

    def release_cache(self) -> None:
        dialog = ConfirmDialog(
            "Release Linux page cache",
            "This starts the existing pkexec workflow: sync, then write 3 to /proc/sys/vm/drop_caches. It can make applications reload data from disk and is not a substitute for closing heavy workloads.",
            summary=(
                ("Authentication", "pkexec prompt"),
                ("Applications", "Not closed"),
                ("Dirty data", "sync requested first"),
                ("Scope", "Page cache, dentries, inodes"),
            ),
            confirm_text="Request cache release",
            tone="orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._start_task("cache")

    def _update_pressure_status(self) -> None:
        data = self._performance
        memory_percent = float(data.get("memoria_porcentaje") or 0)
        memory_available = int(data.get("memoria_disponible") or 0)
        swap_percent = float(data.get("swap_porcentaje") or 0)
        detail = tr_format("RAM {ram}% · swap {swap}% · {available} available", ram=f"{memory_percent:.0f}", swap=f"{swap_percent:.0f}", available=formato_bytes(memory_available))
        self.cache_button.setToolTip(detail)

    def _record_event(self, event_type: str, level: str, title: str, detail: str) -> None:
        self._event_sequence += 1

        def operation() -> object:
            self.controller.registrar_evento(event_type, level, title, detail, {})
            return True

        self._background.start(
            f"process-event:{self._event_sequence}",
            operation,
        )
