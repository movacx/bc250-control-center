from __future__ import annotations

from datetime import datetime
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..components.responsive import clear_grid, configure_responsive_scroll_area, effective_viewport_width
from ..components.async_tools import AsyncRefresh, BackgroundExecutor
from ..i18n import count_label, tr, tr_format
from ..components.page_widgets import (
    ControlPageHeader,
    MetricTile,
    ConfirmDialog,
    PresetButton,
    SectionCard,
    StatusLine,
)
from ..core.state import state_cache_for
from ..theme import COLORS
from ..components.widgets import IconBadge, InfoDialog, PillLabel, apply_shadow, icon


def _dict(value):
    if hasattr(value, "to_dict"):
        return value.to_dict()
    try:
        return dict(value or {})
    except Exception:
        return {}


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _integer(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _format_bytes(value) -> str:
    amount = _number(value, 0.0)
    if amount <= 0:
        return "--"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    index = 0
    while amount >= 1024 and index < len(units) - 1:
        amount /= 1024.0
        index += 1
    precision = 0 if index == 0 else 1
    return f"{amount:.{precision}f} {units[index]}"


class GpuSummaryItem(QFrame):
    """One compact value inside the shared GPU telemetry strip."""

    def __init__(
        self,
        label: str,
        value: str,
        detail: str,
        icon_name: str,
        background: str,
        parent=None,
        *,
        compact: bool = False,
    ):
        super().__init__(parent)
        self.setProperty("gpuSummaryItem", True)
        if compact:
            self.setProperty("compactVoltageSummaryItem", True)
        self.setMinimumHeight(56 if compact else 68)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QHBoxLayout(self)
        if compact:
            row.setContentsMargins(8, 6, 8, 6)
        else:
            row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(7 if compact else 10)
        row.addWidget(IconBadge(icon_name, background, 26 if compact else 30, radius=7 if compact else 8))
        text = QVBoxLayout()
        text.setSpacing(0)
        self.label = QLabel(tr(label))
        self.label.setProperty("gpuSummaryLabel", True)
        self.value = QLabel(tr(value))
        self.value.setProperty("gpuSummaryValue", True)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail = QLabel(tr(detail))
        self.detail.setProperty("gpuSummaryDetail", True)
        self.detail.setWordWrap(True)
        text.addWidget(self.label)
        text.addWidget(self.value)
        text.addWidget(self.detail)
        row.addLayout(text, 1)

    def set_values(self, value: str, detail: str | None = None) -> None:
        self.value.setText(tr(value))
        if detail is not None:
            self.detail.setText(tr(detail))


class GpuSummaryStrip(QFrame):
    """Low-profile GPU summary that expands across the complete viewport."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("gpuSummaryStrip", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        apply_shadow(self, blur=16, y=3, alpha=10)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        self.items = [
            GpuSummaryItem("Governor", "Checking", "service and boot state", "settings_blue", COLORS["blue_soft"]),
            GpuSummaryItem("GPU SCLK", "-- MHz", "real-time core clock", "gpu_purple", COLORS["purple_soft"]),
            GpuSummaryItem("Active range", "--", "runtime D-Bus target", "compute_blue", COLORS["blue_soft"]),
            GpuSummaryItem("GPU load", "-- %", "passive utilization", "activity_purple", COLORS["purple_soft"]),
            GpuSummaryItem("Temperature", "-- °C", "GPU edge sensor", "warning_orange", COLORS["orange_soft"]),
        ]
        self.columns = 0
        self.set_columns(5)

    def set_columns(self, columns: int) -> None:
        columns = max(1, int(columns))
        if columns == self.columns and self.grid.count():
            return
        self.columns = columns
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
        for index, widget in enumerate(self.items):
            self.grid.addWidget(widget, index // columns, index % columns)
        for column in range(columns):
            self.grid.setColumnStretch(column, 1)


class GpuDependencyActionTile(QFrame):
    """Action tile that occupies the former DPM telemetry position."""

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self.setProperty("metricTile", True)
        self.setProperty("dependencyActionTile", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(68)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(11)
        row.addWidget(
            IconBadge("download_blue", COLORS["blue_soft"], 36, radius=10),
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )

        content = QVBoxLayout()
        content.setSpacing(2)

        title = QLabel(tr("BC250 setup"))
        title.setProperty("metricTileLabel", True)
        content.addWidget(title)

        self.button = QPushButton(tr("Prepare dependencies"))
        self.button.setProperty("dependencyPrepareButton", True)
        self.button.setFixedHeight(34)
        self.button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.clicked.connect(callback)
        content.addWidget(self.button)

        detail = QLabel(tr("Installs required BC250 tools"))
        detail.setProperty("metricTileDetail", True)
        content.addWidget(detail)

        row.addLayout(content, 1)


class VoltageLabToolbar(QFrame):
    """Compact laboratory toolbar that stacks controls before they can clip."""

    refresh_requested = pyqtSignal()
    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("voltageLabToolbar", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._compact = False

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(11, 8, 11, 8)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(7)
        self.icon_badge = IconBadge("bolt_blue", COLORS["orange_soft"], 32, radius=9)

        self.copy_host = QWidget()
        self.copy_host.setMinimumWidth(0)
        copy = QVBoxLayout(self.copy_host)
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(0)
        title = QLabel(tr("Voltage laboratory"))
        title.setProperty("voltageToolbarTitle", True)
        copy.addWidget(title)

        self.status = PillLabel("LIVE HARDWARE", "orange")

        refresh = QPushButton(tr("Refresh"))
        refresh.setProperty("compactAction", True)
        refresh.setProperty("voltageToolbarButton", True)
        refresh.setFixedHeight(36)
        refresh.setMinimumWidth(108)
        refresh.setIcon(icon("refresh_gray"))
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.refresh_requested)
        self.refresh_button = refresh

        back = QPushButton(tr("Return to GPU control"))
        back.setObjectName("PrimaryAction")
        back.setProperty("voltageToolbarButton", True)
        back.setFixedHeight(36)
        back.setMinimumWidth(176)
        back.setIcon(icon("collapse_gray"))
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_requested)
        self.back_button = back
        self._reflow(force=True)

    def _reflow(self, *, force: bool = False) -> None:
        compact = 0 < self.width() < 680
        if compact == self._compact and not force:
            return
        for widget in (self.icon_badge, self.copy_host, self.status, self.refresh_button, self.back_button):
            self.grid.removeWidget(widget)
        if compact:
            self.grid.addWidget(self.icon_badge, 0, 0, Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(self.copy_host, 0, 1)
            self.grid.addWidget(self.status, 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
            self.grid.addWidget(self.refresh_button, 2, 0)
            self.grid.addWidget(self.back_button, 2, 1)
            self.refresh_button.setMinimumWidth(0)
            self.back_button.setMinimumWidth(0)
            self.refresh_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.back_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.grid.setColumnStretch(0, 1)
            self.grid.setColumnStretch(1, 1)
        else:
            self.grid.addWidget(self.icon_badge, 0, 0)
            self.grid.addWidget(self.copy_host, 0, 1)
            self.grid.addWidget(self.status, 0, 2)
            self.grid.addWidget(self.refresh_button, 0, 3)
            self.grid.addWidget(self.back_button, 0, 4)
            self.refresh_button.setMinimumWidth(108)
            self.back_button.setMinimumWidth(176)
            self.refresh_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self.back_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self.grid.setColumnStretch(0, 0)
            self.grid.setColumnStretch(1, 1)
            for column in range(2, 5):
                self.grid.setColumnStretch(column, 0)
        self._compact = compact
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._reflow()


class VoltageSummaryStrip(QFrame):
    """Compute-Units-inspired overview for the voltage workspace."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("gpuSummaryStrip", True)
        self.setProperty("voltageSummaryStrip", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        apply_shadow(self, blur=16, y=3, alpha=10)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(6, 6, 6, 6)
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(6)
        self.items = [
            GpuSummaryItem("Safe-points", "--", "active TOML entries", "compute_blue", COLORS["blue_soft"], compact=True),
            GpuSummaryItem("Active profile", "--", "closest validated curve", "gpu_purple", COLORS["purple_soft"], compact=True),
            GpuSummaryItem("Maximum voltage", "-- mV", "hard UI ceiling 1150 mV", "bolt_blue", COLORS["orange_soft"], compact=True),
            GpuSummaryItem("Runtime range", "--", "restored after restart", "settings_blue", COLORS["blue_soft"], compact=True),
            GpuSummaryItem("Safety state", "Checking", "monotonic validation", "shield_green", COLORS["green_soft"], compact=True),
        ]
        self.columns = 0
        self.set_columns(5)

    def set_columns(self, columns: int) -> None:
        columns = max(1, int(columns))
        if columns == self.columns and self.grid.count():
            return
        self.columns = columns
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
        for index, widget in enumerate(self.items):
            self.grid.addWidget(widget, index // columns, index % columns)
        for column in range(columns):
            self.grid.setColumnStretch(column, 1)


class VoltageProfileButton(QPushButton):
    def __init__(self, level: int, title: str, detail: str, tone: str = "blue", parent=None):
        super().__init__(parent)
        self.level = int(level)
        self.setCheckable(True)
        self.setProperty("voltageProfileButton", True)
        self.setProperty("profileTone", tone)
        self.setText(f"{tr(title)}\n{tr(detail)}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(58)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class VoltageGridHeaderCell(QFrame):
    def __init__(self, title: str, detail: str, parent=None):
        super().__init__(parent)
        self.setProperty("voltageGridHeader", True)
        self.setFixedHeight(46)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(0)
        title_label = QLabel(tr(title))
        title_label.setProperty("voltageGridHeaderTitle", True)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_label = QLabel(tr(detail))
        detail_label.setProperty("voltageGridHeaderDetail", True)
        detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        layout.addWidget(detail_label)


class VoltageGridCell(QFrame):
    def __init__(self, value: str, detail: str = "", *, role: str = "neutral", parent=None):
        super().__init__(parent)
        self.setProperty("voltageGridCell", True)
        self.setProperty("cellRole", role)
        self.setFixedHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(0)
        self.value = QLabel(tr(value))
        self.value.setProperty("voltageGridValue", True)
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail = QLabel(tr(detail))
        self.detail.setProperty("voltageGridDetail", True)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)
        layout.addWidget(self.value)
        if detail:
            layout.addWidget(self.detail)

    def set_values(self, value: str, detail: str | None = None, *, role: str | None = None) -> None:
        self.value.setText(tr(value))
        if detail is not None:
            self.detail.setText(tr(detail))
            self.detail.setVisible(bool(detail))
        if role is not None and role != self.property("cellRole"):
            self.setProperty("cellRole", role)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()


class VoltageCurveGrid(QFrame):
    """A readable safe-point matrix modelled after the Compute Units topology grid."""

    HEADERS = (
        ("Frequency", "safe-point"),
        ("Current", "active TOML"),
        ("Proposed", "selected profile"),
        ("Added voltage", "vs governor default"),
        ("Custom control", "all active points"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("voltageCurveGrid", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(7, 7, 7, 7)
        self.grid.setHorizontalSpacing(5)
        self.grid.setVerticalSpacing(5)
        self.proposed_cells: dict[int, VoltageGridCell] = {}
        self.added_cells: dict[int, VoltageGridCell] = {}
        self._reset_headers()

    def _reset_headers(self) -> None:
        for column, (title, detail) in enumerate(self.HEADERS):
            self.grid.addWidget(VoltageGridHeaderCell(title, detail), 0, column)
        stretches = (3, 3, 3, 3, 4)
        for column, stretch in enumerate(stretches):
            self.grid.setColumnStretch(column, stretch)

    def clear_points(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.proposed_cells = {}
        self.added_cells = {}
        self._reset_headers()

    @staticmethod
    def _added_voltage_copy(added: int | None) -> tuple[str, str, str]:
        if added is None:
            return "n/a", "no governor base", "muted"
        if added > 0:
            return f"+{added} mV", "above default", "positive"
        if added < 0:
            return f"{added} mV", "below default", "warning"
        return "0 mV", "governor default", "safe"

    def add_point(
        self,
        row: int,
        *,
        frequency: int,
        current: int,
        proposed: int | None,
        added: int | None,
        margin: int | None,
        editor: QWidget | None,
        editable: bool,
        custom_available: bool,
    ) -> None:
        visual_row = int(row) + 1
        frequency_cell = VoltageGridCell(
            f"{frequency} MHz",
            "custom editable" if custom_available else "read only",
            role="frequency",
        )
        current_cell = VoltageGridCell(f"{current} mV" if current else "Not set", "current curve", role="neutral")
        proposed_cell = VoltageGridCell(
            f"{proposed} mV" if proposed is not None else "Unchanged",
            "new value" if editable else "kept as-is",
            role="warning" if editable and margin is not None and margin < 0 else "proposed" if editable else "muted",
        )
        added_value, added_detail, added_role = self._added_voltage_copy(added)
        added_cell = VoltageGridCell(added_value, added_detail, role=added_role)
        self.grid.addWidget(frequency_cell, visual_row, 0)
        self.grid.addWidget(current_cell, visual_row, 1)
        self.grid.addWidget(proposed_cell, visual_row, 2)
        self.grid.addWidget(added_cell, visual_row, 3)

        editor_cell = QFrame()
        editor_cell.setProperty("voltageGridCell", True)
        editor_cell.setProperty("cellRole", "custom" if custom_available else "muted")
        editor_cell.setFixedHeight(52)
        editor_layout = QHBoxLayout(editor_cell)
        editor_layout.setContentsMargins(8, 5, 8, 5)
        editor_layout.setSpacing(0)
        if editor is not None:
            editor.setProperty("voltageEditor", True)
            editor.setFixedHeight(34)
            editor.setMinimumWidth(116)
            editor_layout.addWidget(editor, 0, Qt.AlignmentFlag.AlignCenter)
        else:
            locked = QLabel("Locked")
            locked.setProperty("voltageGridDetail", True)
            locked.setAlignment(Qt.AlignmentFlag.AlignCenter)
            editor_layout.addWidget(locked, 1)
        self.grid.addWidget(editor_cell, visual_row, 4)

        self.proposed_cells[int(frequency)] = proposed_cell
        self.added_cells[int(frequency)] = added_cell

    def update_point(self, frequency: int, proposed: int, added: int | None, margin: int | None) -> None:
        proposed_cell = self.proposed_cells.get(int(frequency))
        if proposed_cell is not None:
            proposed_cell.set_values(
                f"{int(proposed)} mV",
                "new value",
                role="warning" if margin is not None and margin < 0 else "proposed",
            )
        added_cell = self.added_cells.get(int(frequency))
        if added_cell is not None:
            added_value, added_detail, added_role = self._added_voltage_copy(added)
            added_cell.set_values(added_value, added_detail, role=added_role)



class FrequencyField(QFrame):
    """Direct numeric GPU range field with no slider or increment rail."""

    def __init__(self, label: str, hint: str, value: int, parent=None):
        super().__init__(parent)
        self.setProperty("frequencyField", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.minimum = 0
        self.maximum = 9999
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        title = QLabel(label)
        title.setProperty("fieldLabel", True)
        detail = QLabel(hint)
        detail.setProperty("fieldHint", True)
        detail.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(detail)
        row.addLayout(copy, 1)
        self.input = QLineEdit(str(int(value)))
        self.input.setProperty("frequencyInput", True)
        self.input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.input.setMinimumWidth(88)
        self.input.setMaximumWidth(128)
        self.input.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.input.setValidator(QIntValidator(self.minimum, self.maximum, self.input))
        row.addWidget(self.input, 0, Qt.AlignmentFlag.AlignVCenter)
        unit = QLabel("MHz")
        unit.setProperty("frequencyUnit", True)
        row.addWidget(unit, 0, Qt.AlignmentFlag.AlignVCenter)

    def value(self) -> int:
        return _integer(self.input.text(), 0)

    def setValue(self, value: int) -> None:
        self.input.setText(str(int(value)))

    def set_limits(self, minimum: int, maximum: int) -> None:
        self.minimum = int(minimum)
        self.maximum = max(self.minimum, int(maximum))
        self.input.setValidator(QIntValidator(self.minimum, self.maximum, self.input))


class RuntimeStat(QFrame):
    """Compact status tile used for the runtime state summary."""

    def __init__(self, label: str, value: str, detail: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("runtimeStatCard", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(72)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        label_widget = QLabel(tr(label))
        label_widget.setProperty("runtimeStatLabel", True)
        self.value = QLabel(tr(value))
        self.value.setProperty("runtimeStatValue", True)
        self.detail = QLabel(tr(detail))
        self.detail.setProperty("runtimeStatDetail", True)
        self.detail.setWordWrap(True)
        layout.addWidget(label_widget)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_values(self, value: str, detail: str | None = None) -> None:
        self.value.setText(tr(value))
        if detail is not None:
            self.detail.setText(tr(detail))


class DynamicSafetyNotice(QFrame):
    """Safety banner whose title, message, and tone can change after refresh."""

    def __init__(
        self,
        title: str,
        message: str,
        *,
        tone: str = "blue",
        compact: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._tone = ""
        self._compact = bool(compact)
        if self._compact:
            self.setProperty("compactSafetyNotice", True)
        row = QHBoxLayout(self)
        if self._compact:
            row.setContentsMargins(9, 7, 9, 7)
        else:
            row.setContentsMargins(13, 11, 13, 11)
        row.setSpacing(7 if self._compact else 10)
        badge_size = 28 if self._compact else 34
        self.badge = IconBadge("info_blue", COLORS["blue_soft"], badge_size, radius=8 if self._compact else 10)
        row.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = QLabel(tr(title))
        self.title.setProperty("noticeTitle", True)
        self.body = QLabel(tr(message))
        self.body.setProperty("noticeBody", True)
        self.body.setWordWrap(True)
        text.addWidget(self.title)
        text.addWidget(self.body)
        row.addLayout(text, 1)
        self.set_notice(title, message, tone=tone)

    def set_notice(self, title: str, message: str, *, tone: str = "blue") -> None:
        tone = "blue" if tone == "blue" else "orange"
        self.title.setText(tr(title))
        self.body.setText(tr(message))
        if tone == self._tone:
            return
        self._tone = tone
        self.setProperty("safetyNotice", tone)
        self.badge.setParent(None)
        layout = self.layout()
        self.badge = IconBadge(
            "info_blue" if tone == "blue" else "warning_orange",
            COLORS["blue_soft"] if tone == "blue" else COLORS["orange_soft"],
            28 if self._compact else 34,
            radius=8 if self._compact else 10,
        )
        layout.insertWidget(0, self.badge, 0, Qt.AlignmentFlag.AlignTop)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class GpuGovernorPage(QWidget):
    """Complete GPU control studio using the validated cyan-skillfish governor backend."""

    PROFILE_VALUES = (
        ("Recovery", "500–1000 MHz", (500, 1000)),
        ("Balanced", "500–1500 MHz", (500, 1500)),
        ("Gaming", "1000–1850 MHz", (1000, 1850)),
        ("Benchmark", "1000–2000 MHz", (1000, 2000)),
    )
    QUICK_FLOORS = (500, 1000, 2000)
    VOLTAGE_PROFILE_LEVELS = (0, 3, 6)
    VOLTAGE_LAB_FREQUENCIES = (1850, 2000, 2050, 2100, 2125, 2150, 2200, 2300, 2350, 2400)
    VOLTAGE_LAB_BASE = {
        1850: 930,
        2000: 960,
        2050: 980,
        2100: 1000,
        2125: 1020,
        2150: 1035,
        2200: 1050,
        2300: 1110,
        2350: 1130,
        2400: 1150,
    }
    KNOWN_STABLE_VOLTAGES = {
        1600: 910,
        1700: 920,
        1850: 975,
        2000: 1000,
        2050: 1020,
        2100: 1035,
        2125: 1050,
        2150: 1085,
        2200: 1110,
        2300: 1110,
        2350: 1130,
        2400: 1150,
    }

    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("gpuGovernorPage", True)
        self.controller = controller
        self.current_state: dict = {}
        self._updates_active = False
        self._state_cache = state_cache_for(controller)
        self._background = BackgroundExecutor(self)
        self._action_busy = False
        self.current_perf: dict = {}
        self.allowed_min = 300
        self.allowed_max = 2000
        self.active_min = 500
        self.active_max = 1500
        self._controls_initialized = False
        self.safe_frequencies: list[int] = []
        self.safe_voltage_map: dict[int, int] = {}
        self._workspace_columns = 0
        self._preset_columns = 0
        self._field_columns = 0
        self._metric_columns = 0
        self._runtime_columns = 0
        self._runtime_action_columns = 0
        self._advanced_columns = 0
        self._voltage_summary_columns = 0
        self._voltage_workspace_columns = 0
        self._voltage_profile_columns = 0
        self._voltage_custom_values: dict[int, int] = {}
        self._voltage_spinboxes: dict[int, QSpinBox] = {}
        self._voltage_editable_frequencies: set[int] = set()
        self._voltage_profile_frequencies: set[int] = set()
        self._voltage_detected_level = 0
        self._last_operation_summary = "No hardware command has been executed."
        self._detailed_diagnostics = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.page_stack = QStackedWidget()
        outer.addWidget(self.page_stack)

        self.overview_page = QWidget()
        overview_layout = QVBoxLayout(self.overview_page)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        self.overview_scroll = scroll

        self.content = QWidget()
        configure_responsive_scroll_area(scroll, self.content)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(18, 8, 18, 24)
        layout.setSpacing(14)
        scroll.setWidget(self.content)
        overview_layout.addWidget(scroll)
        self.page_stack.addWidget(self.overview_page)

        self.header = ControlPageHeader(
            "GPU / GOVERNOR CONTROL",
            "Graphics tuning",
            "Validated runtime frequency control, passive hardware telemetry, governor persistence, and safe-point operations.",
            mode_text="● LIVE GOVERNOR",
        )
        self.header.refresh_requested.connect(self._manual_refresh)
        layout.addWidget(self.header)
        # Preserve the existing signal wiring without rendering the introductory
        # banner. The main GPU workspace now occupies the released top area.
        self.header.hide()

        # Preserve the shared live-value model without rendering the former
        # duplicate telemetry rail above the main GPU workspace.
        self.summary = GpuSummaryStrip(self.content)
        self.summary.hide()

        self.workspace = QGridLayout()
        self.workspace.setContentsMargins(0, 0, 0, 0)
        self.workspace.setHorizontalSpacing(14)
        self.workspace.setVerticalSpacing(14)
        layout.addLayout(self.workspace)

        self.configuration_card = self._build_configuration_card()
        self.metrics_card = self._build_metrics_card()
        self.configuration_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.metrics_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.runtime_card = self._build_runtime_card()
        self.advanced_card = self._build_advanced_card()
        self.advanced_card.hide()
        layout.addWidget(self.advanced_card)
        layout.addStretch(1)

        self.voltage_lab_page = self._build_voltage_lab_page()
        self.page_stack.addWidget(self.voltage_lab_page)

        self._reflow(1400)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.refresh)
        self._refresher = AsyncRefresh(
            self,
            "gpu-governor-refresh",
            self._fetch_refresh_payload,
            self._apply_refresh_payload,
            self._refresh_failed,
        )
    def _build_configuration_card(self) -> SectionCard:
        card = SectionCard(
            "GPU configuration",
            "Select a validated profile or stage an explicit D-Bus range. Every hardware change is reviewed before execution.",
            icon_name="settings_blue",
            icon_background=COLORS["blue_soft"],
            status=("Safe mode", "green"),
        )
        self.configuration_status = card.status

        self.safety_notice = DynamicSafetyNotice(
            "Safe mode enabled",
            "Only active TOML safe-points are offered. High OC points above 2000 MHz remain hidden until laboratory mode is enabled.",
            tone="blue",
        )
        card.body.addWidget(self.safety_notice)

        profile_label = QLabel("Operating profile")
        profile_label.setProperty("fieldLabel", True)
        card.body.addWidget(profile_label)

        self.preset_grid = QGridLayout()
        self.preset_grid.setContentsMargins(0, 0, 0, 0)
        self.preset_grid.setHorizontalSpacing(8)
        self.preset_grid.setVerticalSpacing(8)
        self.preset_group = QButtonGroup(self)
        self.preset_group.setExclusive(True)
        self.preset_buttons: list[PresetButton] = []
        for title, summary, payload in self.PROFILE_VALUES:
            button = PresetButton(title, summary, payload)
            button.setProperty("gpuFrequencyPreset", True)
            button.setMinimumHeight(64)
            button.clicked.connect(lambda checked, b=button: self._select_preset(b) if checked else None)
            self.preset_group.addButton(button)
            self.preset_buttons.append(button)
        self._reflow_presets(1400)
        card.body.addLayout(self.preset_grid)

        self.range_fields_grid = QGridLayout()
        self.range_fields_grid.setContentsMargins(0, 0, 0, 0)
        self.range_fields_grid.setHorizontalSpacing(10)
        self.range_fields_grid.setVerticalSpacing(10)
        self.minimum_control = FrequencyField(
            "Minimum frequency",
            "Governor floor applied through the validated D-Bus interface.",
            500,
        )
        self.maximum_control = FrequencyField(
            "Maximum frequency",
            "The ceiling must exist in the active TOML safe-point table.",
            1500,
        )
        self.range_fields = [self.minimum_control, self.maximum_control]
        self.minimum_control.input.textChanged.connect(self._mark_custom_range)
        self.maximum_control.input.textChanged.connect(self._mark_custom_range)
        self._reflow_range_fields(1400)
        card.body.addLayout(self.range_fields_grid)

        self.range_recommendation = QLabel(
            "Refresh loads the active D-Bus range, allowed limits, and validated TOML ceiling."
        )
        self.range_recommendation.setProperty("fieldHint", True)
        self.range_recommendation.setWordWrap(True)
        card.body.addWidget(self.range_recommendation)

        floor_panel = QFrame()
        floor_panel.setProperty("compactPanel", True)
        floor_layout = QVBoxLayout(floor_panel)
        floor_layout.setContentsMargins(12, 10, 12, 10)
        floor_layout.setSpacing(8)
        floor_title = QLabel("Quick frequency floor")
        floor_title.setProperty("fieldLabel", True)
        floor_hint = QLabel(
            "Original GUI function: raise the minimum clock when a light game does not wake the governor correctly."
        )
        floor_hint.setProperty("fieldHint", True)
        floor_hint.setWordWrap(True)
        floor_layout.addWidget(floor_title)
        floor_layout.addWidget(floor_hint)
        floor_actions = QHBoxLayout()
        floor_actions.setSpacing(8)
        self.floor_group = QButtonGroup(self)
        self.floor_group.setExclusive(True)
        self.floor_buttons: list[QPushButton] = []
        for floor in self.QUICK_FLOORS:
            button = QPushButton(f"{floor} MHz")
            button.setCheckable(True)
            button.setProperty("compactAction", True)
            button.setProperty("gpuFrequencyAction", True)
            button.setMinimumHeight(36)
            button.setProperty("floor", floor)
            button.clicked.connect(lambda checked, value=floor: self._select_floor(value) if checked else None)
            self.floor_group.addButton(button)
            self.floor_buttons.append(button)
            floor_actions.addWidget(button, 1)
        floor_layout.addLayout(floor_actions)
        card.body.addWidget(floor_panel)

        apply_row = QHBoxLayout()
        apply_row.setSpacing(8)
        self.use_active_button = QPushButton("Use active range")
        self.use_active_button.setProperty("compactAction", True)
        self.use_active_button.clicked.connect(self._use_active_range)
        apply_row.addWidget(self.use_active_button)
        apply_row.addStretch(1)
        self.apply_range_button = QPushButton("Review and apply range")
        self.apply_range_button.setObjectName("PrimaryAction")
        self.apply_range_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.apply_range_button.setProperty("gamepadEntry", True)
        self.apply_range_button.clicked.connect(self._request_custom_range)
        apply_row.addWidget(self.apply_range_button)
        card.body.addLayout(apply_row)
        return card

    def _build_fixed_safe_point_panel(self) -> QFrame:
        """Advanced fixed-frequency controls kept out of the normal GPU workspace."""

        fixed_panel = QFrame()
        fixed_panel.setProperty("compactPanel", True)
        fixed_panel.setProperty("advancedSafePointPanel", True)
        fixed_layout = QVBoxLayout(fixed_panel)
        fixed_layout.setContentsMargins(12, 10, 12, 10)
        fixed_layout.setSpacing(8)
        fixed_header = QHBoxLayout()
        fixed_copy = QVBoxLayout()
        fixed_copy.setSpacing(1)
        fixed_title = QLabel("Fixed safe-point laboratory")
        fixed_title.setProperty("fieldLabel", True)
        fixed_hint = QLabel(
            "Advanced OC workflow for fixed frequencies, rebuilt around the active TOML and conservative voltage validation."
        )
        fixed_hint.setProperty("fieldHint", True)
        fixed_hint.setWordWrap(True)
        fixed_copy.addWidget(fixed_title)
        fixed_copy.addWidget(fixed_hint)
        fixed_header.addLayout(fixed_copy, 1)
        self.experimental_toggle = QCheckBox("Show high OC points (2050+ MHz)")
        self.experimental_toggle.setToolTip(
            "Exposes high safe-points for controlled laboratory use. It does not guarantee stability."
        )
        self.experimental_toggle.toggled.connect(self._experimental_mode_changed)
        fixed_header.addWidget(self.experimental_toggle, 0, Qt.AlignmentFlag.AlignTop)
        fixed_layout.addLayout(fixed_header)

        fixed_actions = QHBoxLayout()
        fixed_actions.setSpacing(8)
        self.oc_frequency = QComboBox()
        self.oc_frequency.setMinimumWidth(190)
        self.oc_frequency.currentIndexChanged.connect(self._update_selected_safe_point)
        fixed_actions.addWidget(self.oc_frequency)
        self.safe_point_detail = QLabel("Refresh to load safe-points.")
        self.safe_point_detail.setProperty("fieldHint", True)
        self.safe_point_detail.setWordWrap(True)
        fixed_actions.addWidget(self.safe_point_detail, 1)
        self.fixed_button = QPushButton("Review fixed safe-point")
        self.fixed_button.setProperty("dangerAction", True)
        self.fixed_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.fixed_button.clicked.connect(self._request_fixed)
        fixed_actions.addWidget(self.fixed_button)
        fixed_layout.addLayout(fixed_actions)
        return fixed_panel

    def _build_metrics_card(self) -> SectionCard:
        card = SectionCard(
            "Live GPU telemetry",
            "Read-only sensor data refreshed from amdgpu, the governor backend, and the existing performance service.",
            icon_name="gpu_purple",
            icon_background=COLORS["purple_soft"],
            status=("Passive", "green"),
        )
        self.metrics_status = card.status

        self.metrics_grid = QGridLayout()
        self.metrics_grid.setContentsMargins(0, 0, 0, 0)
        self.metrics_grid.setHorizontalSpacing(10)
        self.metrics_grid.setVerticalSpacing(10)
        self.sclk_metric = MetricTile(
            "Core clock", "-- MHz", "Current SCLK state", icon_name="gpu_purple", icon_background=COLORS["purple_soft"]
        )
        self.voltage_metric = MetricTile(
            "GPU voltage", "-- mV", "OD / SMU telemetry", icon_name="bolt_blue", icon_background=COLORS["orange_soft"]
        )
        self.temperature_metric = MetricTile(
            "Temperature", "-- °C", "GPU edge sensor", icon_name="warning_orange", icon_background=COLORS["orange_soft"]
        )
        self.utilization_metric = MetricTile(
            "GPU load", "-- %", "amdgpu busy percentage", icon_name="activity_purple", icon_background=COLORS["purple_soft"]
        )
        self.mclk_metric = MetricTile(
            "Memory clock", "-- MHz", "Current MCLK state", icon_name="compute_blue", icon_background=COLORS["blue_soft"]
        )
        self.vram_metric = MetricTile(
            "VRAM usage", "--", "Dedicated memory counters", icon_name="vram_gray", icon_background="neutral_soft"
        )
        self.power_metric = MetricTile(
            "SoC package power", "-- W", "AMDGPU hwmon sensor", icon_name="power_gray", icon_background="neutral_soft"
        )
        self.dependencies_metric = GpuDependencyActionTile(self.prepare_dependencies)
        self.metric_tiles = [
            self.sclk_metric,
            self.voltage_metric,
            self.temperature_metric,
            self.utilization_metric,
            self.mclk_metric,
            self.vram_metric,
            self.power_metric,
            self.dependencies_metric,
        ]
        for tile in self.metric_tiles:
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            tile.setMinimumHeight(68)
        self._reflow_metric_tiles(1400)
        card.body.addLayout(self.metrics_grid)

        note = QLabel(
            "Telemetry is passive. Use Prepare dependencies for the shared BC250 setup workflow; hardware changes still require explicit confirmation."
        )
        note.setProperty("fieldHint", True)
        note.setWordWrap(True)
        card.body.addWidget(note)
        return card

    def _build_voltage_lab_page(self) -> QWidget:
        page = QWidget()
        page.setProperty("voltageLabPage", True)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        self.voltage_scroll = scroll
        content = QWidget()
        configure_responsive_scroll_area(scroll, content)
        # The voltage map is a dense data grid. At the smallest supported shell
        # it remains legible through local horizontal scrolling instead of being
        # squeezed into overlapping editor cells.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 6, 12, 14)
        layout.setSpacing(8)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)

        self.voltage_header = VoltageLabToolbar()
        self.voltage_header.refresh_requested.connect(self._refresh_voltage_lab)
        self.voltage_header.back_requested.connect(self._close_voltage_lab)
        layout.addWidget(self.voltage_header)

        self.voltage_notice = DynamicSafetyNotice(
            "Stop every 3D workload before applying",
            "A timestamped backup is created, the governor restarts, and the previous D-Bus range is restored only after confirmation.",
            tone="orange",
            compact=True,
        )
        layout.addWidget(self.voltage_notice)

        self.voltage_summary = VoltageSummaryStrip()
        self.voltage_summary_items = self.voltage_summary.items
        layout.addWidget(self.voltage_summary)

        self.voltage_workspace = QGridLayout()
        self.voltage_workspace.setContentsMargins(0, 0, 0, 0)
        self.voltage_workspace.setHorizontalSpacing(8)
        self.voltage_workspace.setVerticalSpacing(8)
        layout.addLayout(self.voltage_workspace)

        curve_card = SectionCard(
            "Voltage map",
            "All active TOML safe-points with current, proposed, added voltage, and custom values.",
            icon_name="compute_blue",
            icon_background=COLORS["blue_soft"],
            status=("Waiting", "gray"),
        )
        curve_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.voltage_curve_card = curve_card
        self.voltage_table_status = curve_card.status
        self.voltage_curve_grid = VoltageCurveGrid()
        curve_card.body.addWidget(self.voltage_curve_grid)

        profiles_card = SectionCard(
            "Voltage profiles",
            "Choose one of three validated levels or unlock every active safe-point for custom editing.",
            icon_name="gpu_purple",
            icon_background=COLORS["purple_soft"],
            status=("Ready", "orange"),
            compact=True,
        )
        profiles_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.voltage_controls_card = profiles_card
        self.voltage_controls_status = profiles_card.status

        self.voltage_level_combo = QComboBox()
        self.voltage_level_combo.addItem("Level 0 · governor defaults", 0)
        self.voltage_level_combo.addItem("Level 3 · default +30 mV", 3)
        self.voltage_level_combo.addItem("Level 6 · default +60 mV", 6)
        self.voltage_level_combo.addItem("Custom · all active safe-points", -1)
        self.voltage_level_combo.currentIndexChanged.connect(self._voltage_level_changed)
        self.voltage_level_combo.hide()

        self.voltage_profile_grid = QGridLayout()
        self.voltage_profile_grid.setContentsMargins(0, 0, 0, 0)
        self.voltage_profile_grid.setHorizontalSpacing(5)
        self.voltage_profile_grid.setVerticalSpacing(5)
        self.voltage_profile_group = QButtonGroup(self)
        self.voltage_profile_group.setExclusive(True)
        profile_specs = [
            (0, "Level 0", "Governor defaults", "green"),
            (3, "Level 3", "+30 mV", "blue"),
            (6, "Level 6", "+60 mV / ceiling", "orange"),
            (-1, "Custom", "Edit every safe-point", "purple"),
        ]
        self.voltage_profile_buttons: list[VoltageProfileButton] = []
        for level, title, detail, tone in profile_specs:
            button = VoltageProfileButton(level, title, detail, tone)
            button.clicked.connect(lambda checked, value=level: self._select_voltage_profile(value) if checked else None)
            self.voltage_profile_group.addButton(button)
            self.voltage_profile_buttons.append(button)
        self._reflow_voltage_profiles(1400)
        profiles_card.body.addLayout(self.voltage_profile_grid)

        self.voltage_level_detail = QLabel(
            "Refresh to compare the selected curve against the active TOML and conservative reference values."
        )
        self.voltage_level_detail.setProperty("voltageProfileDetail", True)
        self.voltage_level_detail.setWordWrap(True)
        profiles_card.body.addWidget(self.voltage_level_detail)

        workflow_card = SectionCard(
            "Review and apply",
            "Review the selected curve and apply it through the existing validated backend.",
            icon_name="shield_green",
            icon_background=COLORS["green_soft"],
            status=("Armed", "orange"),
            compact=True,
        )
        workflow_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.voltage_workflow_card = workflow_card
        self.voltage_workflow_status = workflow_card.status

        workflow_panel = QFrame()
        workflow_panel.setProperty("voltageWorkflowPanel", True)
        workflow_layout = QVBoxLayout(workflow_panel)
        workflow_layout.setContentsMargins(8, 7, 8, 7)
        workflow_layout.setSpacing(6)
        checks = (
            ("1", "Stop games and stress tests"),
            ("2", "Check orange proposed values"),
            ("3", "Confirm the preserved runtime range"),
        )
        checks_grid = QGridLayout()
        checks_grid.setContentsMargins(0, 0, 0, 0)
        checks_grid.setHorizontalSpacing(5)
        checks_grid.setVerticalSpacing(5)
        for column, (token, copy) in enumerate(checks):
            check_item = QFrame()
            check_item.setProperty("voltageStepItem", True)
            check_item.setFixedHeight(40)
            check_row = QHBoxLayout(check_item)
            check_row.setContentsMargins(6, 5, 6, 5)
            check_row.setSpacing(5)
            badge = QLabel(token)
            badge.setProperty("voltageStepBadge", True)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedSize(22, 22)
            check_label = QLabel(copy)
            check_label.setProperty("voltageStepText", True)
            check_label.setWordWrap(True)
            check_row.addWidget(badge)
            check_row.addWidget(check_label, 1)
            checks_grid.addWidget(check_item, 0, column)
            checks_grid.setColumnStretch(column, 1)
        workflow_layout.addLayout(checks_grid)

        self.voltage_apply_button = QPushButton("Review and apply voltage curve")
        self.voltage_apply_button.setProperty("dangerAction", True)
        self.voltage_apply_button.setProperty("voltageApplyButton", True)
        self.voltage_apply_button.setProperty("gamepadEntry", True)
        self.voltage_apply_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.voltage_apply_button.setFixedHeight(40)
        self.voltage_apply_button.setIcon(icon("bolt_blue"))
        self.voltage_apply_button.setEnabled(True)
        self.voltage_apply_button.clicked.connect(self._request_apply_voltage_curve)
        workflow_layout.addWidget(self.voltage_apply_button)
        workflow_card.body.addWidget(workflow_panel)

        # Voltage profiles now occupy the former validation-panel position at the bottom.
        layout.addWidget(profiles_card)

        self._reflow_voltage_workspace(1400)
        layout.addStretch(1)
        return page

    def _build_runtime_card(self) -> SectionCard:
        card = SectionCard(
            "Governor runtime",
            "Service state, boot persistence, D-Bus health, active range, and the complete service workflow from the original GUI.",
            icon_name="shield_green",
            icon_background=COLORS["green_soft"],
            status=("Checking", "gray"),
        )

        stats_panel = QFrame()
        stats_panel.setProperty("compactPanel", True)
        stats_panel_layout = QVBoxLayout(stats_panel)
        stats_panel_layout.setContentsMargins(10, 10, 10, 10)
        stats_panel_layout.setSpacing(0)
        self.runtime_stats_grid = QGridLayout()
        self.runtime_stats_grid.setContentsMargins(0, 0, 0, 0)
        self.runtime_stats_grid.setHorizontalSpacing(10)
        self.runtime_stats_grid.setVerticalSpacing(10)

        self.service_stat = RuntimeStat("Service", "Checking", "cyan-skillfish-governor-smu.service")
        self.boot_stat = RuntimeStat("Boot persistence", "Checking", "systemd UnitFileState")
        self.dbus_stat = RuntimeStat("D-Bus API", "Checking", "runtime range interface")
        self.profile_stat = RuntimeStat("Active range", "--", "current governor target")
        self.points_stat = RuntimeStat("Validated points", "Checking", "active TOML entries")
        self.updated_stat = RuntimeStat("Last refresh", "--:--:--", "passive telemetry")
        self.runtime_stats = [
            self.service_stat,
            self.boot_stat,
            self.dbus_stat,
            self.profile_stat,
            self.points_stat,
            self.updated_stat,
        ]
        self._reflow_runtime_stats(1400)
        stats_panel_layout.addLayout(self.runtime_stats_grid)
        card.body.addWidget(stats_panel)

        controls_panel = QFrame()
        controls_panel.setProperty("compactPanel", True)
        controls_layout = QVBoxLayout(controls_panel)
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.setSpacing(8)
        controls_title = QLabel("Governor service actions")
        controls_title.setProperty("fieldLabel", True)
        controls_copy = QLabel(
            "Enable starts the governor now and at boot. Disable stops it and removes persistence. Status output is shown inside the application console."
        )
        controls_copy.setProperty("fieldHint", True)
        controls_copy.setWordWrap(True)
        controls_layout.addWidget(controls_title)
        controls_layout.addWidget(controls_copy)

        self.runtime_actions_grid = QGridLayout()
        self.runtime_actions_grid.setContentsMargins(0, 0, 0, 0)
        self.runtime_actions_grid.setHorizontalSpacing(8)
        self.runtime_actions_grid.setVerticalSpacing(8)

        self.enable_button = QPushButton("Enable service")
        self.enable_button.setProperty("compactAction", True)
        self.enable_button.setIcon(icon("rocket_blue"))
        self.enable_button.clicked.connect(lambda: self._service_action("activar"))

        self.disable_button = QPushButton("Disable service")
        self.disable_button.setProperty("dangerAction", True)
        self.disable_button.clicked.connect(lambda: self._service_action("desactivar"))

        self.restart_button = QPushButton("Restart service")
        self.restart_button.setProperty("compactAction", True)
        self.restart_button.setIcon(icon("refresh_gray"))
        self.restart_button.clicked.connect(lambda: self._service_action("reiniciar"))

        self.status_button = QPushButton("View service status")
        self.status_button.setProperty("compactAction", True)
        self.status_button.clicked.connect(self.read_service_status)

        self.voltage_lab_button = QPushButton("Open voltage lab")
        self.voltage_lab_button.setProperty("dangerAction", True)
        self.voltage_lab_button.clicked.connect(self.open_voltage_lab)

        self.advanced_toggle = QPushButton("Advanced diagnostics")
        self.advanced_toggle.setProperty("compactAction", True)
        self.advanced_toggle.clicked.connect(self._toggle_advanced)

        self.runtime_action_buttons = [
            self.enable_button,
            self.disable_button,
            self.restart_button,
            self.status_button,
            self.voltage_lab_button,
            self.advanced_toggle,
        ]
        self._reflow_runtime_actions(1400)
        controls_layout.addLayout(self.runtime_actions_grid)
        card.body.addWidget(controls_panel)
        return card

    def _build_advanced_card(self) -> SectionCard:
        card = SectionCard(
            "Advanced GPU diagnostics",
            "Fixed-frequency laboratory controls, safe-point validation, hardware details, and operation output. Hidden by default.",
            icon_name="logs_gray",
            icon_background="neutral_soft",
            status=("Hidden", "gray"),
        )
        card.add_header_button("Clear console", self._clear_console)

        self.advanced_grid = QGridLayout()
        self.advanced_grid.setContentsMargins(0, 0, 0, 0)
        self.advanced_grid.setHorizontalSpacing(12)
        self.advanced_grid.setVerticalSpacing(12)

        self.fixed_safe_point_panel = self._build_fixed_safe_point_panel()

        self.safe_points_panel = QFrame()
        self.safe_points_panel.setProperty("compactPanel", True)
        safe_layout = QVBoxLayout(self.safe_points_panel)
        safe_layout.setContentsMargins(12, 12, 12, 12)
        safe_layout.setSpacing(8)
        safe_header = QLabel("Active TOML safe-points")
        safe_header.setProperty("fieldLabel", True)
        safe_layout.addWidget(safe_header)
        self.points_table = QTableWidget(0, 4)
        self.points_table.setHorizontalHeaderLabels(("Frequency", "Voltage", "Known floor", "Role / validation"))
        self.points_table.setAlternatingRowColors(True)
        self.points_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.points_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.points_table.verticalHeader().setVisible(False)
        header = self.points_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.points_table.setMinimumHeight(250)
        safe_layout.addWidget(self.points_table, 1)

        self.diagnostics_panel = QFrame()
        self.diagnostics_panel.setProperty("compactPanel", True)
        diagnostics_layout = QVBoxLayout(self.diagnostics_panel)
        diagnostics_layout.setContentsMargins(12, 12, 12, 12)
        diagnostics_layout.setSpacing(8)
        diagnostics_header = QLabel("Governor and hardware contract")
        diagnostics_header.setProperty("fieldLabel", True)
        diagnostics_layout.addWidget(diagnostics_header)
        self.device_line = StatusLine("Device", "--", "PCI vendor / device")
        self.driver_line = StatusLine("Driver", "--", "amdgpu path")
        self.config_line = StatusLine("Governor config", "--", "active TOML")
        self.curve_line = StatusLine("Voltage curve", "Checking", "monotonic validation")
        self.missing_line = StatusLine("Missing voltage", "Checking", "safe-points without active voltage")
        self.duplicates_line = StatusLine("Duplicates", "Checking", "duplicate frequency entries")
        self.power_state_line = StatusLine("Power state", "--", "DPM performance level")
        self.last_operation_line = StatusLine("Last operation", "None", self._last_operation_summary)
        for line in (
            self.device_line,
            self.driver_line,
            self.config_line,
            self.curve_line,
            self.missing_line,
            self.duplicates_line,
            self.power_state_line,
            self.last_operation_line,
        ):
            diagnostics_layout.addWidget(line)

        self.console_panel = QFrame()
        self.console_panel.setProperty("compactPanel", True)
        console_layout = QVBoxLayout(self.console_panel)
        console_layout.setContentsMargins(12, 12, 12, 12)
        console_layout.setSpacing(8)
        console_header = QLabel("Governor console")
        console_header.setProperty("fieldLabel", True)
        console_layout.addWidget(console_header)
        self.console = QPlainTextEdit()
        self.console.setObjectName("OperationConsole")
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(230)
        self.console.setPlainText("GPU Governor console ready. No hardware command has been executed.")
        console_layout.addWidget(self.console)

        self._reflow_advanced(1400)
        card.body.addLayout(self.advanced_grid)
        self.advanced_status = card.status
        return card

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        active_scroll = self.voltage_scroll if self.page_stack.currentWidget() is self.voltage_lab_page else self.overview_scroll
        self._reflow(effective_viewport_width(self, active_scroll))

    def _reflow(self, width: int) -> None:
        self._reflow_presets(width)
        self._reflow_range_fields(width)
        self._reflow_metric_tiles(width)
        self._reflow_runtime_stats(width)
        self._reflow_runtime_actions(width)
        self._reflow_advanced(width)
        self._reflow_voltage_summary(width)
        self._reflow_voltage_workspace(width)

        columns = 2 if width >= 1080 else 1
        if columns == self._workspace_columns and self.workspace.count():
            return
        self._workspace_columns = columns
        self._clear_grid(self.workspace)
        self.workspace.setColumnStretch(0, 0)
        self.workspace.setColumnStretch(1, 0)
        if columns == 2:
            self.workspace.addWidget(self.configuration_card, 0, 0)
            self.workspace.addWidget(self.metrics_card, 0, 1)
            self.workspace.addWidget(self.runtime_card, 1, 0, 1, 2, Qt.AlignmentFlag.AlignTop)
            self.workspace.setColumnStretch(0, 7)
            self.workspace.setColumnStretch(1, 5)
        else:
            self.workspace.addWidget(self.configuration_card, 0, 0, 1, 1, Qt.AlignmentFlag.AlignTop)
            self.workspace.addWidget(self.metrics_card, 1, 0, 1, 1, Qt.AlignmentFlag.AlignTop)
            self.workspace.addWidget(self.runtime_card, 2, 0, 1, 1, Qt.AlignmentFlag.AlignTop)
            self.workspace.setColumnStretch(0, 1)

    def _reflow_presets(self, width: int) -> None:
        columns = 4 if width >= 1200 else 2 if width >= 620 else 1
        if columns == self._preset_columns and self.preset_grid.count():
            return
        self._preset_columns = columns
        self._clear_grid(self.preset_grid)
        for index, button in enumerate(self.preset_buttons):
            self.preset_grid.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self.preset_grid.setColumnStretch(column, 1)

    def _reflow_range_fields(self, width: int) -> None:
        columns = 2 if width >= 680 else 1
        if columns == self._field_columns and self.range_fields_grid.count():
            return
        self._field_columns = columns
        self._clear_grid(self.range_fields_grid)
        for index, field in enumerate(self.range_fields):
            self.range_fields_grid.addWidget(field, index // columns, index % columns)
        for column in range(columns):
            self.range_fields_grid.setColumnStretch(column, 1)

    def _reflow_metric_tiles(self, width: int) -> None:
        if not hasattr(self, "metrics_grid"):
            return
        columns = 2 if width >= 720 else 1
        if columns == self._metric_columns and self.metrics_grid.count():
            return
        self._metric_columns = columns
        self._clear_grid(self.metrics_grid)
        for row in range(len(self.metric_tiles)):
            self.metrics_grid.setRowStretch(row, 0)
        for index, tile in enumerate(self.metric_tiles):
            self.metrics_grid.addWidget(tile, index // columns, index % columns)
        for column in range(columns):
            self.metrics_grid.setColumnStretch(column, 1)
        rows = (len(self.metric_tiles) + columns - 1) // columns
        for row in range(rows):
            self.metrics_grid.setRowStretch(row, 1)

    def _reflow_voltage_summary(self, width: int) -> None:
        if not hasattr(self, "voltage_summary"):
            return
        columns = 5 if width >= 1040 else 3 if width >= 680 else 2 if width >= 420 else 1
        if columns == self._voltage_summary_columns:
            return
        self._voltage_summary_columns = columns
        self.voltage_summary.set_columns(columns)

    def _reflow_voltage_profiles(self, width: int) -> None:
        if not hasattr(self, "voltage_profile_grid") or not hasattr(self, "voltage_profile_buttons"):
            return
        columns = 4 if width >= 850 else 2 if width >= 480 else 1
        if columns == self._voltage_profile_columns and self.voltage_profile_grid.count():
            return
        self._voltage_profile_columns = columns
        self._clear_grid(self.voltage_profile_grid)
        for index, button in enumerate(self.voltage_profile_buttons):
            self.voltage_profile_grid.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self.voltage_profile_grid.setColumnStretch(column, 1)

    def _reflow_voltage_workspace(self, width: int) -> None:
        if not hasattr(self, "voltage_workspace") or not hasattr(self, "voltage_curve_card"):
            return
        self._reflow_voltage_profiles(width)
        columns = 1
        if columns == self._voltage_workspace_columns and self.voltage_workspace.count():
            return
        self._voltage_workspace_columns = columns
        self._clear_grid(self.voltage_workspace)
        self.voltage_workspace.setHorizontalSpacing(0)
        self.voltage_workspace.setVerticalSpacing(8)
        self.voltage_workspace.addWidget(self.voltage_curve_card, 0, 0, Qt.AlignmentFlag.AlignTop)
        self.voltage_workspace.addWidget(self.voltage_workflow_card, 1, 0, Qt.AlignmentFlag.AlignTop)
        self.voltage_workspace.setColumnStretch(0, 1)

    def _reflow_runtime_stats(self, width: int) -> None:
        columns = 6 if width >= 1260 else 3 if width >= 760 else 2 if width >= 480 else 1
        if columns == self._runtime_columns and self.runtime_stats_grid.count():
            return
        self._runtime_columns = columns
        self._clear_grid(self.runtime_stats_grid)
        for index, stat in enumerate(self.runtime_stats):
            self.runtime_stats_grid.addWidget(stat, index // columns, index % columns)
        for column in range(columns):
            self.runtime_stats_grid.setColumnStretch(column, 1)

    def _reflow_runtime_actions(self, width: int) -> None:
        # Six service actions form a balanced 3x2 grid on wide layouts.
        columns = 3 if width >= 1080 else 2 if width >= 520 else 1
        if columns == self._runtime_action_columns and self.runtime_actions_grid.count():
            return
        self._runtime_action_columns = columns
        self._clear_grid(self.runtime_actions_grid)
        for index, button in enumerate(self.runtime_action_buttons):
            self.runtime_actions_grid.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self.runtime_actions_grid.setColumnStretch(column, 0)

    def _reflow_advanced(self, width: int) -> None:
        columns = 2 if width >= 1080 else 1
        if columns == self._advanced_columns and self.advanced_grid.count():
            return
        self._advanced_columns = columns
        self._clear_grid(self.advanced_grid)
        if columns == 2:
            self.advanced_grid.addWidget(self.fixed_safe_point_panel, 0, 0, 1, 2)
            self.advanced_grid.addWidget(self.safe_points_panel, 1, 0)
            self.advanced_grid.addWidget(self.diagnostics_panel, 1, 1)
            self.advanced_grid.addWidget(self.console_panel, 2, 0, 1, 2)
            self.advanced_grid.setColumnStretch(0, 7)
            self.advanced_grid.setColumnStretch(1, 5)
        else:
            self.advanced_grid.addWidget(self.fixed_safe_point_panel, 0, 0)
            self.advanced_grid.addWidget(self.safe_points_panel, 1, 0)
            self.advanced_grid.addWidget(self.diagnostics_panel, 2, 0)
            self.advanced_grid.addWidget(self.console_panel, 3, 0)
            self.advanced_grid.setColumnStretch(0, 1)

    @staticmethod
    def _clear_grid(layout: QGridLayout) -> None:
        clear_grid(layout)

    def _select_preset(self, button: PresetButton) -> None:
        minimum, maximum = button.payload
        self._stage_range(int(minimum), int(maximum), preset=button.text().splitlines()[0])

    def _select_floor(self, floor: int) -> None:
        maximum = max(int(floor), self.maximum_control.value())
        self._stage_range(int(floor), maximum)

    def _stage_range(self, minimum: int, maximum: int, *, preset: str = "") -> None:
        minimum = max(self.allowed_min, min(self.allowed_max, int(minimum)))
        maximum = max(minimum, min(self.allowed_max, int(maximum)))
        self.minimum_control.setValue(minimum)
        self.maximum_control.setValue(maximum)
        self._sync_floor_buttons(minimum)
        if preset:
            for button in self.preset_buttons:
                button.setChecked(button.text().splitlines()[0] == preset)

    def _mark_custom_range(self, _text: str = "") -> None:
        current = (self.minimum_control.value(), self.maximum_control.value())
        matched = False
        for button in self.preset_buttons:
            if tuple(button.payload) == current:
                button.setChecked(True)
                matched = True
                break
        if not matched:
            self.preset_group.setExclusive(False)
            for button in self.preset_buttons:
                button.setChecked(False)
            self.preset_group.setExclusive(True)
        self._sync_floor_buttons(current[0])

    def _sync_floor_buttons(self, minimum: int) -> None:
        matched = False
        for button in self.floor_buttons:
            checked = _integer(button.property("floor"), 0) == int(minimum)
            button.setChecked(checked)
            matched = matched or checked
        if not matched:
            self.floor_group.setExclusive(False)
            for button in self.floor_buttons:
                button.setChecked(False)
            self.floor_group.setExclusive(True)

    def _use_active_range(self) -> None:
        self._stage_range(self.active_min, self.active_max, preset=self._profile_name(self.active_min, self.active_max))

    def _experimental_mode_changed(self, enabled: bool) -> None:
        self._populate_points(
            list(self.current_state.get("safe_points_with_voltage") or self.current_state.get("safe_points") or []),
            _integer(self.current_state.get("sclk_actual"), 0),
        )
        self._update_profile_availability()
        self._update_safety_notice(self.current_state)
        if enabled:
            self._show_info(
                "High OC laboratory enabled",
                "Safe-points above 2000 MHz are now visible. This does not make them stable. Change frequencies only with games, FurMark, and other 3D loads stopped.",
                tone="orange",
            )

    def _run_backend_action(
        self,
        operation,
        on_success,
        error_title: str,
        *,
        controls: tuple[QWidget, ...] = (),
        refresh: bool = True,
        keep_voltage_lab: bool = False,
    ) -> bool:
        if self._action_busy:
            self._show_info("GPU operation in progress", "Wait for the current GPU operation to finish.", tone="orange")
            return False
        self._action_busy = True
        for control in controls:
            control.setEnabled(False)

        def success(result: object) -> None:
            on_success(result)
            if refresh:
                self._state_cache.invalidate("gpu", "performance", "tools")
                self.refresh()
            if keep_voltage_lab:
                self.page_stack.setCurrentWidget(self.voltage_lab_page)

        def failure(message: str) -> None:
            self._show_info(error_title, message, tone="red")
            self._append_console(f"{error_title}: {message}")

        def finished() -> None:
            self._action_busy = False
            for control in controls:
                control.setEnabled(True)

        started = self._background.start("gpu-hardware-action", operation, success, failure, finished)
        if not started:
            self._action_busy = False
            for control in controls:
                control.setEnabled(True)
            self._show_info("GPU operation in progress", "Wait for the current GPU operation to finish.", tone="orange")
        return started

    def _request_custom_range(self) -> None:
        minimum = self.minimum_control.value()
        maximum = self.maximum_control.value()
        valid, warning = self._validate_range(minimum, maximum)
        if not valid:
            return
        risk = maximum >= 1850 or minimum >= 2000
        message = tr("This updates the active governor range through D-Bus. The TOML safe-point configuration is not rewritten.")
        if warning:
            message += "\n\n" + tr_format("Safety note: {warning}", warning=warning)
        dialog = ConfirmDialog(
            "Apply GPU runtime range",
            message,
            summary=(
                ("Minimum", f"{minimum} MHz"),
                ("Maximum", f"{maximum} MHz"),
                ("Safe-point voltage", self._safe_point_voltage_text(maximum)),
                ("Persistence", "Runtime range; governor service persistence is unchanged"),
            ),
            confirm_text="Apply range",
            tone="orange" if risk else "blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        def success(_result: object) -> None:
            self._last_operation_summary = f"Requested runtime range {minimum}–{maximum} MHz through D-Bus."
            self.last_operation_line.set_values("Apply range", self._last_operation_summary)
            self._append_console(self._last_operation_summary)

        self._run_backend_action(
            lambda: self.controller.aplicar_rango_bc250(minimum, maximum),
            success,
            "GPU range failed",
            controls=(self.apply_range_button,),
        )

    def _request_fixed(self) -> None:
        frequency = _integer(self.oc_frequency.currentData(), 0)
        if frequency <= 0:
            self._show_info("No safe-point selected", "Refresh after installing or configuring the governor.", tone="orange")
            return
        valid, warning = self._validate_range(frequency, frequency)
        if not valid:
            return
        message = tr(
            "The governor will hold one configured safe-point. Apply a dynamic runtime range later to return to normal scaling."
        )
        if warning:
            message += "\n\n" + tr_format("Safety note: {warning}", warning=warning)
        dialog = ConfirmDialog(
            "Apply fixed GPU safe-point",
            message,
            summary=(
                ("Frequency", f"{frequency} MHz"),
                ("Voltage from TOML", self._safe_point_voltage_text(frequency)),
                ("Known stable floor", self._known_floor_text(frequency)),
                ("Persistence", "Runtime only"),
            ),
            confirm_text="Apply fixed safe-point",
            tone="orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        def success(_result: object) -> None:
            self._last_operation_summary = f"Requested fixed GPU safe-point at {frequency} MHz."
            self.last_operation_line.set_values("Fixed safe-point", self._last_operation_summary)
            self._append_console(self._last_operation_summary)

        self._run_backend_action(
            lambda: self.controller.fijar_frecuencia_bc250(frequency),
            success,
            "Fixed frequency failed",
            controls=(self.fixed_button,),
        )

    def _validate_range(self, minimum: int, maximum: int) -> tuple[bool, str]:
        if minimum <= 0 or maximum <= 0:
            self._show_info("Invalid range", "Enter both minimum and maximum frequencies.", tone="orange")
            return False, ""
        if minimum > maximum:
            self._show_info("Invalid range", "Minimum frequency cannot be greater than maximum frequency.", tone="orange")
            return False, ""
        if minimum < self.allowed_min or maximum > self.allowed_max:
            self._show_info(
                "Range outside allowed limits",
                tr_format(
                    "Requested {minimum}–{maximum} MHz, while D-Bus currently allows {allowed_min}–{allowed_max} MHz.",
                    minimum=minimum, maximum=maximum, allowed_min=self.allowed_min, allowed_max=self.allowed_max,
                ),
                tone="orange",
            )
            return False, ""

        voltage_errors = list(self.current_state.get("safe_points_voltage_errors") or [])
        if voltage_errors:
            details = "; ".join(
                f"{item.get('previous_frequency')} MHz/{item.get('previous_voltage')} mV > "
                f"{item.get('frequency')} MHz/{item.get('voltage')} mV"
                for item in voltage_errors
            )
            self._show_info(
                "Governor TOML curve rejected",
                tr("The voltage curve decreases while frequency rises. No profile will be applied until the TOML is corrected and the governor is restarted.")
                + "\n\n" + details,
                tone="red",
            )
            return False, ""

        if not self.safe_frequencies:
            self._show_info(
                "No active safe-point table",
                "The governor did not expose any TOML safe-point with frequency and voltage. Read the service status and correct the configuration before applying a range.",
                tone="orange",
            )
            return False, ""
        if maximum not in self.safe_frequencies:
            self._show_info(
                "Maximum is not a valid safe-point",
                tr_format(
                    "{maximum} MHz has no active safe-point with voltage in the governor TOML.",
                    maximum=maximum,
                ),
                tone="orange",
            )
            return False, ""

        voltage = self.safe_voltage_map.get(int(maximum))
        known_floor = self.KNOWN_STABLE_VOLTAGES.get(int(maximum))
        experimental = self.experimental_toggle.isChecked()
        warning_parts: list[str] = []
        if maximum > 1500 and (known_floor is None or voltage is None or voltage < known_floor):
            if maximum > 2000 and not experimental:
                self._show_info(
                    "High OC point blocked",
                    tr_format(
                        "{maximum} MHz uses {voltage} mV, while the conservative known-stable floor is {known_floor} mV. Enable high OC laboratory mode only for controlled testing.",
                        maximum=maximum, voltage=voltage or "--", known_floor=known_floor or "--",
                    ),
                    tone="orange",
                )
                return False, ""
            warning_parts.append(
                tr_format(
                    "{maximum} MHz is configured at {voltage} mV; the conservative known-stable floor is {known_floor} mV. This is an undervolt laboratory condition.",
                    maximum=maximum, voltage=voltage or "--", known_floor=known_floor or "--",
                )
            )

        actual_max = _integer(self.current_state.get("current_max"), self.active_max)
        sclk = _integer(self.current_state.get("sclk_actual"), 0)
        busy_raw = self.current_state.get("gpu_busy")
        busy = None if busy_raw is None else _integer(busy_raw, 0)
        drop = actual_max - maximum if actual_max else 0
        high_load = busy is not None and busy >= 35
        abrupt = drop >= 500 or (sclk >= 1800 and maximum <= 1500)
        if drop > 0 and abrupt and high_load:
            self._show_info(
                "Abrupt frequency drop blocked",
                tr_format(
                    "GPU load is {busy}% and the active ceiling is {actual_max} MHz. Stop the game or stress test first, then step down gradually: 2400 → 2200 → 2000 → 1850 → 1500 → 1000 MHz.",
                    busy=busy, actual_max=actual_max,
                ),
                tone="orange",
            )
            return False, ""
        if drop >= 700:
            warning_parts.append(
                tr_format(
                    "This is a {drop} MHz ceiling reduction. Stop all 3D load and lower the range in steps if the display has frozen during previous tests.",
                    drop=drop,
                )
            )
        if maximum >= 1850:
            warning_parts.append(tr("Do not change frequency while a game, FurMark, or another 3D workload is active."))
        return True, " ".join(warning_parts)

    def prepare_dependencies(self) -> None:
        dialog = ConfirmDialog(
            "Prepare BC250 dependencies",
            "This opens the existing distribution-aware R64 workflow. It can install or update the governor, bc250_smu_oc, UMR, and the compute-unit live manager in a visible terminal.",
            summary=(
                ("Scope", "Shared BC250 tools"),
                ("Distribution", "Detected automatically"),
                ("Hardware changes", "No frequency or voltage is applied"),
                ("Authentication", "Administrator prompt may appear"),
            ),
            confirm_text="Prepare dependencies",
            tone="blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # Executed by BackgroundExecutor, equivalent to calling
        # self.controller.instalar_dependencias_bc250() outside the UI thread.
        def success(_result: object) -> None:
            self._last_operation_summary = "Opened the shared BC250 dependency preparation workflow."
            self.last_operation_line.set_values("Prepare dependencies", self._last_operation_summary)
            self._append_console(self._last_operation_summary)

        self._run_backend_action(
            self.controller.instalar_dependencias_bc250,
            success,
            "Could not prepare dependencies",
            controls=(self.dependencies_metric.button,),
        )

    def _service_action(self, action: str) -> None:
        labels = {
            "activar": "Enable and start",
            "reiniciar": "Restart",
            "desactivar": "Stop and disable",
        }
        descriptions = {
            "activar": "This starts the governor now and enables it at boot, restoring the persistence control from the original GUI.",
            "reiniciar": "This restarts the active governor service without changing its boot-enabled state.",
            "desactivar": "This stops the governor now and disables it at boot. GPU range controls will be unavailable until it is enabled again.",
        }
        action_label = labels.get(action, action)
        dialog = ConfirmDialog(
            tr_format("{action} GPU governor", action=tr(action_label)),
            tr(descriptions.get(action, "The existing R64 workflow opens a visible terminal for sudo authentication and service output.")),
            summary=(
                ("Service", "cyan-skillfish-governor-smu.service"),
                ("Action", tr(action_label)),
                ("Boot persistence", "Enabled" if action == "activar" else "Disabled" if action == "desactivar" else "Unchanged"),
            ),
            confirm_text=tr(action_label if action_label else "Continue"),
            tone="orange" if action == "desactivar" else "blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        def success(_result: object) -> None:
            self._last_operation_summary = f"Opened service workflow: {labels.get(action, action)}."
            self.last_operation_line.set_values("Service action", self._last_operation_summary)
            self._append_console(self._last_operation_summary)

        self._run_backend_action(
            lambda: self.controller.controlar_governor(action),
            success,
            "Governor service action failed",
        )

    def read_service_status(self) -> None:
        self._toggle_advanced(show=True)
        def success(result: object) -> None:
            text = str(result or "No status output")
            self._last_operation_summary = "Read systemctl status without changing the governor."
            self.last_operation_line.set_values("Read status", self._last_operation_summary)
            self._append_console(f"systemctl status\n{text}")

        self._run_backend_action(
            self.controller.status_governor,
            success,
            "Could not read governor status",
            refresh=False,
        )

    def open_voltage_lab(self) -> None:
        self._sync_voltage_lab(self.current_state)
        self.page_stack.setCurrentWidget(self.voltage_lab_page)

    def _close_voltage_lab(self) -> None:
        self.page_stack.setCurrentWidget(self.overview_page)

    def _refresh_voltage_lab(self) -> None:
        self.refresh()
        self.page_stack.setCurrentWidget(self.voltage_lab_page)

    def _voltage_for_level(self, frequency: int, level: int) -> int | None:
        frequency = int(frequency)
        base = self.VOLTAGE_LAB_BASE.get(frequency)
        ceiling = self.KNOWN_STABLE_VOLTAGES.get(frequency)
        if base is None or ceiling is None:
            return None
        return min(base + max(0, int(level)) * 10, ceiling)

    def _detect_voltage_level(self, voltage_map: dict[int, int]) -> int:
        best_level = 0
        best_error: int | None = None
        for level in self.VOLTAGE_PROFILE_LEVELS:
            error = 0
            samples = 0
            for frequency in self.VOLTAGE_LAB_FREQUENCIES:
                actual = voltage_map.get(frequency)
                expected = self._voltage_for_level(frequency, level)
                if actual is None or expected is None:
                    continue
                error += abs(int(actual) - int(expected))
                samples += 1
            if samples and (best_error is None or error < best_error):
                best_level = level
                best_error = error
        return best_level

    def _voltage_keypad_edit_active(self) -> bool:
        spinboxes = set(getattr(self, "_voltage_spinboxes", {}).values())
        if not spinboxes:
            return False
        for spin in tuple(spinboxes):
            try:
                if spin.property("gamepadKeypadKeyboardTracking") is None:
                    continue
                if spin.hasFocus() or spin.lineEdit().hasFocus():
                    return True
            except RuntimeError:
                continue
        app = QApplication.instance()
        if app is None:
            return False
        try:
            tops = tuple(app.topLevelWidgets())
        except RuntimeError:
            return False
        for top in tops:
            try:
                candidates = (top, *top.findChildren(QWidget))
            except RuntimeError:
                continue
            for widget in candidates:
                try:
                    if not bool(widget.property("gamepadKeypad")) or not widget.isVisible():
                        continue
                    target = getattr(widget, "_target", None)
                    if target in spinboxes:
                        return True
                except RuntimeError:
                    continue
        return False

    def _sync_voltage_lab(self, gpu: dict) -> None:
        if not hasattr(self, "voltage_curve_grid"):
            return
        if self._voltage_keypad_edit_active():
            return
        points = list(gpu.get("safe_points_with_voltage") or gpu.get("safe_points") or [])
        cleaned: dict[int, int] = {}
        for point in points:
            if not isinstance(point, dict):
                continue
            frequency = _integer(point.get("frequency"), 0)
            voltage = _integer(point.get("voltage"), 0)
            if frequency > 0:
                cleaned[frequency] = voltage
        self._voltage_points = sorted(cleaned.items())
        self._voltage_current_map = {frequency: voltage for frequency, voltage in self._voltage_points if voltage > 0}
        self._voltage_editable_frequencies = {frequency for frequency, _voltage in self._voltage_points}
        self._voltage_profile_frequencies = {
            frequency for frequency, _voltage in self._voltage_points if frequency in self.VOLTAGE_LAB_FREQUENCIES
        }
        self._voltage_detected_level = self._detect_voltage_level(self._voltage_current_map)

        if not getattr(self, "_voltage_lab_initialized", False):
            index = self.voltage_level_combo.findData(self._voltage_detected_level)
            if index >= 0:
                self.voltage_level_combo.blockSignals(True)
                self.voltage_level_combo.setCurrentIndex(index)
                self.voltage_level_combo.blockSignals(False)
            self._voltage_lab_initialized = True

        for frequency in self._voltage_editable_frequencies:
            if frequency not in self._voltage_custom_values:
                current = self._voltage_current_map.get(frequency)
                fallback = self._voltage_for_level(frequency, self._voltage_detected_level)
                self._voltage_custom_values[frequency] = int(current or fallback or 900)

        active_min = _integer(gpu.get("current_min"), self.active_min)
        active_max = _integer(gpu.get("current_max"), self.active_max)
        max_voltage = max(self._voltage_current_map.values(), default=0)
        self.voltage_summary_items[0].set_values(str(len(self._voltage_points)), tr("active TOML entries"))
        self.voltage_summary_items[1].set_values(
            tr_format("Level {level}", level=self._voltage_detected_level), tr("closest validated curve")
        )
        self.voltage_summary_items[2].set_values(
            f"{max_voltage} mV" if max_voltage else tr("Not detected"), tr("hard UI ceiling 1150 mV")
        )
        self.voltage_summary_items[3].set_values(
            f"{active_min}–{active_max} MHz" if active_min or active_max else tr("Not available"),
            tr("restored after governor restart"),
        )
        curve_errors = list(gpu.get("safe_points_voltage_errors") or [])
        safety_valid = bool(self._voltage_points) and not curve_errors
        self.voltage_summary_items[4].set_values(
            tr("Valid" if safety_valid else "Review"),
            tr("monotonic curve") if safety_valid else (tr_format("{count} curve errors", count=len(curve_errors)) if curve_errors else tr("no safe-points detected")),
        )

        if self.voltage_table_status is not None:
            self.voltage_table_status.setText(count_label(len(self._voltage_points), "point"))
            self.voltage_table_status.set_tone("green" if self._voltage_points else "orange")
        if self.voltage_controls_status is not None:
            self.voltage_controls_status.setText(tr("Ready"))
            self.voltage_controls_status.set_tone("orange")
        if getattr(self, "voltage_workflow_status", None) is not None:
            self.voltage_workflow_status.setText(tr("Armed" if self._voltage_editable_frequencies else "Locked"))
            self.voltage_workflow_status.set_tone("orange" if self._voltage_editable_frequencies else "gray")
        # Curve validity remains visible in the summary strip and is rechecked before every apply.
        self._populate_voltage_table()

    def _clear_stale_voltage_keypad_state(self) -> None:
        for spin in getattr(self, "_voltage_spinboxes", {}).values():
            try:
                stored = spin.property("gamepadKeypadKeyboardTracking")
                if stored is not None:
                    spin.setKeyboardTracking(bool(stored))
                    spin.setProperty("gamepadKeypadKeyboardTracking", None)
                spin.setProperty("gamepadKeypadDismissed", False)
            except RuntimeError:
                continue

    def _select_voltage_profile(self, level: int) -> None:
        self._clear_stale_voltage_keypad_state()
        index = self.voltage_level_combo.findData(int(level))
        if index >= 0:
            self.voltage_level_combo.setCurrentIndex(index)
            self._populate_voltage_table()

    def _sync_voltage_profile_buttons(self, level: int) -> None:
        for button in getattr(self, "voltage_profile_buttons", []):
            button.setChecked(button.level == int(level))

    def _voltage_level_changed(self, _index: int = 0) -> None:
        self._sync_voltage_profile_buttons(_integer(self.voltage_level_combo.currentData(), 0))
        self._populate_voltage_table()

    def _populate_voltage_table(self) -> None:
        if not hasattr(self, "voltage_curve_grid"):
            return
        if self._voltage_keypad_edit_active():
            return
        points = list(getattr(self, "_voltage_points", []))
        selected_level = _integer(self.voltage_level_combo.currentData(), 0)
        custom_mode = selected_level == -1
        self._sync_voltage_profile_buttons(selected_level)
        active_frequencies = self._voltage_editable_frequencies if custom_mode else self._voltage_profile_frequencies
        self.voltage_apply_button.setEnabled(bool(active_frequencies))
        self.voltage_curve_grid.clear_points()
        self._voltage_spinboxes = {}

        for row, (frequency, current) in enumerate(points):
            frequency = int(frequency)
            current = int(current or 0)
            custom_available = frequency in self._voltage_editable_frequencies
            profile_editable = frequency in self._voltage_profile_frequencies
            proposed_editable = custom_available if custom_mode else profile_editable
            floor = self.KNOWN_STABLE_VOLTAGES.get(frequency)
            base = self.VOLTAGE_LAB_BASE.get(frequency)
            if custom_mode and custom_available:
                proposed = int(self._voltage_custom_values.get(frequency, current or 900))
            elif profile_editable:
                proposed = self._voltage_for_level(frequency, selected_level)
            else:
                proposed = current or None
            margin = None if proposed is None or floor is None else int(proposed) - int(floor)
            added = None if proposed is None or base is None else int(proposed) - int(base)

            spin = None
            if custom_available:
                spin = QSpinBox()
                spin.setRange(600, 1150)
                spin.setSingleStep(5)
                spin.setSuffix(" mV")
                spin.setValue(int(self._voltage_custom_values.get(frequency, current or proposed or 900)))
                spin.setEnabled(custom_mode)
                spin.valueChanged.connect(lambda value, freq=frequency: self._voltage_custom_changed(freq, value))
                self._voltage_spinboxes[frequency] = spin

            self.voltage_curve_grid.add_point(
                row,
                frequency=frequency,
                current=current,
                proposed=proposed,
                added=added,
                margin=margin,
                editor=spin,
                editable=proposed_editable,
                custom_available=custom_available,
            )

        if not points:
            self.voltage_level_detail.setText(
                tr("No active voltage safe-points were found. Verify the governor TOML and refresh.")
            )
        elif custom_mode:
            self.voltage_level_detail.setText(
                tr_format("Custom mode: all {count} active safe-points are unlocked, including low-frequency entries such as 500 MHz when present.", count=len(self._voltage_editable_frequencies))
            )
        else:
            self.voltage_level_detail.setText(
                tr_format("Level {level}: default +{added} mV on {count} validated laboratory points, capped at known-stable values. Detected curve: Level {detected}.", level=selected_level, added=selected_level * 10, count=len(self._voltage_profile_frequencies), detected=self._voltage_detected_level)
            )

    def _voltage_custom_changed(self, frequency: int, value: int) -> None:
        frequency = int(frequency)
        value = int(value)
        self._voltage_custom_values[frequency] = value
        floor = self.KNOWN_STABLE_VOLTAGES.get(frequency)
        base = self.VOLTAGE_LAB_BASE.get(frequency)
        margin = None if floor is None else value - int(floor)
        added = None if base is None else value - int(base)
        self.voltage_curve_grid.update_point(frequency, value, added, margin)

    def _request_apply_voltage_curve(self) -> None:
        level = _integer(self.voltage_level_combo.currentData(), 0)
        custom_mode = level == -1
        active_frequencies = self._voltage_editable_frequencies if custom_mode else self._voltage_profile_frequencies
        if not active_frequencies:
            self._show_info(
                "No editable voltage points",
                "The active TOML does not contain voltage safe-points supported by the selected profile.",
                tone="orange",
            )
            return

        if custom_mode:
            values = {
                frequency: int(self._voltage_spinboxes[frequency].value())
                for frequency in sorted(active_frequencies)
                if frequency in self._voltage_spinboxes
            }
            proposed_values = dict(values)
            title = "Apply custom GPU voltage curve"
            description = (
                "Only the editable frequencies shown in the table will be changed. A timestamped TOML backup is created, "
                "the governor restarts, and the previous D-Bus range is restored."
            )
            profile_label = "Custom"
            maximum_voltage = max(values.values(), default=0)
        else:
            values = None
            proposed_values = {
                frequency: int(self._voltage_for_level(frequency, level) or self._voltage_current_map.get(frequency) or 0)
                for frequency in sorted(active_frequencies)
            }
            title = tr_format("Apply GPU voltage Level {level}", level=level)
            description = tr_format(
                "This applies governor defaults +{added} mV to supported safe-points, capped at the known stable ceiling. A backup is created before the governor restarts.",
                added=level * 10,
            )
            profile_label = tr_format("Level {level}", level=level)
            maximum_voltage = max(
                (self._voltage_for_level(frequency, level) or 0 for frequency in active_frequencies),
                default=0,
            )

        proposed_map = dict(self._voltage_current_map)
        proposed_map.update({frequency: voltage for frequency, voltage in proposed_values.items() if voltage > 0})
        previous_frequency = None
        previous_voltage = None
        for frequency in sorted(proposed_map):
            voltage = int(proposed_map[frequency])
            if previous_voltage is not None and voltage < previous_voltage:
                self._show_info(
                    "Invalid voltage curve",
                    tr_format(
                        "{frequency} MHz uses {voltage} mV, below {previous_frequency} MHz at {previous_voltage} mV. Voltage cannot decrease while frequency increases.",
                        frequency=frequency, voltage=voltage, previous_frequency=previous_frequency, previous_voltage=previous_voltage,
                    ),
                    tone="red",
                )
                return
            previous_frequency = frequency
            previous_voltage = voltage

        dialog = ConfirmDialog(
            title,
            f"{tr(description)} {tr('Stop every game, benchmark, and 3D workload before continuing.')}",
            summary=(
                ("Profile", profile_label),
                ("Editable points", str(len(active_frequencies))),
                ("Maximum proposed", f"{maximum_voltage} mV"),
                ("D-Bus range", "Preserved and restored after restart"),
            ),
            confirm_text="Apply voltage curve",
            tone="orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def operation() -> object:
            if custom_mode:
                return self.controller.aplicar_laboratorio_voltaje_gpu_personalizado(values)
            return self.controller.aplicar_laboratorio_voltaje_gpu(level)

        def success(output: object) -> None:
            self._last_operation_summary = f"Applied GPU voltage {profile_label} from the integrated Voltage Curve Studio."
            self.last_operation_line.set_values("Voltage curve", self._last_operation_summary)
            self._append_console(self._last_operation_summary)
            if output:
                self._append_console(str(output))
            self._show_info(
                "Voltage curve applied",
                "The governor restarted successfully and the previous runtime range was requested again.",
                tone="blue",
            )

        self._run_backend_action(
            operation,
            success,
            "Voltage curve failed",
            controls=(self.voltage_apply_button,),
            keep_voltage_lab=True,
        )

    def _toggle_advanced(self, _checked: bool = False, *, show: bool | None = None) -> None:
        visible = not self.advanced_card.isVisible() if show is None else bool(show)
        self.advanced_card.setVisible(visible)
        self.advanced_toggle.setText(tr("Hide diagnostics" if visible else "Advanced diagnostics"))
        if self.advanced_status is not None:
            self.advanced_status.setText(tr("Visible" if visible else "Hidden"))
            self.advanced_status.set_tone("orange" if visible else "gray")

    def _manual_refresh(self) -> None:
        self._state_cache.invalidate("gpu", "performance")
        self.refresh()

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if self._updates_active:
            if not self.timer.isActive():
                self.timer.start()
            self._refresher.activate(fresh_for=1.5)
        else:
            self._refresher.set_active(False)
            self.timer.stop()

    def _fetch_refresh_payload(self) -> dict[str, dict]:
        # state_cache.gpu() delegates to controller.estado_bc250() in a worker;
        # the UI refresh slot only schedules/coalesces the request.
        return {
            "gpu": self._state_cache.gpu(),
            "performance": self._state_cache.performance(),
        }

    def refresh(self) -> None:
        if self._action_busy:
            return
        self._refresher.request()

    def _refresh_failed(self, message: str) -> None:
        self._append_console(f"GPU refresh warning: {message}")

    def _apply_refresh_payload(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        gpu = _dict(data.get("gpu"))
        perf = _dict(data.get("performance"))
        self.current_state = gpu
        self.current_perf = perf
        self._apply_state(gpu, perf)

    def _apply_state(self, gpu: dict, perf: dict) -> None:
        frequency = _integer(gpu.get("sclk_actual"), 0)
        mclk = _integer(gpu.get("mclk_actual"), 0)
        minimum = _integer(gpu.get("current_min"), 0)
        maximum = _integer(gpu.get("current_max"), 0)
        allowed_min = _integer(gpu.get("allowed_min"), 300)
        allowed_max = _integer(gpu.get("allowed_max"), gpu.get("config_max_frequency") or maximum or 2000)
        self.allowed_min = max(0, allowed_min)
        self.allowed_max = max(self.allowed_min, allowed_max)
        self.active_min = minimum or self.active_min
        self.active_max = maximum or self.active_max
        self.minimum_control.set_limits(self.allowed_min, self.allowed_max)
        self.maximum_control.set_limits(self.allowed_min, self.allowed_max)

        temperature = _number(perf.get("gpu_temp"), 0)
        raw_utilization = gpu.get("gpu_busy")
        if raw_utilization is None:
            raw_utilization = perf.get("gpu_busy")
        utilization = None if raw_utilization is None else _integer(raw_utilization, 0)
        voltage = _integer(gpu.get("voltaje_actual"), 0)
        points = list(gpu.get("safe_points_with_voltage") or gpu.get("safe_points") or [])
        self._populate_points(points, frequency)
        if not self._controls_initialized:
            self._stage_range(self.active_min, self.active_max, preset=self._profile_name(self.active_min, self.active_max))
            self._controls_initialized = True

        active = str(gpu.get("service_active") or "not-found")
        enabled = str(gpu.get("service_enabled") or "not-found")
        dbus_ok = bool(gpu.get("dbus_ok"))
        running = active.lower() in {"active", "running"}
        enabled_at_boot = enabled.lower() in {"enabled", "enabled-runtime", "static"}
        profile_name = self._profile_name(minimum, maximum)

        frequency_text = f"{frequency} MHz" if frequency else tr("Not detected")
        range_text = f"{minimum}–{maximum} MHz" if minimum or maximum else tr("Not available")
        voltage_text = f"{voltage} mV" if voltage else tr("Not exposed")
        temperature_text = f"{temperature:.1f} °C" if temperature else tr("Not detected")
        utilization_text = tr("Not detected") if utilization is None else f"{utilization} %"
        vram_total = _number(gpu.get("vram_total"), 0)
        vram_used = _number(gpu.get("vram_usado"), 0)
        vram_percent = (vram_used / vram_total * 100.0) if vram_total else 0.0
        vram_value = f"{vram_percent:.0f} %" if vram_total else tr("Not detected")
        vram_detail = (
            tr_format("{used} of {total}", used=_format_bytes(vram_used), total=_format_bytes(vram_total)) if vram_total else tr("VRAM counters unavailable")
        )
        power = _number(perf.get("power_w"), 0)
        power_label = str(perf.get("power_label") or "Power sensor unavailable")
        power_detail = (
            "Dedicated total-board power sensor"
            if bool(perf.get("power_is_total"))
            else "AMDGPU SoC power sensor; total board power unavailable"
            if str(perf.get("power_scope") or "") == "gpu_soc"
            else "No live power sensor exposed"
        )
        power_text = f"{power:.0f} W" if power else tr("Not detected")
        power_state = str(gpu.get("power_state") or "--")
        power_level = str(gpu.get("power_level") or "--")
        dpm_text = power_state if power_state != "--" else power_level

        self.summary.items[0].set_values(tr("Active") if running else tr(active.capitalize()), tr_format("boot: {state}", state=tr(enabled.capitalize())))
        self.summary.items[1].set_values(frequency_text, tr("real-time SCLK"))
        self.summary.items[2].set_values(range_text, tr_format("allowed {minimum}–{maximum}", minimum=self.allowed_min, maximum=self.allowed_max))
        self.summary.items[3].set_values(utilization_text, tr("current GPU load"))
        self.summary.items[4].set_values(temperature_text, self._temperature_status(temperature))

        self.sclk_metric.set_values(frequency_text, tr("Current SCLK state"))
        self.voltage_metric.set_values(voltage_text, tr("OD / SMU telemetry"))
        self.temperature_metric.set_values(temperature_text, self._temperature_status(temperature))
        self.utilization_metric.set_values(utilization_text, tr("amdgpu busy percentage"))
        self.mclk_metric.set_values(f"{mclk} MHz" if mclk else tr("Not detected"), tr("Current MCLK state"))
        self.vram_metric.set_values(vram_value, vram_detail)
        self.power_metric.set_label(power_label)
        self.power_metric.set_values(power_text, tr(power_detail))
        if self.metrics_status is not None:
            self.metrics_status.setText(tr("Live"))
            self.metrics_status.set_tone("green")

        self.service_stat.set_values(tr("Running") if running else tr(active.capitalize()), str(gpu.get("service_sub") or tr("systemd state")))
        self.boot_stat.set_values(tr("Enabled") if enabled_at_boot else tr(enabled.capitalize()), tr("persistent at boot" if enabled_at_boot else "not persistent"))
        self.dbus_stat.set_values(tr("Connected" if dbus_ok else "Unavailable"), tr("runtime range API"))
        self.profile_stat.set_values(range_text, profile_name)
        self.points_stat.set_values(str(len(self.safe_frequencies)), tr("active TOML entries with frequency"))
        self.updated_stat.set_values(datetime.now().strftime("%H:%M:%S"), tr("passive refresh"))
        if self.runtime_card.status is not None:
            self.runtime_card.status.setText(tr("Running") if running else tr(active.capitalize()))
            self.runtime_card.status.set_tone("green" if running and dbus_ok else "orange")

        self.enable_button.setEnabled(not (running and enabled_at_boot))
        self.disable_button.setEnabled(running or enabled_at_boot)
        self.restart_button.setEnabled(running)
        self.apply_range_button.setEnabled(dbus_ok)
        self.fixed_button.setEnabled(dbus_ok and self.oc_frequency.count() > 0)

        self.range_recommendation.setText(
            tr_format("D-Bus allowed range: {allowed_min}–{allowed_max} MHz · active profile: {minimum}–{maximum} MHz · TOML maximum: {toml_max} MHz.", allowed_min=self.allowed_min, allowed_max=self.allowed_max, minimum=minimum, maximum=maximum, toml_max=_integer(gpu.get("config_max_frequency"), 0) or "--")
        )
        self._update_profile_availability()
        self._update_safety_notice(gpu)
        self._update_diagnostics(gpu)
        self._sync_voltage_lab(gpu)

    def _populate_points(self, points: list, current: int) -> None:
        cleaned: list[tuple[int, int]] = []
        for point in points:
            if not isinstance(point, dict):
                continue
            frequency = _integer(point.get("frequency"), 0)
            voltage = _integer(point.get("voltage"), 0)
            if frequency:
                cleaned.append((frequency, voltage))
        cleaned = sorted(set(cleaned), key=lambda item: item[0])
        self.safe_frequencies = [frequency for frequency, _voltage in cleaned]
        self.safe_voltage_map = {frequency: voltage for frequency, voltage in cleaned if voltage > 0}

        self.points_table.setRowCount(len(cleaned))
        previous = self.oc_frequency.currentData()
        self.oc_frequency.blockSignals(True)
        self.oc_frequency.clear()
        experimental = self.experimental_toggle.isChecked()
        selectable: list[int] = []
        for row, (frequency, voltage) in enumerate(cleaned):
            floor = self.KNOWN_STABLE_VOLTAGES.get(frequency)
            stable = floor is None or voltage >= floor
            if frequency == current:
                role = "Current SCLK"
            elif frequency == self.active_max:
                role = "Active ceiling"
            elif frequency > 2000 and not stable:
                role = "High OC / undervolt lab"
            elif frequency > 2000:
                role = "High OC safe-point"
            elif frequency >= 1850 and not stable:
                role = "Undervolt warning"
            elif frequency >= 1850:
                role = "OC safe-point"
            else:
                role = "Safe-point"
            self.points_table.setItem(row, 0, QTableWidgetItem(f"{frequency} MHz"))
            self.points_table.setItem(row, 1, QTableWidgetItem(f"{voltage} mV" if voltage else "Not specified"))
            self.points_table.setItem(row, 2, QTableWidgetItem(f"{floor} mV" if floor else "n/a"))
            self.points_table.setItem(row, 3, QTableWidgetItem(role))

            if frequency <= 2000 or experimental:
                selectable.append(frequency)
        if not selectable:
            selectable = list(self.safe_frequencies)
        for frequency in selectable:
            voltage = self.safe_voltage_map.get(frequency)
            self.oc_frequency.addItem(
                f"{frequency} MHz · {voltage} mV" if voltage else f"{frequency} MHz",
                frequency,
            )
        desired = previous if previous in selectable else current if current in selectable else (selectable[0] if selectable else None)
        if desired is not None:
            index = self.oc_frequency.findData(desired)
            if index >= 0:
                self.oc_frequency.setCurrentIndex(index)
        self.oc_frequency.blockSignals(False)
        self._update_selected_safe_point()

    def _update_selected_safe_point(self, _index: int = 0) -> None:
        frequency = _integer(self.oc_frequency.currentData(), 0)
        if frequency <= 0:
            self.safe_point_detail.setText(tr("No selectable safe-point is available."))
            if hasattr(self, "fixed_button"):
                self.fixed_button.setEnabled(False)
            return
        voltage = self.safe_voltage_map.get(frequency)
        floor = self.KNOWN_STABLE_VOLTAGES.get(frequency)
        if floor is None:
            status = tr("No conservative reference floor is defined.")
        elif voltage is None:
            status = tr_format("Voltage missing; known floor {floor} mV.", floor=floor)
        elif voltage >= floor:
            status = tr_format("TOML {voltage} mV · known floor {floor} mV · conservative check passed.", voltage=voltage, floor=floor)
        else:
            status = tr_format("TOML {voltage} mV · known floor {floor} mV · undervolt laboratory condition.", voltage=voltage, floor=floor)
        self.safe_point_detail.setText(status)
        if hasattr(self, "fixed_button"):
            self.fixed_button.setEnabled(bool(self.current_state.get("dbus_ok", True)))

    def _update_profile_availability(self) -> None:
        safe = set(self.safe_frequencies)
        for button in self.preset_buttons:
            preset_minimum, preset_maximum = button.payload
            available = (
                self.allowed_min <= preset_minimum <= self.allowed_max
                and self.allowed_min <= preset_maximum <= self.allowed_max
                and (not safe or preset_maximum in safe)
            )
            button.setEnabled(available)
            button.setToolTip(
                "" if available else tr("This profile ceiling is not available in the active governor safe-point table or D-Bus range.")
            )
        for button in self.floor_buttons:
            floor = _integer(button.property("floor"), 0)
            button.setEnabled(self.allowed_min <= floor <= self.allowed_max)

    def _update_safety_notice(self, gpu: dict) -> None:
        errors = list(gpu.get("safe_points_voltage_errors") or [])
        missing = list(gpu.get("safe_points_missing_voltage") or [])
        duplicates = list(gpu.get("safe_points_duplicate_frequencies") or [])
        dbus_ok = bool(gpu.get("dbus_ok"))
        experimental = self.experimental_toggle.isChecked()

        if errors:
            self.safety_notice.set_notice(
                "Governor blocked by invalid voltage curve",
                "A later safe-point has lower voltage than an earlier frequency. Correct or comment the invalid TOML entry, then restart cyan-skillfish-governor-smu.service.",
                tone="orange",
            )
            if self.configuration_status is not None:
                self.configuration_status.setText(tr("Blocked"))
                self.configuration_status.set_tone("orange")
        elif not dbus_ok:
            detail = ""
            if missing:
                detail = " " + tr_format(
                    "Missing voltage entries: {values}.",
                    values=", ".join(str(item.get("frequency") or item) for item in missing),
                )
            self.safety_notice.set_notice(
                "Governor D-Bus unavailable",
                tr("The page can still show passive telemetry, but runtime ranges cannot be applied. Read the service status and inspect the TOML before continuing. The governor service may be disabled; enable it with the Enable service button.") + detail,
                tone="orange",
            )
            if self.configuration_status is not None:
                self.configuration_status.setText(tr("Offline"))
                self.configuration_status.set_tone("orange")
        elif experimental:
            extra = ""
            if duplicates:
                extra = " " + tr("Duplicate frequencies were also detected in the TOML.")
            self.safety_notice.set_notice(
                "High OC laboratory mode",
                tr("Safe-points above 2000 MHz are visible. Voltage is validated against the conservative reference curve, but laboratory mode can still expose undervolted points. Stop all 3D load before every change.") + extra,
                tone="orange",
            )
            if self.configuration_status is not None:
                self.configuration_status.setText(tr("Lab mode"))
                self.configuration_status.set_tone("orange")
        else:
            self.safety_notice.set_notice(
                "Safe mode enabled",
                "Only active TOML safe-points up to 2000 MHz are exposed. High OC points remain hidden, and abrupt frequency drops under GPU load are blocked.",
                tone="blue",
            )
            if self.configuration_status is not None:
                self.configuration_status.setText(tr("Safe mode"))
                self.configuration_status.set_tone("green")

    @staticmethod
    def _compact_path(value: str) -> str:
        text = str(value or "--")
        if text in {"", "--"}:
            return "--"
        return f"…/{text.rsplit('/', 1)[-1]}"

    def set_detailed_diagnostics(self, enabled: bool) -> None:
        self._detailed_diagnostics = bool(enabled)
        if self.current_state:
            self._update_diagnostics(self.current_state)

    def _update_diagnostics(self, gpu: dict) -> None:
        vendor = str(gpu.get("vendor") or "--")
        device = str(gpu.get("device") or "--")
        path = str(gpu.get("gpu_path") or "--")
        config = str(gpu.get("config_path") or "--")
        if not self._detailed_diagnostics:
            path = self._compact_path(path)
            config = self._compact_path(config)
        errors = list(gpu.get("safe_points_voltage_errors") or [])
        missing = list(gpu.get("safe_points_missing_voltage") or [])
        duplicates = list(gpu.get("safe_points_duplicate_frequencies") or [])
        power_state = str(gpu.get("power_state") or "--")
        power_level = str(gpu.get("power_level") or "--")

        self.device_line.set_values(f"{vendor} / {device}", tr("AMD BC250 PCI identifiers"))
        self.driver_line.set_values(str(gpu.get("driver") or "--"), path)
        self.config_line.set_values(tr_format("{value} MHz max", value=_integer(gpu.get("config_max_frequency"), 0) or "--"), config)
        if errors:
            detail = "; ".join(
                f"{item.get('previous_frequency')}/{item.get('previous_voltage')} > {item.get('frequency')}/{item.get('voltage')}"
                for item in errors
            )
            self.curve_line.set_values(tr("Invalid"), detail)
        else:
            self.curve_line.set_values(tr("Valid"), tr("Voltage does not decrease as frequency rises"))
        if missing:
            frequencies = ", ".join(str(item.get("frequency") or item) for item in missing)
            self.missing_line.set_values(str(len(missing)), frequencies)
        else:
            self.missing_line.set_values(tr("None"), tr("Every active point exposes voltage"))
        if duplicates:
            self.duplicates_line.set_values(str(len(duplicates)), ", ".join(str(item) for item in duplicates))
        else:
            self.duplicates_line.set_values(tr("None"), tr("No duplicate frequency entries detected"))
        self.power_state_line.set_values(power_state, tr_format("force performance level: {level}", level=power_level))

    def _safe_point_voltage_text(self, frequency: int) -> str:
        voltage = self.safe_voltage_map.get(int(frequency))
        return f"{voltage} mV" if voltage else tr("Not specified")

    def _known_floor_text(self, frequency: int) -> str:
        floor = self.KNOWN_STABLE_VOLTAGES.get(int(frequency))
        return f"{floor} mV" if floor else tr("No reference")

    @classmethod
    def _profile_name(cls, minimum: int, maximum: int) -> str:
        profiles = {tuple(payload): name for name, _summary, payload in cls.PROFILE_VALUES}
        if minimum and maximum and minimum == maximum:
            return "Fixed"
        return profiles.get((minimum, maximum), "Custom")

    @staticmethod
    def _temperature_status(value: float) -> str:
        if value <= 0:
            return "Sensor unavailable"
        if value < 75:
            return tr("Normal")
        if value < 85:
            return tr("Warm")
        return "High"

    def _append_console(self, message: str) -> None:
        if not hasattr(self, "console"):
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        text = str(message or "").strip("\n")
        if not text:
            return
        self.console.appendPlainText(f"[{timestamp}] {text}")
        scrollbar = self.console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear_console(self) -> None:
        self.console.setPlainText("GPU Governor console cleared. No hardware command has been executed.")

    def _show_info(self, title: str, message: str, *, tone: str = "blue") -> None:
        icons = {
            "red": "warning_orange",
            "orange": "warning_orange",
            "purple": "gpu_purple",
            "green": "shield_green",
            "blue": "info_blue",
        }
        dialog = InfoDialog(
            title,
            message,
            icons.get(tone, "info_blue"),
            self,
            eyebrow="GPU GOVERNOR",
            notice="",
            tone=tone,
        )
        dialog.exec()
