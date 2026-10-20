"""Processes: the user's applications and games, what they use, and control.

One row per application, every helper, renderer and GPU process included
(see bc250cc.infrastructure.process_inventory): CPU, GPU, memory (PSS) and
VRAM, sortable. The game in play gets its own card. Rows can be paused,
resumed and ended through the protected sequence; desktop-session programs
stay visible under System and are never closable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Iterable

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..components.async_tools import BackgroundExecutor
from ..components.buttons import WrappingButton as QPushButton
from ..components.dashboard_instruments import HeadingLabel
from ..components.page_widgets import ConfirmDialog, ControlPageHeader, SectionCard
from ..components.responsive import (
    configure_responsive_scroll_area,
    effective_viewport_width,
)
from ..components.toast import show_toast
from ..components.toggle_switch import ToggleSwitch
from ..components.widgets import InfoDialog, icon
from ..core.state import state_cache_for
from ..i18n import count_label, current_language, tr, tr_format
from ..theme import COLORS, scale_stylesheet

#: Seconds between automatic refreshes while the page is shown. CPU and GPU
#: percentages are measured across this interval.
REFRESH_INTERVAL_MS = 3000
#: Rows below this, with no CPU, GPU or VRAM use, are not listed unless
#: searched for: tray applets and idle helpers of a few megabytes.
SMALL_ENTRY_BYTES = 8 * 1024 * 1024

FILTERS = (
    ("apps", "Apps and games"),
    ("background", "Background"),
    ("system", "System"),
    ("all", "All"),
)
COLUMNS = ("", "Application", "CPU", "GPU", "Memory", "GPU memory", "Status")
SORT_KEYS = {1: "name", 2: "cpu", 3: "gpu", 4: "memory", 5: "vram"}


def formato_bytes(value: int | float) -> str:
    """Format byte counters locally without importing the retired GUI tree."""
    size = max(0.0, float(value or 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            precision = 0 if unit == "B" else 1
            return f"{size:.{precision}f} {unit}"
        size /= 1024.0
    return "0 B"


def _percent_text(value: float | None) -> str:
    if value is None:
        return "—"
    if value < 0.05:
        return "0 %"
    return f"{value:.1f} %" if value < 10 else f"{value:.0f} %"


@lru_cache(maxsize=512)
def icono_app(name: str, program: str, kind: str = "app") -> QIcon:
    """The application's theme icon, resolved once per signature."""
    for candidate in dict.fromkeys((name, program, program.lower(), name.rsplit(".", 1)[-1].lower())):
        if candidate:
            themed = QIcon.fromTheme(candidate)
            if not themed.isNull():
                return themed
    if kind == "game":
        themed = QIcon.fromTheme("applications-games")
        if not themed.isNull():
            return themed
    return icon("processes_gray")


def process_stylesheet() -> str:
    """The Processes page in the CPU, GPU and Fans modules' own language:
    one card, hairlines between rows, underlined tabs, no boxes in boxes."""
    c = COLORS
    return scale_stylesheet(f"""
QWidget[processPage='true'] QFrame[processTabRail='true'] {{
    background: transparent; border: none; border-bottom: 1px solid {c['border_soft']};
}}
QWidget[processPage='true'] QPushButton[processTab='true'] {{
    background: transparent; border: none; border-bottom: 2px solid transparent;
    border-radius: 0px; min-height: 0px; padding: 8px 2px 7px 2px;
    color: {c['muted']}; font-size: 12px; font-weight: 700;
}}
QWidget[processPage='true'] QPushButton[processTab='true']:hover {{ color: {c['text']}; }}
QWidget[processPage='true'] QPushButton[processTab='true']:checked {{
    color: {c['text']}; border-bottom: 2px solid {c['blue']}; font-weight: 780;
}}
QWidget[processPage='true'] QLineEdit[processSearch='true'] {{
    min-height: 32px; background: transparent; border: 1px solid {c['border']};
    border-radius: 8px; padding: 0 11px; color: {c['text']}; font-size: 11px; font-weight: 560;
    selection-background-color: {c['blue']}; selection-color: {c['on_accent']};
}}
QWidget[processPage='true'] QLineEdit[processSearch='true']:focus {{ border-color: {c['blue']}; }}
QWidget[processPage='true'] QTableWidget {{
    background: transparent; border: none; outline: none;
    gridline-color: transparent; color: {c['text']}; font-size: 11px;
}}
QWidget[processPage='true'] QTableWidget::item {{ border-bottom: 1px solid {c['border_soft']}; padding: 0 6px; }}
QWidget[processPage='true'] QTableWidget::item:selected {{ background: {c['blue_soft']}; color: {c['text']}; }}
QWidget[processPage='true'] QHeaderView,
QWidget[processPage='true'] QTableWidget QTableCornerButton::section {{ background: transparent; border: none; }}
QWidget[processPage='true'] QHeaderView::section {{
    background: transparent; color: {c['muted']}; border: none;
    border-bottom: 1px solid {c['border_soft']}; padding: 6px 6px; font-size: 9px; font-weight: 800;
}}
QWidget[processPage='true'] QHeaderView::section:hover {{ color: {c['text']}; }}
QWidget[processPage='true'] QLabel[appName='true'] {{ color: {c['text']}; font-size: 12px; font-weight: 720; }}
QWidget[processPage='true'] QLabel[appCommand='true'],
QWidget[processPage='true'] QLabel[processFooter='true'] {{ color: {c['muted']}; font-size: 10px; font-weight: 500; }}
QWidget[processPage='true'] QLabel[memoryValue='true'] {{ color: {c['text']}; font-size: 11px; font-weight: 700; }}
QWidget[processPage='true'] QLabel[processStatus='true'] {{ font-size: 11px; font-weight: 650; color: {c['muted']}; }}
QWidget[processPage='true'] QLabel[processStatus='true'][tone='green'] {{ color: {c['green']}; font-weight: 560; }}
QWidget[processPage='true'] QLabel[processStatus='true'][tone='orange'] {{ color: {c['orange']}; }}
QWidget[processPage='true'] QLabel[processStatus='true'][tone='gray'] {{ color: {c['subtle']}; }}
QWidget[processPage='true'] QLabel[gameName='true'] {{ color: {c['text']}; font-size: 14px; font-weight: 780; }}
QWidget[processPage='true'] QLabel[selectedSummary='true'] {{ color: {c['text']}; font-size: 11px; font-weight: 650; }}
QWidget[processPage='true'] QPushButton[processButton='secondary'],
QWidget[processPage='true'] QPushButton[processButton='danger'] {{
    background: transparent; color: {c['text']}; border: 1px solid {c['border']};
    border-radius: 8px; min-height: 0px; padding: 7px 16px; font-size: 11px; font-weight: 650;
}}
QWidget[processPage='true'] QPushButton[processButton='secondary']:hover {{
    background: {c['control_hover']}; border-color: {c['border_strong']};
}}
QWidget[processPage='true'] QPushButton[processButton='danger'] {{ color: {c['red']}; border-color: {c['red_border']}; }}
QWidget[processPage='true'] QPushButton[processButton='danger']:hover {{ background: {c['red_soft']}; }}
QWidget[processPage='true'] QPushButton[processButton='secondary']:disabled,
QWidget[processPage='true'] QPushButton[processButton='danger']:disabled {{
    color: {c['disabled_text']}; border-color: {c['border_soft']}; background: transparent;
}}
QWidget[processPage='true'] QFrame[processRule='true'] {{ background: {c['border_soft']}; border: none; }}
QWidget[processPage='true'] QProgressBar[processMeter='true'] {{
    min-height: 4px; max-height: 4px; background: {c['progress_track']}; border: none; border-radius: 2px;
}}
QWidget[processPage='true'] QProgressBar[processMeter='true']::chunk {{ background: {c['blue']}; border-radius: 2px; }}
""")


