"""Compact voltage-curve drawer for the desktop GPU page.

Redesign 3a: a single panel surface divided by 1px separators, with a live V/F
chart whose points can be dragged, a flat preset row, a hairline voltage table
and a footer that summarises the pending change.
"""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWidgets import (
    QPushButton as NativePushButton,
)

from bc250cc.application.gpu.voltage_table import VoltageTableRow
from bc250cc.domain.gpu.voltage_profiles import (
    CUSTOM_VOLTAGE_MAX_MV,
    CUSTOM_VOLTAGE_MIN_MV,
)

from ..i18n import tr
from ..theme import COLORS
from .buttons import WrappingButton as QPushButton
from .widgets import icon


def _separator(parent: QWidget | None = None) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.NoFrame)
    line.setFixedHeight(1)
    line.setProperty("voltageDrawerSeparator", True)
    return line


class _CurveChart(QWidget):
    """V/F plot. The proposed curve is drawn over the active one and its
    points can be dragged vertically when the custom editor is unlocked."""

    voltage_dragged = pyqtSignal(int, int)
    custom_requested = pyqtSignal()

    PAD_LEFT = 46
    PAD_RIGHT = 12
    PAD_TOP = 12
    PAD_BOTTOM = 20
    HIT_RADIUS = 16

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._points: list[dict] = []
        self._editable = False
        self._drag_index: int | None = None
        self._hover_index: int | None = None

    # ----- data -------------------------------------------------------
    def set_points(self, points: Sequence[dict], *, editable: bool) -> None:
        self._points = [dict(point) for point in points]
        self._editable = bool(editable)
        if not self._editable:
            self._drag_index = None
        self.update()

    def _values(self) -> list[int]:
        values: list[int] = []
        for point in self._points:
            for key in ("current", "proposed"):
                value = point.get(key)
                if value:
                    values.append(int(value))
        return values

    def _bounds(self) -> tuple[float, float]:
        values = self._values()
        if not values:
            return 700.0, 1000.0
        if self._editable:
            # While points can be dragged the axis has to cover the whole
            # editable band, or the top of the range is unreachable and the
            # scale jumps under the cursor as the maximum moves.
            values = values + [CUSTOM_VOLTAGE_MAX_MV]
        low = (min(values) - 40) // 50 * 50
        high = -(-(max(values) + 40) // 50) * 50
        if high - low < 100:
            high = low + 100
        return float(low), float(high)

    def _plot_rect(self) -> QRectF:
        return QRectF(
            self.PAD_LEFT,
            self.PAD_TOP,
            max(1.0, self.width() - self.PAD_LEFT - self.PAD_RIGHT),
            max(1.0, self.height() - self.PAD_TOP - self.PAD_BOTTOM),
        )

    def _x_for(self, frequency: float) -> float:
        plot = self._plot_rect()
        freqs = [float(point["frequency"]) for point in self._points]
        if len(freqs) < 2:
            return plot.center().x()
        low, high = min(freqs), max(freqs)
        span = max(1.0, high - low)
        return plot.left() + (frequency - low) / span * plot.width()

    def _y_for(self, voltage: float) -> float:
        plot = self._plot_rect()
        low, high = self._bounds()
        return plot.bottom() - (voltage - low) / max(1.0, high - low) * plot.height()

    def _voltage_for(self, y: float) -> int:
        plot = self._plot_rect()
        low, high = self._bounds()
        ratio = (plot.bottom() - y) / max(1.0, plot.height())
        return int(round(low + ratio * (high - low)))

    # ----- painting ---------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        plot = self._plot_rect()
        low, high = self._bounds()

        grid = QColor(COLORS["chart_grid"])
        axis = QColor(COLORS["chart_axis"])
        label = QColor(COLORS["subtle"])
        accent = QColor(COLORS["blue"])

        font = painter.font()
        font.setPointSizeF(max(6.5, font.pointSizeF() - 2.0))
        font.setBold(False)
        painter.setFont(font)

        step = 100 if (high - low) <= 600 else 200
        value = int(low // step * step)
        while value <= high:
            if value >= low:
                y = self._y_for(value)
                painter.setPen(QPen(grid, 1))
                painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
                painter.setPen(QPen(label, 1))
                painter.drawText(
                    QRectF(0, y - 8, self.PAD_LEFT - 8, 16),
                    int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                    str(value),
                )
            value += step

        painter.setPen(QPen(axis, 1))
        painter.drawLine(
            QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom())
        )

        if len(self._points) >= 2:
            current = QPolygonF()
            proposed = QPolygonF()
            for point in self._points:
                x = self._x_for(float(point["frequency"]))
                if point.get("current"):
                    current.append(QPointF(x, self._y_for(float(point["current"]))))
                if point.get("proposed"):
                    proposed.append(QPointF(x, self._y_for(float(point["proposed"]))))
            if current.count() >= 2:
                pen = QPen(axis, 1.2)
                pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawPolyline(current)
            if proposed.count() >= 2:
                pen = QPen(accent, 2.0)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawPolyline(proposed)

        surface = QColor(COLORS["panel"])
        for index, point in enumerate(self._points):
            if not point.get("proposed"):
                continue
            x = self._x_for(float(point["frequency"]))
            y = self._y_for(float(point["proposed"]))
            size = 7.0 if index == self._hover_index else 6.0
            handle = QRectF(x - size / 2, y - size / 2, size, size)
            painter.setPen(QPen(accent, 1.8))
            painter.setBrush(surface)
            painter.drawRect(handle)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # The safe-points above 2000 MHz sit 25-50 MHz apart, so on a linear
        # axis their labels land on top of each other.  Draw a label only where
        # there is room for it, always keeping the first and the last.
        painter.setPen(QPen(label, 1))
        metrics = painter.fontMetrics()

        def half_width(point: dict) -> float:
            return metrics.horizontalAdvance(str(int(point["frequency"]))) / 2.0 + 5.0

        if self._points:
            final = self._points[-1]
            final_left = self._x_for(float(final["frequency"])) - half_width(final)
            drawn_right = float("-inf")
            for index, point in enumerate(self._points):
                x = self._x_for(float(point["frequency"]))
                half = half_width(point)
                is_final = index == len(self._points) - 1
                if not is_final and (x - half < drawn_right or x + half > final_left):
                    continue
                painter.drawText(
                    QRectF(x - 30, plot.bottom() + 4, 60, 16),
                    int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                    str(int(point["frequency"])),
                )
                drawn_right = x + half
        painter.end()

    # ----- interaction ------------------------------------------------
    def _index_at(self, position) -> int | None:
        best: int | None = None
        best_distance = float(self.HIT_RADIUS)
        for index, point in enumerate(self._points):
            if not point.get("proposed"):
                continue
            x = self._x_for(float(point["frequency"]))
            y = self._y_for(float(point["proposed"]))
            distance = ((position.x() - x) ** 2 + (position.y() - y) ** 2) ** 0.5
            if distance <= best_distance:
                best_distance = distance
                best = index
        return best

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        position = event.position()
        if self._drag_index is None:
            hovered = self._index_at(position)
            if hovered != self._hover_index:
                self._hover_index = hovered
                self.setCursor(
                    Qt.CursorShape.SizeVerCursor
                    if hovered is not None
                    else Qt.CursorShape.ArrowCursor
                )
                self.update()
            return
        point = self._points[self._drag_index]
        if not point.get("editable"):
            return
        value = self._voltage_for(position.y())
        floor = CUSTOM_VOLTAGE_MIN_MV
        ceiling = CUSTOM_VOLTAGE_MAX_MV
        if self._drag_index > 0:
            previous = self._points[self._drag_index - 1].get("proposed")
            if previous:
                floor = max(floor, int(previous))
        if self._drag_index < len(self._points) - 1:
            following = self._points[self._drag_index + 1].get("proposed")
            if following:
                ceiling = min(ceiling, int(following))
        value = max(floor, min(ceiling, value))
        if value != int(point["proposed"]):
            point["proposed"] = value
            self.update()
            self.voltage_dragged.emit(int(point["frequency"]), int(value))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        index = self._index_at(event.position())
        if index is None:
            super().mousePressEvent(event)
            return
        if not self._editable or not self._points[index].get("editable"):
            self.custom_requested.emit()
            event.accept()
            return
        self._drag_index = index
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._drag_index = None
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._hover_index = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        super().leaveEvent(event)


class _DrawerCurveRow(QFrame):
    voltage_changed = pyqtSignal(int, int)

    def __init__(
        self,
        row: VoltageTableRow,
        *,
        custom_mode: bool,
        read_only: bool,
        first: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.frequency = int(row.frequency)
        self.original = row.original
        self.setProperty("voltageDrawerCurveRow", True)
        self.setProperty("rowFirst", bool(first))
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 4, 2, 4)
        layout.setSpacing(12)

        frequency = QLabel(f"{row.frequency} MHz")
        frequency.setProperty("voltageDrawerFrequency", True)
        frequency.setFixedWidth(92)
        layout.addWidget(frequency)
        layout.addStretch(1)

        current = QLabel(f"{row.current} mV" if row.current else tr("Not set"))
        current.setProperty("voltageDrawerCurrent", True)
        current.setFixedWidth(84)
        layout.addWidget(current)

        self.editor: QSpinBox | None = None
        if custom_mode and row.custom_available:
            editor = QSpinBox()
            editor.setProperty("voltageDrawerEditor", True)
            editor.setRange(CUSTOM_VOLTAGE_MIN_MV, CUSTOM_VOLTAGE_MAX_MV)
            editor.setSingleStep(5)
            editor.setSuffix(" mV")
            editor.setValue(int(row.editor_value))
            editor.setFixedWidth(112)
            editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
            editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            editor.valueChanged.connect(self._editor_changed)
            self.editor = editor
            layout.addWidget(editor)
        else:
            proposed = QLabel(
                f"{row.proposed} mV" if row.proposed is not None else tr("Unchanged")
            )
            proposed.setProperty("voltageDrawerTarget", True)
            proposed.setFixedWidth(112)
            proposed.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(proposed)

        self.delta = QLabel(tr("Read only") if read_only else self._delta_text(row.added))
        self.delta.setProperty("voltageDrawerDelta", True)
        self.delta.setProperty("deltaTone", self._delta_tone(row.added))
        self.delta.setFixedWidth(66)
        self.delta.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.delta)

    @staticmethod
    def _delta_text(value: int | None) -> str:
        if value is None:
            return "—"
        if value > 0:
            return f"+{value}"
        if value < 0:
            return str(value)
        return "—"

    @staticmethod
    def _delta_tone(value: int | None) -> str:
        if value is None:
            return "muted"
        if value > 0:
            return "raised"
        if value < 0:
            return "lowered"
        return "default"

    def _editor_changed(self, value: int) -> None:
        added = None if self.original is None else int(value) - int(self.original)
        self.delta.setText(self._delta_text(added))
        self.delta.setProperty("deltaTone", self._delta_tone(added))
        self.delta.style().unpolish(self.delta)
        self.delta.style().polish(self.delta)
        self.voltage_changed.emit(self.frequency, int(value))


