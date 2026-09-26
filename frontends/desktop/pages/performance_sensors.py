"""The Sensors view of the Performance page: every sensor, as a list.

A hardware monitor's list, in the place of the chart: one row per sensor
grouped by the part it belongs to, with the value now and its minimum,
average and maximum since the list started (or since Reset). Ticking a row
draws its last two minutes beside the list. The list can be narrowed by
name or kind, channels that never read anything can be hidden, and the page
can show the list, the list with its graphs, or only the graphs.

Built for reading many numbers at once: dense rows, figures right-aligned
in tabular digits, colour kept for the traces and the sensor kinds.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QPointF,
    QRectF,
    QSize,
    QSortFilterProxyModel,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from bc250cc.infrastructure.sensor_inventory import (
    CLOCK,
    CURRENT,
    DATA,
    FAN,
    GPU_DEVICE,
    GROUP_CPU,
    GROUP_GDDR6,
    GROUP_GPU,
    GROUP_MEMORY,
    GROUP_NETWORK,
    GROUP_STORAGE,
    GROUP_VRM,
    POWER,
    RATE,
    TEMPERATURE,
    USAGE,
    VOLTAGE,
    SensorReading,
)

from ..components.chart_axes import range_axis
from ..components.chart_strokes import draw_series, fill_area
from ..components.flow_layout import FlowLayout
from ..core.preferences import application_settings
from ..core.sensor_log import SensorEntry, SensorLog, format_sensor_value
from ..i18n import tr, tr_format
from ..theme import COLORS

#: The table's columns, in order.
COLUMNS = ("Sensor", "Value", "Min", "Avg", "Max")
NAME, VALUE, MINIMUM, AVERAGE, MAXIMUM = range(len(COLUMNS))

#: Rendered on first open, before the user has ticked anything.
DEFAULT_PLOTTED = ("hwmon/k10temp/temp1", "cpu/usage")

#: Filter choices: (label, kinds they keep). The first shows everything; the
#: others are chips that can be combined, the way a hardware monitor's type
#: buttons are: temperatures and fans together, say, while tuning a curve.
KIND_FILTERS = (
    ("All sensors", ()),
    ("Temperatures", (TEMPERATURE,)),
    ("Clocks", (CLOCK,)),
    ("Usage", (USAGE,)),
    ("Power", (POWER,)),
    ("Voltages", (VOLTAGE,)),
    ("Currents", (CURRENT,)),
    ("Fans", (FAN,)),
    ("Memory and throughput", (DATA, RATE)),
)

#: The view modes: the list, the list with its graphs, only the graphs.
MODES = (("list", "List"), ("split", "List + graphs"), ("graphs", "Graphs"))

#: Where each fixed group sits; hwmon chips go between the GPU parts and
#: memory, where a hardware monitor lists the board.
_GROUP_RANK = {
    GROUP_CPU: 0, GROUP_GPU: 1, GROUP_GDDR6: 2, GROUP_VRM: 3,
    GROUP_MEMORY: 5, GROUP_STORAGE: 6, GROUP_NETWORK: 7,
}

#: The one colour mark per kind of sensor, from the palette's series slots.
_KIND_TONE = {
    TEMPERATURE: "series_2", CLOCK: "series_1", USAGE: "series_7", POWER: "series_8",
    VOLTAGE: "series_3", CURRENT: "series_4", FAN: "series_6", DATA: "series_5", RATE: "series_5",
}

_KEY_ROLE = Qt.ItemDataRole.UserRole + 1
_KIND_ROLE = Qt.ItemDataRole.UserRole + 2
_ACTIVE_ROLE = Qt.ItemDataRole.UserRole + 3
_SEARCH_ROLE = Qt.ItemDataRole.UserRole + 4


def sensor_label(reading: SensorReading) -> str:
    """The row's name: the kernel's label as is, or a translated template."""
    if not reading.fields:
        return tr(reading.label) if not reading.key.startswith("hwmon/") else reading.label
    try:
        return tr(reading.label).format(**dict(reading.fields))
    except (KeyError, IndexError, ValueError):
        return reading.label.format(**dict(reading.fields))


def _search_text(reading: SensorReading) -> str:
    """What the filter field is matched against, for the list and the graphs."""
    return f"{sensor_label(reading)} {reading.device} {reading.label}".casefold()


def _group_title(group: str, reading: SensorReading) -> str:
    if group == GROUP_STORAGE:
        return tr_format("Storage · {device}", device=reading.device)
    if group == GROUP_NETWORK:
        return tr_format("Network · {device}", device=reading.device)
    if group in (GROUP_MEMORY, GROUP_GDDR6, GROUP_VRM, GROUP_GPU):
        return tr(reading.device) if reading.device != GPU_DEVICE else reading.device
    return reading.device


_MARKS: dict[tuple[str, str], QPixmap] = {}


def _kind_mark(kind: str) -> QPixmap:
    """A small square in the kind's colour, the only colour on a row."""
    color = COLORS.get(_KIND_TONE.get(kind, "subtle"), COLORS["subtle"])
    cached = _MARKS.get((kind, color))
    if cached is not None:
        return cached
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(QRectF(3, 3, 6, 6), 1.5, 1.5)
    painter.end()
    _MARKS[(kind, color)] = pixmap
    return pixmap