# ---------------------------------------------------------------------- model


@dataclass
class ProcessEntry:
    """One table row: an application (grouped) or a single process."""

    key: str
    name: str
    kind: str
    icon_name: str
    program: str
    processes: list
    grouped: bool = False
    steam_appid: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def memory_exact(self) -> bool:
        """Whether every process gave its PSS. One that did not (another
        user namespace, a game) makes the whole group count RSS, so PSS and
        RSS are never added together."""
        return all(getattr(process, "pss", 0) is not None for process in self.processes)

    @property
    def memory(self) -> int:
        if self.memory_exact:
            return sum(int(getattr(process, "memoria", 0) or 0) for process in self.processes)
        return sum(int(getattr(process, "rss", 0) or getattr(process, "memoria", 0) or 0)
                   for process in self.processes)

    @property
    def cpu(self) -> float | None:
        values = [getattr(process, "cpu_percent", None) for process in self.processes]
        values = [value for value in values if value is not None]
        return sum(values) if values else None

    @property
    def gpu(self) -> float | None:
        values = [getattr(process, "gpu_percent", None) for process in self.processes]
        values = [value for value in values if value is not None]
        return min(100.0, sum(values)) if values else None

    @property
    def vram(self) -> int:
        """GPU memory: VRAM plus GTT. The BC-250 keeps a small VRAM
        carve-out, so most of a game's GPU memory is GTT."""
        return self.vram_only + self.gtt

    @property
    def vram_only(self) -> int:
        return sum(int(getattr(process, "vram", 0) or 0) for process in self.processes)

    @property
    def gtt(self) -> int:
        return sum(int(getattr(process, "gtt", 0) or 0) for process in self.processes)

    def memory_tooltip(self) -> str:
        if self.memory_exact:
            return ""
        return tr("Approximate: some of these processes do not let their shared memory be measured.")

    def gpu_memory_tooltip(self) -> str:
        if not self.vram:
            return ""
        return tr_format("VRAM {v} · GTT {g}", v=formato_bytes(self.vram_only), g=formato_bytes(self.gtt))

    @property
    def threads(self) -> int:
        return sum(int(getattr(process, "threads", 0) or 0) for process in self.processes)

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
    def paused(self) -> bool:
        closable = self.closable
        return bool(closable) and all(bool(getattr(process, "paused", False)) for process in closable)

    @property
    def started(self) -> float | None:
        times = [getattr(process, "create_time", None) for process in self.processes]
        times = [value for value in times if value]
        return min(times) if times else None

    @property
    def subtitle(self) -> str:
        if self.grouped or not self.processes:
            return count_label(len(self.processes), "process")
        return f"PID {self.processes[0].pid}"

    def status(self) -> tuple[str, str, str]:
        """(text, tone, tooltip) for the Status column."""
        if self.fully_protected:
            reasons = sorted({str(getattr(process, "razon", "") or "system") for process in self.processes})
            return "Protected", "gray", tr_format("Protected · {reasons}", reasons=", ".join(tr(r) for r in reasons[:2]))
        if self.paused:
            return "Paused", "orange", tr("Paused: it uses no CPU until it is resumed.")
        if self.protected_count:
            return "Partial", "orange", tr_format("Partial · {count} protected", count=self.protected_count)
        return "Running", "green", tr("Safe to close")

    def sort_value(self, key: str):
        if key == "name":
            return self.name.lower()
        if key == "cpu":
            return self.cpu or 0.0
        if key == "gpu":
            return self.gpu or 0.0
        if key == "vram":
            return self.vram
        return self.memory


def localized_name(default: str, names, language: str) -> str:
    """A .desktop file's Name[<locale>] for the page's language (es-419
    tries es_419, then es), or its untranslated Name."""
    if not names or not language:
        return default
    code = language.replace("-", "_")
    return names.get(code) or names.get(code.split("_", 1)[0]) or default