class VoltageLabDrawer(QWidget):
    """Right-side laboratory surface; it delegates every write to the GPU page."""

    close_requested = pyqtSignal()
    profile_requested = pyqtSignal(int)
    custom_voltage_changed = pyqtSignal(int, int)
    apply_requested = pyqtSignal()
    restore_requested = pyqtSignal()

    PROFILE_LEVELS = (1, 2, 3, -1)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("VoltageLabDrawerOverlay")
        self.setProperty("voltageLabDrawerOverlay", True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()
        self._last_focus: QWidget | None = None
        self._selected_level = 1
        self._editors: dict[int, QSpinBox] = {}
        self._curve_signature: tuple | None = None
        self._profile_columns = 0
        self._footer_horizontal: bool | None = None

        self.drawer = QFrame(self)
        self.drawer.setObjectName("VoltageLabDrawer")
        self.drawer.setProperty("voltageLabDrawer", True)
        root = QVBoxLayout(self.drawer)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- header ----------------------------------------------------
        header = QHBoxLayout()
        header.setContentsMargins(18, 15, 18, 15)
        header.setSpacing(12)
        self.close_button = QPushButton("")
        self.close_button.setObjectName("VoltageDrawerClose")
        self.close_button.setProperty("voltageDrawerClose", True)
        self.close_button.setProperty("gamepadEntry", True)
        self.close_button.setProperty("gamepadCancel", True)
        self.close_button.setAccessibleName(tr("Close GPU voltage curve"))
        self.close_button.setIcon(icon("collapse_gray"))
        self.close_button.setFixedSize(32, 32)
        self.close_button.clicked.connect(self.close_animated)
        header.addWidget(self.close_button)
        title_host = QWidget()
        title_layout = QVBoxLayout(title_host)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(1)
        title = QLabel(tr("GPU voltage curve"))
        title.setProperty("voltageDrawerTitle", True)
        subtitle = QLabel(tr("Choose a safe preset or drag the active points"))
        subtitle.setProperty("voltageDrawerSubtitle", True)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header.addWidget(title_host, 1)
        root.addLayout(header)
        root.addWidget(_separator())

        # --- compatibility note (Oberon only) --------------------------
        self.compatibility_note = QFrame()
        self.compatibility_note.setProperty("voltageDrawerCompatibility", True)
        compatibility_layout = QVBoxLayout(self.compatibility_note)
        compatibility_layout.setContentsMargins(18, 12, 18, 12)
        compatibility_layout.setSpacing(3)
        compatibility_title = QLabel(tr("Oberon compatibility mode"))
        compatibility_title.setProperty("voltageDrawerCompatibilityTitle", True)
        compatibility_text = QLabel(
            tr(
                "Oberon uses two YAML endpoints. They are shown below for reference; "
                "curve editing is unavailable for this governor."
            )
        )
        compatibility_text.setProperty("voltageDrawerCompatibilityText", True)
        compatibility_text.setWordWrap(True)
        compatibility_layout.addWidget(compatibility_title)
        compatibility_layout.addWidget(compatibility_text)
        self.compatibility_note.hide()
        root.addWidget(self.compatibility_note)

        # --- chart -----------------------------------------------------
        chart_host = QWidget()
        chart_layout = QVBoxLayout(chart_host)
        chart_layout.setContentsMargins(18, 14, 18, 10)
        chart_layout.setSpacing(2)
        chart_head = QHBoxLayout()
        chart_head.setContentsMargins(0, 0, 0, 0)
        chart_head.setSpacing(8)
        chart_title = QLabel(tr("V/F curve"))
        chart_title.setProperty("voltageDrawerSectionTitle", True)
        chart_head.addWidget(chart_title)
        chart_head.addStretch(1)
        self.chart_legend = QLabel(f"— — {tr('current')}    ——  {tr('proposed')}")
        self.chart_legend.setProperty("voltageDrawerLegend", True)
        chart_head.addWidget(self.chart_legend)
        chart_layout.addLayout(chart_head)
        self.chart = _CurveChart()
        self.chart.voltage_dragged.connect(self._chart_dragged)
        self.chart.custom_requested.connect(lambda: self._choose_profile(-1))
        chart_layout.addWidget(self.chart)
        root.addWidget(chart_host)
        self.chart_separator = _separator()
        root.addWidget(self.chart_separator)

        # --- presets ---------------------------------------------------
        self.profiles_card = QWidget()
        profiles_layout = QVBoxLayout(self.profiles_card)
        profiles_layout.setContentsMargins(18, 14, 18, 14)
        profiles_layout.setSpacing(8)
        profiles_title = QLabel(tr("Curve boost"))
        profiles_title.setProperty("voltageDrawerSectionTitle", True)
        profiles_layout.addWidget(profiles_title)
        self.profile_grid = QGridLayout()
        self.profile_grid.setContentsMargins(0, 0, 0, 0)
        self.profile_grid.setHorizontalSpacing(7)
        self.profile_grid.setVerticalSpacing(7)
        self.profile_group = QButtonGroup(self)
        self.profile_group.setExclusive(True)
        self.profile_buttons: dict[int, NativePushButton] = {}
        for level in self.PROFILE_LEVELS:
            custom = level == -1
            descriptions = {1: "Gentle", 2: "Moderate", 3: "High"}
            button = NativePushButton(
                tr("Custom\nEdit active points")
                if custom
                else f"+{level * 10} mV\n{tr(descriptions[level])}"
            )
            button.setCheckable(True)
            button.setFixedHeight(46)
            button.setProperty("voltageDrawerProfile", True)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.clicked.connect(
                lambda checked, value=level: self._choose_profile(value) if checked else None
            )
            self.profile_group.addButton(button)
            self.profile_buttons[level] = button
        profiles_layout.addLayout(self.profile_grid)
        self.profile_detail = QLabel(
            tr("Select a level to preview the exact curve before applying.")
        )
        self.profile_detail.setProperty("voltageDrawerDetail", True)
        self.profile_detail.setWordWrap(True)
        profiles_layout.addWidget(self.profile_detail)
        root.addWidget(self.profiles_card)
        self.profiles_separator = _separator()
        root.addWidget(self.profiles_separator)

        # --- voltage table ---------------------------------------------
        table_host = QWidget()
        table_layout = QVBoxLayout(table_host)
        table_layout.setContentsMargins(18, 12, 18, 0)
        table_layout.setSpacing(0)
        columns = QHBoxLayout()
        columns.setContentsMargins(2, 0, 2, 8)
        columns.setSpacing(12)
        frequency_column = QLabel(tr("Frequency"))
        frequency_column.setProperty("voltageDrawerColumn", True)
        frequency_column.setFixedWidth(92)
        columns.addWidget(frequency_column)
        columns.addStretch(1)
        current_column = QLabel(tr("Current"))
        current_column.setProperty("voltageDrawerColumn", True)
        current_column.setFixedWidth(84)
        columns.addWidget(current_column)
        self.selected_column = QLabel(tr("Selected"))
        self.selected_column.setProperty("voltageDrawerColumn", True)
        self.selected_column.setFixedWidth(112)
        self.selected_column.setAlignment(Qt.AlignmentFlag.AlignCenter)
        columns.addWidget(self.selected_column)
        delta_column = QLabel("Δ")
        delta_column.setProperty("voltageDrawerColumn", True)
        delta_column.setFixedWidth(66)
        delta_column.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        columns.addWidget(delta_column)
        table_layout.addLayout(columns)

        scroll = QScrollArea()
        scroll.setObjectName("VoltageLabDrawerScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("VoltageLabDrawerBody")
        self.curve_rows = QVBoxLayout(body)
        self.curve_rows.setContentsMargins(0, 0, 3, 0)
        self.curve_rows.setSpacing(0)
        scroll.setWidget(body)
        table_layout.addWidget(scroll, 1)
        root.addWidget(table_host, 1)
        root.addWidget(_separator())

        # --- footer ------------------------------------------------------
        self.footer = QWidget()
        self.footer_layout = QGridLayout(self.footer)
        self.footer_layout.setContentsMargins(18, 12, 18, 14)
        self.footer_layout.setHorizontalSpacing(10)
        self.footer_layout.setVerticalSpacing(8)
        self.footer_summary = QLabel("")
        self.footer_summary.setProperty("voltageDrawerSummary", True)
        self.restore_button = QPushButton(tr("Restore governor defaults"))
        self.restore_button.setProperty("voltageDrawerSecondary", True)
        self.restore_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.restore_button.clicked.connect(self.restore_requested)
        self.apply_button = QPushButton(tr("Review and apply"))
        self.apply_button.setObjectName("VoltageDrawerApply")
        self.apply_button.setProperty("voltageDrawerApply", True)
        self.apply_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.apply_button.setIcon(icon("bolt_blue"))
        self.apply_button.clicked.connect(self.apply_requested)
        root.addWidget(self.footer)

        self._animation = QPropertyAnimation(self.drawer, b"geometry", self)
        self._animation.setDuration(170)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._reflow_controls(self._drawer_rect().width())
        self.set_profile(1)

    # ------------------------------------------------------------------
    def set_profile(self, level: int) -> None:
        level = int(level)
        if level not in self.profile_buttons:
            level = 1
        self._selected_level = level
        for value, button in self.profile_buttons.items():
            button.setChecked(value == level)

    def selected_level(self) -> int:
        return self._selected_level

    def set_oberon_mode(self, enabled: bool) -> None:
        read_only = bool(enabled)
        self.compatibility_note.setVisible(read_only)
        self.profiles_card.setVisible(not read_only)
        self.profiles_separator.setVisible(not read_only)
        self.footer.setVisible(not read_only)
        self.selected_column.setText(tr("Configured" if read_only else "Selected"))

    def _choose_profile(self, level: int) -> None:
        self._selected_level = int(level)
        self.set_profile(self._selected_level)
        self.profile_requested.emit(self._selected_level)

    def _chart_dragged(self, frequency: int, millivolts: int) -> None:
        editor = self._editors.get(int(frequency))
        if editor is not None:
            editor.blockSignals(True)
            editor.setValue(int(millivolts))
            editor.blockSignals(False)
        self.custom_voltage_changed.emit(int(frequency), int(millivolts))

    def set_curve(
        self,
        rows: Sequence[VoltageTableRow],
        *,
        custom_mode: bool,
        detail: str,
        apply_enabled: bool,
        read_only: bool = False,
    ) -> None:
        signature = (tuple(rows), bool(custom_mode), bool(read_only))
        if signature != self._curve_signature:
            while self.curve_rows.count():
                item = self.curve_rows.takeAt(0)
                if item.widget() is not None:
                    item.widget().deleteLater()
            self._editors = {}
            for index, row in enumerate(rows):
                widget = _DrawerCurveRow(
                    row,
                    custom_mode=custom_mode,
                    read_only=read_only,
                    first=index == 0,
                )
                widget.voltage_changed.connect(self.custom_voltage_changed)
                widget.voltage_changed.connect(self._row_voltage_changed)
                self.curve_rows.addWidget(widget)
                if widget.editor is not None:
                    self._editors[int(row.frequency)] = widget.editor
            self._curve_signature = signature
        self.chart.set_points(
            [
                {
                    "frequency": int(row.frequency),
                    "current": int(row.current) if row.current else None,
                    "proposed": int(row.proposed) if row.proposed is not None else None,
                    "editable": bool(custom_mode and row.custom_available and not read_only),
                }
                for row in rows
            ],
            editable=bool(custom_mode and not read_only),
        )
        self.profile_detail.setText(str(detail))
        self.apply_button.setEnabled(bool(apply_enabled))
        self._refresh_summary(rows)

    def _row_voltage_changed(self, frequency: int, millivolts: int) -> None:
        for point in self.chart._points:  # noqa: SLF001 - sibling widget of the same drawer
            if int(point["frequency"]) == int(frequency):
                point["proposed"] = int(millivolts)
                break
        self.chart.update()

    def _refresh_summary(self, rows: Sequence[VoltageTableRow]) -> None:
        proposed = [row.proposed for row in rows if row.proposed is not None]
        changed = sum(
            1
            for row in rows
            if row.proposed is not None and row.current and int(row.proposed) != int(row.current)
        )
        added = [row.added for row in rows if row.added is not None]
        parts = [
            tr("{count} points changed").format(count=changed)
            if changed != 1
            else tr("1 point changed")
        ]
        if proposed:
            parts.append(tr("peak {value} mV").format(value=max(proposed)))
        if added:
            top = max(added)
            parts.append(tr("max {value} mV").format(value=f"+{top}" if top > 0 else top))
        self.footer_summary.setText(" · ".join(parts))

    def custom_values(self) -> dict[int, int]:
        return {
            frequency: int(editor.value())
            for frequency, editor in self._editors.items()
        }

    def editors(self) -> tuple[QSpinBox, ...]:
        return tuple(self._editors.values())

    def is_open(self) -> bool:
        return self.isVisible()

    # ------------------------------------------------------------------
    def show_animated(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self._last_focus = QApplication.focusWidget()
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        end = self._drawer_rect()
        self._reflow_controls(end.width())
        start = end.translated(end.width(), 0)
        self._animation.stop()
        try:
            self._animation.finished.disconnect(self._finish_close)
        except TypeError:
            pass
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self._animation.start()
        QTimer.singleShot(self._animation.duration() + 20, self._focus_close_button)

    def _focus_close_button(self) -> None:
        try:
            self.close_button.setFocus(Qt.FocusReason.OtherFocusReason)
        except RuntimeError:
            # The delayed callback can outlive a drawer destroyed by a page
            # refresh or application shutdown.
            pass

    def close_animated(self) -> None:
        if not self.isVisible():
            return
        start = self.drawer.geometry()
        end = start.translated(start.width(), 0)
        self._animation.stop()
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        try:
            self._animation.finished.disconnect()
        except TypeError:
            pass
        self._animation.finished.connect(self._finish_close)
        self._animation.start()

    def _finish_close(self) -> None:
        self.hide()
        focus = self._last_focus
        if isinstance(focus, QWidget):
            try:
                focus.setFocus(Qt.FocusReason.OtherFocusReason)
            except RuntimeError:
                pass
        self.close_requested.emit()

    def _drawer_rect(self) -> QRect:
        horizontal_margin = 3
        top_margin = 8
        bottom_margin = 0
        available = max(0, self.width() - (horizontal_margin * 2))
        if self.width() <= 760:
            width = available
        else:
            width = min(760, max(580, round(self.width() * 0.53)))
        right_offset = 2
        return QRect(
            max(horizontal_margin, self.width() - horizontal_margin - width) + right_offset,
            top_margin,
            width,
            max(0, self.height() - top_margin - bottom_margin),
        )

    def _reflow_controls(self, width: int) -> None:
        profile_columns = 4 if int(width) >= 640 else (2 if int(width) >= 420 else 1)
        if profile_columns != self._profile_columns:
            self._profile_columns = profile_columns
            while self.profile_grid.count():
                self.profile_grid.takeAt(0)
            for index, button in enumerate(self.profile_buttons.values()):
                row, column = divmod(index, profile_columns)
                button.setProperty("gamepadHorizontalGroup", f"voltage-level-{row}")
                button.setProperty("gamepadHorizontalIndex", column)
                self.profile_grid.addWidget(button, row, column)
            for column in range(4):
                self.profile_grid.setColumnStretch(
                    column, 1 if column < profile_columns else 0
                )

        footer_horizontal = int(width) >= 520
        if footer_horizontal != self._footer_horizontal:
            self._footer_horizontal = footer_horizontal
            while self.footer_layout.count():
                self.footer_layout.takeAt(0)
            if footer_horizontal:
                self.footer_layout.addWidget(self.footer_summary, 0, 0)
                self.footer_layout.addWidget(self.restore_button, 0, 1)
                self.footer_layout.addWidget(self.apply_button, 0, 2)
                self.footer_layout.setColumnStretch(0, 1)
                self.footer_layout.setColumnStretch(1, 0)
                self.footer_layout.setColumnStretch(2, 0)
            else:
                self.footer_layout.addWidget(self.footer_summary, 0, 0, 1, 2)
                self.footer_layout.addWidget(self.restore_button, 1, 0)
                self.footer_layout.addWidget(self.apply_button, 1, 1)
                self.footer_layout.setColumnStretch(0, 1)
                self.footer_layout.setColumnStretch(1, 1)
                self.footer_layout.setColumnStretch(2, 0)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        target = self._drawer_rect()
        self._reflow_controls(target.width())
        if self._animation.state() != QPropertyAnimation.State.Running:
            self.drawer.setGeometry(target)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if not self.drawer.geometry().contains(event.position().toPoint()):
            self.close_animated()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.key() in {Qt.Key.Key_Escape, Qt.Key.Key_Back}:
            self.close_animated()
            event.accept()
            return
        super().keyPressEvent(event)