def _tabular(font: QFont) -> QFont:
    """Digits of one width, so a column of readings lines up."""
    try:
        font.setFeature(QFont.Tag("tnum"), 1)
    except (AttributeError, TypeError, ValueError):
        pass
    return font


class SensorTableModel(QAbstractItemModel):
    """Groups at the top level, sensors under them, five columns."""

    plotted_changed = pyqtSignal()

    def __init__(self, log: SensorLog, parent=None) -> None:
        super().__init__(parent)
        self._log = log
        self._groups: list[tuple[str, str, list[str]]] = []
        self._known = 0
        self.plotted: list[str] = []
        self._bold: QFont | None = None

    # ------------------------------------------------------------- structure

    def sync(self) -> None:
        """Pick up new sensors, else refresh the numbers in place."""
        if len(self._log.order) != self._known:
            self.beginResetModel()
            self._rebuild()
            self.endResetModel()
            return
        for row, (_group, _title, keys) in enumerate(self._groups):
            if not keys:
                continue
            parent = self.index(row, 0, QModelIndex())
            self.dataChanged.emit(
                self.index(0, VALUE, parent),
                self.index(len(keys) - 1, MAXIMUM, parent),
                [Qt.ItemDataRole.DisplayRole, _ACTIVE_ROLE],
            )

    def _rebuild(self) -> None:
        groups: dict[str, tuple[str, list[str]]] = {}
        for key in self._log.order:
            reading = self._log.entries[key].reading
            if reading.group not in groups:
                groups[reading.group] = (_group_title(reading.group, reading), [])
            groups[reading.group][1].append(key)
        ordered = sorted(
            groups.items(), key=lambda item: (_GROUP_RANK.get(item[0], 4), list(groups).index(item[0]))
        )
        self._groups = [(group, title, keys) for group, (title, keys) in ordered]
        self._known = len(self._log.order)

    def retitle(self) -> None:
        """After a language change: names and titles are read again."""
        self.beginResetModel()
        self._rebuild()
        self.endResetModel()

    # --------------------------------------------------------------- the API

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if not parent.isValid():
            return self.createIndex(row, column, 0)
        return self.createIndex(row, column, parent.row() + 1)

    def parent(self, index: QModelIndex = QModelIndex()) -> QModelIndex:  # type: ignore[override]
        if not index.isValid() or index.internalId() == 0:
            return QModelIndex()
        return self.createIndex(index.internalId() - 1, 0, 0)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 - Qt API
        if not parent.isValid():
            return len(self._groups)
        if parent.internalId() == 0 and parent.column() == 0 and parent.row() < len(self._groups):
            return len(self._groups[parent.row()][2])
        return 0

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 - Qt API
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return tr(COLUMNS[section])
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.TextAlignmentRole:
            if section != NAME:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def entry(self, index: QModelIndex) -> SensorEntry | None:
        if not index.isValid() or index.internalId() == 0:
            return None
        group = index.internalId() - 1
        if group >= len(self._groups):
            return None
        keys = self._groups[group][2]
        return self._log.get(keys[index.row()]) if index.row() < len(keys) else None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.internalId() != 0 and index.column() == NAME:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if index.internalId() == 0:
            return self._group_data(index, role)
        entry = self.entry(index)
        if entry is None:
            return None
        reading = entry.reading
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == NAME:
                return sensor_label(reading)
            value = {
                VALUE: entry.value, MINIMUM: entry.minimum,
                AVERAGE: entry.average, MAXIMUM: entry.maximum,
            }[column]
            return format_sensor_value(value, reading.unit)
        if role == Qt.ItemDataRole.CheckStateRole and column == NAME:
            return Qt.CheckState.Checked if reading.key in self.plotted else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.TextAlignmentRole and column != NAME:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole and column in (MINIMUM, AVERAGE, MAXIMUM):
            return QColor(COLORS["muted"])
        if role == Qt.ItemDataRole.FontRole and column == VALUE:
            if self._bold is None:
                self._bold = QFont()
                self._bold.setWeight(QFont.Weight.DemiBold)
            return self._bold
        if role == Qt.ItemDataRole.DecorationRole and column == NAME:
            return _kind_mark(reading.kind)
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{sensor_label(reading)} · {reading.device}\n{reading.key}"
        if role == _KEY_ROLE:
            return reading.key
        if role == _KIND_ROLE:
            return reading.kind
        if role == _ACTIVE_ROLE:
            return entry.active
        if role == _SEARCH_ROLE:
            return _search_text(reading)
        return None

    def _group_data(self, index: QModelIndex, role):
        if index.row() >= len(self._groups):
            return None
        _group, title, keys = self._groups[index.row()]
        if role == Qt.ItemDataRole.DisplayRole and index.column() == NAME:
            return title
        if role == Qt.ItemDataRole.FontRole:
            font = QFont()
            font.setWeight(QFont.Weight.Bold)
            return font
        if role == Qt.ItemDataRole.ForegroundRole:
            return QColor(COLORS["text"])
        if role == _SEARCH_ROLE:
            return ""
        return None

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:  # noqa: N802
        if role != Qt.ItemDataRole.CheckStateRole or index.column() != NAME:
            return False
        entry = self.entry(index)
        if entry is None:
            return False
        key = entry.reading.key
        checked = Qt.CheckState(value) == Qt.CheckState.Checked
        if checked and key not in self.plotted:
            self.plotted.append(key)
        elif not checked and key in self.plotted:
            self.plotted.remove(key)
        else:
            return False
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        self.plotted_changed.emit()
        return True


