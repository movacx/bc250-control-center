from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from html import escape
from math import log10
from typing import Callable, Iterable

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QKeyEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from bc250cc.infrastructure.sensor_inventory import SensorInventory

from ..components.async_tools import AsyncRefresh
from ..components.chart_axes import (
    ValueAxis,
    format_age,
    range_axis,
    ticks_for_height,
    time_ticks,
    value_axis,
    zoomed_percent_axis,
)
from ..components.chart_strokes import draw_series, fill_area
from ..components.responsive import (
    clear_grid,
    configure_responsive_scroll_area,
    effective_viewport_width,
)
from ..components.widgets import IconBadge, PillLabel, apply_shadow, readable_text_on
from ..core.gddr6_monitor import gddr6_monitor_for
from ..core.performance_sample_presenter import present_performance_sample
from ..core.performance_views import (
    MAX_LINES,
    VIEW_BY_KEY,
    MetricView,
    available_views,
    series_label,
    views_for,
)
from ..core.sensor_log import SensorLog, format_sensor_value
from ..core.state import state_cache_for
from ..i18n import tr, tr_format
from ..theme import COLORS, palette_color, scale_stylesheet
from .performance_sensors import SensorBoard

logger = logging.getLogger(__name__)


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
    color: {c['text']}; font-size: 20px; font-weight: 860;
}}
QWidget[performancePage='true'] QLabel[detailContext='true'] {{
    color: {c['muted']}; font-size: 11px; font-weight: 650;
}}
QWidget[performancePage='true'] QLabel[legendLabel='true'] {{
    color: {c['muted']}; font-size: 10px; font-weight: 650;
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
QWidget[performancePage='true'] QPushButton[scaleMode='true'] {{
    min-height: 0; padding: 2px 9px; border-radius: 7px; font-size: 9px; font-weight: 750;
    background: transparent; color: {c['muted']}; border: 1px solid {c['border_soft']};
}}
QWidget[performancePage='true'] QPushButton[scaleMode='true']:checked {{
    background: {c['blue_soft']}; color: {c['blue']}; border-color: {c['blue_border']};
}}
QWidget[performancePage='true'] QPushButton[viewSwitch='true'] {{
    min-height: 0; padding: 2px 10px; border-radius: 7px; font-size: 9px; font-weight: 780;
    background: {c['panel_alt']}; color: {c['text']}; border: 1px solid {c['border']};
}}
QWidget[performancePage='true'] QPushButton[viewSwitch='true']:hover {{
    background: {c['control_hover']}; border-color: {c['blue_border']};
}}
QWidget[performancePage='true'] QFrame[viewFlyout='true'] {{
    background: {c['panel_raised']}; border: 1px solid {c['border_strong']}; border-radius: 10px;
}}
QWidget[performancePage='true'] QLabel[viewFlyoutHeading='true'] {{
    color: {c['muted']}; font-size: 9px; font-weight: 780;
}}
QWidget[performancePage='true'] QFrame[viewRow='true'] {{
    background: transparent; border: 1px solid transparent; border-radius: 7px;
}}
QWidget[performancePage='true'] QFrame[viewRow='true']:hover,
QWidget[performancePage='true'] QFrame[viewRow='true']:focus {{
    background: {c['control_hover']}; border-color: {c['border_soft']};
}}
QWidget[performancePage='true'] QFrame[viewRow='true'][current='true'] {{
    background: {c['blue_soft']}; border-color: {c['blue_border']};
}}
QWidget[performancePage='true'] QLabel[viewRowTitle='true'] {{
    color: {c['text']}; font-size: 11px; font-weight: 760;
}}
QWidget[performancePage='true'] QLabel[viewRowTitle='true'][current='true'] {{
    color: {c['blue']};
}}
QWidget[performancePage='true'] QLabel[viewRowHint='true'] {{
    color: {c['muted']}; font-size: 9px;
}}
QWidget[performancePage='true'] QLabel[viewRowTitle='true']:disabled,
QWidget[performancePage='true'] QLabel[viewRowHint='true']:disabled {{
    color: {c['disabled_text']};
}}
QWidget[performancePage='true'] QFrame[sensorBoard='true'] {{
    background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 18px;
}}
QWidget[performancePage='true'] QTreeView#sensorTree {{
    background: {c['panel']}; alternate-background-color: {c['panel_alt']};
    border: 1px solid {c['border_soft']}; border-radius: 8px;
    font-size: 11px; color: {c['text']};
    selection-background-color: {c['blue_soft']}; selection-color: {c['text']};
    outline: 0;
}}
QWidget[performancePage='true'] QTreeView#sensorTree::item {{
    padding: 2px 4px; min-height: 22px; border: none;
}}
QWidget[performancePage='true'] QTreeView#sensorTree QHeaderView::section {{
    background: {c['panel_alt']}; color: {c['muted']}; font-size: 9px; font-weight: 820;
    border: none; border-bottom: 1px solid {c['border']}; padding: 5px 8px;
}}
QWidget[performancePage='true'] QLineEdit#sensorFilter {{
    min-height: 0px; padding: 2px 10px; font-size: 11px; border-radius: 7px;
}}
QWidget[performancePage='true'] QPushButton[kindChip='true'] {{
    min-height: 0; padding: 3px 10px; border-radius: 7px; font-size: 10px; font-weight: 720;
    background: transparent; color: {c['muted']}; border: 1px solid {c['border_soft']};
}}
QWidget[performancePage='true'] QPushButton[kindChip='true']:hover {{
    background: {c['control_hover']}; color: {c['text']};
}}
QWidget[performancePage='true'] QPushButton[kindChip='true']:checked {{
    background: {c['blue_soft']}; color: {c['text']}; border-color: {c['blue_border']};
}}
QWidget[performancePage='true'] QTreeView#sensorTree::indicator {{
    width: 12px; height: 12px; border-radius: 3px;
    border: 1px solid {c['border_strong']}; background: {c['panel']};
}}
QWidget[performancePage='true'] QTreeView#sensorTree::indicator:checked {{
    border-color: {c['blue']}; background: {c['blue']};
}}
QWidget[performancePage='true'] QSplitter::handle {{
    background: transparent;
}}
QWidget[performancePage='true'] QLabel#sensorPlotsEmpty {{
    color: {c['muted']}; font-size: 10px; padding: 24px;
}}
QWidget[performancePage='true'] QWidget#sensorPlotsBody {{
    background: transparent;
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
    #: What the values are measured in: "%" (the summaries), or the unit of a
    #: view (MHz, °C, W, V), which frames its own range instead of 0–100.
    unit: str = "%"
    #: "lines", or "heatmap" for a view with one row per thread.
    form: str = "lines"


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

#: The smallest range a view's axis spans, so an idle reading is not blown up
#: into a jagged line filling the plot.
_MINIMUM_SPAN = {"MHz": 200.0, "°C": 10.0, "W": 10.0, "V": 0.1}


def view_definition(view: MetricView, names: Iterable[str]) -> ResourceDefinition:
    """The chart definition of a view, once its series are known."""
    names = tuple(names)
    resource = RESOURCE_BY_KEY[view.resource]
    single = len(names) == 1
    return ResourceDefinition(
        view.key,
        view.title,
        view.hint,
        resource.icon_name,
        resource.icon_background,
        # A series keeps its slot (core 3 is always the fourth colour), and
        # past eight there are no more slots: those views are heat maps.
        tuple((name, f"series_{index + 1}" if index < MAX_LINES else "blue") for index, name in enumerate(names)),
        ("Now", "Minimum", "Average", "Maximum") if single else ("Highest", "Lowest", "Mean", "Window peak"),
        fixed_maximum=100 if view.unit == "%" else None,
        unit=view.unit,
        form=view.form,
    )


