from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import log10
from typing import Iterable

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..components.async_tools import AsyncRefresh
from ..components.responsive import clear_grid, configure_responsive_scroll_area, effective_viewport_width
from ..core.state import state_cache_for
from ..i18n import tr, tr_format
from ..theme import COLORS, palette_color, scale_stylesheet
from ..components.widgets import IconBadge, PillLabel, apply_shadow


def performance_stylesheet() -> str:
    c = COLORS
    return scale_stylesheet(f"""
QWidget[performancePage='true'] QFrame[resourceRail='true'] {{
    background: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: 18px;
}}
QWidget[performancePage='true'] QLabel[railKicker='true'] {{
    color: {c['blue']}; font-size: 8px; font-weight: 850; letter-spacing: 0.9px;
}}
QWidget[performancePage='true'] QLabel[railTitle='true'] {{
    color: {c['text']}; font-size: 15px; font-weight: 840;
}}
QWidget[performancePage='true'] QLabel[railHint='true'] {{
    color: {c['muted']}; font-size: 9px;
}}
QWidget[performancePage='true'] QFrame[resourceTile='true'] {{
    background: {c['panel']}; border: 1px solid transparent; border-radius: 12px;
}}
QWidget[performancePage='true'] QFrame[resourceTile='true']:hover {{
    background: {c['control_hover']}; border-color: {c['border']};
}}
QWidget[performancePage='true'] QFrame[resourceTile='true'][selected='true'] {{
    background: {c['blue_soft']}; border: 1px solid {c['blue_border']};
}}
QWidget[performancePage='true'] QLabel[resourceTitle='true'] {{
    color: {c['text']}; font-size: 11px; font-weight: 820;
}}
QWidget[performancePage='true'] QLabel[resourceValue='true'] {{
    color: {c['text']}; font-size: 15px; font-weight: 860;
}}
QWidget[performancePage='true'] QLabel[resourceContext='true'] {{
    color: {c['muted']}; font-size: 9px; font-weight: 620;
}}
QWidget[performancePage='true'] QFrame[detailPanel='true'] {{
    background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 18px;
}}
QWidget[performancePage='true'] QFrame[detailHero='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 13px;
}}
QWidget[performancePage='true'] QLabel[detailEyebrow='true'] {{
    color: {c['blue']}; font-size: 8px; font-weight: 850; letter-spacing: 0.8px;
}}
QWidget[performancePage='true'] QLabel[detailTitle='true'] {{
    color: {c['text']}; font-size: 18px; font-weight: 850;
}}
QWidget[performancePage='true'] QLabel[detailSubtitle='true'] {{
    color: {c['muted']}; font-size: 10px;
}}
QWidget[performancePage='true'] QLabel[detailPrimary='true'] {{
    color: {c['text']}; font-size: 38px; font-weight: 880;
}}
QWidget[performancePage='true'] QLabel[detailContext='true'] {{
    color: {c['muted']}; font-size: 11px; font-weight: 660;
}}
QWidget[performancePage='true'] QLabel[legendLabel='true'] {{
    color: {c['muted']}; font-size: 9px; font-weight: 700;
}}
QWidget[performancePage='true'] QFrame[detailStat='true'] {{
    min-height: 50px; background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 11px;
}}
QWidget[performancePage='true'] QLabel[detailStatLabel='true'] {{
    color: {c['subtle']}; font-size: 8px; font-weight: 840; letter-spacing: 0.7px;
}}
QWidget[performancePage='true'] QLabel[detailStatValue='true'] {{
    color: {c['text']}; font-size: 12px; font-weight: 790;
}}
QWidget[performancePage='true'] QLabel[sampleFooter='true'] {{
    color: {c['subtle']}; font-size: 9px; font-weight: 630;
}}
""")