class SensorFilter(QSortFilterProxyModel):
    """Name, kind and "hide unused" together; groups follow their sensors."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRecursiveFilteringEnabled(True)
        self.setDynamicSortFilter(False)
        self._text = ""
        self._kinds: tuple[str, ...] = ()
        self._hide_unused = True

    def configure(self, *, text: str | None = None, kinds=None, hide_unused: bool | None = None) -> None:
        if text is not None:
            self._text = text.strip().casefold()
        if kinds is not None:
            self._kinds = tuple(kinds)
        if hide_unused is not None:
            self._hide_unused = bool(hide_unused)
        self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        index = model.index(row, NAME, parent)
        if not parent.isValid():
            # A group is shown for its sensors, never on its own.
            return False
        if self._kinds and model.data(index, _KIND_ROLE) not in self._kinds:
            return False
        if self._hide_unused and not model.data(index, _ACTIVE_ROLE):
            return False
        if self._text and self._text not in str(model.data(index, _SEARCH_ROLE) or ""):
            return False
        return True


class SensorTrace(QWidget):
    """One sensor's last two minutes, with its name and value on top."""

    HEIGHT = 122

    def __init__(self, entry: SensorEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self._hover_x: float | None = None
        self.setMinimumHeight(self.HEIGHT)
        self.setMaximumHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._hover_x = event.position().x()
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_x = None
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # pragma: no cover - visual rendering
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        frame = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(COLORS["border_soft"]), 1))
        painter.setBrush(QColor(COLORS["chart_surface"]))
        painter.drawRoundedRect(frame, 8, 8)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        reading = self.entry.reading
        font = painter.font()
        font.setPointSize(8)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(_tabular(font))
        metrics = painter.fontMetrics()
        # The kind's mark leads the header, and the line is drawn in the
        # kind's colour: a wall of traces reads by type at a glance.
        mark = _kind_mark(reading.kind)
        painter.drawPixmap(QPointF(frame.left() + 6, frame.top() + 6 + (metrics.height() + 2 - mark.height()) / 2), mark)
        header = QRectF(frame.left() + 20, frame.top() + 6, frame.width() - 30, metrics.height() + 2)
        painter.setPen(QColor(COLORS["text"]))
        painter.drawText(header, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sensor_label(reading))
        value_text = format_sensor_value(self.entry.value, reading.unit)
        painter.drawText(header, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, value_text)
        name_width = metrics.horizontalAdvance(sensor_label(reading))
        painter.setPen(QColor(COLORS["subtle"]))
        painter.drawText(
            QRectF(header.left() + name_width + 8, header.top(), max(0.0, header.width() - name_width - metrics.horizontalAdvance(value_text) - 20), header.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            reading.device,
        )

        trace = list(self.entry.trace)
        label_room = metrics.horizontalAdvance("00000.0") + 8
        plot = QRectF(frame.left() + 10, header.bottom() + 6, frame.width() - 20 - label_room, frame.bottom() - header.bottom() - 14)
        if plot.height() < 12 or not trace:
            return
        values = [value for _moment, value in trace]
        low, high = min(values), max(values)
        if reading.unit == "%":
            axis_low, axis_high, ticks = 0.0, 100.0, (0.0, 50.0, 100.0)
        else:
            axis = range_axis(low, high, minimum_span=_TRACE_SPAN.get(reading.unit, max(1.0, abs(high) * 0.05)), target_ticks=2)
            axis_low, axis_high, ticks = axis.minimum, axis.maximum, axis.ticks
        span = max(1e-9, axis_high - axis_low)
        now = trace[-1][0]
        window = 120.0

        def x_for(moment: float) -> float:
            return plot.right() - plot.width() * max(0.0, min(window, now - moment)) / window

        def y_for(value: float) -> float:
            return plot.bottom() - plot.height() * (min(axis_high, max(axis_low, value)) - axis_low) / span

        grid = QColor(COLORS["chart_grid"])
        for tick in ticks:
            y = y_for(tick)
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(COLORS["subtle"]))
            painter.drawText(
                QRectF(plot.right() + 6, y - metrics.height() / 2, label_room, metrics.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{tick:g}",
            )

        color = QColor(COLORS.get(_KIND_TONE.get(reading.kind, ""), COLORS["blue"]))
        runs: list[list[QPointF]] = [[]]
        previous = trace[0][0]
        for moment, value in trace:
            if moment - previous > 3.5:
                runs.append([])
            runs[-1].append(QPointF(x_for(moment), y_for(value)))
            previous = moment
        gradient = QLinearGradient(0.0, plot.top(), 0.0, plot.bottom())
        top_fill, bottom_fill = QColor(color), QColor(color)
        top_fill.setAlpha(58)
        bottom_fill.setAlpha(4)
        gradient.setColorAt(0.0, top_fill)
        gradient.setColorAt(1.0, bottom_fill)
        for points in runs:
            fill_area(painter, points, plot.bottom(), QBrush(gradient))
        draw_series(painter, runs, color, 2.0)

        if self._hover_x is None or not plot.contains(QPointF(self._hover_x, plot.center().y())):
            return
        index = min(range(len(trace)), key=lambda item: abs(x_for(trace[item][0]) - self._hover_x))
        moment, value = trace[index]
        x = x_for(moment)
        painter.setPen(QPen(QColor(COLORS["muted"]), 1))
        painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        painter.setPen(QPen(QColor(COLORS["chart_surface"]), 1.5))
        painter.setBrush(color)
        painter.drawEllipse(QPointF(x, y_for(value)), 3.5, 3.5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        age = round(now - moment)
        text = format_sensor_value(value, reading.unit) + (f"  -{age} s" if age else "")
        width = metrics.horizontalAdvance(text) + 12
        box = QRectF(min(max(plot.left(), x - width / 2), plot.right() - width), plot.top(), width, metrics.height() + 4)
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.setBrush(QColor(COLORS["panel_raised"]))
        painter.drawRoundedRect(box, 4, 4)
        painter.setPen(QColor(COLORS["text"]))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)


#: The narrowest a trace's axis spans, per unit, so noise stays small.
_TRACE_SPAN = {"MHz": 100.0, "°C": 4.0, "W": 4.0, "V": 0.05, "A": 2.0, "RPM": 200.0}


class SensorPlots(QScrollArea):
    """The traces of the ticked sensors, one column or two."""

    def __init__(self, log: SensorLog, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._log = log
        self.setObjectName("sensorPlots")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("sensorPlotsBody")
        self._grid = QGridLayout(body)
        self._grid.setContentsMargins(0, 0, 4, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(8)
        self.empty = QLabel(tr("Tick a sensor in the list to draw its last two minutes here."), body)
        self.empty.setObjectName("sensorPlotsEmpty")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidget(body)
        self.traces: dict[str, SensorTrace] = {}
        self._columns = 1
        self._max_columns = 1
        self._keys: list[str] = []

    #: Narrower than this a trace's scale labels crowd its line.
    MIN_TRACE_WIDTH = 340

    def set_max_columns(self, columns: int) -> None:
        """As many columns as fit, up to ``columns``."""
        self._max_columns = max(1, int(columns))
        self._fit_columns()

    def _fit_columns(self) -> None:
        width = self.viewport().width() if self.viewport() is not None else self.width()
        columns = max(1, min(self._max_columns, width // self.MIN_TRACE_WIDTH))
        if columns != self._columns:
            self._columns = columns
            self._place()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._fit_columns()

    def set_keys(self, keys: list[str]) -> None:
        keys = [key for key in keys if self._log.get(key) is not None]
        for key in [key for key in self.traces if key not in keys]:
            trace = self.traces.pop(key)
            trace.setParent(None)
            trace.deleteLater()
        for key in keys:
            if key not in self.traces:
                self.traces[key] = SensorTrace(self._log.get(key))
        self._keys = keys
        self._place()

    def _place(self) -> None:
        while self._grid.count():
            self._grid.takeAt(0)
        for row in range(self._grid.rowCount()):
            self._grid.setRowStretch(row, 0)
        # Every column this placement uses, the new ones included: a column
        # added here with no stretch shrank to nothing, and its traces with it.
        for column in range(max(self._columns, self._grid.columnCount())):
            self._grid.setColumnStretch(column, 1 if column < self._columns else 0)
        if not self._keys:
            self._grid.addWidget(self.empty, 0, 0, 1, self._columns)
            self.empty.show()
            self._grid.setRowStretch(1, 1)
            return
        self.empty.hide()
        for position, key in enumerate(self._keys):
            row, column = divmod(position, self._columns)
            trace = self.traces[key]
            if trace.parent() is not self.widget():
                trace.setParent(self.widget())
            self._grid.addWidget(trace, row, column)
            trace.show()
        self._grid.setRowStretch((len(self._keys) - 1) // self._columns + 1, 1)

    def refresh(self) -> None:
        for trace in self.traces.values():
            trace.update()


class SensorBoard(QFrame):
    """The whole Sensors view: its bar, the list and the traces."""

    back_requested = pyqtSignal()

    def __init__(self, log: SensorLog, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("sensorBoard", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(560)
        self._log = log
        self._settings = application_settings()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        # First line: the way back, what this is, and how to lay it out.
        top = QHBoxLayout()
        top.setSpacing(10)
        self.back_button = QPushButton(tr("Chart"))
        self.back_button.setProperty("viewSwitch", True)
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.setToolTip(tr("Back to the chart of the selected resource"))
        self.back_button.clicked.connect(self.back_requested.emit)
        top.addWidget(self.back_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = QLabel(tr("Sensors"))
        self.title.setProperty("detailTitle", True)
        top.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)
        self.summary = QLabel("")
        self.summary.setProperty("detailContext", True)
        self.summary.setProperty("i18nLiteral", True)
        top.addWidget(self.summary, 1, Qt.AlignmentFlag.AlignVCenter)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons: dict[str, QPushButton] = {}
        for mode, text in MODES:
            button = QPushButton(tr(text))
            button.setCheckable(True)
            button.setProperty("scaleMode", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, value=mode: self.set_mode(value))
            self.mode_group.addButton(button)
            self.mode_buttons[mode] = button
            top.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(top)

        # Second line: narrowing the list.
        tools = QHBoxLayout()
        tools.setSpacing(10)
        self.filter_field = QLineEdit()
        self.filter_field.setObjectName("sensorFilter")
        self.filter_field.setPlaceholderText(tr("Filter by name"))
        self.filter_field.setClearButtonEnabled(True)
        self.filter_field.setFixedHeight(30)
        tools.addWidget(self.filter_field, 1)
        self.unused_toggle = QCheckBox(tr("Hide unused channels"))
        self.unused_toggle.setToolTip(
            tr("Channels that have read nothing but zero since the list started, like a fan header with no fan.")
        )
        tools.addWidget(self.unused_toggle, 0)
        self.reset_button = QPushButton(tr("Reset min/max"))
        self.reset_button.setProperty("viewSwitch", True)
        self.reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_button.clicked.connect(self.reset_statistics)
        tools.addWidget(self.reset_button, 0)
        root.addLayout(tools)

        # Third line: the kinds, as chips that combine; wraps when narrow.
        self.kind_row = QWidget()
        self.kind_row.setObjectName("sensorKinds")
        chips = FlowLayout(self.kind_row, spacing=6)
        self.kind_chips: dict[str, QPushButton] = {}
        self._chip_kinds: dict[str, tuple[str, ...]] = {}
        for label, kinds in KIND_FILTERS:
            chip = QPushButton(tr(label))
            chip.setCheckable(True)
            chip.setProperty("kindChip", True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            if kinds:
                chip.setIcon(QIcon(_kind_mark(kinds[0])))
                chip.setIconSize(QSize(12, 12))
            chip.clicked.connect(lambda _checked=False, key=label: self._kind_chip_clicked(key))
            chips.addWidget(chip)
            self.kind_chips[label] = chip
            self._chip_kinds[label] = tuple(kinds)
        self._all_label = KIND_FILTERS[0][0]
        root.addWidget(self.kind_row)

        self.model = SensorTableModel(log, self)
        self.proxy = SensorFilter(self)
        self.proxy.setSourceModel(self.model)
        self.tree = QTreeView()
        self.tree.setObjectName("sensorTree")
        self.tree.setModel(self.proxy)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setIndentation(12)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setFont(_tabular(QFont(self.tree.font())))
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(NAME, QHeaderView.ResizeMode.Stretch)
        for column in (VALUE, MINIMUM, AVERAGE, MAXIMUM):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(column, 96)
        header.setMinimumSectionSize(60)
        self.tree.doubleClicked.connect(self._toggle_plot)

        self.plots = SensorPlots(log)
        self.plots.setMinimumWidth(260)
        self.tree.setMinimumWidth(420)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(10)
        self._split_sized = False
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.plots)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        root.addWidget(self.splitter, 1)

        self.footer = QLabel("")
        self.footer.setProperty("sampleFooter", True)
        self.footer.setProperty("i18nLiteral", True)
        root.addWidget(self.footer)

        self._restore()
        self.filter_field.textChanged.connect(self._filter_changed)
        self.unused_toggle.toggled.connect(self._filter_changed)
        self.model.plotted_changed.connect(self._plotted_changed)
        self.model.modelReset.connect(self.tree.expandAll)
        self._filter_changed()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        if not self._split_sized and self.splitter.width() > 0:
            # Three fifths for the list, the rest for the traces, the first
            # time it has a width to share; the user's drag wins after that.
            width = self.splitter.width()
            self.splitter.setSizes([int(width * 0.6), width - int(width * 0.6)])
            self._split_sized = True

    # ------------------------------------------------------------- settings

    def _restore(self) -> None:
        settings = self._settings
        mode = str(settings.value("performance/sensors_mode", "split") or "split")
        stored = settings.value("performance/sensors_plotted", None)
        if isinstance(stored, str):
            stored = [item for item in stored.split("\n") if item]
        self.model.plotted = list(stored) if stored is not None else list(DEFAULT_PLOTTED)
        hide = str(settings.value("performance/sensors_hide_unused", "true")).lower() in {"1", "true", "yes"}
        self.unused_toggle.setChecked(hide)
        stored_kinds = settings.value("performance/sensors_kinds", None)
        if stored_kinds is None:
            # Before the chips there was one choice in a list, by position.
            try:
                index = int(settings.value("performance/sensors_kind", 0) or 0)
            except (TypeError, ValueError):
                index = 0
            chosen = [KIND_FILTERS[index][0]] if 0 < index < len(KIND_FILTERS) else []
        else:
            chosen = [item for item in str(stored_kinds).split("\n") if item in self._chip_kinds]
        self._set_kind_selection(chosen)
        self.set_mode(mode, persist=False)

    def _save(self) -> None:
        settings = self._settings
        settings.setValue("performance/sensors_mode", self.mode)
        settings.setValue("performance/sensors_plotted", "\n".join(self.model.plotted))
        settings.setValue("performance/sensors_hide_unused", "true" if self.unused_toggle.isChecked() else "false")
        settings.setValue("performance/sensors_kinds", "\n".join(self._chosen_kind_labels()))

    # --------------------------------------------------------------- layout

    def set_mode(self, mode: str, *, persist: bool = True) -> None:
        if mode not in dict(MODES):
            mode = "split"
        self.mode = mode
        self.mode_buttons[mode].setChecked(True)
        self.tree.setVisible(mode != "graphs")
        self.plots.setVisible(mode != "list")
        self.plots.set_max_columns(3 if mode == "graphs" else 2)
        if persist:
            self._save()

    def _chosen_kind_labels(self) -> list[str]:
        return [label for label, chip in self.kind_chips.items() if label != self._all_label and chip.isChecked()]

    def selected_kinds(self) -> tuple[str, ...]:
        """The kinds the chips keep; empty means every kind."""
        kinds: list[str] = []
        for label in self._chosen_kind_labels():
            kinds.extend(self._chip_kinds[label])
        return tuple(kinds)

    def _set_kind_selection(self, labels) -> None:
        chosen = set(labels)
        for label, chip in self.kind_chips.items():
            chip.setChecked(label in chosen and label != self._all_label)
        self.kind_chips[self._all_label].setChecked(not self._chosen_kind_labels())

    def _kind_chip_clicked(self, label: str) -> None:
        if label == self._all_label:
            self._set_kind_selection(())
        else:
            self._set_kind_selection(self._chosen_kind_labels())
        self._filter_changed()

    def _filter_changed(self, *_args) -> None:
        self.proxy.configure(
            text=self.filter_field.text(),
            kinds=self.selected_kinds(),
            hide_unused=self.unused_toggle.isChecked(),
        )
        self.plots.set_keys(self._visible_plotted())
        self.tree.expandAll()
        self._save()

    def _toggle_plot(self, proxy_index: QModelIndex) -> None:
        index = self.proxy.mapToSource(proxy_index.siblingAtColumn(NAME))
        if index.internalId() == 0:
            return
        state = self.model.data(index, Qt.ItemDataRole.CheckStateRole)
        self.model.setData(
            index,
            Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked,
            Qt.ItemDataRole.CheckStateRole,
        )

    def _visible_plotted(self) -> list[str]:
        """The ticked sensors the chips and the filter text still keep.

        The chips narrowed only the list, so with the graphs alone on screen
        choosing "Temperatures" seemed to do nothing at all.
        """
        kinds = set(self.selected_kinds())
        text = self.filter_field.text().strip().casefold()
        visible = []
        for key in self.model.plotted:
            entry = self._log.get(key)
            if entry is None:
                continue
            if kinds and entry.reading.kind not in kinds:
                continue
            if text and text not in _search_text(entry.reading):
                continue
            visible.append(key)
        return visible

    def _plotted_changed(self) -> None:
        self.plots.set_keys(self._visible_plotted())
        self._save()

    def reset_statistics(self) -> None:
        self._log.reset_statistics()
        self.refresh()

    # -------------------------------------------------------------- refresh

    def refresh(self) -> None:
        """Numbers and traces from the log, as they stand now."""
        structure_changed = len(self._log.order) != self.model._known
        self.model.sync()
        if structure_changed:
            self.proxy.invalidateFilter()
            self.tree.expandAll()
        # The traces for plotted keys whose sensors have now appeared.
        visible = self._visible_plotted()
        if list(self.plots.traces) != visible:
            self.plots.set_keys(visible)
        self.plots.refresh()
        count = len(self._log.order)
        shown = sum(self.proxy.rowCount(self.proxy.index(row, 0)) for row in range(self.proxy.rowCount()))
        self.summary.setText(tr_format("{shown} of {count} sensors", shown=shown, count=count))
        started = datetime.now() - timedelta(seconds=max(0.0, self._log._clock() - self._log.started_at))
        self.footer.setText(
            tr_format(
                "Minimum, average and maximum since {time} · 1 s cadence · double-click a row to draw it",
                time=started.strftime("%H:%M:%S"),
            )
        )

    def retranslate(self) -> None:
        self.model.retitle()
        self.tree.expandAll()
        self.refresh()