def build_entries(processes: Iterable, *, grouped: bool, view: str, query: str = "") -> list[ProcessEntry]:
    """Rows for the table, for one filter and an optional search."""
    rows: dict[str, ProcessEntry] = {}
    language = current_language()
    for process in processes:
        kind = str(getattr(process, "kind", "app") or "app")
        app_key = str(getattr(process, "app_key", "") or f"pid:{process.pid}")
        key = app_key if grouped else f"pid:{process.pid}"
        entry = rows.get(key)
        if entry is None:
            entry = rows[key] = ProcessEntry(
                key=key,
                name=localized_name(
                    str(getattr(process, "app_name", "") or getattr(process, "nombre", "") or "?"),
                    getattr(process, "app_names", None), language,
                ),
                kind=kind,
                icon_name=str(getattr(process, "icon", "") or ""),
                program=str(getattr(process, "program", "") or getattr(process, "nombre", "")),
                processes=[],
                steam_appid=str(getattr(process, "steam_appid", "") or ""),
            )
        entry.processes.append(process)
        # A group is an application when any of its processes is one.
        rank = {"game": 0, "app": 1, "background": 2, "system": 3}
        if rank.get(kind, 1) < rank.get(entry.kind, 1):
            entry.kind = kind
    output = []
    needle = query.strip().lower()
    for entry in rows.values():
        entry.grouped = grouped and len(entry.processes) > 1
        entry.processes.sort(key=lambda process: int(getattr(process, "memoria", 0) or 0), reverse=True)
        if needle:
            haystack = " ".join(
                f"{entry.name} {getattr(p, 'pid', '')} {getattr(p, 'nombre', '')} {getattr(p, 'comando', '')}"
                for p in entry.processes
            ).lower()
            if needle not in haystack:
                continue
        elif view == "apps" and entry.kind not in {"app", "game"}:
            continue
        elif view in {"background", "system"} and entry.kind != view:
            continue
        if not needle and view != "all" and entry.memory < SMALL_ENTRY_BYTES \
                and not entry.cpu and not entry.vram and entry.kind != "game":
            continue
        output.append(entry)
    return output


# ---------------------------------------------------------------------- tasks


class ProcessTask(QThread):
    completed = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, controller, operation: str, *, payload=None, state_cache=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.operation = operation
        self.payload = payload
        self.state_cache = state_cache

    def _performance(self) -> dict:
        try:
            value = self.state_cache.performance() if self.state_cache is not None else {}
        except Exception:  # the header falls back to the inventory's own totals
            value = {}
        if hasattr(value, "to_dict"):
            return dict(value.to_dict())
        return dict(value) if isinstance(value, dict) else {}

    def _snapshot(self) -> dict:
        reader = getattr(self.controller, "inventario_procesos", None)
        if callable(reader):
            snapshot = dict(reader())
        else:  # an older controller: the plain process list
            snapshot = {"processes": list(self.controller.procesos(False))}
        snapshot["performance"] = self._performance()
        snapshot["refreshed_at"] = datetime.now().strftime("%H:%M:%S")
        return snapshot

    def run(self) -> None:  # pragma: no cover - thread execution
        try:
            if self.operation == "refresh":
                self.completed.emit(self.operation, self._snapshot())
                return
            if self.operation == "terminate":
                self.controller.cerrar_procesos(list(self.payload or []))
            elif self.operation in {"pause", "resume"}:
                self.controller.pausar_procesos(list(self.payload or []), self.operation == "pause")
            elif self.operation == "cache":
                result = self.controller.limpiar_cache()
                if self.state_cache is not None:
                    self.state_cache.invalidate("performance")
                self.completed.emit(self.operation, result or {"returncode": 0})
                return
            else:
                raise ValueError(f"Unknown process task: {self.operation}")
            if self.state_cache is not None:
                self.state_cache.invalidate("performance")
            self.completed.emit(self.operation, self._snapshot())
        except Exception as error:
            self.failed.emit(self.operation, str(error))


# ---------------------------------------------------------------------- cells


class ApplicationCell(QWidget):
    """Icon, application name and what it is (process count or command)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)
        self.icon = QLabel()
        self.icon.setFixedSize(26, 26)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon)
        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(1)
        self.name = QLabel()
        self.name.setProperty("appName", True)
        self.command = QLabel()
        self.command.setProperty("appCommand", True)
        for label in (self.name, self.command):
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        copy.addWidget(self.name)
        copy.addWidget(self.command)
        layout.addLayout(copy, 1)
        self._icon_key: tuple | None = None

    def set_entry(self, entry: ProcessEntry, *, with_status: bool = False) -> None:
        key = (entry.icon_name, entry.program, entry.kind)
        if key != self._icon_key:
            self._icon_key = key
            self.icon.setPixmap(icono_app(*key).pixmap(24, 24))
        self.name.setText(entry.name)
        subtitle = entry.subtitle
        status = entry.status()[0]
        if with_status and status != "Running":
            subtitle = f"{tr(status)} · {subtitle}"
        self.command.setText(subtitle)
        self.setToolTip(subtitle)


class MeterCell(QWidget):
    """A value over a thin bar, for memory and VRAM."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(0)
        self.value = QLabel()
        self.value.setProperty("memoryValue", True)
        self.bar = QProgressBar()
        self.bar.setProperty("processMeter", True)
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        layout.addWidget(self.value)
        layout.addWidget(self.bar)
        self.bar.hide()

    def set_values(self, value: int, maximum: int, *, empty: str = "", tooltip: str = "") -> None:
        self.setToolTip(tooltip)
        if not value and empty:
            self.value.setText(empty)
            self.bar.setValue(0)
            return
        self.value.setText(formato_bytes(value))
        self.bar.setValue(int(max(0, min(1000, value * 1000 / max(1, maximum)))))