def _number(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _format_bytes(value: float, *, decimals: int = 1) -> str:
    value = max(0.0, float(value or 0.0))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    index = 0
    while value >= 1024.0 and index < len(units) - 1:
        value /= 1024.0
        index += 1
    if index == 0:
        return f"{value:.0f} {units[index]}"
    return f"{value:.{decimals}f} {units[index]}"


def _format_rate(value: float) -> str:
    return f"{_format_bytes(value)}/s"


def _nice_ceiling(value: float) -> float:
    value = max(1.0, float(value))
    exponent = 10 ** max(0, int(log10(value)))
    normalized = value / exponent
    if normalized <= 1:
        step = 1
    elif normalized <= 2:
        step = 2
    elif normalized <= 5:
        step = 5
    else:
        step = 10
    return float(step * exponent)


@dataclass(frozen=True)
class ResourceDefinition:
    key: str
    title: str
    subtitle: str
    icon_name: str
    icon_background: str
    series: tuple[tuple[str, str], ...]
    stat_labels: tuple[str, str, str, str]
    fixed_maximum: float | None = None
    rate_scale: bool = False


RESOURCE_DEFINITIONS = (
    ResourceDefinition(
        "cpu",
        "CPU",
        "Scheduler load and package frequency.",
        "cpu_blue",
        "blue_soft",
        (("Usage", "blue"),),
        ("Frequency", "Temperature", "Load average", "Peak"),
        fixed_maximum=100,
    ),
    ResourceDefinition(
        "gpu",
        "GPU",
        "Graphics engine load, clock, thermals, and power.",
        "gpu_purple",
        "purple_soft",
        (("Usage", "purple"),),
        ("SCLK", "Temperature", "SoC power", "Peak"),
        fixed_maximum=100,
    ),
    ResourceDefinition(
        "vram",
        "VRAM",
        "Dedicated graphics memory pressure.",
        "vram_gray",
        "purple_soft",
        (("Used", "purple"),),
        ("Used", "Available", "Total", "Peak"),
        fixed_maximum=100,
    ),
    ResourceDefinition(
        "memory",
        "RAM",
        "Memory pressure, availability, and swap usage.",
        "memory_green",
        "green_soft",
        (("Used", "green"),),
        ("Used", "Available", "Swap", "Peak"),
        fixed_maximum=100,
    ),
    ResourceDefinition(
        "disk",
        "Disk",
        "Root filesystem usage, throughput, and active I/O time.",
        "disk_orange",
        "orange_soft",
        (("Read", "blue"), ("Write", "orange")),
        ("Used", "Available", "Active time", "Peak I/O"),
        rate_scale=True,
    ),
    ResourceDefinition(
        "network",
        "Network",
        "Traffic on the active default interface.",
        "network_cyan",
        "cyan_soft",
        (("Download", "cyan"), ("Upload", "purple")),
        ("Interface", "Download", "Upload", "Peak"),
        rate_scale=True,
    ),
)
RESOURCE_BY_KEY = {definition.key: definition for definition in RESOURCE_DEFINITIONS}


class PaletteDot(QFrame):
    """Small legend marker that follows live theme and accent changes."""

    def __init__(self, tone: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._tone = str(tone or "blue")
        self.setFixedSize(8, 8)
        self._refresh_palette()

    def _refresh_palette(self) -> None:
        self.setStyleSheet(
            f"background:{palette_color(self._tone)}; border:none; border-radius:4px;"
        )


class MetricHistory:
    def __init__(self, definition: ResourceDefinition):
        self.definition = definition
        self.values = {name: deque(maxlen=120) for name, _color in definition.series}

    def append(self, values: dict[str, float]) -> None:
        for name, _color in self.definition.series:
            self.values[name].append(max(0.0, _number(values.get(name))))

    def peak(self, name: str | None = None) -> float:
        if name is not None:
            return max(self.values.get(name, ()), default=0.0)
        return max((max(values, default=0.0) for values in self.values.values()), default=0.0)

    def maximum(self) -> float:
        if self.definition.fixed_maximum is not None:
            return max(1.0, self.definition.fixed_maximum)
        peak = self.peak()
        return _nice_ceiling(peak * 1.15) if peak > 0 else 1024.0


class Sparkline(QWidget):
    HISTORY_POINTS = 120

    def __init__(self, history: MetricHistory, parent: QWidget | None = None):
        super().__init__(parent)
        self.history = history
        self.setMinimumHeight(28)
        self.setMaximumHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # pragma: no cover - visual rendering
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bounds = QRectF(self.rect()).adjusted(1, 3, -1, -2)
        maximum = self.history.maximum()
        painter.setPen(QPen(QColor(COLORS["chart_grid"]), 1))
        painter.drawLine(int(bounds.left()), int(bounds.bottom()), int(bounds.right()), int(bounds.bottom()))
        for name, color_text in self.history.definition.series:
            values = list(self.history.values[name])
            if not values:
                continue
            padded = [0.0] * max(0, self.HISTORY_POINTS - len(values)) + values
            line = QPainterPath()
            area = QPainterPath()
            for index, value in enumerate(padded):
                x = bounds.left() + bounds.width() * index / max(1, len(padded) - 1)
                y = bounds.bottom() - bounds.height() * min(maximum, value) / maximum
                if index == 0:
                    line.moveTo(x, y)
                    area.moveTo(x, bounds.bottom())
                    area.lineTo(x, y)
                else:
                    line.lineTo(x, y)
                    area.lineTo(x, y)
            area.lineTo(bounds.right(), bounds.bottom())
            area.closeSubpath()
            color = QColor(palette_color(color_text))
            fill = QColor(color)
            fill.setAlpha(20)
            painter.fillPath(area, fill)
            painter.setPen(QPen(color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(line)


class ResourceTile(QFrame):
    activated = pyqtSignal(str)

    def __init__(self, definition: ResourceDefinition, history: MetricHistory, parent: QWidget | None = None):
        super().__init__(parent)
        self.definition = definition
        self.history = history
        self.setProperty("resourceTile", True)
        self.setProperty("selected", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(50)
        self.setMaximumHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(8)
        root.addWidget(IconBadge(definition.icon_name, definition.icon_background, 28, radius=8), 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = QLabel(tr(definition.title))
        self.title.setProperty("resourceTitle", True)
        root.addWidget(self.title, 1)

    def set_values(self, primary: str, context: str) -> None:
        self.setToolTip(f"{tr(self.definition.title)}\n{primary}\n{context}")

    def set_selected(self, selected: bool) -> None:
        if bool(self.property("selected")) == bool(selected):
            return
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def gamepad_activate(self) -> None:
        self.activated.emit(self.definition.key)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.definition.key)
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit(self.definition.key)
            event.accept()
            return
        super().keyPressEvent(event)


class DetailStat(QFrame):
    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("detailStat", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 9, 11, 9)
        layout.setSpacing(2)
        self.label = QLabel(tr(label).upper())
        self.label.setProperty("detailStatLabel", True)
        self.value = QLabel("--")
        self.value.setProperty("detailStatValue", True)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.label)
        layout.addWidget(self.value)

    def set_label(self, label: str) -> None:
        self.label.setText(tr(label).upper())

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class DetailGraph(QWidget):
    HISTORY_POINTS = 120

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.history: MetricHistory | None = None
        self.setMinimumHeight(330)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_history(self, history: MetricHistory) -> None:
        self.history = history
        self.update()

    def _scale_text(self, value: float) -> str:
        if self.history is None:
            return "--"
        if self.history.definition.rate_scale:
            return _format_rate(value)
        return f"{value:.0f}%"

    def paintEvent(self, event) -> None:  # pragma: no cover - visual rendering
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        outer = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.setBrush(QColor(COLORS["chart_surface"]))
        painter.drawRoundedRect(outer, 13, 13)
        if self.history is None:
            return

        plot = outer.adjusted(68, 18, -15, -32)
        maximum = self.history.maximum()
        painter.setPen(QPen(QColor(COLORS["chart_grid"]), 1))
        for index in range(5):
            y = plot.top() + plot.height() * index / 4
            painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))
        for index in range(9):
            x = plot.left() + plot.width() * index / 8
            painter.drawLine(int(x), int(plot.top()), int(x), int(plot.bottom()))

        painter.setPen(QColor(COLORS["subtle"]))
        font = painter.font()
        font.setPointSize(8)
        font.setWeight(650)
        painter.setFont(font)
        for index in range(5):
            value = maximum * (4 - index) / 4
            y = plot.top() + plot.height() * index / 4 - 7
            label = "0" if index == 4 else self._scale_text(value)
            painter.drawText(QRectF(outer.left() + 8, y, 54, 16), Qt.AlignmentFlag.AlignRight, label)
        painter.drawText(QRectF(plot.left(), plot.bottom() + 7, 62, 15), Qt.AlignmentFlag.AlignLeft, tr("2 min"))
        painter.drawText(QRectF(plot.center().x() - 26, plot.bottom() + 7, 52, 15), Qt.AlignmentFlag.AlignCenter, tr("1 min"))
        painter.drawText(QRectF(plot.right() - 42, plot.bottom() + 7, 42, 15), Qt.AlignmentFlag.AlignRight, tr("Now"))

        for name, color_text in self.history.definition.series:
            values = list(self.history.values[name])
            if not values:
                continue
            padded = [0.0] * max(0, self.HISTORY_POINTS - len(values)) + values
            line = QPainterPath()
            area = QPainterPath()
            for index, value in enumerate(padded):
                x = plot.left() + plot.width() * index / max(1, len(padded) - 1)
                y = plot.bottom() - plot.height() * min(maximum, value) / maximum
                if index == 0:
                    line.moveTo(x, y)
                    area.moveTo(x, plot.bottom())
                    area.lineTo(x, y)
                else:
                    line.lineTo(x, y)
                    area.lineTo(x, y)
            area.lineTo(plot.right(), plot.bottom())
            area.closeSubpath()
            color = QColor(palette_color(color_text))
            fill = QColor(color)
            fill.setAlpha(18)
            painter.fillPath(area, fill)
            painter.setPen(QPen(color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(line)

        painter.setPen(QPen(QColor(COLORS["chart_axis"]), 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(plot.right()), int(plot.top()), int(plot.right()), int(plot.bottom()))


class DetailPanel(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("detailPanel", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(560)
        apply_shadow(self, blur=14, y=3, alpha=9)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(18, 17, 18, 15)
        self.root.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(11)
        self.icon_host = QHBoxLayout()
        self.icon_host.setContentsMargins(0, 0, 0, 0)
        header.addLayout(self.icon_host)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        self.title = QLabel(tr("CPU"))
        self.title.setProperty("detailTitle", True)
        self.subtitle = QLabel(tr("Waiting for first sample"))
        self.subtitle.setProperty("detailSubtitle", True)
        self.subtitle.setWordWrap(True)
        copy.addWidget(self.title)
        copy.addWidget(self.subtitle)
        header.addLayout(copy, 1)
        self.sample_state = PillLabel(tr("Paused"), "gray")
        header.addWidget(self.sample_state, 0, Qt.AlignmentFlag.AlignTop)
        self.root.addLayout(header)

        hero = QFrame()
        hero.setProperty("detailHero", True)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(14, 11, 14, 11)
        hero_layout.setSpacing(14)
        current_copy = QVBoxLayout()
        current_copy.setSpacing(0)
        current_label = QLabel(tr("CURRENT"))
        current_label.setProperty("detailEyebrow", True)
        self.primary = QLabel("--")
        self.primary.setProperty("detailPrimary", True)
        self.primary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        current_copy.addWidget(current_label)
        current_copy.addWidget(self.primary)
        hero_layout.addLayout(current_copy)
        hero_layout.addStretch(1)
        self.context = QLabel(tr("Waiting for sample"))
        self.context.setProperty("detailContext", True)
        self.context.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.context.setWordWrap(True)
        self.context.setMaximumWidth(330)
        hero_layout.addWidget(self.context)
        self.root.addWidget(hero)

        graph_header = QHBoxLayout()
        graph_header.setSpacing(10)
        graph_label = QLabel(tr("LIVE HISTORY"))
        graph_label.setProperty("detailEyebrow", True)
        graph_header.addWidget(graph_label)
        graph_header.addStretch(1)
        self.legend = QHBoxLayout()
        self.legend.setSpacing(10)
        graph_header.addLayout(self.legend)
        self.root.addLayout(graph_header)

        self.graph = DetailGraph()
        self.root.addWidget(self.graph, 1)

        self.stats_grid = QGridLayout()
        self.stats_grid.setContentsMargins(0, 0, 0, 0)
        self.stats_grid.setHorizontalSpacing(8)
        self.stats_grid.setVerticalSpacing(8)
        self.stats = [DetailStat(tr("Metric")) for _ in range(4)]
        self._stats_columns = 0
        self._reflow_stats(900)
        self.root.addLayout(self.stats_grid)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.footer_left = QLabel(tr("120 samples · 1 s cadence · 2 minute window"))
        self.footer_left.setProperty("sampleFooter", True)
        footer.addWidget(self.footer_left)
        footer.addStretch(1)
        self.footer_right = QLabel(tr("Last sample --:--:--"))
        self.footer_right.setProperty("sampleFooter", True)
        footer.addWidget(self.footer_right)
        self.root.addLayout(footer)

    def _reflow_stats(self, width: int) -> None:
        columns = 4 if width >= 780 else 2 if width >= 420 else 1
        if columns == self._stats_columns and self.stats_grid.count():
            return
        self._stats_columns = columns
        clear_grid(self.stats_grid)
        for index, stat in enumerate(self.stats):
            self.stats_grid.addWidget(stat, index // columns, index % columns)
        for column in range(columns):
            self.stats_grid.setColumnStretch(column, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._reflow_stats(event.size().width())

    @staticmethod
    def _clear_layout(layout: QHBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def select_resource(self, definition: ResourceDefinition, history: MetricHistory) -> None:
        self._clear_layout(self.icon_host)
        self.icon_host.addWidget(IconBadge(definition.icon_name, definition.icon_background, 42, radius=11))
        self.title.setText(tr(definition.title))
        self.subtitle.setText(tr(definition.subtitle))
        self.graph.set_history(history)
        self._clear_layout(self.legend)
        for name, color in definition.series:
            self.legend.addWidget(PaletteDot(color))
            label = QLabel(tr(name))
            label.setProperty("legendLabel", True)
            self.legend.addWidget(label)
        for stat, label in zip(self.stats, definition.stat_labels):
            stat.set_label(tr(label))
        self.graph.update()

    def set_values(self, primary: str, context: str, values: Iterable[str], *, sampled_at: str) -> None:
        self.primary.setText(primary)
        self.context.setText(context)
        for stat, value in zip(self.stats, values):
            stat.set_value(value)
        self.footer_right.setText(tr_format("Last sample {time}", time=sampled_at))
        self.graph.update()


class PerformancePage(QWidget):
    def apply_appearance(self) -> None:
        if hasattr(self, "content"):
            self.content.setStyleSheet(performance_stylesheet())
            self.content.update()

    """Passive CPU/GPU/VRAM/RAM/disk/network monitor sampled only while visible."""

    SAMPLE_INTERVAL_MS = 1000

    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self._state_cache = state_cache_for(controller)
        self._layout_mode = 0
        self._selected_key = "cpu"
        self._last_error = ""
        self._sample_views: dict[str, tuple[str, str, tuple[str, str, str, str]]] = {}
        self.histories = {definition.key: MetricHistory(definition) for definition in RESOURCE_DEFINITIONS}
        self.setProperty("performancePage", True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        self.scroll = scroll
        self.content = QWidget()
        self.content.setProperty("performancePage", True)
        self.content.setStyleSheet(performance_stylesheet())
        configure_responsive_scroll_area(scroll, self.content)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(18, 8, 18, 24)
        layout.setSpacing(14)
        scroll.setWidget(self.content)
        outer.addWidget(scroll)

        self.workspace = QGridLayout()
        self.workspace.setContentsMargins(0, 0, 0, 0)
        self.workspace.setHorizontalSpacing(14)
        self.workspace.setVerticalSpacing(14)
        layout.addLayout(self.workspace, 1)

        self.resource_host = QFrame()
        self.resource_host.setProperty("resourceBar", True)
        self.resource_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        rail_layout = QVBoxLayout(self.resource_host)
        rail_layout.setContentsMargins(14, 12, 14, 12)
        rail_layout.setSpacing(0)
        self.resource_grid = QGridLayout()
        self.resource_grid.setContentsMargins(0, 0, 0, 0)
        self.resource_grid.setHorizontalSpacing(10)
        self.resource_grid.setVerticalSpacing(10)
        rail_layout.addLayout(self.resource_grid)

        self.tiles: dict[str, ResourceTile] = {}
        for definition in RESOURCE_DEFINITIONS:
            tile = ResourceTile(definition, self.histories[definition.key])
            tile.activated.connect(self._select_resource)
            self.tiles[definition.key] = tile

        self.detail = DetailPanel()
        self.detail.select_resource(RESOURCE_BY_KEY[self._selected_key], self.histories[self._selected_key])
        self.tiles[self._selected_key].set_selected(True)

        self._updates_active = False
        self.timer = QTimer(self)
        self.timer.setInterval(self.SAMPLE_INTERVAL_MS)
        self.timer.timeout.connect(self.refresh)
        self._refresher = AsyncRefresh(
            self,
            "performance-sample",
            self._state_cache.realtime_metrics,
            self._sample_ready,
            self._sample_failed,
        )
        self._reflow(1400)

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if self._updates_active:
            self.detail.sample_state.setText(tr("Sampling"))
            self.detail.sample_state.set_tone("green")
            if not self.timer.isActive():
                self.timer.start()
            self._refresher.activate(fresh_for=0.75, refresh_delay_ms=60)
        else:
            self._refresher.set_active(False)
            self.timer.stop()
            self.detail.sample_state.setText(tr("Paused"))
            self.detail.sample_state.set_tone("gray")

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # Central navigation normally starts sampling before the page is shown.
        # Restart only after an external hide/show cycle; do not activate the
        # refresher twice during an ordinary QStackedWidget transition.
        if self._updates_active and not self.timer.isActive():
            self.timer.start()
            self._refresher.activate(fresh_for=0.75, refresh_delay_ms=60)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._refresher.set_active(False)
        self.timer.stop()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow(effective_viewport_width(self, self.scroll))

    @staticmethod
    def _clear_grid(layout: QGridLayout) -> None:
        clear_grid(layout)

    def _reflow(self, width: int) -> None:
        columns = 6 if width >= 1320 else 3 if width >= 760 else 2 if width >= 480 else 1
        if columns == self._layout_mode:
            return
        self._layout_mode = columns
        self._clear_grid(self.workspace)
        self._clear_grid(self.resource_grid)
        for index, definition in enumerate(RESOURCE_DEFINITIONS):
            row, column = divmod(index, columns)
            self.resource_grid.addWidget(self.tiles[definition.key], row, column)
            self.resource_grid.setColumnStretch(column, 1)
        self.workspace.addWidget(self.resource_host, 0, 0)
        self.workspace.addWidget(self.detail, 1, 0)
        self.workspace.setColumnStretch(0, 1)

    def _select_resource(self, key: str) -> None:
        if key not in RESOURCE_BY_KEY:
            return
        self._selected_key = key
        for tile_key, tile in self.tiles.items():
            tile.set_selected(tile_key == key)
        self.detail.select_resource(RESOURCE_BY_KEY[key], self.histories[key])
        self._refresh_detail()

    def refresh(self) -> None:
        if not self._updates_active or not self.isVisible():
            return
        self._refresher.request()

    def _sample_failed(self, message: str) -> None:
        self._last_error = message
        self.detail.sample_state.setText(tr("Read error"))
        self.detail.sample_state.set_tone("red")

    def _set_resource(
        self,
        key: str,
        *,
        primary: str,
        context: str,
        graph_values: dict[str, float],
        stats: tuple[str, str, str, str],
    ) -> None:
        self.histories[key].append(graph_values)
        self._sample_views[key] = (primary, context, stats)
        self.tiles[key].set_values(primary, context)

    def _sample_ready(self, sample: dict) -> None:
        from datetime import datetime

        self._last_error = ""
        self.detail.sample_state.setText(tr("Sampling"))
        self.detail.sample_state.set_tone("green")

        cpu = dict(sample.get("cpu") or {})
        cpu_usage = _number(cpu.get("usage_percent"))
        cpu_freq = _number(cpu.get("frequency_mhz"))
        cpu_temp = cpu.get("temperature_c")
        load_average = list(cpu.get("load_average") or [])
        cpu_peak = max(self.histories["cpu"].peak("Usage"), cpu_usage)
        self._set_resource(
            "cpu",
            primary=f"{cpu_usage:.0f}%",
            context=f"{cpu_freq / 1000:.2f} GHz" if cpu_freq else tr("Frequency unavailable"),
            graph_values={"Usage": cpu_usage},
            stats=(
                f"{cpu_freq / 1000:.2f} GHz" if cpu_freq else "--",
                f"{_number(cpu_temp):.1f} °C" if cpu_temp is not None else "--",
                f"{_number(load_average[0]):.2f}" if load_average else "--",
                f"{cpu_peak:.0f}%",
            ),
        )

        gpu = dict(sample.get("gpu") or {})
        gpu_usage_value = gpu.get("usage_percent")
        gpu_usage = _number(gpu_usage_value)
        gpu_freq = _number(gpu.get("frequency_mhz"))
        gpu_temp = gpu.get("temperature_c")
        gpu_power = gpu.get("power_w")
        gpu_peak = max(self.histories["gpu"].peak("Usage"), gpu_usage)
        self._set_resource(
            "gpu",
            primary=f"{gpu_usage:.0f}%" if gpu_usage_value is not None else "--",
            context=f"{gpu_freq:.0f} MHz" if gpu_freq else "AMDGPU",
            graph_values={"Usage": gpu_usage},
            stats=(
                f"{gpu_freq:.0f} MHz" if gpu_freq else "--",
                f"{_number(gpu_temp):.1f} °C" if gpu_temp is not None else "--",
                f"{_number(gpu_power):.1f} W" if gpu_power is not None else "--",
                f"{gpu_peak:.0f}%",
            ),
        )

        vram_used = _number(gpu.get("vram_used"))
        vram_total = _number(gpu.get("vram_total"))
        vram_percent = vram_used * 100.0 / vram_total if vram_total > 0 else 0.0
        vram_available = max(0.0, vram_total - vram_used)
        vram_peak = max(self.histories["vram"].peak("Used"), vram_percent)
        self._set_resource(
            "vram",
            primary=f"{vram_percent:.0f}%" if vram_total else "--",
            context=f"{_format_bytes(vram_used)} / {_format_bytes(vram_total)}" if vram_total else tr("Counters unavailable"),
            graph_values={"Used": vram_percent},
            stats=(
                _format_bytes(vram_used) if vram_total else "--",
                _format_bytes(vram_available) if vram_total else "--",
                _format_bytes(vram_total) if vram_total else "--",
                f"{vram_peak:.0f}%" if vram_total else "--",
            ),
        )

        memory = dict(sample.get("memory") or {})
        memory_percent = _number(memory.get("usage_percent"))
        memory_used = _number(memory.get("used"))
        memory_total = _number(memory.get("total"))
        memory_available = _number(memory.get("available"))
        swap_percent = _number(memory.get("swap_percent"))
        memory_peak = max(self.histories["memory"].peak("Used"), memory_percent)
        self._set_resource(
            "memory",
            primary=f"{memory_percent:.0f}%",
            context=f"{_format_bytes(memory_used)} / {_format_bytes(memory_total)}",
            graph_values={"Used": memory_percent},
            stats=(
                _format_bytes(memory_used),
                _format_bytes(memory_available),
                f"{swap_percent:.0f}%",
                f"{memory_peak:.0f}%",
            ),
        )

        disk = dict(sample.get("disk") or {})
        disk_usage = _number(disk.get("usage_percent"), -1.0)
        disk_used = _number(disk.get("used"))
        disk_total = _number(disk.get("total"))
        disk_available = max(0.0, disk_total - disk_used)
        read_bps = _number(disk.get("read_bps"))
        write_bps = _number(disk.get("write_bps"))
        active = _number(disk.get("active_percent"))
        disk_peak = max(self.histories["disk"].peak(), read_bps, write_bps)
        disk_usage_available = disk_total > 0 and disk_usage >= 0
        disk_capacity = (
            f"{_format_bytes(disk_used)} / {_format_bytes(disk_total)}"
            if disk_usage_available
            else tr("Capacity unavailable")
        )
        self._set_resource(
            "disk",
            primary=f"{disk_usage:.0f}%" if disk_usage_available else "--",
            context=f"{disk_capacity} · ↓ {_format_rate(read_bps)} · ↑ {_format_rate(write_bps)}",
            graph_values={"Read": read_bps, "Write": write_bps},
            stats=(
                _format_bytes(disk_used) if disk_usage_available else "--",
                _format_bytes(disk_available) if disk_usage_available else "--",
                f"{active:.0f}%",
                _format_rate(disk_peak),
            ),
        )

        network = dict(sample.get("network") or {})
        download = _number(network.get("download_bps"))
        upload = _number(network.get("upload_bps"))
        network_peak = max(self.histories["network"].peak(), download, upload)
        interface = str(network.get("interface") or tr("not detected"))
        self._set_resource(
            "network",
            primary=f"↓ {_format_rate(download)}",
            context=f"↑ {_format_rate(upload)} · {interface}",
            graph_values={"Download": download, "Upload": upload},
            stats=(
                interface,
                _format_rate(download),
                _format_rate(upload),
                _format_rate(network_peak),
            ),
        )

        self._sample_time = datetime.now().strftime("%H:%M:%S")
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        view = self._sample_views.get(self._selected_key)
        if view is None:
            return
        primary, context, stats = view
        self.detail.set_values(primary, context, stats, sampled_at=getattr(self, "_sample_time", "--:--:--"))