class MetricHistory:
    """The last two minutes of one resource, with when each sample arrived.

    Timestamps place every point where it belongs on the time axis, so a
    stalled or late sample shows as a gap instead of silently compressing the
    rest of the line.
    """

    WINDOW_SECONDS = 120

    def __init__(self, definition: ResourceDefinition):
        self.definition = definition
        self.values = {name: deque(maxlen=120) for name, _color in definition.series}
        self.times: deque[float] = deque(maxlen=120)
        #: Bumped by every sample, so a chart knows its cached drawing is stale.
        self.revision = 0

    def append(self, values: dict[str, float], *, moment: float | None = None) -> None:
        self.times.append(time.monotonic() if moment is None else float(moment))
        for name, _color in self.definition.series:
            self.values[name].append(max(0.0, _number(values.get(name))))
        self.revision += 1

    def peak(self, name: str | None = None) -> float:
        if name is not None:
            return max(self.values.get(name, ()), default=0.0)
        return max((max(values, default=0.0) for values in self.values.values()), default=0.0)

    def average(self, name: str) -> float | None:
        values = self.values.get(name) or ()
        return sum(values) / len(values) if values else None

    def low(self) -> float:
        """The lowest value of any series in the window."""
        return min((min(values) for values in self.values.values() if values), default=0.0)

    def maximum(self) -> float:
        if self.definition.fixed_maximum is not None:
            return max(1.0, self.definition.fixed_maximum)
        peak = self.peak()
        return _nice_ceiling(peak * 1.15) if peak > 0 else 1024.0


_RATE_UNITS = (("B/s", 1.0), ("KiB/s", 1024.0), ("MiB/s", 1024.0 ** 2), ("GiB/s", 1024.0 ** 3))


def rate_axis(peak: float, *, target_ticks: int = 5) -> tuple[ValueAxis, str, float]:
    """A throughput axis in the unit its peak reads best in, never below KiB/s."""
    wanted = max(1024.0, float(peak) * 1.15)
    name, factor = _RATE_UNITS[1]
    for candidate, candidate_factor in _RATE_UNITS[1:]:
        if wanted >= candidate_factor:
            name, factor = candidate, candidate_factor
    return value_axis(peak / factor, minimum_span=1.0, target_ticks=target_ticks), name, factor


def _tick_text(value: float) -> str:
    return f"{value:.0f}" if abs(value - round(value)) < 1e-6 else f"{value:g}"


class ResourceTile(QFrame):
    activated = pyqtSignal(str)
    #: The pointer came onto the tile (True) or left it (False).
    hover_changed = pyqtSignal(str, bool)
    #: Asked for its other views without a pointer: X on a controller,
    #: the context-menu key, a right click.
    views_requested = pyqtSignal(str)

    def __init__(self, definition: ResourceDefinition, history: MetricHistory, parent: QWidget | None = None):
        super().__init__(parent)
        self.definition = definition
        self.history = history
        self.reading: tuple[str, str] = ("--", "")
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
        self.reading = (primary, context)
        # A tile with views shows its reading in the views menu instead; two
        # boxes opening on one hover would cover each other.
        if not self.has_views():
            self.setToolTip(f"{tr(self.definition.title)}\n{primary}\n{context}")

    def has_views(self) -> bool:
        return len(views_for(self.definition.key)) > 1

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        self.hover_changed.emit(self.definition.key, True)

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self.hover_changed.emit(self.definition.key, False)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        if self.has_views():
            self.views_requested.emit(self.definition.key)
            event.accept()
            return
        super().contextMenuEvent(event)

    # X on a controller opens the views; A still selects the tile.
    def gamepad_secondary(self) -> None:
        self.views_requested.emit(self.definition.key)

    def gamepad_secondary_available(self) -> bool:
        return self.has_views()

    @staticmethod
    def gamepad_secondary_label() -> str:
        return "Views"

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