class StatusCell(QWidget):
    """A coloured dot and a word, the way the Fans page states a mode."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        self.label = QLabel()
        self.label.setProperty("processStatus", True)
        layout.addWidget(self.label)
        layout.addStretch(1)

    def set_values(self, text: str, tone: str, tooltip: str = "") -> None:
        self.label.setText(tr(text))
        if self.label.property("tone") != tone:
            self.label.setProperty("tone", tone)
            self.label.style().unpolish(self.label)
            self.label.style().polish(self.label)
        self.setToolTip(tooltip)


class ProcessTable(QTableWidget):
    row_activated = pyqtSignal(int)
    delete_requested = pyqtSignal()

    def gamepad_activate(self) -> None:
        row = self.currentRow()
        if row >= 0:
            self.row_activated.emit(row)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.key() in {Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self.gamepad_activate()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------- page


class ProcessesPage(QWidget):
    """Task manager for the user's applications and games."""

    def apply_appearance(self) -> None:
        self.setStyleSheet(process_stylesheet())
        self.update()

    def __init__(self, controller, *, activity_service, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.activity_service = activity_service
        self.setProperty("processPage", True)
        self.setStyleSheet(process_stylesheet())
        self._worker: ProcessTask | None = None
        self._busy = False
        self._action_layout_mode = ""
        self._compact_columns: str | None = None
        self._processes: list = []
        self._entries: list[ProcessEntry] = []
        self._row_entries: list[ProcessEntry] = []
        self._selected_keys: set[str] = set()
        self._snapshot: dict = {}
        self._view = "apps"
        self._sort_key = "memory"
        self._sort_descending = True
        self._updates_active = False
        self._pending_result: dict | None = None
        self._last_snapshot_at = 0.0
        self._state_cache = state_cache_for(controller)
        self._background = BackgroundExecutor(self)
        self._event_sequence = 0
        self._game: ProcessEntry | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea()
        self.content = QWidget()
        configure_responsive_scroll_area(self.scroll, self.content)
        # The process table owns its own horizontal viewport: its column
        # widths must never widen the page.
        self.content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        root = QVBoxLayout(self.content)
        root.setContentsMargins(18, 8, 18, 20)
        root.setSpacing(14)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll)

        # Kept for the refresh connection other pages rely on; not shown.
        self.header = ControlPageHeader("TASK MANAGER", "Processes", "", mode_text="● LIVE SESSION")
        self.header.refresh_requested.connect(self.refresh)
        root.addWidget(self.header)
        self.header.hide()

        self.content.setProperty("redesignedModule", True)

        self.cache_button = QPushButton(tr("Release page cache"))
        self.cache_button.setToolTip(tr(
            "Writes pending data to disk and drops the kernel's file cache. No application is closed; the administrator password is asked."
        ))
        self.cache_button.clicked.connect(self.release_cache)

        self.inventory_card = self._build_inventory_card()
        self.inventory_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.inventory_card, 1)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(REFRESH_INTERVAL_MS)
        self.refresh_timer.timeout.connect(self._automatic_refresh)
        self.filter_timer = QTimer(self)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.setInterval(120)
        self.filter_timer.timeout.connect(self._apply_text_filter)

        QShortcut(QKeySequence.StandardKey.Find, self, activated=self._focus_search)
        QShortcut(QKeySequence(Qt.Key.Key_F5), self, activated=self.refresh)
        self._reflow(1400)
        self._render_game()
        self._render_table()

    # -- construction -------------------------------------------------------

    @staticmethod
    def _heading(source: str) -> HeadingLabel:
        """An upper-case group title, as the Fans and GPU modules head a list."""
        heading = HeadingLabel()
        heading.source_text = source
        heading.setText(tr(source))
        heading.setProperty("groupTitle", True)
        heading.setMinimumWidth(0)
        return heading

    @staticmethod
    def _rule() -> QFrame:
        line = QFrame()
        line.setProperty("processRule", True)
        line.setFixedHeight(1)
        return line

    def _button(self, text: str, slot, *, tone: str = "ghost", tip: str = "") -> QPushButton:
        button = QPushButton(tr(text))
        if tone == "danger":
            button.setProperty("processButton", "danger")
        else:
            button.setProperty("processButton", "secondary")
        if tip:
            button.setToolTip(tr(tip))
        button.clicked.connect(slot)
        return button

    def _build_game_section(self) -> QWidget:
        """The game in play, as the first group of the card."""
        section = QWidget()
        box = QVBoxLayout(section)
        box.setContentsMargins(0, 0, 0, 4)
        box.setSpacing(6)
        box.addWidget(self._heading("Playing now"))
        row = QGridLayout()
        row.setContentsMargins(0, 2, 0, 0)
        row.setHorizontalSpacing(12)
        row.setVerticalSpacing(6)
        self.game_icon = QLabel()
        self.game_icon.setFixedSize(36, 36)
        self.game_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.game_icon, 0, 0, 2, 1, Qt.AlignmentFlag.AlignTop)
        self.game_name = QLabel("")
        self.game_name.setProperty("gameName", True)
        self.game_name.setWordWrap(True)
        self.game_metrics = QLabel("")
        self.game_metrics.setProperty("readingLabel", True)
        self.game_metrics.setWordWrap(True)
        self.game_note = QLabel(tr(
            "systemd-oomd is running: if the paused game's memory goes to swap, it may close the game and Steam with it."
        ))
        self.game_note.setProperty("readingLabel", True)
        self.game_note.setProperty("tone", "orange")
        self.game_note.setWordWrap(True)
        self.game_note.hide()
        row.addWidget(self.game_name, 0, 1)
        row.addWidget(self.game_metrics, 1, 1)
        row.addWidget(self.game_note, 2, 1, 1, 2)
        row.setColumnStretch(1, 1)
        self.game_pause_button = self._button(
            "Pause game", self._toggle_game_pause,
            tip="Stops the game's processes where they are, so it uses no CPU or GPU; Resume carries on. Online games may disconnect.",
        )
        self.game_close_button = self._button("Close game", self._close_game, tone="danger")
        self.game_buttons = QHBoxLayout()
        self.game_buttons.setSpacing(8)
        self.game_buttons.addWidget(self.game_pause_button)
        self.game_buttons.addWidget(self.game_close_button)
        self._game_layout = row
        row.addLayout(self.game_buttons, 0, 2, 2, 1, Qt.AlignmentFlag.AlignVCenter)
        box.addLayout(row)
        box.addWidget(self._rule())
        section.hide()
        return section

    def _build_inventory_card(self) -> SectionCard:
        card = SectionCard(
            "Application inventory",
            "Every application with all its processes: CPU, GPU, memory and VRAM. Desktop session programs stay listed under System and cannot be ended.",
            icon_name="processes_blue",
            icon_background=COLORS["blue_soft"],
            status=("Loading", "gray"),
        )
        # The navigation already says "Processes": a title, a paragraph and a
        # counter above the list only repeat it.
        card.drop_header()
        self.game_card = self._build_game_section()
        card.body.addWidget(self.game_card)

        # Filters as the Fans page's mode tabs: words underlined, no boxes.
        self.tab_rail = QFrame()
        self.tab_rail.setProperty("processTabRail", True)
        self.filter_layout = QGridLayout(self.tab_rail)
        self.filter_layout.setContentsMargins(0, 0, 0, 0)
        self.filter_layout.setHorizontalSpacing(18)
        self.filter_layout.setVerticalSpacing(8)
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self.filter_buttons: dict[str, QPushButton] = {}
        for key, label in FILTERS:
            button = QPushButton(tr(label))
            button.setCheckable(True)
            button.setProperty("processTab", True)
            button.setChecked(key == self._view)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, view=key: self._set_view(view))
            self.filter_group.addButton(button)
            self.filter_buttons[key] = button
        self.search = QLineEdit()
        self.search.setProperty("processSearch", True)
        self.search.setPlaceholderText(tr("Search application, PID, or command"))
        self.search.setAccessibleName(tr("Search processes"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_changed)
        self.group_apps = ToggleSwitch()
        self.group_apps.setChecked(True)
        self.group_apps.setAccessibleName(tr("Group by application"))
        self.group_apps.toggled.connect(self._grouping_changed)
        self.group_label = QLabel(tr("Group by application"))
        self.group_label.setProperty("readingLabel", True)
        self._filter_compact: bool | None = None
        card.body.addWidget(self.tab_rail)

        self.options_row = QGridLayout()
        self.options_row.setContentsMargins(0, 2, 0, 0)
        self.options_row.setHorizontalSpacing(10)
        self.options_row.setVerticalSpacing(8)
        card.body.addLayout(self.options_row)

        self.table = ProcessTable(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(label) for label in COLUMNS])
        self.table.setAccessibleName(tr("Applications"))
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setCornerButtonEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        header = self.table.horizontalHeader()
        header.setFixedHeight(32)
        header.setMinimumSectionSize(40)
        header.setStretchLastSection(False)
        header.setSectionsClickable(True)
        header.setHighlightSections(False)
        header.sectionClicked.connect(self._header_clicked)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 40)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in range(2, len(COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        self.table.setMinimumHeight(360)
        self.table.cellClicked.connect(self._row_clicked)
        self.table.row_activated.connect(self._activate_table_row)
        self.table.delete_requested.connect(self.terminate_selected)
        card.body.addWidget(self.table, 1)


        # The action bar as on the Fans page: a hairline, then the buttons.
        card.body.addWidget(self._rule())
        self.action_bar = QWidget()
        self.action_layout = QGridLayout(self.action_bar)
        self.action_layout.setContentsMargins(0, 2, 0, 0)
        self.action_layout.setHorizontalSpacing(8)
        self.action_layout.setVerticalSpacing(8)
        self.selection_copy = QWidget()
        selection_copy_layout = QVBoxLayout(self.selection_copy)
        selection_copy_layout.setContentsMargins(0, 0, 0, 0)
        selection_copy_layout.setSpacing(0)
        self.selected_summary = QLabel(tr("No applications selected"))
        self.selected_summary.setProperty("selectedSummary", True)
        self.selected_summary.setMinimumWidth(0)
        self.selected_summary.setWordWrap(True)
        selection_copy_layout.addWidget(self.selected_summary)
        self.select_safe_button = self._button("Select visible", self.select_safe_visible,
                                               tip="Selects every visible row that can be ended.")
        self.clear_button = self._button("Clear selection", self.clear_selection)
        self.cache_button.setProperty("processButton", "secondary")
        self.pause_button = self._button(
            "Pause", self.pause_selected,
            tip="Pauses the selected applications (SIGSTOP). They keep their memory and carry on when resumed.",
        )
        self.terminate_button = self._button(
            "End tasks", self.terminate_selected, tone="danger",
            tip="Asks the selected applications to close, then ends what is left after 1.5 s. Shortcut: Delete.",
        )
        # Ticking rows is the selection; "select all" and "clear" were two
        # more buttons for what the list already does.
        for button in (self.select_safe_button, self.clear_button):
            button.setParent(self.action_bar)
            button.hide()
        self.action_buttons = (self.cache_button, self.pause_button, self.terminate_button)
        card.body.addWidget(self.action_bar)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(10)
        self.visible_summary = QLabel(tr("Waiting for process inventory"))
        self.visible_summary.setWordWrap(True)
        self.visible_summary.setProperty("processFooter", True)
        footer.addWidget(self.visible_summary, 1)
        # The list refreshes itself every few seconds: a clock beside it is noise.
        self.last_refresh = QLabel(tr_format("Last refresh {time}", time="--:--:--"))
        self.last_refresh.setParent(self.action_bar)
        self.last_refresh.hide()
        card.body.addLayout(footer)
        return card

    # -- layout -------------------------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow(effective_viewport_width(self, self.scroll))

    def _reflow(self, width: int) -> None:
        self._reflow_filter_bar(width)
        self._reflow_columns(width)
        self._reflow_action_bar(width)
        self._game_layout.removeItem(self.game_buttons)
        if width < 640:
            self._game_layout.addLayout(self.game_buttons, 2, 0, 1, 2)
        else:
            self._game_layout.addLayout(self.game_buttons, 0, 2, 2, 1, Qt.AlignmentFlag.AlignVCenter)

    def _reflow_filter_bar(self, width: int) -> None:
        compact = width < 720
        if compact == self._filter_compact:
            return
        self._filter_compact = compact
        for button in self.filter_buttons.values():
            self.filter_layout.removeWidget(button)
        buttons = list(self.filter_buttons.values())
        per_row = 2 if width < 420 else len(buttons)
        for index, button in enumerate(buttons):
            self.filter_layout.addWidget(button, index // per_row, index % per_row)
        self.filter_layout.setColumnStretch(len(buttons), 1)
        for widget in (self.search, self.group_apps, self.group_label):
            self.options_row.removeWidget(widget)
        for column in range(3):
            self.options_row.setColumnStretch(column, 0)
        if compact:
            self.options_row.addWidget(self.search, 0, 0, 1, 2)
            self.options_row.addWidget(self.group_apps, 1, 0)
            self.options_row.addWidget(self.group_label, 1, 1)
            self.options_row.setColumnStretch(1, 1)
        else:
            self.options_row.addWidget(self.search, 0, 0)
            self.options_row.addWidget(self.group_apps, 0, 1)
            self.options_row.addWidget(self.group_label, 0, 2)
            self.options_row.setColumnStretch(0, 1)

    def _reflow_columns(self, width: int) -> None:
        tier = "wide" if width >= 760 else "medium" if width >= 600 else "narrow"
        if tier == self._compact_columns:
            return
        self._compact_columns = tier
        # The Status pill must fit "Ejecutándose" and "Wird ausgeführt". On a
        # narrow window the application name matters most: GPU, VRAM and
        # Status give way, and a paused or protected row says so in its line.
        widths = {
            "wide": {2: 64, 3: 64, 4: 108, 5: 96, 6: 136},
            "medium": {2: 56, 3: 56, 4: 92, 5: 0, 6: 120},
            "narrow": {2: 54, 3: 0, 4: 88, 5: 0, 6: 0},
        }[tier]
        for column, section_width in widths.items():
            self.table.setColumnHidden(column, section_width == 0)
            if section_width:
                self.table.setColumnWidth(column, section_width)
        if self._processes:
            self._render_table()

    def _reflow_action_bar(self, width: int) -> None:
        mode = "wide" if width >= 1100 else "medium" if width >= 720 else "compact" if width >= 440 else "stack"
        if mode == self._action_layout_mode:
            return
        self._action_layout_mode = mode
        while self.action_layout.count():
            self.action_layout.takeAt(0)
        for column in range(len(self.action_buttons) + 1):
            self.action_layout.setColumnStretch(column, 0)
        if mode == "wide":
            self.action_layout.addWidget(self.selection_copy, 0, 0)
            for index, button in enumerate(self.action_buttons, start=1):
                self.action_layout.addWidget(button, 0, index)
            self.action_layout.setColumnStretch(0, 1)
        elif mode == "medium":
            self.action_layout.addWidget(self.selection_copy, 0, 0, 1, len(self.action_buttons))
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

    # -- refresh ------------------------------------------------------------

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if self._updates_active:
            if not self.refresh_timer.isActive():
                self.refresh_timer.start()
            # Let the stack paint the page before the table fills.
            QTimer.singleShot(16, self._resume_updates)
        else:
            self.refresh_timer.stop()

    def _resume_updates(self) -> None:
        if not self._updates_active:
            return
        if self._pending_result is not None:
            pending, self._pending_result = self._pending_result, None
            self._apply_snapshot(pending)
            return
        if not self._processes or time.monotonic() - self._last_snapshot_at > 2.5:
            self.refresh()

    def _automatic_refresh(self) -> None:
        if self._updates_active and not self._busy:
            self.refresh()

    def refresh(self) -> None:
        if self._busy or not self._updates_active:
            return
        self._start_task("refresh")

    def _start_task(self, operation: str, *, payload=None) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._set_busy(operation != "refresh", operation)
        worker = ProcessTask(self.controller, operation, payload=payload, state_cache=self._state_cache, parent=self)
        worker.completed.connect(self._task_completed)
        worker.failed.connect(self._task_failed)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _task_completed(self, operation: str, result) -> None:
        self._worker = None
        self._set_busy(False, operation)
        if operation == "cache":
            self._record_event("memory", "success", "Page cache released", "The privileged sync/drop_caches workflow completed successfully.")
            show_toast(self, "Page cache released", "Applications were not closed by this action.", tone="green")
            if self._updates_active:
                self.refresh()
            return
        if operation in {"terminate", "pause", "resume"}:
            self._selected_keys.clear()
            titles = {
                "terminate": ("Selected tasks ended", "SIGTERM followed by protected force-close fallback."),
                "pause": ("Applications paused", "SIGSTOP sent to the selected applications."),
                "resume": ("Applications resumed", "SIGCONT sent to the selected applications."),
            }
            self._record_event("process", "info", *titles[operation])
        data = dict(result or {})
        if not self._updates_active:
            self._pending_result = data
        else:
            self._apply_snapshot(data)

    def _apply_snapshot(self, data: dict) -> None:
        self._last_snapshot_at = time.monotonic()
        self._snapshot = data
        self._processes = list(data.get("processes") or [])
        self.last_refresh.setText(tr_format("Last refresh {time}", time=data.get("refreshed_at") or datetime.now().strftime("%H:%M:%S")))
        self._render_game()
        self._render_table()

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
        for widget in (self.search, self.group_apps, *self.filter_buttons.values(), self.cache_button,
                       self.game_pause_button, self.game_close_button):
            widget.setEnabled(not busy)
        if busy:
            self.visible_summary.setText(tr("Applying selected action…"))
        self._update_action_availability()

    # -- summary and game ---------------------------------------------------

    def _all_entries(self) -> list[ProcessEntry]:
        return build_entries(self._processes, grouped=True, view="all")

    def _render_game(self) -> None:
        games = [entry for entry in self._all_entries() if entry.kind == "game"]
        games.sort(key=lambda entry: (entry.gpu or 0.0, entry.memory), reverse=True)
        self._game = games[0] if games else None
        if self._game is None:
            self.game_card.hide()
            return
        game = self._game
        self.game_icon.setPixmap(icono_app(game.icon_name, game.program, "game").pixmap(36, 36))
        self.game_name.setText(game.name)
        parts = [
            tr_format("CPU {value}", value=_percent_text(game.cpu)),
            tr_format("GPU {value}", value=_percent_text(game.gpu)),
            tr_format("RAM {value}", value=formato_bytes(game.memory)),
        ]
        if game.vram:
            parts.append(tr_format("GPU memory {value}", value=formato_bytes(game.vram)))
        parts.append(count_label(len(game.processes), "process"))
        if game.steam_appid:
            parts.append(f"Steam {game.steam_appid}")
        self.game_metrics.setText(" · ".join(parts))
        self.game_pause_button.setText(tr("Resume game" if game.paused else "Pause game"))
        # systemd-oomd ends the unit using the most swap, and a paused game's
        # memory drifts there: in Steam's unit that ends Steam as well.
        self.game_note.setVisible(game.paused and bool(self._snapshot.get("oomd")))
        self.game_close_button.setEnabled(bool(game.closable) and not self._busy)
        self.game_pause_button.setEnabled(bool(game.closable) and not self._busy)
        self.game_card.show()

    def _toggle_game_pause(self) -> None:
        if self._game is None or not self._game.closable:
            return
        self._start_task("resume" if self._game.paused else "pause", payload=list(self._game.closable))

    def _close_game(self) -> None:
        if self._game is not None:
            self._confirm_and_end([self._game])

    # -- table --------------------------------------------------------------

    def _set_view(self, view: str) -> None:
        if view == self._view:
            return
        self._view = view
        self.filter_buttons[view].setChecked(True)
        self.clear_selection(render=False)
        self._render_table()

    def _grouping_changed(self, _checked: bool) -> None:
        self.clear_selection(render=False)
        self._render_table()

    def _filter_changed(self, _text: str) -> None:
        self.filter_timer.start()

    def _apply_text_filter(self) -> None:
        self._render_table()

    def _focus_search(self) -> None:
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()

    def _header_clicked(self, column: int) -> None:
        key = SORT_KEYS.get(column)
        if key is None:
            return
        if key == self._sort_key:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_key, self._sort_descending = key, key != "name"
        self._render_table()

    def _update_header_labels(self) -> None:
        for column, label in enumerate(COLUMNS):
            text = tr(label)
            if SORT_KEYS.get(column) == self._sort_key:
                text += " ▾" if self._sort_descending else " ▴"
            item = self.table.horizontalHeaderItem(column)
            if item is None:
                item = QTableWidgetItem()
                self.table.setHorizontalHeaderItem(column, item)
            item.setText(text)
            alignment = Qt.AlignmentFlag.AlignLeft if column == 1 else Qt.AlignmentFlag.AlignCenter
            item.setTextAlignment(alignment | Qt.AlignmentFlag.AlignVCenter)

    def _current_table_key(self) -> str | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._row_entries):
            return self._row_entries[row].key
        return None

    def _row_checkbox(self, row: int) -> QCheckBox:
        """The selection box for a row, built once and reused afterwards."""
        wrap = self.table.cellWidget(row, 0)
        if wrap is not None:
            existing = wrap.findChild(QCheckBox)
            if existing is not None:
                return existing
        checkbox = QCheckBox()
        checkbox.setProperty("gamepadSkip", True)
        checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        checkbox.stateChanged.connect(
            lambda state, box=checkbox: self._checkbox_changed(str(box.property("entryKey") or ""), state)
        )
        wrap = QWidget()
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(checkbox)
        self.table.setCellWidget(row, 0, wrap)
        return checkbox

    def _cell(self, row: int, column: int, kind):
        cell = self.table.cellWidget(row, column)
        if not isinstance(cell, kind):
            cell = kind()
            self.table.setCellWidget(row, column, cell)
        return cell

    def _text_item(self, row: int, column: int, text: str, *, muted: bool = False) -> None:
        item = self.table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, column, item)
        item.setText(text)
        item.setForeground(QColor(COLORS["subtle"] if muted else COLORS["text"]))

    def _render_table(self) -> None:
        previous_key = self._current_table_key()
        self._entries = build_entries(
            self._processes,
            grouped=self.group_apps.isChecked(),
            view=self._view,
            query=self.search.text(),
        )
        self._entries.sort(key=lambda entry: entry.sort_value(self._sort_key), reverse=self._sort_descending)
        entries = self._row_entries = self._entries
        self._selected_keys.intersection_update({entry.key for entry in entries if entry.closable})
        self._update_header_labels()
        max_memory = max((entry.memory for entry in entries), default=1)
        max_vram = max((entry.vram for entry in entries), default=1)
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                checkbox = self._row_checkbox(row)
                checkbox.setProperty("entryKey", entry.key)
                checkbox.blockSignals(True)
                checkbox.setEnabled(bool(entry.closable))
                checkbox.setChecked(entry.key in self._selected_keys)
                checkbox.setAccessibleName(tr_format("Select {name}", name=entry.name))
                checkbox.blockSignals(False)
                self._cell(row, 1, ApplicationCell).set_entry(entry, with_status=self.table.isColumnHidden(6))
                self._text_item(row, 2, _percent_text(entry.cpu), muted=entry.paused or entry.fully_protected)
                self._text_item(row, 3, _percent_text(entry.gpu), muted=entry.gpu is None)
                self._cell(row, 4, MeterCell).set_values(entry.memory, max_memory, tooltip=entry.memory_tooltip())
                self._cell(row, 5, MeterCell).set_values(entry.vram, max_vram, empty="—",
                                                         tooltip=entry.gpu_memory_tooltip())
                self._cell(row, 6, StatusCell).set_values(*entry.status())
        finally:
            self.table.setUpdatesEnabled(True)
            self.table.blockSignals(False)
        self._restore_table_cursor(previous_key)

        summary = tr_format(
            "{rows} · {processes}",
            rows=count_label(len(entries), "row"),
            processes=count_label(sum(len(entry.processes) for entry in entries), "process"),
        )
        self.visible_summary.setText(summary if self._processes else tr("Waiting for process inventory"))
        self._update_selection_summary()

    def _restore_table_cursor(self, preferred_key: str | None) -> None:
        if not self._row_entries:
            self.table.clearSelection()
            self.table.setCurrentIndex(self.table.model().index(-1, -1))
            return
        row = next((index for index, entry in enumerate(self._row_entries) if entry.key == preferred_key), None)
        if row is None:
            return
        self.table.blockSignals(True)
        self.table.setCurrentCell(row, 1)
        self.table.blockSignals(False)

    def _activate_table_row(self, row: int) -> None:
        self._row_clicked(row, 1)

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
        for row in rows if rows is not None else range(len(self._row_entries)):
            if not 0 <= row < len(self._row_entries):
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

    # -- selection and actions ---------------------------------------------

    def _selected_entries(self) -> list[ProcessEntry]:
        return [entry for entry in self._row_entries if entry.key in self._selected_keys and entry.closable]

    @staticmethod
    def _real_closable(entries: Iterable[ProcessEntry]) -> list:
        output, seen = [], set()
        for entry in entries:
            for process in entry.closable:
                pid = int(getattr(process, "pid", -1))
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

    def _update_selection_summary(self) -> None:
        entries = self._selected_entries()
        real = self._real_closable(entries)
        if entries:
            self.selected_summary.setText(tr_format(
                "{applications} · {processes} · approx. {memory}",
                applications=count_label(len(entries), "application"),
                processes=count_label(len(real), "process"),
                memory=formato_bytes(sum(int(getattr(process, "memoria", 0) or 0) for process in real)),
            ))
        else:
            # Nothing ticked: the buttons beside it are disabled and say enough.
            self.selected_summary.setText("")
        if self.inventory_card.status is not None:
            if self._busy:
                self.inventory_card.status.setText(tr("Working"))
                self.inventory_card.status.set_tone("blue")
            elif self._row_entries:
                self.inventory_card.status.setText(
                    tr_format("{visible} visible · {selected} selected", visible=len(self._row_entries), selected=len(entries))
                    if entries else tr_format("{count} visible", count=len(self._row_entries))
                )
                self.inventory_card.status.set_tone("orange" if entries else "blue")
            else:
                self.inventory_card.status.setText(tr("Loading") if not self._processes else tr("Empty"))
                self.inventory_card.status.set_tone("gray")
        self._update_action_availability()

    def _update_action_availability(self) -> None:
        entries = self._selected_entries()
        ready = not self._busy
        all_paused = bool(entries) and all(entry.paused for entry in entries)
        self.pause_button.setText(tr("Resume" if all_paused else "Pause"))
        self.pause_button.setEnabled(ready and bool(entries))
        self.terminate_button.setEnabled(ready and bool(entries))
        self.select_safe_button.setEnabled(ready and any(entry.closable for entry in self._row_entries))
        self.clear_button.setEnabled(ready and bool(self._selected_keys))
        self.cache_button.setEnabled(ready)

    def pause_selected(self) -> None:
        entries = self._selected_entries()
        if not entries:
            return
        resume = all(entry.paused for entry in entries)
        self._start_task("resume" if resume else "pause", payload=self._real_closable(entries))

    def terminate_selected(self) -> None:
        entries = self._selected_entries()
        if not entries:
            row = self.table.currentRow()
            if 0 <= row < len(self._row_entries) and self._row_entries[row].closable:
                entries = [self._row_entries[row]]
        if not entries:
            show_toast(
                self,
                "Nothing safe is selected",
                "Select one or more unprotected application rows before ending tasks.",
                tone="blue",
            )
            return
        self._confirm_and_end(entries)

    def _confirm_and_end(self, entries: list[ProcessEntry]) -> None:
        real = self._real_closable(entries)
        if not real:
            return
        names = ", ".join(entry.name for entry in entries[:4])
        if len(entries) > 4:
            names += " " + tr_format("and {count} more", count=len(entries) - 4)
        dialog = ConfirmDialog(
            "End selected tasks",
            "Each application is asked to close first; whatever is still running 1.5 seconds later is ended. Unsaved work in them is lost. Protected desktop programs are never touched.",
            summary=(
                ("Applications", names),
                ("Real processes", str(len(real))),
                ("Approx. memory", formato_bytes(sum(int(getattr(process, "memoria", 0) or 0) for process in real))),
            ),
            confirm_text="End tasks",
            tone="red",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._start_task("terminate", payload=real)

    def release_cache(self) -> None:
        # sync, then drop_caches: nothing is closed and nothing is lost. The
        # administrator prompt is the one question this needs.
        self._start_task("cache")

    def _record_event(self, event_type: str, level: str, title: str, detail: str) -> None:
        self._event_sequence += 1

        def operation() -> object:
            self.activity_service.record(event_type, level, title, detail, {})
            return True

        self._background.start(f"process-event:{self._event_sequence}", operation)