class _ViewRow(QFrame):
    """One view in the menu: its name over one line of what it shows."""

    chosen = pyqtSignal(str)

    def __init__(self, view: MetricView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.view = view
        self.setProperty("viewRow", True)
        self.setProperty("current", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(1)
        self.title = QLabel(tr(view.title))
        self.title.setProperty("viewRowTitle", True)
        self.hint = QLabel(tr(view.hint))
        self.hint.setProperty("viewRowHint", True)
        self.hint.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.hint)

    def set_state(self, *, current: bool, available: bool) -> None:
        self.setEnabled(available)
        self.hint.setText(tr(self.view.hint if available or not self.view.unavailable_hint else self.view.unavailable_hint))
        if bool(self.property("current")) != current:
            self.setProperty("current", current)
            for widget in (self, self.title):
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def gamepad_activate(self) -> None:
        if self.isEnabled():
            self.chosen.emit(self.view.key)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.gamepad_activate()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.gamepad_activate()
            event.accept()
            return
        super().keyPressEvent(event)


class ResourceViewFlyout(QFrame):
    """The views of one tile, dropped under it while the pointer is there.

    A child of the page rather than a window of its own: it scrolls with the
    tile, needs no popup placement from the compositor, and a pointer moving
    from the tile into it never crosses a window boundary.
    """

    view_chosen = pyqtSignal(str, str)
    hover_changed = pyqtSignal(bool)
    dismissed = pyqtSignal()

    WIDTH = 300

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setProperty("viewFlyout", True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        apply_shadow(self, blur=22, y=6, alpha=22)
        self.resource = ""
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 8, 6, 6)
        self._layout.setSpacing(2)
        self.heading = QLabel("")
        self.heading.setProperty("viewFlyoutHeading", True)
        self.heading.setProperty("i18nLiteral", True)
        self.heading.setContentsMargins(10, 0, 10, 4)
        self._layout.addWidget(self.heading)
        self.rows: list[_ViewRow] = []
        self.hide()

    def present(
        self,
        resource: str,
        *,
        heading: str,
        current: str,
        available: set[str],
        anchor: QRect,
    ) -> None:
        if resource != self.resource:
            for row in self.rows:
                row.setParent(None)
                row.deleteLater()
            self.rows = []
            for view in views_for(resource):
                row = _ViewRow(view, self)
                row.chosen.connect(lambda key, owner=resource: self.view_chosen.emit(owner, key))
                self._layout.addWidget(row)
                # Added to a menu already on screen (the pointer slid from
                # one tile to the next), a row stays hidden until the next
                # pass of the event loop, and the menu below was measured
                # without it: an empty strip under the tile.
                row.show()
                self.rows.append(row)
            self.resource = resource
        self.heading.setText(heading)
        for row in self.rows:
            row.set_state(current=row.view.key == current, available=row.view.key in available)
        width = max(self.WIDTH, anchor.width())
        self.setFixedWidth(width)
        self._layout.activate()
        self.adjustSize()
        host = self.parentWidget()
        left = min(anchor.left(), max(0, host.width() - width - 4))
        self.move(left, anchor.bottom() + 6)
        self.show()
        self.raise_()

    def focus_current(self) -> None:
        row = next((row for row in self.rows if bool(row.property("current"))), None)
        target = row or next((row for row in self.rows if row.isEnabled()), None)
        if target is not None:
            target.setFocus(Qt.FocusReason.OtherFocusReason)

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        self.hover_changed.emit(True)

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self.hover_changed.emit(False)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.dismissed.emit()
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


@dataclass
class _ChartFrame:
    """Where the cached drawing put things, for the pointer readout over it."""

    plot: QRectF
    times: list[float]
    now: float
    x_for: Callable[[float], float]
    y_for: Callable[[float], float] | None = None
    names: tuple[str, ...] = ()
    row_height: float = 0.0


class DetailGraph(QWidget):
    """Two minutes of history on axes a reading can be taken from.

    The scale gets finer as the chart gets taller (one labelled step per
    ~48 px, half steps in between), time is marked on round seconds counted
    back from now with five-second ticks, and each series ends in a tag with
    its latest value on the right edge. A missed sample breaks the line
    instead of bridging it. Single-series charts add the window average and
    peak, and the pointer reads the exact values under it. Percent resources
    can zoom to the smallest round range that holds the data (Auto) or show
    the whole 0–100 % scale.
    """

    HISTORY_POINTS = 120
    #: Two samples further apart than this are drawn as a gap: the reader
    #: missed at least one second-long cadence in between.
    GAP_SECONDS = 3.5

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.history: MetricHistory | None = None
        self.scale_mode = "auto"
        self._hover_x: float | None = None
        self._hover_y: float | None = None
        self._cache: QPixmap | None = None
        self._cache_key_value: tuple | None = None
        self._frame: _ChartFrame | None = None
        self.setMinimumHeight(330)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_history(self, history: MetricHistory) -> None:
        self.history = history
        self.update()

    def set_scale_mode(self, mode: str) -> None:
        self.scale_mode = "full" if mode == "full" else "auto"
        self.update()

    def axis(self, target_ticks: int = 5) -> tuple[ValueAxis, str, float]:
        """The value axis, its unit and the factor raw values are divided by."""
        if self.history is None:
            return value_axis(0, fixed_maximum=100, target_ticks=target_ticks), "%", 1.0
        definition = self.history.definition
        peak = self.history.peak()
        if definition.rate_scale:
            return rate_axis(peak, target_ticks=target_ticks)
        if definition.unit != "%":
            if self.scale_mode == "full":
                return value_axis(peak, target_ticks=target_ticks), definition.unit, 1.0
            return (
                range_axis(
                    self.history.low(),
                    peak,
                    minimum_span=_MINIMUM_SPAN.get(definition.unit, 1.0),
                    target_ticks=target_ticks,
                ),
                definition.unit,
                1.0,
            )
        if self.scale_mode == "full" or definition.fixed_maximum is None:
            return value_axis(0, fixed_maximum=definition.fixed_maximum or 100, target_ticks=target_ticks), "%", 1.0
        return zoomed_percent_axis(peak, target_ticks=target_ticks), "%", 1.0

    def _format_value(self, value: float) -> str:
        if self.history is not None and self.history.definition.rate_scale:
            return _format_rate(value)
        if self.history is not None and self.history.definition.unit != "%":
            return format_sensor_value(value, self.history.definition.unit)
        return f"{value:.1f}%"

    def segments(self, name: str) -> list[list[tuple[float, float]]]:
        """(moment, value) runs of one series, split wherever samples were missed."""
        if self.history is None:
            return []
        values = list(self.history.values.get(name, ()))
        times = list(self.history.times)
        if not values or len(values) != len(times):
            return []
        runs: list[list[tuple[float, float]]] = [[(times[0], values[0])]]
        for previous, moment, value in zip(times, times[1:], values[1:]):
            if moment - previous > self.GAP_SECONDS:
                runs.append([])
            runs[-1].append((moment, value))
        return runs

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._hover_x = event.position().x()
        self._hover_y = event.position().y()
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_x = None
        self._hover_y = None
        self.update()
        super().leaveEvent(event)

    @staticmethod
    def _paint_time_axis(painter: QPainter, plot: QRectF, outer: QRectF, window: float, metrics) -> None:
        """Round seconds counted back from now, under the plot."""
        grid = QColor(COLORS["chart_grid"])
        axis_pen = QPen(QColor(COLORS["chart_axis"]), 1)
        marks = time_ticks(window, width_pixels=plot.width())
        if plot.width() / (window / 5) >= 5:
            painter.setPen(axis_pen)
            for age in range(0, int(window) + 1, 5):
                if age in marks:
                    continue
                x = plot.right() - plot.width() * age / window
                painter.drawLine(QPointF(x, plot.bottom()), QPointF(x, plot.bottom() + 3))
        for age in marks:
            x = plot.right() - plot.width() * age / window
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(axis_pen)
            painter.drawLine(QPointF(x, plot.bottom()), QPointF(x, plot.bottom() + 5))
            text = format_age(age) or tr("Now")
            width = metrics.horizontalAdvance(text) + 6
            anchor = min(max(outer.left() + 4, x - width / 2), outer.right() - width - 4)
            painter.setPen(QColor(COLORS["subtle"]))
            painter.drawText(
                QRectF(anchor, plot.bottom() + 7, width, metrics.height()),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                text,
            )

    # ------------------------------------------------------------- drawing
    #
    # Everything but the pointer's readout is drawn once per sample into a
    # cached pixmap. Moving the pointer only draws the readout over it: every
    # mouse move used to redraw the whole chart.

    def _cache_key(self) -> tuple:
        history = self.history
        return (
            self.width(),
            self.height(),
            self.devicePixelRatioF(),
            id(history),
            history.revision if history is not None else -1,
            self.scale_mode,
            tuple(COLORS.get(key) for key in ("chart_surface", "border", "blue", "text", "chart_grid", "series_1")),
            tr("Now"),
        )

    def _chart_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSize(8)
        font.setWeight(QFont.Weight(650))
        return font

    def paintEvent(self, event) -> None:  # pragma: no cover - visual rendering
        key = self._cache_key()
        if self._cache is None or key != self._cache_key_value:
            ratio = self.devicePixelRatioF()
            pixmap = QPixmap(max(1, round(self.width() * ratio)), max(1, round(self.height() * ratio)))
            pixmap.setDevicePixelRatio(ratio)
            pixmap.fill(Qt.GlobalColor.transparent)
            canvas = QPainter(pixmap)
            canvas.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            canvas.setFont(self._chart_font())
            self._frame = self._render(canvas)
            canvas.end()
            self._cache = pixmap
            self._cache_key_value = key
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cache)
        if self._frame is None or self._hover_x is None:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(self._chart_font())
        if self._frame.names:
            self._paint_heatmap_readout(painter, self._frame)
        else:
            self._paint_readout(painter, self._frame)

    def _render(self, painter: QPainter) -> _ChartFrame | None:  # pragma: no cover - visual
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.setBrush(QColor(COLORS["chart_surface"]))
        painter.drawRoundedRect(outer, 12, 12)
        # Every path below is an outline or has its own fill; a brush left
        # set here would close each open line back to its start and paint it.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.history is None:
            return None
        if self.history.definition.form == "heatmap":
            return self._render_heatmap(painter, outer)
        return self._render_lines(painter, outer)

    def _render_heatmap(self, painter: QPainter, outer: QRectF) -> _ChartFrame | None:  # pragma: no cover - visual
        """One row per series, one column per sample, stronger for more.

        Twelve or sixteen threads as lines are a tangle nobody can follow; as
        rows of one colour ramp they read at a glance, and a thread pinned at
        100 % is a solid stripe. The ramp runs from the chart surface to the
        accent, so it is one hue whatever the theme.
        """
        history = self.history
        metrics = painter.fontMetrics()
        names = [name for name, _tone in history.definition.series]
        if not names:
            return None
        times = list(history.times)
        label_width = max(metrics.horizontalAdvance(name) for name in names) + 12
        legend_width = metrics.horizontalAdvance("100 %") + 26
        top_pad = 12.0
        bottom_pad = metrics.height() + 16.0
        plot = QRectF(
            outer.left() + 12 + label_width,
            outer.top() + top_pad,
            max(40.0, outer.width() - 12 - label_width - legend_width - 12),
            max(40.0, outer.height() - top_pad - bottom_pad),
        )
        row_height = plot.height() / len(names)
        window = MetricHistory.WINDOW_SECONDS
        now = times[-1] if times else 0.0

        def x_for(moment: float) -> float:
            age = max(0.0, min(window, now - moment))
            return plot.right() - plot.width() * age / window

        surface = QColor(COLORS["chart_surface"])
        accent = QColor(COLORS["blue"])

        def shade(value: float) -> QColor:
            # Square root: a thread at 10 % is already visible against the
            # ground, and the ramp still only ever climbs.
            share = max(0.0, min(1.0, value / 100.0)) ** 0.5
            return QColor(
                round(surface.red() + (accent.red() - surface.red()) * share),
                round(surface.green() + (accent.green() - surface.green()) * share),
                round(surface.blue() + (accent.blue() - surface.blue()) * share),
            )

        painter.setPen(Qt.PenStyle.NoPen)
        for row, name in enumerate(names):
            top = plot.top() + row * row_height
            values = list(history.values[name])
            for index, (moment, value) in enumerate(zip(times, values)):
                previous = times[index - 1] if index else None
                start = previous if previous is not None and moment - previous <= self.GAP_SECONDS else moment - 1.0
                left = x_for(start)
                right = x_for(moment)
                if right <= plot.left():
                    continue
                painter.fillRect(
                    QRectF(max(plot.left(), left), top, right - max(plot.left(), left) + 0.6, max(1.0, row_height - 1.0)),
                    shade(value),
                )
            painter.setPen(QColor(COLORS["subtle"]))
            painter.drawText(
                QRectF(outer.left() + 8, top, label_width - 4, row_height),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                name,
            )
            painter.setPen(Qt.PenStyle.NoPen)

        self._paint_time_axis(painter, plot, outer, window, metrics)

        # The key: the ramp itself, with its two ends named.
        bar = QRectF(plot.right() + 12, plot.top(), 10, plot.height())
        ramp = QLinearGradient(0.0, bar.top(), 0.0, bar.bottom())
        for stop in range(11):
            ramp.setColorAt(stop / 10.0, shade(100.0 - stop * 10.0))
        painter.setPen(QPen(QColor(COLORS["chart_axis"]), 1))
        painter.setBrush(QBrush(ramp))
        painter.drawRect(bar)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QColor(COLORS["subtle"]))
        for text, y, align in (
            ("100 %", bar.top(), Qt.AlignmentFlag.AlignTop),
            ("0 %", bar.bottom() - metrics.height(), Qt.AlignmentFlag.AlignBottom),
        ):
            painter.drawText(
                QRectF(bar.right() + 4, y, legend_width - 16, metrics.height()),
                Qt.AlignmentFlag.AlignLeft | align,
                text,
            )
        return _ChartFrame(plot, times, now, x_for, names=tuple(names), row_height=row_height)

    def _paint_heatmap_readout(self, painter: QPainter, frame: _ChartFrame) -> None:  # pragma: no cover - visual
        if self._hover_y is None or not frame.times:
            return
        point = QPointF(self._hover_x, self._hover_y)
        plot, times, names = frame.plot, frame.times, frame.names
        if not plot.contains(point):
            return
        metrics = painter.fontMetrics()
        row = min(len(names) - 1, int((point.y() - plot.top()) // frame.row_height))
        index = min(range(len(times)), key=lambda item: abs(frame.x_for(times[item]) - point.x()))
        values = list(self.history.values[names[row]])
        if index >= len(values):
            return
        x = frame.x_for(times[index])
        painter.setPen(QPen(QColor(COLORS["text"]), 1))
        painter.drawRect(QRectF(plot.left(), plot.top() + row * frame.row_height, plot.width(), frame.row_height - 1))
        painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        rows = [
            f"{names[row]}  {values[index]:.1f}%",
            format_age(round(frame.now - times[index])) or tr("Now"),
        ]
        self._paint_readout_box(painter, metrics, plot, x, rows)

    def _render_lines(self, painter: QPainter, outer: QRectF) -> _ChartFrame:  # pragma: no cover - visual
        metrics = painter.fontMetrics()
        top_pad = 14.0
        bottom_pad = metrics.height() + 16.0
        plot_height = max(40.0, outer.height() - top_pad - bottom_pad)
        axis, unit, factor = self.axis(ticks_for_height(plot_height))
        labels = [
            f"{_tick_text(tick)}%" if unit == "%" else f"{_tick_text(tick)} {unit}"
            for tick in axis.ticks
        ]
        label_width = max(metrics.horizontalAdvance(label) for label in labels)

        series = self.history.definition.series
        times = list(self.history.times)
        # Tags beside the scale name each line's latest value; past six they
        # stack into a column that says nothing, and the legend has them.
        latest = [
            (QColor(palette_color(tone)), self.history.values[name][-1])
            for name, tone in series
            if self.history.values[name]
        ] if len(series) <= 6 else []
        tag_texts = [self._format_value(value) for _color, value in latest]
        tag_width = max((metrics.horizontalAdvance(text) for text in tag_texts), default=0) + 14
        tag_height = metrics.height() + 6
        # The scale sits on the right, beside the newest values, as on a
        # trading chart: its gutter holds the labels and the live tags over
        # them, instead of a strip that only ever held the tags.
        gutter = max(label_width + 10, tag_width + 8 if latest else 0) + 12
        left = 14.0
        plot = QRectF(outer.left() + left, outer.top() + top_pad, outer.width() - left - gutter, plot_height)
        span = max(1e-9, axis.maximum - axis.minimum)

        def y_for(raw: float) -> float:
            value = min(axis.maximum, max(axis.minimum, raw / factor))
            return plot.bottom() - plot.height() * (value - axis.minimum) / span

        window = MetricHistory.WINDOW_SECONDS
        now = times[-1] if times else 0.0

        def x_for(moment: float) -> float:
            age = max(0.0, min(window, now - moment))
            return plot.right() - plot.width() * age / window

        # Where each series' latest value is tagged; tags that would overlap
        # are pushed apart, and a scale label under a tag is left out.
        tags = sorted(
            ([y_for(value), color, text] for (color, value), text in zip(latest, tag_texts)),
            key=lambda tag: tag[0],
        )
        for index in range(1, len(tags)):
            tags[index][0] = max(tags[index][0], tags[index - 1][0] + tag_height + 2)
        for tag in tags:
            tag[0] = min(max(tag[0], plot.top() + tag_height / 2), plot.bottom() - tag_height / 2)

        grid = QColor(COLORS["chart_grid"])
        minor = QColor(grid)
        minor.setAlpha(90)
        painter.setPen(QPen(minor, 1, Qt.PenStyle.DotLine))
        for tick in axis.minor_ticks:
            y = y_for(tick * factor)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        for tick, label in zip(axis.ticks, labels):
            y = y_for(tick * factor)
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            if any(abs(y - tag[0]) < tag_height / 2 + 5 for tag in tags):
                continue
            painter.setPen(QColor(COLORS["subtle"]))
            painter.drawText(
                QRectF(plot.right() + 10, y - 8, label_width + 4, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

        axis_pen = QPen(QColor(COLORS["chart_axis"]), 1)
        # Five-second ticks under the baseline between the labelled marks.
        self._paint_time_axis(painter, plot, outer, window, metrics)
        painter.setPen(axis_pen)
        painter.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))
        painter.drawLine(QPointF(plot.right(), plot.top()), QPointF(plot.right(), plot.bottom()))

        # Areas first, then every line over them, so no fill veils a line.
        # Filled areas only while they can be told apart; with more lines
        # the fills stack into one muddy band over everything.
        fill_alpha = 64 if len(series) == 1 else 34 if len(series) == 2 else 0
        lines: list[tuple[QColor, list[list[QPointF]]]] = []
        for name, tone in series:
            color = QColor(palette_color(tone))
            runs = [[QPointF(x_for(moment), y_for(value)) for moment, value in run] for run in self.segments(name)]
            if fill_alpha:
                gradient = QLinearGradient(0.0, plot.top(), 0.0, plot.bottom())
                top_fill, bottom_fill = QColor(color), QColor(color)
                top_fill.setAlpha(fill_alpha)
                bottom_fill.setAlpha(3)
                gradient.setColorAt(0.0, top_fill)
                gradient.setColorAt(1.0, bottom_fill)
                for points in runs:
                    fill_area(painter, points, plot.bottom(), QBrush(gradient))
            lines.append((color, runs))
        for color, runs in lines:
            draw_series(painter, runs, color, 1.8)

        if len(series) == 1 and times:
            name, tone = series[0]
            values = list(self.history.values[name])
            color = QColor(palette_color(tone))
            average = self.history.average(name)
            if average is not None:
                y = y_for(average)
                painter.setPen(QPen(QColor(COLORS["subtle"]), 1, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
                text = tr_format("avg {value}", value=self._format_value(average))
                painter.setPen(QColor(COLORS["muted"]))
                painter.drawText(
                    QRectF(plot.left() + 6, y - metrics.height() - 2, plot.width() * 0.5, metrics.height()),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                    text,
                )
            peak_index = max(range(len(values)), key=values.__getitem__)
            peak_point = QPointF(x_for(times[peak_index]), y_for(values[peak_index]))
            painter.setPen(QPen(QColor(COLORS["panel"]), 1.5))
            painter.setBrush(color)
            painter.drawEllipse(peak_point, 3.5, 3.5)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            peak_text = tr_format("peak {value}", value=self._format_value(values[peak_index]))
            width = metrics.horizontalAdvance(peak_text) + 8
            anchor = min(max(plot.left(), peak_point.x() - width / 2), plot.right() - width)
            painter.setPen(QColor(COLORS["text"]))
            painter.drawText(
                QRectF(anchor, max(plot.top(), peak_point.y() - metrics.height() - 6), width, metrics.height()),
                Qt.AlignmentFlag.AlignCenter,
                peak_text,
            )

        # The latest value of each series, tagged on the scale where its
        # line ends.
        for y, color, text in tags:
            box = QRectF(plot.right() + 8, y - tag_height / 2, tag_width, tag_height)
            shape = QPainterPath()
            shape.addRoundedRect(box, 4, 4)
            pointer = QPainterPath(QPointF(plot.right() + 2, y))
            pointer.lineTo(box.left() + 1, y - 4)
            pointer.lineTo(box.left() + 1, y + 4)
            pointer.closeSubpath()
            painter.fillPath(shape.united(pointer), color)
            painter.setPen(readable_text_on(color))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        return _ChartFrame(plot, times, now, x_for, y_for=y_for)

    def _paint_readout(self, painter: QPainter, frame: _ChartFrame) -> None:  # pragma: no cover - visual
        plot, times = frame.plot, frame.times
        if not times or not plot.contains(QPointF(self._hover_x, plot.center().y())):
            return
        metrics = painter.fontMetrics()
        index = min(range(len(times)), key=lambda item: abs(frame.x_for(times[item]) - self._hover_x))
        x = frame.x_for(times[index])
        painter.setPen(QPen(QColor(COLORS["muted"]), 1))
        painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        rows = [format_age(round(frame.now - times[index])) or tr("Now")]
        for name, tone in self.history.definition.series:
            values = self.history.values[name]
            if index < len(values):
                painter.setPen(QPen(QColor(COLORS["panel"]), 1.5))
                painter.setBrush(QColor(palette_color(tone)))
                painter.drawEllipse(QPointF(x, frame.y_for(values[index])), 3.5, 3.5)
                rows.append(f"{tr(name)}  {self._format_value(values[index])}")
        painter.setBrush(Qt.BrushStyle.NoBrush)
        self._paint_readout_box(painter, metrics, plot, x, rows)

    @staticmethod
    def _paint_readout_box(painter: QPainter, metrics, plot: QRectF, x: float, rows: list[str]) -> None:  # pragma: no cover - visual
        box_width = max(metrics.horizontalAdvance(row) for row in rows) + 16
        box_height = len(rows) * metrics.height() + 10
        box_x = x + 10 if x + 10 + box_width <= plot.right() else x - 10 - box_width
        box = QRectF(box_x, plot.top() + 6, box_width, box_height)
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.setBrush(QColor(COLORS["panel_raised"]))
        painter.drawRoundedRect(box, 6, 6)
        painter.setPen(QColor(COLORS["text"]))
        for row_index, row in enumerate(rows):
            painter.drawText(
                QRectF(box.left() + 8, box.top() + 5 + row_index * metrics.height(), box_width - 16, metrics.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                row,
            )


def series_statistics(history: MetricHistory, name: str) -> tuple[float, float, float] | None:
    """Minimum, average and maximum of one series over the window."""
    values = list(history.values.get(name, ()))
    if not values:
        return None
    return min(values), sum(values) / len(values), max(values)


class DetailPanel(QFrame):
    #: The Sensors button: show the full sensor list in this panel's place.
    sensors_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("detailPanel", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(560)
        apply_shadow(self, blur=14, y=3, alpha=9)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(18, 16, 18, 14)
        self.root.setSpacing(10)

        # One line for the resource, its live reading and what goes with it,
        # with the scale choice at its end; the description and the window
        # statistics share the line under it. No icon: the tile above already
        # names the resource, and every pixel saved here goes to the chart.
        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        self.title = QLabel(tr("CPU"))
        self.title.setProperty("detailTitle", True)
        self.primary = QLabel("--")
        self.primary.setProperty("detailPrimary", True)
        self.primary.setProperty("i18nLiteral", True)
        self.primary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.context = QLabel(tr("Waiting for sample"))
        self.context.setProperty("detailContext", True)
        self.context.setWordWrap(True)
        top_row.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self.primary, 0, Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self.context, 1, Qt.AlignmentFlag.AlignVCenter)
        self.graph_header = top_row
        # On a narrow window the scale choice moves under the title row
        # instead of squeezing it.
        self.scale_row = QHBoxLayout()
        self.scale_row.setContentsMargins(0, 0, 0, 0)
        self.scale_row.setSpacing(6)
        self.scale_row.addStretch(1)
        self._scale_in_header = True
        # Auto zooms to the smallest round range that holds the data, so a
        # 12 % load is readable instead of a line along the floor; 0–100 %
        # keeps the absolute picture. Throughput always scales itself.
        self.scale_buttons = QButtonGroup(self)
        self.scale_buttons.setExclusive(True)
        self.scale_mode_buttons: dict[str, QPushButton] = {}
        for mode, text in (("auto", "Auto"), ("full", "0–100 %")):
            button = QPushButton(tr(text))
            button.setCheckable(True)
            button.setChecked(mode == "auto")
            button.setProperty("scaleMode", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, value=mode: self.graph.set_scale_mode(value))
            self.scale_buttons.addButton(button)
            self.scale_mode_buttons[mode] = button
            top_row.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        # Every sensor in a list, loaded in this panel's place.
        self.sensors_button = QPushButton(tr("Sensors"))
        self.sensors_button.setProperty("viewSwitch", True)
        self.sensors_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sensors_button.setToolTip(tr("Every sensor in a list, with minimum, average and maximum"))
        self.sensors_button.clicked.connect(self.sensors_requested.emit)
        top_row.addWidget(self.sensors_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.root.addLayout(top_row)
        self.root.addLayout(self.scale_row)

        # The description, and each series with its minimum, average and
        # maximum over the window; stacked on a narrow panel.
        self.info_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.info_row.setSpacing(16)
        self.subtitle = QLabel(tr("Waiting for first sample"))
        self.subtitle.setProperty("detailSubtitle", True)
        self.subtitle.setWordWrap(True)
        self.legend = QLabel()
        self.legend.setProperty("legendLabel", True)
        self.legend.setProperty("i18nLiteral", True)
        self.legend.setTextFormat(Qt.TextFormat.RichText)
        self.legend.setWordWrap(True)
        self.legend.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.info_row.addWidget(self.subtitle, 1)
        self.info_row.addWidget(self.legend, 1)
        self._info_side_by_side = True
        self.root.addLayout(self.info_row)

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
        self.sample_state = PillLabel(tr("Paused"), "gray")
        footer.addWidget(self.sample_state, 0, Qt.AlignmentFlag.AlignVCenter)
        self.footer_left = QLabel(tr("120 samples · 1 s cadence · 2 minute window"))
        self.footer_left.setProperty("sampleFooter", True)
        self.footer_left.setWordWrap(True)
        self.footer_left.setMinimumWidth(0)
        footer.addWidget(self.footer_left, 1)
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
        width = event.size().width()
        self._reflow_stats(width)
        self._place_scale_buttons(width >= 460)
        self._place_info(width >= 720)

    def _place_info(self, side_by_side: bool) -> None:
        """Description and statistics side by side, or stacked when narrow."""
        if side_by_side == self._info_side_by_side:
            return
        self._info_side_by_side = side_by_side
        self.info_row.setDirection(
            QBoxLayout.Direction.LeftToRight if side_by_side else QBoxLayout.Direction.TopToBottom
        )
        side = Qt.AlignmentFlag.AlignRight if side_by_side else Qt.AlignmentFlag.AlignLeft
        self.legend.setAlignment(side | Qt.AlignmentFlag.AlignVCenter)

    def _place_scale_buttons(self, in_header: bool) -> None:
        if in_header == self._scale_in_header:
            return
        self._scale_in_header = in_header
        target = self.graph_header if in_header else self.scale_row
        for button in self.scale_mode_buttons.values():
            button.setParent(None)
            target.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
            definition = self.graph.history.definition if self.graph.history else None
            button.setVisible(
                definition is None or (not definition.rate_scale and definition.form != "heatmap")
            )
        # The Sensors switch stays last on whichever row holds the scale.
        self.sensors_button.setParent(None)
        target.addWidget(self.sensors_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.sensors_button.show()

    def _legend_html(self) -> str:
        history = self.graph.history
        if history is None:
            return ""
        colors = COLORS
        rate = history.definition.rate_scale
        series = history.definition.series
        if history.definition.form == "heatmap":
            latest = [
                (values[-1], name)
                for name, _tone in series
                if (values := history.values.get(name))
            ]
            text = tr_format("{count} threads · the stronger the colour, the busier", count=len(series))
            if latest:
                value, name = max(latest)
                text += " · " + tr_format(
                    "busiest now {name} {value}", name=name, value=self.graph._format_value(value)
                )
            return escape(text)
        if len(series) > 4:
            # Many lines: each name beside its latest value, the statistics
            # are in the boxes below and under the pointer.
            entries = []
            for name, tone in series:
                values = history.values.get(name)
                reading = self.graph._format_value(values[-1]) if values else "–"
                entries.append(
                    f"<span style='color:{palette_color(tone)}'>●</span>&nbsp;"
                    f"<span style='color:{colors['text']}; font-weight:750'>{escape(tr(name))}</span>"
                    f"&nbsp;{escape(reading).replace(' ', '&nbsp;')}"
                )
            return " &nbsp;&nbsp; ".join(entries)
        entries = []
        for name, tone in series:
            head = (
                f"<span style='color:{palette_color(tone)}'>●</span>&nbsp;"
                f"<span style='color:{colors['text']}; font-weight:750'>{escape(tr(name))}</span>"
            )
            statistics = series_statistics(history, name)
            if statistics is not None:
                low, average, high = statistics
                cells = [] if rate else [("min {value}", low)]
                cells += [("avg {value}", average), ("max {value}", high)]
                text = [
                    escape(tr_format(key, value=self.graph._format_value(value))).replace(" ", "&nbsp;")
                    for key, value in cells
                ]
                head += "&nbsp;&nbsp; " + " &nbsp;·&nbsp; ".join(text)
            entries.append(head)
        return " &nbsp;&nbsp;&nbsp;&nbsp; ".join(entries)

    def refresh_legend(self) -> None:
        html = self._legend_html()
        if html != self.legend.text():
            self.legend.setText(html)

    def select_resource(
        self, definition: ResourceDefinition, history: MetricHistory, *, title: str = ""
    ) -> None:
        self.title.setText(title or tr(definition.title))
        self.subtitle.setText(tr(definition.subtitle))
        self.graph.set_history(history)
        # Throughput and heat maps scale themselves; a measured unit is
        # framed around its data or drawn from zero, which is what the
        # second button means there.
        scalable = not definition.rate_scale and definition.form != "heatmap"
        self.scale_mode_buttons["full"].setText(
            tr("0–100 %") if definition.unit == "%" else tr("From zero")
        )
        for button in self.scale_mode_buttons.values():
            button.setVisible(scalable)
        for stat, label in zip(self.stats, definition.stat_labels):
            stat.set_label(tr(label))
        self.refresh_legend()
        self.graph.update()

    def set_values(self, primary: str, context: str, values: Iterable[str], *, sampled_at: str) -> None:
        self.primary.setText(primary)
        self.context.setText(context)
        for stat, value in zip(self.stats, values):
            stat.set_value(value)
        self.footer_right.setText(tr_format("Last sample {time}", time=sampled_at))
        self.refresh_legend()
        self.graph.update()


class PerformancePage(QWidget):
    """Passive CPU/GPU/VRAM/RAM/disk/network monitor.

    Sampling and drawing are separate. Once recording starts it samples every
    second whichever page is on screen, so the two minutes on the graph have
    no holes; the widgets are only redrawn while this page is visible.
    """

    SAMPLE_INTERVAL_MS = 1000

    def apply_appearance(self) -> None:
        if hasattr(self, "content"):
            self.content.setStyleSheet(performance_stylesheet())
            self.content.update()

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
        self.content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
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
            tile.hover_changed.connect(self._tile_hovered)
            tile.views_requested.connect(self._open_views)
            self.tiles[definition.key] = tile

        # The other views of CPU, GPU and VRAM (see core/performance_views),
        # recorded from the first sample like the tiles' own, so a view has
        # its two minutes the moment it is chosen.
        self._chosen_view = {key: key for key in RESOURCE_BY_KEY}
        self.view_histories: dict[str, MetricHistory] = {}
        self._available_views = {key for key, view in VIEW_BY_KEY.items() if view.is_summary}
        self.sensor_log = SensorLog()
        self._inventory = SensorInventory()
        self._gddr6_chips: tuple[tuple[int, float], ...] = ()
        # The Dashboard's GDDR6 engine, shared: its session's chips are
        # listed here too. A backend without GDDR6 support has none to share.
        if callable(getattr(controller, "comando_monitorizar_vram", None)):
            gddr6_monitor_for(controller).changed.connect(self._gddr6_changed)

        self.detail = DetailPanel()
        self.detail.select_resource(RESOURCE_BY_KEY[self._selected_key], self.histories[self._selected_key])
        self.detail.sensors_requested.connect(self.show_sensors)
        self.tiles[self._selected_key].set_selected(True)
        self.sensor_board = SensorBoard(self.sensor_log)
        self.sensor_board.back_requested.connect(self.show_chart)
        # The chart and the sensor list share one place on the page.
        self.body = QStackedWidget()
        self.body.addWidget(self.detail)
        self.body.addWidget(self.sensor_board)

        self.flyout = ResourceViewFlyout(self.content)
        self.flyout.view_chosen.connect(self._choose_view)
        self.flyout.hover_changed.connect(self._flyout_hovered)
        self.flyout.dismissed.connect(self._flyout_dismissed)
        self._flyout_pending = ""
        #: Held open by the guided tour: the spotlight covering the page sends
        #: the tile a leave event, which would otherwise close the menu the
        #: tour is pointing at.
        self._flyout_pinned = False
        self._flyout_show_timer = QTimer(self)
        self._flyout_show_timer.setSingleShot(True)
        self._flyout_show_timer.setInterval(220)
        self._flyout_show_timer.timeout.connect(lambda: self._show_flyout(self._flyout_pending))
        self._flyout_hide_timer = QTimer(self)
        self._flyout_hide_timer.setSingleShot(True)
        self._flyout_hide_timer.setInterval(260)
        self._flyout_hide_timer.timeout.connect(self.flyout.hide)

        self._recording = False
        self.timer = QTimer(self)
        self.timer.setInterval(self.SAMPLE_INTERVAL_MS)
        # Coarse timers may fire up to 5 % late, which over two minutes adds
        # up to visible drift between the ticks and the samples they draw.
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.refresh)
        self._refresher = AsyncRefresh(
            self,
            "performance-sample",
            self._collect_sample,
            self._sample_ready,
            self._sample_failed,
        )
        self._reflow(1400)

    def _collect_sample(self) -> dict:
        """One sample for the tiles and, from the same moment, every sensor.

        Runs on the worker; the inventory is only ever used here, one sample
        at a time.
        """
        metrics = dict(self._state_cache.realtime_metrics())
        try:
            metrics["sensor_readings"] = self._inventory.read(
                metrics, gddr6_chips=self._gddr6_chips
            )
        except Exception:  # noqa: BLE001 - the list is extra; the tiles still draw
            logger.debug("The sensor list could not be read", exc_info=True)
        return metrics

    def _gddr6_changed(self, reading) -> None:
        """Chips of a running GDDR6 session join the list and the VRAM views."""
        chips = getattr(reading, "chips", ()) or ()
        self._gddr6_chips = tuple((chip.index, chip.temperature_c) for chip in chips)

    def start_recording(self) -> None:
        """Sample every second from now on, whichever page is on screen.

        A monitor that stops when you look away is not one: every visit to
        another page, and every minimised window, left a hole in the history
        that the graph drew as a break in the line. A sample costs a few
        milliseconds on a background thread; only drawing waits for the page.
        """
        if self._recording:
            return
        self._recording = True
        self.detail.sample_state.setText(tr("Sampling"))
        self.detail.sample_state.set_tone("green")
        self._refresher.set_active(True)
        self.timer.start()
        self._refresher.request()

    def stop_recording(self) -> None:
        """Stop sampling for good, so a closing window has no reads to wait on."""
        self._recording = False
        self.timer.stop()
        self._refresher.set_active(False)

    def set_updates_active(self, active: bool) -> None:
        """Start drawing; leaving the page no longer stops the sampling."""
        if active:
            self.start_recording()
            self._render_latest()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # Back from another page or window: catch up on what was recorded
        # meanwhile rather than waiting for the next sample.
        self._render_latest()

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
        self.workspace.addWidget(self.body, 1, 0)
        self.workspace.setColumnStretch(0, 1)
        self.flyout.hide()

    def retranslate_dynamic_copy(self) -> None:
        """Relabel the detail panel after a live language change.

        Its stat captions are upper-cased translations, which the shared
        widget-tree pass cannot map back to a source string.
        """
        # View series are named in the language they were first drawn in.
        self.view_histories.clear()
        self.flyout.resource = ""
        self.sensor_board.retranslate()
        if self.body.currentWidget() is self.sensor_board:
            return
        self._select_resource(self._selected_key)

    # ---------------------------------------------------------------- views

    def _current_view(self, key: str | None = None) -> str:
        key = key or self._selected_key
        return self._chosen_view.get(key, key)

    def _view_history(self, view_key: str) -> MetricHistory:
        history = self.view_histories.get(view_key)
        if history is None:
            # Chosen before its first sample: an empty chart that fills in.
            history = MetricHistory(view_definition(VIEW_BY_KEY[view_key], ()))
            self.view_histories[view_key] = history
        return history

    def _select_resource(self, key: str) -> None:
        if key not in RESOURCE_BY_KEY:
            return
        self._selected_key = key
        self.flyout.hide()
        if self.body.currentWidget() is not self.detail:
            self.body.setCurrentWidget(self.detail)
        for tile_key, tile in self.tiles.items():
            tile.set_selected(tile_key == key)
        view_key = self._current_view(key)
        if view_key == key:
            self.detail.select_resource(RESOURCE_BY_KEY[key], self.histories[key])
        else:
            view = VIEW_BY_KEY[view_key]
            self.detail.select_resource(
                self._view_history(view_key).definition,
                self._view_history(view_key),
                title=f"{tr(RESOURCE_BY_KEY[key].title)} · {tr(view.title)}",
            )
        self._refresh_detail()

    def _choose_view(self, resource: str, view_key: str) -> None:
        if view_key not in VIEW_BY_KEY or VIEW_BY_KEY[view_key].resource != resource:
            return
        # Chosen with the keyboard or a controller: the focus goes back to
        # the tile rather than wherever Qt sends it when the menu closes.
        from_menu = QApplication.focusWidget() in self.flyout.rows
        self._chosen_view[resource] = view_key
        self._select_resource(resource)
        tile = self.tiles.get(resource)
        if tile is not None and from_menu:
            tile.setFocus(Qt.FocusReason.OtherFocusReason)

    def _tile_hovered(self, key: str, inside: bool) -> None:
        if self._flyout_pinned:
            return
        if inside and len(views_for(key)) > 1:
            self._flyout_hide_timer.stop()
            self._flyout_pending = key
            if self.flyout.isVisible() and self.flyout.resource != key:
                self._show_flyout(key)
            else:
                self._flyout_show_timer.start()
            return
        self._flyout_show_timer.stop()
        if self.flyout.isVisible():
            self._flyout_hide_timer.start()

    def _flyout_hovered(self, inside: bool) -> None:
        if self._flyout_pinned:
            return
        if inside:
            self._flyout_hide_timer.stop()
        else:
            self._flyout_hide_timer.start()

    def _show_flyout(self, key: str) -> None:
        tile = self.tiles.get(key)
        if tile is None or not tile.isVisible():
            return
        primary, context = tile.reading
        heading = " · ".join(part for part in (tr(tile.definition.title), primary, context) if part and part != "--")
        top_left = tile.mapTo(self.content, tile.rect().topLeft())
        self.flyout.present(
            key,
            heading=heading,
            current=self._current_view(key),
            available=self._available_views,
            anchor=QRect(top_left, tile.size()),
        )

    def pin_views_menu(self, key: str = "cpu") -> None:
        """Hold one tile's views menu open until :meth:`unpin_views_menu`."""
        self._flyout_show_timer.stop()
        self._flyout_hide_timer.stop()
        if self.body.currentWidget() is not self.detail:
            self.show_chart()
        self._flyout_pinned = True
        self._show_flyout(key)

    def unpin_views_menu(self) -> None:
        self._flyout_pinned = False
        self.flyout.hide()

    def _open_views(self, key: str) -> None:
        """X, the context-menu key or a right click: the menu, with the focus."""
        self._flyout_hide_timer.stop()
        self._show_flyout(key)
        self.flyout.focus_current()

    def _flyout_dismissed(self) -> None:
        tile = self.tiles.get(self.flyout.resource)
        if tile is not None:
            tile.setFocus(Qt.FocusReason.OtherFocusReason)

    def gamepad_back(self) -> bool:
        """B closes the views menu before it leaves the page."""
        if self.flyout.isVisible():
            self.flyout.hide()
            self._flyout_dismissed()
            return True
        if self.body.currentWidget() is self.sensor_board:
            self.show_chart()
            return True
        return False

    # -------------------------------------------------------------- sensors

    def show_sensors(self) -> None:
        """Every sensor, in the chart's place."""
        self.flyout.hide()
        self.body.setCurrentWidget(self.sensor_board)
        for tile in self.tiles.values():
            tile.set_selected(False)
        self.sensor_board.refresh()

    def show_chart(self) -> None:
        self._select_resource(self._selected_key)

    def refresh(self) -> None:
        if not self._recording:
            return
        self._refresher.request()

    def _drawing(self) -> bool:
        return self.isVisible()

    def _render_latest(self) -> None:
        for key, (primary, context, _stats) in self._sample_views.items():
            self.tiles[key].set_values(primary, context)
        self._refresh_detail()

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

    def _sample_ready(self, sample: dict) -> None:
        from datetime import datetime

        self._last_error = ""
        self.detail.sample_state.setText(tr("Sampling"))
        self.detail.sample_state.set_tone("green")

        peaks = {
            "cpu": self.histories["cpu"].peak("Usage"),
            "gpu": self.histories["gpu"].peak("Usage"),
            "vram": self.histories["vram"].peak("Used"),
            "memory": self.histories["memory"].peak("Used"),
            "disk": self.histories["disk"].peak(),
            "network": self.histories["network"].peak(),
        }
        for plan in present_performance_sample(
            sample,
            previous_peaks=peaks,
            translate=tr,
        ):
            self._set_resource(
                plan.key,
                primary=plan.primary,
                context=plan.context,
                graph_values=dict(plan.graph_values),
                stats=plan.stats,
            )

        readings = sample.get("sensor_readings") or ()
        if readings:
            self.sensor_log.record(readings)
            self._record_views(readings)

        self._sample_time = datetime.now().strftime("%H:%M:%S")
        if self._drawing():
            self._render_latest()
            if self.body.currentWidget() is self.sensor_board:
                self.sensor_board.refresh()

    def _record_views(self, readings) -> None:
        self._available_views = available_views(readings)
        moment = time.monotonic()
        for key, view in VIEW_BY_KEY.items():
            if view.is_summary:
                continue
            series = view.series(readings)
            if not series:
                continue
            names = tuple(series_label(item, tr) for item in series)
            history = self.view_histories.get(key)
            if history is None or tuple(name for name, _tone in history.definition.series) != names:
                history = MetricHistory(view_definition(view, names))
                self.view_histories[key] = history
                if self._current_view() == key and self.body.currentWidget() is self.detail:
                    self.detail.select_resource(
                        history.definition,
                        history,
                        title=f"{tr(RESOURCE_BY_KEY[view.resource].title)} · {tr(view.title)}",
                    )
            history.append(
                {name: (item.value if item.value is not None else 0.0) for name, item in zip(names, series)},
                moment=moment,
            )


    def _refresh_detail(self) -> None:
        sampled_at = getattr(self, "_sample_time", "--:--:--")
        view_key = self._current_view()
        if view_key != self._selected_key:
            primary, context, stats = self._view_summary(VIEW_BY_KEY[view_key], self._view_history(view_key))
            self.detail.set_values(primary, context, stats, sampled_at=sampled_at)
            return
        view = self._sample_views.get(self._selected_key)
        if view is None:
            return
        primary, context, stats = view
        self.detail.set_values(primary, context, stats, sampled_at=sampled_at)

    def _view_summary(self, view: MetricView, history: MetricHistory) -> tuple[str, str, tuple[str, str, str, str]]:
        """The header reading and the four boxes of a view."""
        unit = history.definition.unit

        def show(value: float | None) -> str:
            if value is None:
                return "--"
            return f"{value:.1f}%" if unit == "%" else format_sensor_value(value, unit)

        latest = [
            (values[-1], name)
            for name, _tone in history.definition.series
            if (values := history.values.get(name))
        ]
        if not latest:
            unavailable = view.unavailable_hint if view.key not in self._available_views else ""
            return "--", tr(unavailable or "Waiting for sample"), ("--", "--", "--", "--")
        if len(latest) == 1:
            value, name = latest[0]
            statistics = series_statistics(history, name)
            low, average, high = statistics if statistics else (None, None, None)
            return show(value), name, (show(value), show(low), show(average), show(high))
        high_value, high_name = max(latest)
        low_value, low_name = min(latest)
        mean = sum(value for value, _name in latest) / len(latest)
        return (
            show(high_value),
            tr_format("highest: {name} · {count} series", name=high_name, count=len(latest)),
            (
                f"{high_name} · {show(high_value)}",
                f"{low_name} · {show(low_value)}",
                show(mean),
                show(history.peak()),
            ),
        )
