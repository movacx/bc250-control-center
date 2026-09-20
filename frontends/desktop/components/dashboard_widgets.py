"""Proposal-N dashboard widgets backed by the real BC250 preparation state."""

from __future__ import annotations

import shlex
import textwrap
from collections.abc import Iterable, Mapping
from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QBoxLayout,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWidgets import QPushButton as IconButton

from bc250cc.infrastructure.terminal_repository import TerminalRepository

from .. import theme
from ..core.feature_visibility import FSR4_UI_ENABLED
from ..core.gfx1013_presenter import present_gfx1013
from ..core.preferences import application_settings
from ..i18n import tr, tr_format
from .buttons import WrappingButton as QPushButton
from .dashboard_instruments import HeadingLabel
from .responsive import clear_grid
from .system_setup_controls import (
    VRAM_SIZE_PRESETS_MB,
    bazzite_ui_preview_enabled,
    is_bazzite_host,
    update_memory_controls,
    vram_size_label,
)
from .widgets import ICON_DIR, IconBadge, InfoDialog, PillLabel, apply_shadow, icon


def _label(text: str, property_name: str, *, wrap: bool = True) -> QLabel:
    widget = QLabel(tr(text))
    widget.setProperty(property_name, True)
    widget.setWordWrap(wrap)
    widget.setMinimumWidth(0)
    return widget


# Plain-language detail shown under each swap-policy row. Keyed by the same
# option values BAZZITE_MEMORY_OPTIONS/MEMORY_OPTIONS already use, so it stays
# correct regardless of which option set the current host exposes.
_MEMORY_POLICY_DETAILS = {
    "current": "The current ZRAM, ZSWAP and backing-swap configuration would be preserved.",
    "preserve": "The current ZRAM, ZSWAP and backing-swap configuration would be preserved.",
    "zram": "ZRAM would remain the compressed in-memory swap device; no disk swapfile would be created.",
    "zram-swap-16": "ZRAM remains primary and a verified 16 GiB disk swapfile is used only as an emergency fallback.",
    "swap-16": "Creates or reuses a verified 16 GiB disk swapfile as backing swap.",
    "swap-32": "Creates or reuses a verified 32 GiB disk swapfile as backing swap.",
    "zswap-16": "A verified 16 GiB backing swapfile would be required before enabling ZSWAP and disabling ZRAM.",
    "zswap-32": "A verified 32 GiB backing swapfile would be required before enabling ZSWAP and disabling ZRAM.",
    "restore": "Reverts every BC250 memory change back to what it was before.",
}


class _MemoryOptionRow(QFrame):
    """One clickable swap-policy choice: a radio dot plus title and detail.

    A visual stand-in for a QComboBox row so every policy reads at a glance,
    while the combo itself stays the single source of truth other code and
    tests already rely on.
    """

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("dashboardMemoryOptionRow", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(12)
        self.indicator = QFrame()
        self.indicator.setProperty("dashboardMemoryOptionIndicator", True)
        self.indicator.setFixedSize(16, 16)
        layout.addWidget(self.indicator, 0, Qt.AlignmentFlag.AlignTop)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        self.title_label = _label("", "actionTitle")
        copy.addWidget(self.title_label)
        self.detail_label = _label("", "actionSubtitle")
        copy.addWidget(self.detail_label)
        layout.addLayout(copy, 1)

    def set_content(self, title: str, detail: str) -> None:
        self.title_label.setText(title)
        self.detail_label.setText(detail)
        self.detail_label.setVisible(bool(detail))

    def set_selected(self, selected: bool) -> None:
        for widget in (self, self.indicator):
            widget.setProperty("selected", selected)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.clicked.emit()
        super().mousePressEvent(event)


class _AllocationTimeline(QWidget):
    """A single horizontal line of stops mirroring a combo box's items.

    Clicking or dragging along the line jumps straight to the nearest
    enabled stop. The combo box stays the tested source of truth; this is
    only its on-screen presentation, same spirit as ``_MemoryOptionRow``.
    """

    MARGIN = 14.0
    TRACK_Y = 17.0
    DOT_RADIUS = 5.5
    SELECTED_RADIUS = 8.0

    def __init__(self, combo: QComboBox, parent: QWidget | None = None):
        super().__init__(parent)
        self._combo = combo
        self._hover_index = -1
        self.setMinimumHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        combo.currentIndexChanged.connect(lambda _index: self.update())

    def sizeHint(self) -> QSize:
        return QSize(280, 34)

    def refresh(self) -> None:
        self.update()

    def _stop_x(self, index: int) -> float:
        count = self._combo.count()
        usable = max(1.0, self.width() - 2 * self.MARGIN)
        if count <= 1:
            return self.MARGIN + usable / 2
        return self.MARGIN + usable * index / (count - 1)

    def _index_at(self, x: float) -> int:
        best_index = 0
        best_distance: float | None = None
        for index in range(self._combo.count()):
            distance = abs(self._stop_x(index) - x)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_index = index
        return best_index

    def _is_enabled(self, index: int) -> bool:
        if not self.isEnabled() or not self._combo.isEnabled():
            return False
        model_item = self._combo.model().item(index)
        return model_item is None or model_item.isEnabled()

    def _select(self, x: float) -> None:
        index = self._index_at(x)
        if self._is_enabled(index):
            self._combo.setCurrentIndex(index)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._select(event.position().x())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._select(event.position().x())
        index = self._index_at(event.position().x())
        if index != self._hover_index:
            self._hover_index = index
            self.update()
        if self._is_enabled(index):
            QToolTip.showText(event.globalPosition().toPoint(), self._combo.itemText(index), self)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._hover_index != -1:
            self._hover_index = -1
            self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        count = self._combo.count()
        if count == 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width = self.width()
        current_index = self._combo.currentIndex()
        accent = QColor(theme.COLORS["blue"])
        muted = QColor(theme.COLORS["border_strong"])
        hover_color = QColor(theme.COLORS["muted"])
        disabled = QColor(theme.COLORS["disabled_text"])

        painter.setPen(QPen(QColor(theme.COLORS["border_soft"]), 3, cap=Qt.PenCapStyle.RoundCap))
        painter.drawLine(
            QPointF(self.MARGIN, self.TRACK_Y), QPointF(width - self.MARGIN, self.TRACK_Y)
        )
        if current_index > 0:
            painter.setPen(QPen(accent, 3, cap=Qt.PenCapStyle.RoundCap))
            painter.drawLine(
                QPointF(self.MARGIN, self.TRACK_Y),
                QPointF(self._stop_x(current_index), self.TRACK_Y),
            )

        for index in range(count):
            x = self._stop_x(index)
            enabled = self._is_enabled(index)
            selected = index == current_index
            hovered = index == self._hover_index and enabled and not selected
            radius = self.SELECTED_RADIUS if selected else self.DOT_RADIUS + (1.0 if hovered else 0.0)
            color = disabled if not enabled else accent if selected else (hover_color if hovered else muted)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x, self.TRACK_Y), radius, radius)
            if selected:
                painter.setBrush(QColor(theme.COLORS["panel"]))
                painter.drawEllipse(QPointF(x, self.TRACK_Y), radius - 3.0, radius - 3.0)
                painter.setBrush(accent)
                painter.drawEllipse(QPointF(x, self.TRACK_Y), radius - 4.5, radius - 4.5)
        painter.end()


def _mapping(value: object) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


DECKY_PREVIEW_IMAGE = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "screenshots"
    / "decky-quick-access.png"
)


class _ClickOnlyComboBox(QComboBox):
    """Do not let incidental scrolling change a saved compatibility choice."""

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API name
        # Let the parent scroll area receive the wheel event when the pointer
        # merely crosses this control.  Selecting remains an explicit click.
        event.ignore()


class _DeckyScreenshotDialog(QDialog):
    """Static Decky screenshot preview; the older interactive overlay is retained."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("DeckyScreenshotPreview")
        self.setWindowTitle(tr("Decky Quick Access preview"))
        self.setModal(False)
        self.setMinimumSize(720, 460)
        available = parent.screen().availableGeometry() if parent.screen() else None
        if available is None:
            self.resize(1440, 920)
        else:
            self.resize(
                max(720, min(1440, available.width() - 80)),
                max(460, min(920, available.height() - 80)),
            )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(_label("Decky Quick Access preview", "dashboardComponentTitle"))

        self.image = QLabel()
        self.image.setObjectName("DeckyScreenshotPreviewImage")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setAccessibleName(tr("Decky Quick Access preview image"))
        pixmap = QPixmap(str(DECKY_PREVIEW_IMAGE))
        if pixmap.isNull():
            self.image.setText(tr("Preview image is unavailable."))
        else:
            self.image.setPixmap(pixmap)
            self.image.setMinimumSize(pixmap.size())

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setWidget(self.image)
        layout.addWidget(scroll, 1)


class DashboardScrollArea(QScrollArea):
    """Report the usable width without reserving an asymmetric action gutter."""

    viewport_width_changed = pyqtSignal(int)

    def __init__(self) -> None:
        super().__init__()
        self._last_viewport_width = -1
        self.viewport().installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.viewport() and event.type() == QEvent.Type.Resize:
            width = self.viewport().width()
            if width != self._last_viewport_width:
                self._last_viewport_width = width
                self.viewport_width_changed.emit(width)
        return super().eventFilter(watched, event)


class _PreparationStack(QWidget):
    """Hidden tabs must not impose their height on the selected preparation tab."""

    def __init__(self) -> None:
        super().__init__()
        self._pages: list[QWidget] = []
        self._index = -1
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def addWidget(self, page: QWidget) -> None:
        self._pages.append(page)
        self._layout.addWidget(page)
        page.hide()
        if self._index < 0:
            self.setCurrentIndex(0)

    def currentIndex(self) -> int:
        return self._index

    def currentWidget(self) -> QWidget | None:
        return self._pages[self._index] if self._index >= 0 else None

    def setCurrentIndex(self, index: int) -> None:
        if index == self._index or not 0 <= index < len(self._pages):
            return
        if self.currentWidget() is not None:
            self.currentWidget().hide()
        self._index = index
        self._pages[index].show()
        self._layout.invalidate()
        self.updateGeometry()


#: Bands for the JEDEC MR3 junction temperature. GDDR6 runs hotter than the
#: CPU package, so the package bands would cry wolf: these follow the device
#: rating instead.
GDDR6_WARM_C = 80.0
GDDR6_HOT_C = 95.0

#: The BC-250 carries eight GDDR6 devices, so the strip is a fixed size and
#: its cells can be built once and refreshed in place.
GDDR6_CHIP_COUNT = 8


def gddr6_tone(temperature: float | None) -> str:
    if temperature is None:
        return "gray"
    if temperature >= GDDR6_HOT_C:
        return "red"
    if temperature >= GDDR6_WARM_C:
        return "orange"
    return "green"


class _MemoryChipCell(QFrame):
    """One GDDR6 device, drawn exactly as a CPU core cell is drawn.

    The board has eight cores and eight memory devices sitting next to each
    other in the same view; reading them in two different shapes made one
    module look like two.
    """

    def __init__(self, index: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("dashboardCoreCell", True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        box = QVBoxLayout(self)
        box.setContentsMargins(8, 5, 8, 5)
        box.setSpacing(1)
        self.name = _label(
            tr_format("Chip {index}", index=index), "dashboardCoreName", wrap=False
        )
        self.temperature = _label("--", "dashboardCoreFrequency", wrap=False)
        self.separator = _label("·", "dashboardCoreSeparator", wrap=False)
        self.code = _label("--", "dashboardCoreUsage", wrap=False)
        reading = QHBoxLayout()
        reading.setContentsMargins(0, 0, 0, 0)
        reading.setSpacing(4)
        box.addWidget(self.name)
        reading.addWidget(self.temperature)
        reading.addWidget(self.separator)
        reading.addWidget(self.code)
        reading.addStretch(1)
        box.addLayout(reading)

    def set_chip(self, temperature: float | None, code: int | None) -> None:
        """Fill the cell using the theme's own core-cell styling.

        No per-reading colour and no highlight: the strip is read alongside
        the CPU core strip, and those cells do not recolour themselves
        either. Which device is hottest is stated in words by the summary
        tile instead of being implied by a glow.
        """
        if temperature is None:
            # A dash, not a sentence: eight cells each demanding the width of
            # "Waiting for sample" push the whole strip's minimum width up and
            # squeeze the core strip beside it. The header already says it.
            self.temperature.setText("--")
            self.code.setText("")
            self.separator.setVisible(False)
            return
        self.temperature.setText(f"{temperature:.1f} °C")
        # The only other per-device value MR3 gives back. The memory clock is
        # not one: all eight chips share a single MCLK, which the hero already
        # reports once.
        self.code.setText("" if code is None else f"MR3 0x{int(code):02X}")
        self.separator.setVisible(code is not None)


class DashboardMemorySummary(QFrame):
    """The eight GDDR6 devices, laid out like the CPU core strip.

    Presentation only: it is *shown* readings and never fetches one. The one
    button it owns emits an intent; whoever wired it decides what that costs.
    """

    MINIMUM_CELL = 150

    live_toggled = pyqtSignal(bool)
    prepare_requested = pyqtSignal()

    def __init__(
        self,
        *,
        show_header: bool = True,
        live_action: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setProperty("dashboardMetricTile", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 9, 12, 9)
        root.setSpacing(7)

        self.header = QGridLayout()
        self.header.setContentsMargins(0, 0, 0, 0)
        self.header.setHorizontalSpacing(10)
        self.header.setVerticalSpacing(3)
        # The same heading style the instrument panels use, and it survives a
        # language switch because the widget upper-cases whatever it is given.
        self.label = HeadingLabel()
        self.label.source_text = "GDDR6 memory temperature"
        self.label.setText(tr("GDDR6 memory temperature"))
        self.label.setProperty("dashboardCoreSummaryLabel", True)
        self.label.setWordWrap(False)
        # The caption keeps its own dot so the row reads as the fourth group of
        # the card it now sits in, next to Thermal, Power and Memory.
        self.title_box = QWidget()
        title_row = QHBoxLayout(self.title_box)
        title_row.setContentsMargins(1, 0, 0, 0)
        title_row.setSpacing(7)
        self.dot = QLabel()
        self.dot.setProperty("sensorBoardDot", True)
        self.dot.setProperty("accent", "muted")
        title_row.addWidget(self.dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.label)
        self.dot.hide()
        self.value = _label("Waiting for sample", "dashboardCoreSummaryValue", wrap=False)
        self.detail = _label("", "dashboardCoreSummaryDetail", wrap=False)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._show_header = bool(show_header)
        self._compact_header: bool | None = None
        self.live_button = QPushButton(tr("Monitor live"))
        self.live_button.setProperty("dashboardCardAction", True)
        self.live_button.setCheckable(True)
        self.live_button.toggled.connect(self._on_live_toggled)
        self.live_button.setVisible(bool(live_action))
        # Shown in the live button's place when the readings cannot be taken
        # yet. One button that is grey forever explains nothing; this one says
        # what is missing and fetches it.
        self.prepare_button = QPushButton(tr("Prepare readings"))
        self.prepare_button.setProperty("dashboardCardAction", True)
        self.prepare_button.clicked.connect(self.prepare_requested)
        self.prepare_button.setVisible(False)
        self._live_action = bool(live_action)
        if self._show_header:
            root.addLayout(self.header)
            self._layout_header(1000)
        else:
            root.setContentsMargins(0, 0, 0, 0)
            for widget in (self.title_box, self.value, self.detail):
                widget.hide()

        self._columns = 0
        # The eight cells live in their own host so the whole strip can step
        # aside while there is nothing to put in it: eight cells reading "--"
        # said less than the one line above them and made the card look broken.
        self.cell_host = QWidget()
        self.cell_grid = QGridLayout(self.cell_host)
        self.cell_grid.setContentsMargins(0, 0, 0, 0)
        self.cell_grid.setHorizontalSpacing(6)
        self.cell_grid.setVerticalSpacing(6)
        self.cells = [_MemoryChipCell(index, self) for index in range(GDDR6_CHIP_COUNT)]
        root.addWidget(self.cell_host)
        # A sentence, so it gets its own wrapped line under the devices rather
        # than a cell on the header row: sharing that row with the short values
        # forced the whole card wider than the window at 1024 px.
        self.blocker = _label("", "dashboardCoreSummaryDetail", wrap=True)
        self.blocker.setVisible(False)
        root.addWidget(self.blocker)
        self._apply_columns(GDDR6_CHIP_COUNT)
        self.set_chips(())

    def _apply_columns(self, columns: int) -> None:
        columns = max(1, min(GDDR6_CHIP_COUNT, int(columns)))
        if columns == self._columns:
            return
        self._columns = columns
        for cell in self.cells:
            self.cell_grid.removeWidget(cell)
        for index, cell in enumerate(self.cells):
            self.cell_grid.addWidget(cell, index // columns, index % columns)
        for column in range(GDDR6_CHIP_COUNT):
            self.cell_grid.setColumnStretch(column, 1 if column < columns else 0)

    def set_ready(self, ready: bool) -> None:
        """Offer the readings, or offer to make them possible."""
        if not self._live_action:
            return
        self.live_button.setVisible(bool(ready))
        self.prepare_button.setVisible(not ready)

    def set_blocker(self, message: str) -> None:
        """Why there is nothing to show, when there is nothing to show."""
        self.blocker.setText(tr(message) if message else "")
        self.blocker.setVisible(bool(message))

    def _on_live_toggled(self, active: bool) -> None:
        self.live_button.setText(tr("Stop monitoring") if active else tr("Monitor live"))
        self.live_toggled.emit(bool(active))

    def set_live(self, active: bool) -> None:
        """Reflect the engine's state without re-emitting the intent."""
        if self.live_button.isChecked() == bool(active):
            return
        blocked = self.live_button.blockSignals(True)
        self.live_button.setChecked(bool(active))
        self.live_button.blockSignals(blocked)
        self.live_button.setText(
            tr("Stop monitoring") if active else tr("Monitor live")
        )

    def _layout_header(self, width: int) -> None:
        """Wrap the caption onto its own row when the card gets narrow.

        Same behaviour as the core strip above it: at 360 px the three header
        labels do not fit on one line and would be clipped out of the card.
        """
        compact = width < 700
        if compact == self._compact_header and self.header.count():
            return
        self._compact_header = compact
        for widget in (self.title_box, self.value, self.detail):
            self.header.removeWidget(widget)
        for column in range(4):
            self.header.setColumnStretch(column, 0)
        self.label.setWordWrap(compact)
        self.detail.setWordWrap(compact)
        for button in (self.live_button, self.prepare_button):
            self.header.removeWidget(button)
        self.header.addWidget(self.title_box, 0, 0)
        self.header.addWidget(self.value, 0, 1)
        if compact:
            self.header.addWidget(self.detail, 1, 0, 1, 3)
            self.header.setColumnStretch(2, 1)
            self.header.addWidget(self.live_button, 2, 0, 1, 4)
            # The same cell: only ever one of the two is visible, and a layout
            # ignores the hidden one, so this costs no width. Giving them a
            # column each widened the header enough to clip the core strip's
            # caption next to it at 1024 px in Spanish.
            self.header.addWidget(self.prepare_button, 2, 0, 1, 4)
        else:
            self.header.addWidget(self.detail, 0, 2)
            self.header.setColumnStretch(3, 1)
            self.header.addWidget(self.live_button, 0, 4)
            self.header.addWidget(self.prepare_button, 0, 4)
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        if self._show_header:
            self._layout_header(event.size().width())
        spacing = self.cell_grid.horizontalSpacing()
        fit = (self.width() + spacing) // (self._cell_minimum() + spacing)
        # Eight devices split evenly into 8, 4, 2 or 1 columns; five, six or
        # seven would leave a row of orphans under a full one.
        self._apply_columns(next(count for count in (8, 4, 2, 1) if count <= fit or count == 1))

    def _cell_minimum(self) -> int:
        """Narrowest a device cell can be and still show its whole reading.

        The reading is a temperature and the MR3 code side by side, so the room
        it needs follows the font: a user scale of 150 % needs far more than
        the fixed floor, and clipping the code is what this prevents.
        """
        probe = self.cells[0]
        needed = (
            probe.temperature.fontMetrics().horizontalAdvance("88.8 °C")
            + probe.separator.fontMetrics().horizontalAdvance(" · ")
            + probe.code.fontMetrics().horizontalAdvance("MR3 0x33")
            + 24
        )
        return max(self.MINIMUM_CELL, needed)

    def set_value(self, value: str) -> None:
        self.value.setText(tr(value))

    def set_detail(self, detail: str) -> None:
        self.detail.setText(tr(detail))
        self.detail.setVisible(bool(detail))

    def set_chips(
        self, chips: Iterable[tuple[int, int | None, float | None]]
    ) -> None:
        """``chips`` is ``(index, MR3 code, temperature)`` per device."""
        by_index = {
            int(index): (code, temperature) for index, code, temperature in chips
        }
        for index, cell in enumerate(self.cells):
            code, temperature = by_index.get(index, (None, None))
            cell.set_chip(temperature, code)
        self.cell_host.setVisible(
            any(temperature is not None for _code, temperature in by_index.values())
        )


class _ComponentCheckbox(QAbstractButton):
    """A small rounded checkbox painted by hand, not the platform style.

    The old control was a plain ``QPushButton`` carrying only an icon, which
    read as a stray green badge rather than a checkbox — its purpose was not
    obvious at a glance. This borrows the same drawn tick used by
    ``CheckRow`` on the GPU governor page (``pages/gpu_governor_view.py``)
    so both read as the same control, and looks identical in light and dark
    instead of the platform theme showing through.
    """

    BOX = 14.0

    def sizeHint(self) -> QSize:
        return QSize(int(self.BOX) + 2, int(self.BOX) + 2)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = QRectF(
            (self.width() - self.BOX) / 2.0, (self.height() - self.BOX) / 2.0,
            self.BOX, self.BOX,
        )

        if not self.isEnabled():
            painter.setPen(QPen(QColor(theme.COLORS["border_soft"]), 1.4))
            painter.setBrush(QColor(theme.COLORS["disabled_bg"]))
        elif self.isChecked():
            painter.setPen(QPen(QColor(theme.COLORS["blue"]), 1.4))
            painter.setBrush(QColor(theme.COLORS["blue"]))
        else:
            painter.setPen(QPen(QColor(theme.COLORS["border_strong"]), 1.4))
            painter.setBrush(
                QColor(theme.COLORS["control_hover"])
                if self.underMouse() else QColor(theme.COLORS["control"])
            )
        painter.drawRoundedRect(box, 4, 4)

        if self.isChecked():
            tick = QPainterPath()
            tick.moveTo(box.left() + box.width() * 0.26, box.top() + box.height() * 0.52)
            tick.lineTo(box.left() + box.width() * 0.43, box.top() + box.height() * 0.70)
            tick.lineTo(box.left() + box.width() * 0.76, box.top() + box.height() * 0.32)
            pen = QPen(
                QColor(theme.COLORS["on_accent"] if self.isEnabled() else theme.COLORS["disabled_text"]),
                1.6,
            )
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(tick)
        painter.end()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().leaveEvent(event)
        self.update()


class PreparationComponentCard(QFrame):
    def __init__(self, key: str, title: str, detail: str) -> None:
        super().__init__()
        self.key = key
        self.setProperty("dashboardComponentCard", True)
        self.setMinimumWidth(0)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(8)
        self.setMinimumHeight(34)
        self.setMaximumHeight(34)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        self.title = _label(title, "dashboardComponentTitle")
        self.title.source_text = title
        self.detail = _label(detail, "dashboardComponentDetail")
        self.detail.source_text = detail
        copy.addWidget(self.title)
        self.detail.hide()
        self.setToolTip(tr(detail))
        row.addLayout(copy, 1)
        self.checkbox = _ComponentCheckbox()
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkbox.setCheckable(True)
        self.checkbox.setAccessibleName(tr(title))
        self.checkbox.setChecked(True)
        self.checkbox.setToolTip(tr("Include this component when preparing"))
        row.addWidget(self.checkbox, alignment=Qt.AlignmentFlag.AlignVCenter)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.checkbox.isEnabled():
            self.checkbox.click()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def set_capability(self, capability: Mapping[str, object]) -> None:
        available = bool(capability.get("available", True))
        installed = bool(capability.get("installed", False))
        self.setProperty("installed", installed)
        self.setProperty("available", available)
        self.checkbox.setEnabled(available and self.key != "runtime")
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if self.checkbox.isEnabled()
            else Qt.CursorShape.ArrowCursor
        )
        if not available:
            self.checkbox.setChecked(False)
        elif self.key == "runtime":
            self.checkbox.setChecked(True)
        detail = str(capability.get("detail") or "")
        if detail:
            self.detail.setText(tr(detail))
            self.setToolTip(tr(detail))
        # No restyle here. ``installed`` and ``available`` are recorded as data
        # — nothing in the stylesheet selects on either, so the unpolish/polish
        # this used to run recomputed the style of the whole card, seven cards
        # over, on every five-second dashboard tick, and changed nothing.


class PreparationInfoCard(QFrame):
    action_requested = pyqtSignal(object)

    def __init__(
        self,
        title: str,
        detail: str,
        *,
        action_text: str = "",
        payload: Mapping[str, object] | None = None,
        secondary_action_text: str = "",
        secondary_payload: Mapping[str, object] | None = None,
        scope_text: str = "",
        status_text: str = "",
        status_tone: str = "gray",
    ) -> None:
        super().__init__()
        self.setProperty("dashboardPreparationInfo", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        header = QHBoxLayout()
        header.setSpacing(7)
        self.title = _label(title, "dashboardComponentTitle")
        self.title.setProperty("i18nSourceText", title)
        self.title.setProperty("i18nSourceTextLanguage", "en")
        header.addWidget(self.title, 1)
        self.scope = PillLabel(scope_text or "Compatibility", "gray")
        self.scope.setVisible(bool(scope_text))
        header.addWidget(self.scope)
        self.status = PillLabel(status_text or "Not detected", status_tone)
        self.status.setVisible(bool(status_text))
        header.addWidget(self.status)
        layout.addLayout(header)
        self.detail = _label(detail, "dashboardComponentDetail")
        self.detail.setProperty("i18nSourceText", detail)
        self.detail.setProperty("i18nSourceTextLanguage", "en")
        layout.addWidget(self.detail)
        self.actions_panel = QFrame()
        self.actions_panel.setProperty("dashboardCompatibilityActions", True)
        self.actions = QHBoxLayout(self.actions_panel)
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(6)
        self.primary_button: QPushButton | None = None
        self.secondary_button: QPushButton | None = None
        if action_text:
            self.primary_button = self._action_button(action_text, payload)
            self.actions.addWidget(self.primary_button, 1)
        if secondary_action_text:
            self.secondary_button = self._action_button(
                secondary_action_text,
                secondary_payload,
                danger=True,
            )
            self.actions.addWidget(self.secondary_button, 1)
        layout.addWidget(self.actions_panel)
        if not (self.primary_button or self.secondary_button):
            self.actions_panel.hide()
        self._refresh_action_styles()

    #: Source strings (pre-``tr()``) that open an external page rather than
    #: run a workflow. These read as plain links, not boxed buttons, and
    #: never get the "primary action" accent — a URL is never the recommended
    #: choice among a card's actions.
    _LINK_ACTION_TEXTS = frozenset({"Open upstream project"})

    @classmethod
    def _is_link_action(cls, text: str) -> bool:
        return text in cls._LINK_ACTION_TEXTS

    def _action_button(
        self,
        text: str,
        payload: Mapping[str, object] | None,
        *,
        danger: bool = False,
    ) -> QPushButton:
        button = QPushButton(tr(text))
        button.source_text = text
        button.setProperty("dashboardCardAction", True)
        button.setProperty("i18nSourceText", text)
        button.setProperty("i18nSourceTextLanguage", "en")
        button.setProperty("linkAction", self._is_link_action(text))
        if danger:
            button.setProperty("dangerAction", True)
        button.setSizePolicy(
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )
        button.request_payload = dict(payload or {})
        button.clicked.connect(
            lambda: self.action_requested.emit(dict(button.request_payload))
        )
        return button

    def _refresh_action_styles(self) -> None:
        """Accent the first action only when the row ends in a plain link.

        A row of parallel, equally valid choices (e.g. install the kernel,
        Mesa, or both) must not have one arbitrarily highlighted as "the"
        answer. But a row shaped like primary action + a link out to the
        upstream project (the common case) reads better with that primary
        action picked out, so the eye lands on it instead of every button in
        the row looking equally weighted. Recomputed on every change instead
        of decided once, since the same button swaps between an action and a
        link as install state changes (see the "Check status" / "Open
        upstream project" toggle above).
        """
        buttons = [
            self.actions.itemAt(index).widget()
            for index in range(self.actions.count())
        ]
        buttons = [button for button in buttons if button is not None and button.isVisibleTo(self)]
        primary_gets_accent = (
            len(buttons) >= 2
            and bool(buttons[-1].property("linkAction"))
            and not buttons[0].property("linkAction")
            and not buttons[0].property("dangerAction")
        )
        for index, button in enumerate(buttons):
            button.setProperty("accented", index == 0 and primary_gets_accent)
            button.style().unpolish(button)
            button.style().polish(button)

    def add_action(
        self,
        text: str,
        payload: Mapping[str, object],
        *,
        danger: bool = False,
    ) -> QPushButton:
        button = self._action_button(text, payload, danger=danger)
        self.actions.addWidget(button, 1)
        self.actions_panel.show()
        self._refresh_action_styles()
        return button

    def update_action(
        self,
        button: QPushButton,
        *,
        text: str,
        payload: Mapping[str, object] | None = None,
        enabled: bool = True,
        visible: bool = True,
        tooltip: str = "",
    ) -> None:
        button.setText(tr(text))
        button.source_text = text
        button.setProperty("i18nSourceText", text)
        button.setProperty("linkAction", self._is_link_action(text))
        if payload is not None:
            button.request_payload = dict(payload)
        button.setEnabled(enabled)
        button.setVisible(visible)
        button.setToolTip(tr(tooltip) if tooltip else "")
        self._refresh_action_styles()

    def set_status(self, text: str, tone: str) -> None:
        self.status.setText(tr(text))
        self.status.set_tone(tone)
        self.status.show()

    def set_scope(self, text: str, tone: str = "gray") -> None:
        self.scope.setText(tr(text))
        self.scope.set_tone(tone)
        self.scope.show()


class PreparationSidebar(QFrame):
    """Compact in-dashboard adaptation of DependencyPreparationDialog."""

    prepare_requested = pyqtSignal(object)
    dependency_action_requested = pyqtSignal(object)
    driver_support_requested = pyqtSignal(str)

    COMPONENTS = (
        ("runtime", "Base dependencies", "Runtime files and packages."),
        ("governor", "Selected GPU governor", "Cyan or Oberon setup."),
        ("cpu_oc", "CPU OC tools", "bc250_smu_oc support."),
        ("core_unlock", "CPU Core Unlock source", "Experimental source."),
        ("umr", "UMR database", "Required for 40CU."),
        ("cu_manager", "40CU manager", "CU routing and restore."),
        ("fan_pwm", "NCT sensors and PWM", "Fan control route."),
    )

    def __init__(self, parent: QWidget | None = None, *, settings=None) -> None:
        super().__init__(parent)
        self._settings = settings or application_settings()
        self.setProperty("dashboardPreparation", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.system_bar = QFrame()
        system_layout = QHBoxLayout(self.system_bar)
        self.system_layout = system_layout
        system_layout.setContentsMargins(16, 12, 16, 10)
        system_layout.setSpacing(8)
        heading_copy = QVBoxLayout()
        heading_copy.setSpacing(3)
        heading_copy.addWidget(_label("Prepare BC250 system", "dashboardCardTitle"))
        self.system_label = _label(
            "Detected system: Not detected", "dashboardCardSubtitle"
        )
        heading_copy.addWidget(self.system_label)
        system_layout.addLayout(heading_copy, 1)
        self._header_actions: QWidget | None = None
        self.system_status = PillLabel("Not detected", "gray")
        self.system_status.hide()
        self.status = PillLabel("Not detected", "gray")
        self.status.hide()
        root.addWidget(self.system_bar)

        self.tabs_host = QWidget()
        self.tabs_host.setProperty("dashboardPreparationTabs", True)
        self.tabs_grid = QGridLayout(self.tabs_host)
        self.tabs_grid.setContentsMargins(12, 5, 12, 5)
        self.tabs_grid.setHorizontalSpacing(6)
        self.tabs_grid.setVerticalSpacing(8)
        self.tab_buttons: list[QPushButton] = []
        for index, text in enumerate(
            ("Components", "Compatibility", "Memory & Swap", "Decky", "Drivers")
        ):
            button = QPushButton(tr(text))
            button.setCheckable(True)
            button.setProperty("dashboardPreparationTab", True)
            button.setProperty("gamepadHorizontalGroup", "preparation-tabs")
            button.setProperty("gamepadHorizontalIndex", index)
            button.clicked.connect(
                lambda _checked=False, value=index: self.select_tab(value)
            )
            self.tab_buttons.append(button)
        root.addWidget(self.tabs_host)

        self.stack = _PreparationStack()
        self.stack.setMinimumWidth(0)
        self.stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        self.stack.addWidget(self._components_page())
        self.stack.addWidget(self._compatibility_page())
        self.stack.addWidget(self._memory_page())
        self.stack.addWidget(self._decky_page())
        self.stack.addWidget(self._drivers_page())
        root.addWidget(self.stack, 1)

        footer = QWidget()
        self.prepare_footer = footer
        footer.setProperty("dashboardPreparationFooter", True)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(7)
        self.prepare_button = QPushButton(tr("Prepare selected"))
        self.prepare_button.setProperty("dependencyPrepareButton", True)
        self.prepare_button.setProperty("dashboardPrepareAction", True)
        self.prepare_button.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.prepare_button.clicked.connect(self._emit_prepare)
        footer_layout.addWidget(self.prepare_button)

        self.rows = list(self.component_cards.values())
        self._tools: dict = {}
        self.memory_policy_combo.currentIndexChanged.connect(
            lambda: self._update_memory_controls(self._tools)
        )
        self.ttm_limit_combo.currentIndexChanged.connect(
            lambda: self._update_memory_controls(self._tools)
        )
        self._tab_columns = 0
        self._component_columns = 0
        self._reflow(390)
        self.select_tab(0)
        self._sync_components()

    def retranslate_dynamic_copy(self) -> None:
        """Refresh combo-box rows that the generic widget translator cannot see."""
        selected = self.compatibility_filter.currentData()
        blocked = self.compatibility_filter.blockSignals(True)
        try:
            for index, (label, _identifier) in enumerate(
                self.compatibility_filter_entries
            ):
                self.compatibility_filter.setItemText(index, tr(label))
            self.compatibility_filter.setAccessibleName(
                tr("Compatibility distribution filter")
            )
            self.compatibility_filter.setToolTip(
                tr(
                    "The detected distribution is selected by default. Your last filter is remembered."
                )
            )
            selected_index = self.compatibility_filter.findData(selected)
            if selected_index >= 0:
                self.compatibility_filter.setCurrentIndex(selected_index)
        finally:
            self.compatibility_filter.blockSignals(blocked)
        if getattr(self, "_last_preparation_state", None) is not None:
            self.set_state(self._last_preparation_state)

    def set_header_actions(self, actions: QWidget) -> None:
        """Place compact external links in the preparation header.

        The dashboard owns the buttons and their signals; this panel only gives
        them a stable, contextual location without consuming page space.
        """
        if self._header_actions is actions:
            return
        if self._header_actions is not None:
            self.system_layout.removeWidget(self._header_actions)
            self._header_actions.hide()
        self._header_actions = actions
        actions.setParent(self.system_bar)
        self.system_layout.addWidget(
            actions,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        actions.show()

    def _components_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)

        self.components_host = QWidget()
        self.components_grid = QGridLayout(self.components_host)
        self.components_grid.setContentsMargins(0, 0, 0, 0)
        self.components_grid.setHorizontalSpacing(8)
        self.components_grid.setVerticalSpacing(8)
        self.component_cards: dict[str, PreparationComponentCard] = {}
        for index, (key, title, detail) in enumerate(self.COMPONENTS):
            card = PreparationComponentCard(key, title, detail)
            card.checkbox.toggled.connect(self._sync_components)
            self.component_cards[key] = card
        layout.addWidget(self._bazzite_mitigations_panel())
        layout.addWidget(self.components_host)
        layout.addStretch(1)
        return page

    def _memory_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)
        layout.addWidget(self._build_memory_panel())
        layout.addStretch(1)
        return page

    def _memory_summary_tile(self, label: str, value: str) -> QFrame:
        tile = QFrame()
        tile.setProperty("metricTile", True)
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        layout.addWidget(_label(label, "metricTileLabel", wrap=False))
        value_label = _label(value, "metricTileValue", wrap=False)
        layout.addWidget(value_label)
        tile.value_label = value_label
        return tile

    def _memory_card(
        self, icon_name: str, background: str, title: str
    ) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
        card = QFrame()
        card.setProperty("dashboardMemoryCard", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(IconBadge(icon_name, background, 34, radius=9))
        header.addWidget(_label(title, "cardTitle"), 1)
        layout.addLayout(header)
        return card, layout, header

    def _build_memory_panel(self) -> QFrame:
        self.memory_panel = QFrame()
        memory_layout = QVBoxLayout(self.memory_panel)
        memory_layout.setContentsMargins(0, 0, 0, 0)
        memory_layout.setSpacing(16)

        panel_header = QHBoxLayout()
        panel_header.setSpacing(10)
        header_copy = QVBoxLayout()
        header_copy.setSpacing(3)
        header_copy.addWidget(_label("Memory & Swap", "dashboardCardTitle"))
        self.memory_detail = _label("Not detected", "dashboardCardSubtitle")
        header_copy.addWidget(self.memory_detail)
        panel_header.addLayout(header_copy, 1)
        self.memory_status_button = QPushButton(tr("View detailed status"))
        self.memory_status_button.setProperty("dashboardCardAction", True)
        self.memory_status_button.setIcon(icon("terminal_blue"))
        self.memory_status_button.setToolTip(
            tr("Opens a full technical report of the current memory and swap state in the built-in terminal.")
        )
        self.memory_status_button.clicked.connect(self._show_memory_status_report)
        panel_header.addWidget(self.memory_status_button, 0, Qt.AlignmentFlag.AlignTop)
        memory_layout.addLayout(panel_header)

        summary = QGridLayout()
        summary.setContentsMargins(0, 0, 0, 0)
        summary.setHorizontalSpacing(10)
        summary.setVerticalSpacing(10)
        self.memory_ram_tile = self._memory_summary_tile("Physical RAM", "—")
        self.memory_zram_tile = self._memory_summary_tile("ZRAM", "—")
        self.memory_backing_tile = self._memory_summary_tile("Disk swap", "—")
        self.memory_zswap_tile = self._memory_summary_tile("ZSWAP", "—")
        for column, tile in enumerate(
            (
                self.memory_ram_tile,
                self.memory_zram_tile,
                self.memory_backing_tile,
                self.memory_zswap_tile,
            )
        ):
            summary.addWidget(tile, 0, column)
            summary.setColumnStretch(column, 1)
        memory_layout.addLayout(summary)

        # ---- Swap and compression ----
        swap_card, swap_layout, swap_header = self._memory_card(
            "memory_green", "green_soft", "Swap and compression"
        )
        self.memory_scope = PillLabel("Bazzite only", "gray")
        swap_header.addWidget(self.memory_scope)

        self.memory_option_rows_host = QWidget()
        self.memory_option_rows_layout = QVBoxLayout(self.memory_option_rows_host)
        self.memory_option_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.memory_option_rows_layout.setSpacing(8)
        self.memory_option_rows: list[_MemoryOptionRow] = []
        swap_layout.addWidget(self.memory_option_rows_host)

        self.memory_swap_target_label = _label(
            "Swapfile location", "dashboardMemoryControlLabel"
        )
        self.memory_swap_target_combo = QComboBox()
        self.memory_swap_target_combo.setProperty("dashboardMemoryCombo", True)
        self.memory_swap_target_combo.addItem(tr("Default (/var/lib)"), "")
        swap_layout.addWidget(self.memory_swap_target_label)
        swap_layout.addWidget(self.memory_swap_target_combo)
        self.memory_swap_target_label.hide()
        self.memory_swap_target_combo.hide()

        self.memory_zram_warning_frame = QFrame()
        self.memory_zram_warning_frame.setProperty("dashboardMemoryNote", True)
        self.memory_zram_warning_frame.setProperty("tone", "orange")
        warning_row = QHBoxLayout(self.memory_zram_warning_frame)
        warning_row.setContentsMargins(10, 8, 10, 8)
        warning_row.setSpacing(8)
        warning_row.addWidget(IconBadge("warning_orange", "orange_soft", 32))
        self.memory_zram_warning = _label("", "dashboardMemoryWarning")
        self.memory_zram_warning.setWordWrap(True)
        warning_row.addWidget(self.memory_zram_warning, 1)
        self.memory_zram_warning_frame.hide()
        swap_layout.addWidget(self.memory_zram_warning_frame)

        usage_row = QHBoxLayout()
        usage_row.setSpacing(8)
        self.memory_swap_usage_bar = QProgressBar()
        self.memory_swap_usage_bar.setProperty("dashboardMemoryUsage", True)
        self.memory_swap_usage_bar.setTextVisible(False)
        self.memory_swap_usage_bar.setRange(0, 100)
        self.memory_swap_usage_bar.setFixedHeight(6)
        usage_row.addWidget(self.memory_swap_usage_bar, 1)
        self.memory_swap_usage_label = _label("", "dashboardMemoryDetail", wrap=False)
        usage_row.addWidget(self.memory_swap_usage_label)
        self.memory_usage_row = usage_row
        self.memory_swap_usage_bar.hide()
        self.memory_swap_usage_label.hide()
        swap_layout.addLayout(usage_row)

        self.memory_policy_combo = QComboBox()
        self.memory_policy_combo.setProperty("dashboardMemoryCombo", True)
        for label, value in (
            ("Keep Bazzite default (ZRAM)", "current"),
            ("Recommended · ZRAM + 16 GiB emergency swap", "zram-swap-16"),
            ("Advanced · ZSWAP + 16 GiB swapfile", "zswap-16"),
            ("Advanced heavy loads · ZSWAP + 32 GiB swapfile", "zswap-32"),
        ):
            self.memory_policy_combo.addItem(tr(label), value)
        # The combo stays the real, tested source of truth for the selected
        # policy; _MemoryOptionRow is only its on-screen presentation.
        self.memory_policy_combo.hide()
        swap_actions = QHBoxLayout()
        swap_actions.addStretch(1)
        self.memory_swap_apply_button = QPushButton(tr("Apply Swap"))
        self.memory_swap_apply_button.setProperty("dashboardCardAction", True)
        self.memory_swap_apply_button.clicked.connect(self._request_memory_swap)
        swap_actions.addWidget(self.memory_swap_apply_button)
        swap_layout.addLayout(swap_actions)
        memory_layout.addWidget(swap_card)

        # ---- TTM + VRAM ----
        gpu_row = QGridLayout()
        gpu_row.setHorizontalSpacing(16)
        gpu_row.setVerticalSpacing(16)
        gpu_row.setColumnStretch(0, 1)
        gpu_row.setColumnStretch(1, 1)

        ttm_card, ttm_layout, _ttm_header = self._memory_card(
            "gpu_purple", "purple_soft", "Dynamic GPU Memory Limit (TTM)"
        )
        self.memory_ttm_readout = _label("—", "metricTileValue", wrap=False)
        ttm_layout.addWidget(self.memory_ttm_readout)
        self.ttm_limit_combo = QComboBox()
        self.ttm_limit_combo.setProperty("dashboardMemoryCombo", True)
        self.ttm_limit_combo.addItem(tr("Keep current TTM limit"), 0)
        self.ttm_limit_combo.addItem(tr("Kernel default (remove BC250 TTM limit)"), -1)
        for target in (8, 10, 12):
            self.ttm_limit_combo.addItem(
                tr_format("Limit GPU allocations to {size} GiB", size=target), target
            )
        self.ttm_limit_combo.hide()
        self.ttm_limit_combo.currentIndexChanged.connect(self._update_ttm_readout)
        self.memory_ttm_timeline = _AllocationTimeline(self.ttm_limit_combo)
        ttm_layout.addWidget(self.memory_ttm_timeline)
        ttm_layout.addWidget(
            _label(
                "TTM limits managed GPU pages; it is not a guaranteed VRAM reservation.",
                "dashboardMemoryDetail",
            )
        )
        self.memory_ttm_apply_button = QPushButton(tr("Apply TTM"))
        self.memory_ttm_apply_button.setProperty("dashboardCardAction", True)
        self.memory_ttm_apply_button.clicked.connect(self._request_memory_ttm)
        ttm_layout.addWidget(self.memory_ttm_apply_button)
        gpu_row.addWidget(ttm_card, 0, 0)

        vram_card, vram_layout, _vram_header = self._memory_card(
            "vram_gray", "cyan_soft", "VRAM size (UMA_SIZE)"
        )
        self.memory_vram_readout = _label("—", "metricTileValue", wrap=False)
        vram_layout.addWidget(self.memory_vram_readout)
        self._tools_snapshot: Mapping[str, object] = {}
        self.vram_size_combo = QComboBox()
        self.vram_size_combo.setProperty("dashboardMemoryCombo", True)
        self.vram_size_combo.addItem(tr("Keep current VRAM size"), 0)
        for target in VRAM_SIZE_PRESETS_MB:
            self.vram_size_combo.addItem(vram_size_label(target), target)
        self.vram_size_combo.hide()
        self.vram_size_combo.currentIndexChanged.connect(self._update_vram_control)
        self.memory_vram_timeline = _AllocationTimeline(self.vram_size_combo)
        vram_layout.addWidget(self.memory_vram_timeline)
        self.vram_apply_button = QPushButton(tr("Apply VRAM"))
        self.vram_apply_button.setProperty("dashboardCardAction", True)
        self.vram_apply_button.clicked.connect(self._request_vram_apply)
        vram_layout.addWidget(self.vram_apply_button)
        gpu_row.addWidget(vram_card, 0, 1)
        memory_layout.addLayout(gpu_row)

        self._sync_memory_option_rows()
        self._update_ttm_readout()
        self._update_vram_readout()
        return self.memory_panel

    def _sync_memory_option_rows(self) -> None:
        combo = self.memory_policy_combo
        while len(self.memory_option_rows) < combo.count():
            row = _MemoryOptionRow()
            index = len(self.memory_option_rows)
            row.clicked.connect(lambda i=index: self.memory_policy_combo.setCurrentIndex(i))
            self.memory_option_rows.append(row)
            self.memory_option_rows_layout.addWidget(row)
        while len(self.memory_option_rows) > combo.count():
            row = self.memory_option_rows.pop()
            self.memory_option_rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        for index, row in enumerate(self.memory_option_rows):
            value = str(combo.itemData(index) or "")
            row.set_content(combo.itemText(index), tr(_MEMORY_POLICY_DETAILS.get(value, "")))
            row.set_selected(index == combo.currentIndex())
            model_item = combo.model().item(index)
            enabled = combo.isEnabled() and (model_item is None or model_item.isEnabled())
            row.setEnabled(enabled)
            tooltip = model_item.toolTip() if model_item is not None else ""
            row.setToolTip(tooltip)

    def _update_ttm_readout(self) -> None:
        self.memory_ttm_readout.setText(self.ttm_limit_combo.currentText())
        self.memory_ttm_timeline.refresh()

    def _update_vram_readout(self) -> None:
        self.memory_vram_readout.setText(self.vram_size_combo.currentText())
        self.memory_vram_timeline.refresh()

    def _update_memory_summary_tiles(self, runtime: Mapping[str, object]) -> None:
        physical = runtime.get("physical_ram_bytes")
        self.memory_ram_tile.value_label.setText(
            f"{round(int(physical) / (1024 ** 3), 1)} GiB"
            if isinstance(physical, (int, float)) and physical
            else "—"
        )
        zram = runtime.get("zram_total_bytes")
        self.memory_zram_tile.value_label.setText(
            f"{round(int(zram) / (1024 ** 3), 1)} GiB"
            if runtime.get("zram_active") and isinstance(zram, (int, float))
            else tr("Disabled")
        )
        self.memory_backing_tile.value_label.setText(
            tr("Active") if runtime.get("backing_swap_active") else tr("None")
        )
        self.memory_zswap_tile.value_label.setText(
            tr("Active") if runtime.get("zswap_enabled") is True else tr("Disabled")
        )

    # ---------------------------------------------------------- status report

    @staticmethod
    def _report_gib(value: object, *, default: str) -> str:
        try:
            if value is None:
                return default
            return f"{round(int(value) / (1024 ** 3), 1)} GiB"
        except (TypeError, ValueError):
            return default

    #: Column budget for the report body. Chosen to fit an 80-column terminal
    #: with a little breathing room either side.
    REPORT_WIDTH = 76

    @classmethod
    def _report_banner(cls, title: str) -> list[str]:
        """The single top/bottom framed banner. Everything else is plain text.

        Boxing every subsection used to fight word-wrap: a label plus a long
        translated value routinely overflowed the inner width, and the ``|``
        borders turned that overflow into a visibly broken frame. One banner
        at each end reads as "this is a report", without re-fighting wrap on
        every paragraph inside it.
        """
        border = "+" * cls.REPORT_WIDTH
        return [border, f"  {title}", border]

    @classmethod
    def _report_heading(cls, title: str) -> list[str]:
        return ["", title.upper(), "-" * cls.REPORT_WIDTH]

    @classmethod
    def _report_field(cls, label: str, value: str) -> str:
        """One ``label ..... value`` line, wrapping the value below when it

        cannot fit next to its label instead of overflowing the column.
        """
        label = str(label)
        value = str(value)
        gap = cls.REPORT_WIDTH - len(label) - len(value) - 2
        if gap >= 3:
            return f"{label} {'.' * gap} {value}"
        return f"{label}:\n      {value}"

    @classmethod
    def _report_paragraph(cls, text: str, *, indent: str = "") -> list[str]:
        return textwrap.wrap(
            text, width=cls.REPORT_WIDTH - len(indent),
            initial_indent=indent, subsequent_indent=indent,
        ) or [""]

    def _build_memory_status_report(self) -> str:
        """Compose the human-readable report shown in the embedded terminal.

        Pulled entirely from the state already cached for the on-screen
        tiles/combos, so opening it never waits on the privileged helper or
        touches the system — it is read-only by construction.
        """
        tools = _mapping(self._tools_snapshot) or _mapping(self._tools)
        setup = _mapping(tools.get("system_setup"))
        memory = _mapping(setup.get("memory"))
        runtime = _mapping(tools.get("memory_runtime"))
        host_label = "Bazzite" if is_bazzite_host(tools) else tr("Generic Linux host")

        physical = self._report_gib(runtime.get("physical_ram_bytes"), default=tr("unknown"))
        zram_active = bool(runtime.get("zram_active"))
        zram_line = (
            self._report_gib(runtime.get("zram_total_bytes"), default=tr("unknown"))
            if zram_active else tr("Disabled")
        )
        backing_line = tr("Active") if runtime.get("backing_swap_active") else tr("None")
        zswap_line = tr("Active") if runtime.get("zswap_enabled") is True else tr("Disabled")
        ttm_bytes = runtime.get("ttm_limit_bytes")
        ttm_line = (
            self._report_gib(ttm_bytes, default=tr("unknown"))
            if isinstance(ttm_bytes, (int, float)) and ttm_bytes
            else tr("Kernel default (no BC250 limit set)")
        )

        used_bytes = memory.get("swap_used_bytes")
        swap_active = bool(memory.get("swap_active"))
        usage_line = (
            tr_format(
                "{used} in use",
                used=self._report_gib(used_bytes, default=tr("unknown")),
            )
            if swap_active and isinstance(used_bytes, (int, float))
            else tr("Not in use right now")
        )
        configured_policy = str(memory.get("configured_policy") or "") or tr("none applied yet")
        reboot_pending = any(
            memory.get(key)
            for key in ("restore_pending", "zram_pending", "zram_restore_pending", "zswap_pending")
        )

        selected_policy = self.memory_policy_combo.currentText()
        selected_ttm = self.ttm_limit_combo.currentText()
        selected_vram = self.vram_size_combo.currentText()

        lines: list[str] = []
        lines += self._report_banner(tr("BC250 CONTROL CENTER - MEMORY & SWAP STATUS"))

        lines += self._report_heading(tr("Current state"))
        lines.append(self._report_field(tr("Detected system"), host_label))
        lines.append(self._report_field(tr("Physical RAM"), physical))
        lines.append("")
        lines.append(self._report_field(tr("ZRAM (compressed RAM swap)"), zram_line))
        lines.append(self._report_field(tr("Disk swap (swapfile on disk)"), backing_line))
        lines.append(self._report_field(tr("ZSWAP (compressed cache before swap)"), zswap_line))
        lines.append(self._report_field(tr("Swap usage right now"), usage_line))
        lines.append("")
        lines.append(self._report_field(tr("Active swap policy"), tr(configured_policy)))
        lines.append(self._report_field(tr("GPU memory limit (TTM) applied"), ttm_line))
        if reboot_pending:
            lines.append("")
            lines += self._report_paragraph(
                tr("[!] A change is saved but needs a REBOOT before it takes full effect.")
            )

        lines += self._report_heading(tr("Selected in the UI (not applied yet)"))
        lines.append(self._report_field(tr("Swap option"), selected_policy))
        lines.append(self._report_field(tr("TTM limit"), selected_ttm))
        lines.append(self._report_field(tr("VRAM size"), selected_vram))
        lines.append("")
        lines += self._report_paragraph(
            tr(
                "Nothing above changes anything by itself: press \"Apply Swap\", "
                "\"Apply TTM\" or \"Apply VRAM\" in the dashboard to actually apply it."
            )
        )
        return "\n".join(lines)

    def _show_memory_status_report(self) -> None:
        report = self._build_memory_status_report()
        heredoc_marker = "BC250_MEMORY_STATUS_REPORT"
        width = self.REPORT_WIDTH
        rule = "-" * width
        banner = "+" * width
        tech_heading = tr("Live technical detail (read-only)")
        close_hint = tr("Press Enter to close this report")
        script = (
            f"cat <<'{heredoc_marker}'\n{report}\n{heredoc_marker}\n"
            "echo\n"
            f"printf '%s\\n' {shlex.quote(rule)}\n"
            f"printf '%s\\n' {shlex.quote(tech_heading)}\n"
            f"printf '%s\\n' {shlex.quote(rule)}\n"
            "{ free -h 2>/dev/null || echo '(free: unavailable)'; } | sed 's/^/  /'\n"
            "echo\n"
            "{ swapon --show 2>/dev/null || echo '(no active swap devices)'; } | sed 's/^/  /'\n"
            "echo\n"
            "{ zramctl 2>/dev/null || echo '(zramctl: unavailable)'; } | sed 's/^/  /'\n"
            "echo\n"
            f"printf '%s\\n' {shlex.quote(banner)}\n"
            "echo\n"
            f"read -r -p {shlex.quote(close_hint + '... ')} _ || true\n"
        )
        try:
            TerminalRepository()._abrir_terminal(
                script, tr("BC250 memory and swap status")
            )
        except RuntimeError as error:
            InfoDialog(
                "Could not open the status report",
                str(error),
                icon_name="warning_orange",
                parent=self.window(),
                eyebrow="Memory & Swap",
                notice="No changes were made.",
                tone="orange",
            ).open()

    def _bazzite_mitigations_panel(self) -> QFrame:
        panel = QFrame()
        self.mitigations_panel = panel
        panel.setProperty("dashboardMemoryPanel", True)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QBoxLayout(QBoxLayout.Direction.LeftToRight, panel)
        self.mitigations_layout = root
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        copy = QVBoxLayout()
        copy.setSpacing(4)
        header = QHBoxLayout()
        header.setSpacing(8)
        self.mitigations_label = _label(
            "CPU security mitigations", "dashboardComponentTitle"
        )
        header.addWidget(self.mitigations_label)
        self.mitigations_status = PillLabel("Not detected", "gray")
        header.addWidget(self.mitigations_status)
        header.addStretch(1)
        # No distribution badge here. The whole panel is already hidden unless
        # this host can act on mitigations, so a pill saying "Bazzite" beside
        # the button only repeated what showing the panel at all had said.
        copy.addLayout(header)
        self.mitigations_detail = _label(
            "Disabling CPU security mitigations can improve some workloads but exposes the system to additional CPU vulnerabilities.",
            "dashboardMemoryDetail",
        )
        self.mitigations_detail.setWordWrap(True)
        copy.addWidget(self.mitigations_detail)
        root.addLayout(copy, 1)

        self.mitigations_apply_button = QPushButton(tr("Disable mitigations"))
        self.mitigations_apply_button.setProperty("dashboardCardAction", True)
        self.mitigations_apply_button.setProperty("dangerAction", True)
        self.mitigations_apply_button.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.mitigations_apply_button.clicked.connect(self._request_mitigations)
        self._mitigations_action = "disable"
        root.addWidget(self.mitigations_apply_button)
        panel.hide()
        return panel

    def _compatibility_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)

        self.compatibility_filter_panel = QFrame()
        self.compatibility_filter_panel.setProperty(
            "dashboardCompatibilityFilter", True
        )
        filter_layout = QHBoxLayout(self.compatibility_filter_panel)
        filter_layout.setContentsMargins(12, 8, 12, 8)
        filter_layout.setSpacing(8)
        filter_layout.addWidget(
            _label("Show compatibility for", "dashboardCompatibilityLabel", wrap=False)
        )
        self.compatibility_filter = _ClickOnlyComboBox()
        self.compatibility_filter.setProperty("dashboardMemoryCombo", True)
        self.compatibility_filter.setProperty("gamepadEntry", True)
        self.compatibility_filter.setMinimumWidth(0)
        self.compatibility_filter.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.compatibility_filter.setAccessibleName(
            tr("Compatibility distribution filter")
        )
        self.compatibility_filter.setToolTip(
            tr(
                "The detected distribution is selected by default. Your last filter is remembered."
            )
        )
        self.compatibility_filter_entries = (
            ("Detected system", "detected"),
            ("All distributions", "all"),
            ("SteamOS", "steamos"),
            ("Bazzite", "bazzite"),
            ("Arch Linux / CachyOS / Manjaro", "arch"),
            ("Fedora", "fedora"),
            ("Ubuntu / Debian", "debian"),
            ("Other distributions", "other"),
        )
        for label, identifier in self.compatibility_filter_entries:
            self.compatibility_filter.addItem(tr(label), identifier)
        stored_filter = str(
            self._settings.value("compatibility/distribution_filter", "detected")
            or "detected"
        )
        selected_index = self.compatibility_filter.findData(stored_filter)
        self.compatibility_filter.setCurrentIndex(max(0, selected_index))
        self.compatibility_filter.currentIndexChanged.connect(
            self._compatibility_filter_changed
        )
        filter_layout.addWidget(self.compatibility_filter, 1)
        layout.addWidget(self.compatibility_filter_panel)
        # The distribution filter stays wired (settings, tests, and the
        # "detected" default all still go through it) but is not shown: it
        # sat above every card fighting for attention, and "detected" is
        # already the right choice for the one system this window is on.
        self.compatibility_filter_panel.hide()
        self.acpi_card = PreparationInfoCard(
            "CPU power management · ACPI",
            "Upstream CPU idle and frequency tables. The original boot entry remains available for recovery.",
            scope_text="Validated · Arch / CachyOS / Manjaro",
            status_text="Not installed",
        )
        self.acpi_card.action_requested.connect(self._forward_dependency_action)
        self.acpi_detail = self.acpi_card.detail
        self.acpi_status = self.acpi_card.status
        self.acpi_install_button = self.acpi_card.add_action(
            "Install correction", {"action": "acpi-install"}
        )
        self.acpi_remove_button = self.acpi_card.add_action(
            "Uninstall", {"action": "acpi-uninstall"}, danger=True
        )
        self.acpi_check_button = self.acpi_card.add_action(
            "Check status", {"action": "acpi-status"}
        )
        self.acpi_upstream_button = self.acpi_card.add_action(
            "Open upstream project", {"action": "acpi_upstream"}
        )
        self.acpi_install_button.setEnabled(False)
        self.acpi_remove_button.setEnabled(False)
        layout.addWidget(self.acpi_card)
        self.cyan_card = PreparationInfoCard(
            "Cyan Skillfish Governor",
            "Recommended GPU governor. Supports SMU or patched-kernel controls, selectable load monitoring and D-Bus ranges.",
            action_text="Install / update",
            payload={"action": "prepare", "governor": "cyan-skillfish-governor-smu"},
            secondary_action_text="Uninstall",
            secondary_payload={
                "action": "remove",
                "governor": "cyan-skillfish-governor-smu",
            },
            scope_text="Arch · Fedora · Debian/Ubuntu · Bazzite",
            status_text="Not installed",
        )
        self.oberon_card = PreparationInfoCard(
            "Oberon Governor",
            "Alternative YAML-based backend. GPU telemetry repair remains a separate compatibility step.",
            action_text="Install / update",
            payload={"action": "prepare", "governor": "oberon-governor"},
            secondary_action_text="Uninstall",
            secondary_payload={"action": "remove", "governor": "oberon-governor"},
            scope_text="Alternative backend",
            status_text="Not installed",
        )
        for card in (self.cyan_card, self.oberon_card):
            card.action_requested.connect(self._forward_dependency_action)
            layout.addWidget(card)
        self.gfx_card = PreparationInfoCard(
            "GFX1013 async compute",
            "Kernel and Mesa must be matched. The interface enables installation only on a reviewed distribution path.",
            scope_text="Detecting distribution",
            status_text="Checking",
        )
        self.gfx_primary_button = self.gfx_card.add_action(
            "Open upstream project", {"action": "gfx1013_upstream", "governor": ""}
        )
        self.gfx_secondary_button = self.gfx_card.add_action(
            "Open upstream project", {"action": "gfx1013_upstream", "governor": ""}
        )
        self.gfx_tertiary_button = self.gfx_card.add_action(
            "Open upstream project", {"action": "gfx1013_upstream", "governor": ""}
        )
        self.gfx_quaternary_button = self.gfx_card.add_action(
            "Open upstream project", {"action": "gfx1013_upstream", "governor": ""}
        )
        self.gfx_quinary_button = self.gfx_card.add_action(
            "Open upstream project",
            {"action": "gfx1013_upstream", "governor": ""},
            danger=True,
        )
        self.gfx_secondary_button.hide()
        self.gfx_tertiary_button.hide()
        self.gfx_tertiary_button.setEnabled(FSR4_UI_ENABLED)
        self.gfx_quaternary_button.hide()
        self.gfx_quinary_button.hide()
        self.gfx_card.primary_button = self.gfx_primary_button
        self.gfx_card.secondary_button = self.gfx_secondary_button
        self.gfx_card.action_requested.connect(self._forward_dependency_action)
        self.steamos_graphics_state = QFrame()
        self.steamos_graphics_state.setProperty("dashboardCompatibilityState", True)
        steamos_state_layout = QHBoxLayout(self.steamos_graphics_state)
        steamos_state_layout.setContentsMargins(9, 6, 9, 6)
        steamos_state_layout.setSpacing(8)
        self.steamos_kernel_status = PillLabel("Not installed", "gray")
        self.steamos_radv_status = PillLabel("Not installed", "gray")
        self.steamos_fsr4_status = PillLabel("Not installed", "gray")
        steamos_graphics_rows = [
            ("Kernel / AMDGPU", self.steamos_kernel_status),
            ("Mesa / RADV", self.steamos_radv_status),
        ]
        if FSR4_UI_ENABLED:
            steamos_graphics_rows.append(
                ("FSR4 per game", self.steamos_fsr4_status)
            )
        for label, pill in steamos_graphics_rows:
            steamos_state_layout.addWidget(
                _label(label, "dashboardCompatibilityLabel", wrap=False)
            )
            steamos_state_layout.addWidget(pill)
        steamos_state_layout.addStretch(1)
        self.gfx_card.layout().insertWidget(2, self.steamos_graphics_state)
        self.steamos_graphics_state.hide()
        self.steamos_fsr4_launch_row = QFrame()
        self.steamos_fsr4_launch_row.setProperty("fsr4LaunchOption", True)
        steamos_fsr4_launch_layout = QHBoxLayout(self.steamos_fsr4_launch_row)
        steamos_fsr4_launch_layout.setContentsMargins(8, 5, 6, 5)
        steamos_fsr4_launch_layout.setSpacing(7)
        steamos_fsr4_launch_layout.addWidget(
            _label("Steam launch option", "dashboardCompatibilityLabel", wrap=False)
        )
        steamos_fsr4_launch_layout.addStretch(1)
        self.steamos_fsr4_copy_button = IconButton("⧉")
        self.steamos_fsr4_copy_button.setProperty("fsr4LaunchCopy", True)
        self.steamos_fsr4_copy_button.setFixedSize(30, 30)
        self.steamos_fsr4_copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.steamos_fsr4_copy_button.setAccessibleName(
            tr("Copy Steam launch option")
        )
        self.steamos_fsr4_copy_button.setToolTip(tr("Copy Steam launch option"))
        self.steamos_fsr4_copy_button.clicked.connect(
            self._copy_steamos_fsr4_launch_option
        )
        steamos_fsr4_launch_layout.addWidget(self.steamos_fsr4_copy_button)
        if FSR4_UI_ENABLED:
            self.gfx_card.layout().insertWidget(3, self.steamos_fsr4_launch_row)
        self.steamos_fsr4_launch_row.hide()
        self._steamos_fsr4_launch_option = ""
        layout.addWidget(self.gfx_card)
        self.cachyos_stack_card = PreparationInfoCard(
            "Arch / CachyOS BC-250 graphics stack · includes GFX1013 fix",
            "MastaG's matched kernel and Mesa/RADV include the GFX1013 async-compute fix. They can be installed separately or together; the current kernel stays as a boot fallback.",
            scope_text="Arch Linux · CachyOS",
            status_text="Checking",
        )
        cachyos_state = QFrame()
        cachyos_state.setProperty("dashboardCompatibilityState", True)
        cachyos_state_layout = QHBoxLayout(cachyos_state)
        cachyos_state_layout.setContentsMargins(9, 6, 9, 6)
        cachyos_state_layout.setSpacing(10)
        cachyos_state_layout.addWidget(
            _label("Kernel", "dashboardCompatibilityLabel", wrap=False)
        )
        self.cachyos_kernel_status = PillLabel("Not installed", "gray")
        cachyos_state_layout.addWidget(self.cachyos_kernel_status)
        cachyos_state_layout.addSpacing(8)
        cachyos_state_layout.addWidget(
            _label("Mesa / RADV", "dashboardCompatibilityLabel", wrap=False)
        )
        self.cachyos_mesa_status = PillLabel("Not installed", "gray")
        cachyos_state_layout.addWidget(self.cachyos_mesa_status)
        cachyos_state_layout.addStretch(1)
        self.cachyos_stack_card.layout().insertWidget(2, cachyos_state)
        self.cachyos_kernel_button = self.cachyos_stack_card.add_action(
            "Install kernel", {"action": "cachyos_bc250_kernel", "governor": ""}
        )
        self.cachyos_mesa_button = self.cachyos_stack_card.add_action(
            "Install Mesa", {"action": "cachyos_bc250_mesa", "governor": ""}
        )
        self.cachyos_full_button = self.cachyos_stack_card.add_action(
            "Install kernel + Mesa", {"action": "cachyos_bc250_full", "governor": ""}
        )
        self.cachyos_stack_card.primary_button = self.cachyos_kernel_button
        self.cachyos_stack_card.secondary_button = self.cachyos_mesa_button
        self.cachyos_stack_card.action_requested.connect(
            self._forward_dependency_action
        )
        # Compatibility aliases for callers that previously addressed three cards.
        self.cachyos_kernel_card = self.cachyos_stack_card
        self.cachyos_mesa_card = self.cachyos_stack_card
        self.cachyos_full_card = self.cachyos_stack_card

        self.fsr4_card = PreparationInfoCard(
            "BC-250 FSR4 V3 (experimental)",
            "Official upstream per-game RADV runtime. It is isolated in your user folder and never replaces system Mesa.",
            scope_text="Prebuilt: Arch/CachyOS · Source build: other distros",
            status_text="Checking",
        )
        self.fsr4_launch_row = QFrame()
        self.fsr4_launch_row.setProperty("fsr4LaunchOption", True)
        fsr4_launch_layout = QHBoxLayout(self.fsr4_launch_row)
        fsr4_launch_layout.setContentsMargins(8, 5, 6, 5)
        fsr4_launch_layout.setSpacing(7)
        self.fsr4_launch_label = _label(
            "Steam launch option", "dashboardCompatibilityLabel", wrap=False
        )
        fsr4_launch_layout.addWidget(self.fsr4_launch_label)
        fsr4_launch_layout.addStretch(1)
        self.fsr4_copy_button = IconButton("⧉")
        self.fsr4_copy_button.setProperty("fsr4LaunchCopy", True)
        self.fsr4_copy_button.setFixedSize(30, 30)
        self.fsr4_copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fsr4_copy_button.setAccessibleName(tr("Copy Steam launch option"))
        self.fsr4_copy_button.setToolTip(tr("Copy Steam launch option"))
        self.fsr4_copy_button.clicked.connect(self._copy_fsr4_launch_option)
        fsr4_launch_layout.addWidget(self.fsr4_copy_button)
        self.fsr4_card.layout().insertWidget(2, self.fsr4_launch_row)
        self.fsr4_launch_row.hide()
        self._fsr4_launch_option = ""
        self.fsr4_install_button = self.fsr4_card.add_action(
            "Install per-game FSR4", {"action": "fsr4_install", "governor": ""}
        )
        self.fsr4_remove_button = self.fsr4_card.add_action(
            "Remove per-game FSR4",
            {"action": "fsr4_uninstall", "governor": ""},
            danger=True,
        )
        self.fsr4_upstream_button = self.fsr4_card.add_action(
            "Open upstream project", {"action": "fsr4_upstream", "governor": ""}
        )
        self.fsr4_card.action_requested.connect(self._forward_dependency_action)
        self.fsr4_card.setEnabled(FSR4_UI_ENABLED)
        self.fsr4_install_card = self.fsr4_card
        self.fsr4_remove_card = self.fsr4_card
        self.fsr4_source_card = self.fsr4_card
        self.cachyos_cards = (self.cachyos_stack_card,)
        self.fsr4_cards = (self.fsr4_card,)
        for card in (*self.cachyos_cards, *self.fsr4_cards):
            layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _decky_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)
        self.decky_card = PreparationInfoCard(
            "Game Mode Quick Access (Beta)",
            "Decky is optional. It is never installed by generic dependency preparation.",
            action_text="Install Decky + Quick Access (Beta)",
            payload={"action": "quick_access_install_decky", "governor": ""},
        )
        self.decky_preview_button = self.decky_card.add_action(
            "Preview", {"action": "decky_preview", "governor": ""}
        )
        self.decky_card.action_requested.connect(self._handle_decky_action)
        layout.addWidget(self.decky_card)
        explanation = PreparationInfoCard(
            "Console interface preview",
            "Open the current BC250 panel screenshot in a separate preview window. It never contacts the privileged helper or changes hardware.",
            scope_text="Safe preview",
            status_text="No hardware actions",
            status_tone="green",
        )
        layout.addWidget(explanation)
        layout.addStretch(1)
        return page

    def _handle_decky_action(self, payload: object) -> None:
        values = dict(payload) if isinstance(payload, Mapping) else {}
        if values.get("action") != "decky_preview":
            self._forward_dependency_action(values)
            return
        host = self.window()
        dialog = getattr(self, "_decky_screenshot_dialog", None)
        if dialog is None or dialog.parentWidget() is not host:
            dialog = _DeckyScreenshotDialog(host)
            dialog.destroyed.connect(self._clear_decky_screenshot_dialog)
            self._decky_screenshot_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    @pyqtSlot()
    def _clear_decky_screenshot_dialog(self) -> None:
        # Qt disconnects this receiver during destruction of its parent page.
        self._decky_screenshot_dialog = None

    def _drivers_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        self.network_driver_card = PreparationInfoCard(
            "Wi-Fi and Bluetooth support",
            # Keep this source aligned with the complete driver catalog so the
            # Wi-Fi and Bluetooth preparation copy is available in every locale.
            "Active kernel drivers and official firmware packages.",
            action_text="Install support",
        )
        self.network_driver_card.action_requested.connect(
            lambda _payload: self.driver_support_requested.emit("connectivity")
        )
        self.printing_driver_card = PreparationInfoCard(
            "Printing support",
            "Driverless printing with CUPS, IPP and IPP-over-USB. Existing queues are preserved.",
            action_text="Install support",
        )
        self.printing_driver_card.action_requested.connect(
            lambda _payload: self.driver_support_requested.emit("printing")
        )
        layout.addWidget(self.network_driver_card)
        layout.addWidget(self.printing_driver_card)
        layout.addWidget(
            PreparationInfoCard(
                "External drivers",
                "Device-specific kernel modules are not generic driver packs.",
            )
        )
        layout.addStretch(1)
        return page

    def select_tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.prepare_footer.setVisible(index == 0)
        for button_index, button in enumerate(self.tab_buttons):
            button.setChecked(button_index == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def _reflow(self, width: int) -> None:
        tab_columns = 5 if width >= 620 else 3 if width >= 420 else 2
        self.system_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if width < 480
            else QBoxLayout.Direction.LeftToRight
        )
        self.system_layout.setAlignment(self.status, Qt.AlignmentFlag.AlignLeft)
        # Content-sized actions must recover their single-line width after a
        # compact layout. WrappingButton's visible sizeHint follows its width.
        self.prepare_button.setMinimumWidth(
            min(max(0, width - 34), IconButton.sizeHint(self.prepare_button).width())
        )
        for button in (
            self.memory_swap_apply_button,
            self.memory_ttm_apply_button,
            self.mitigations_apply_button,
        ):
            button.setMinimumWidth(
                min(max(0, (width - 64) // 3), IconButton.sizeHint(button).width())
            )
        compact_mitigations = width < 660
        self.mitigations_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if compact_mitigations
            else QBoxLayout.Direction.LeftToRight
        )
        self.mitigations_layout.setAlignment(
            self.mitigations_apply_button,
            Qt.AlignmentFlag.AlignLeft
            if compact_mitigations
            else Qt.AlignmentFlag.AlignVCenter,
        )
        component_columns = (
            4 if width >= 1280 else 3 if width >= 980 else 2 if width >= 650 else 1
        )
        if tab_columns != self._tab_columns:
            self._tab_columns = tab_columns
            clear_grid(self.tabs_grid, reset_columns=5, reset_rows=3)
            for index, button in enumerate(self.tab_buttons):
                self.tabs_grid.addWidget(
                    button, index // tab_columns, index % tab_columns
                )
            for column in range(tab_columns):
                self.tabs_grid.setColumnStretch(column, 1)
        if component_columns != self._component_columns:
            self._component_columns = component_columns
            clear_grid(self.components_grid, reset_columns=4, reset_rows=8)
            if component_columns == 1:
                row = 0
                for key, card in self.component_cards.items():
                    self.components_grid.addWidget(card, row, 0)
                    row += 1
                    if key == "core_unlock":
                        self.components_grid.addWidget(self.prepare_footer, row, 0)
                        row += 1
            else:
                last = component_columns - 1
                self.components_grid.addWidget(
                    self.component_cards["core_unlock"], 0, last
                )
                self.components_grid.addWidget(self.prepare_footer, 1, last)
                positions = (
                    (r, c)
                    for r in range(7)
                    for c in range(component_columns)
                    if (r, c) not in {(0, last), (1, last)}
                )
                for key, card in self.component_cards.items():
                    if key != "core_unlock":
                        row, column = next(positions)
                        self.components_grid.addWidget(card, row, column)
            for column in range(component_columns):
                self.components_grid.setColumnStretch(column, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow(event.size().width())

    def _sync_components(self) -> None:
        manager = self.component_cards.get("cu_manager")
        umr = self.component_cards.get("umr")
        if manager and umr:
            sender = self.sender()
            if sender is manager.checkbox and manager.checkbox.isChecked():
                umr.checkbox.setChecked(True)
            elif sender is umr.checkbox and not umr.checkbox.isChecked():
                manager.checkbox.setChecked(False)
        selected = self.selected_components
        self.prepare_button.setText(
            tr_format("Prepare selected ({count})", count=len(selected))
        )
        self.prepare_button.setEnabled("runtime" in selected)

    @property
    def selected_components(self) -> set[str]:
        return {
            key
            for key, card in self.component_cards.items()
            if card.checkbox.isChecked()
        }

    def _emit_prepare(self) -> None:
        self.prepare_requested.emit(
            {
                "action": "prepare",
                "governor": "auto",
                "selected_components": self.selected_components,
            }
        )

    def _request_memory_swap(self) -> None:
        self.dependency_action_requested.emit(
            {
                "action": "memory_swap",
                "governor": "",
                "selected_components": self.selected_components,
                "memory_policy": str(
                    self.memory_policy_combo.currentData() or "current"
                ),
                "memory_ttm_gib": 0,
                "memory_takeover_zram": self.memory_zram_warning.isVisible(),
                "memory_target_mount": str(
                    self.memory_swap_target_combo.currentData() or ""
                ) if hasattr(self, "memory_swap_target_combo") else "",
            }
        )

    def _request_memory_ttm(self) -> None:
        self.dependency_action_requested.emit(
            {
                "action": "memory_ttm",
                "governor": "",
                "selected_components": self.selected_components,
                "memory_policy": "preserve",
                "memory_ttm_gib": int(self.ttm_limit_combo.currentData() or 0),
            }
        )

    def _request_vram_apply(self) -> None:
        self.dependency_action_requested.emit(
            {
                "action": "vram_apply",
                "governor": "",
                "selected_components": self.selected_components,
                "vram_uma_size_mb": int(self.vram_size_combo.currentData() or 0),
            }
        )

    def _update_vram_control(self) -> None:
        setup = _mapping(self._tools_snapshot.get("system_setup"))
        vram = _mapping(setup.get("vram"))
        supported = bool(setup.get("helper_available") and vram.get("supported"))
        selected = int(self.vram_size_combo.currentData() or 0) != 0
        self.vram_apply_button.setEnabled(supported and selected)
        reason = str(setup.get("reason") or vram.get("reason") or "")
        tooltip = (
            tr(reason)
            if reason
            else tr("Written to CMOS immediately; takes effect after the next reboot.")
        )
        self.vram_size_combo.setToolTip(tooltip)
        self.vram_apply_button.setToolTip(tooltip)
        if hasattr(self, "memory_vram_timeline"):
            self._update_vram_readout()

    def _request_mitigations(self) -> None:
        self.dependency_action_requested.emit(
            {
                "action": f"bazzite_mitigations_{self._mitigations_action}",
                "governor": "",
                "selected_components": self.selected_components,
            }
        )

    def _update_mitigation_control(
        self, tools: Mapping[str, object], *, actionable: bool
    ) -> None:
        state = _mapping(tools.get("bazzite_mitigations"))
        configured = bool(state.get("configured"))
        managed = bool(state.get("managed"))
        available = bool(state.get("available"))
        preview = not actionable and bazzite_ui_preview_enabled()
        self.mitigations_panel.setVisible(actionable or preview)
        self.mitigations_status.setVisible(actionable)
        if not actionable:
            status = tr("Unavailable")
            tone = "gray"
        elif state.get("reboot_required"):
            status = tr("Reboot required")
            tone = "orange"
        elif configured:
            status = tr("Disabled")
            tone = "orange"
        else:
            status = tr("Enabled") if available else tr("Not detected")
            tone = "green" if available else "gray"
        self.mitigations_status.setText(status)
        self.mitigations_status.set_tone(tone)

        self._mitigations_action = "restore" if managed else "disable"
        self.mitigations_apply_button.setText(
            tr(
                "Managed externally"
                if configured and not managed
                else "Restore mitigations"
                if self._mitigations_action == "restore"
                else "Disable mitigations"
            )
        )
        self.mitigations_apply_button.setProperty(
            "dangerAction", self._mitigations_action == "disable"
        )
        self.mitigations_apply_button.style().unpolish(self.mitigations_apply_button)
        self.mitigations_apply_button.style().polish(self.mitigations_apply_button)
        self.mitigations_apply_button.setEnabled(
            actionable and available and (not configured or managed)
        )
        if configured and not managed:
            tooltip = tr(
                "mitigations=off was configured outside Control Center and is preserved."
            )
        elif not actionable:
            tooltip = tr("This workflow is available only on Bazzite.")
        else:
            tooltip = tr(
                "Disabling CPU security mitigations can improve some workloads but exposes the system to additional CPU vulnerabilities."
            )
        self.mitigations_apply_button.setToolTip(tooltip)

    def _update_memory_controls(self, tools: Mapping[str, object]) -> None:
        self._tools_snapshot = tools
        self._update_vram_control()
        actionable = is_bazzite_host(tools)
        self._update_mitigation_control(tools, actionable=actionable)
        runtime = _mapping(tools.get("memory_runtime"))
        zram = runtime.get("zram_total_bytes")
        zram_label = (
            f"{round(int(zram) / (1024**3), 1)} GiB"
            if runtime.get("zram_active") and isinstance(zram, (int, float))
            else tr("Disabled")
        )
        backing = tr("Active") if runtime.get("backing_swap_active") else tr("None")
        zswap = tr("Active") if runtime.get("zswap_enabled") is True else tr("Disabled")
        self.memory_detail.setText(
            tr_format(
                "Active now: ZRAM {zram} · disk swap {backing} · ZSWAP {zswap}",
                zram=zram_label,
                backing=backing,
                zswap=zswap,
            )
            if runtime
            else tr("Not detected")
        )
        self._update_memory_summary_tiles(runtime)
        if not update_memory_controls(self, tools):
            self.memory_scope.setText("Bazzite" if actionable else "Bazzite only")
            self.memory_scope.set_tone("green" if actionable else "gray")
            current_bytes = runtime.get("ttm_limit_bytes")
            current_gib = (
                round(int(current_bytes) / (1024**3))
                if isinstance(current_bytes, (int, float))
                else 0
            )
            if current_gib in {8, 10, 12} and self.ttm_limit_combo.currentData() == 0:
                self.ttm_limit_combo.setCurrentIndex((8, 10, 12).index(current_gib) + 2)
            policy = str(self.memory_policy_combo.currentData() or "current")
            swap_selected = policy != "current" or bool(
                runtime.get("backing_swap_active") or runtime.get("zswap_enabled") is True
            )
            ttm_selected = int(self.ttm_limit_combo.currentData() or 0) != 0
            self.memory_policy_combo.setEnabled(actionable)
            self.ttm_limit_combo.setEnabled(actionable)
            self.memory_swap_apply_button.setEnabled(actionable and swap_selected)
            self.memory_ttm_apply_button.setEnabled(actionable and ttm_selected)
            if not actionable:
                tooltip = tr("This memory workflow is currently validated only on Bazzite.")
                for control in (
                    self.memory_policy_combo,
                    self.ttm_limit_combo,
                    self.memory_swap_apply_button,
                    self.memory_ttm_apply_button,
                ):
                    control.setToolTip(tooltip)
        self._sync_memory_option_rows()
        self._update_ttm_readout()
        self._update_vram_readout()

    def _forward_dependency_action(self, payload: object) -> None:
        values = dict(payload) if isinstance(payload, Mapping) else {}
        values.setdefault("selected_components", self.selected_components)
        self.dependency_action_requested.emit(values)

    def _copy_fsr4_launch_option(self) -> None:
        if not self._fsr4_launch_option:
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._fsr4_launch_option)
        self.fsr4_copy_button.setText("✓")
        self.fsr4_copy_button.setToolTip(tr("Copied"))
        QTimer.singleShot(1600, self._restore_fsr4_copy_button)

    def _restore_fsr4_copy_button(self) -> None:
        self.fsr4_copy_button.setText("⧉")
        self.fsr4_copy_button.setToolTip(tr("Copy Steam launch option"))

    def _copy_steamos_fsr4_launch_option(self) -> None:
        if not self._steamos_fsr4_launch_option:
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._steamos_fsr4_launch_option)
        self.steamos_fsr4_copy_button.setText("✓")
        self.steamos_fsr4_copy_button.setToolTip(tr("Copied"))
        QTimer.singleShot(1600, self._restore_steamos_fsr4_copy_button)

    def _restore_steamos_fsr4_copy_button(self) -> None:
        self.steamos_fsr4_copy_button.setText("⧉")
        self.steamos_fsr4_copy_button.setToolTip(tr("Copy Steam launch option"))

    @staticmethod
    def _distribution_group(family: str) -> str:
        family = str(family or "").strip().lower()
        if family in {"arch", "cachyos", "manjaro"}:
            return "arch"
        if family in {"ubuntu", "debian"}:
            return "debian"
        if family in {"steamos", "bazzite", "fedora"}:
            return family
        return "other"

    def _compatibility_filter_changed(self) -> None:
        identifier = str(self.compatibility_filter.currentData() or "detected")
        self._settings.setValue("compatibility/distribution_filter", identifier)
        self._settings.sync()
        if getattr(self, "_last_preparation_state", None) is not None:
            self.set_state(self._last_preparation_state)
        else:
            self._apply_compatibility_filter()

    def _restore_compatibility_preview_actions(self) -> None:
        for button, enabled in getattr(self, "_preview_button_states", {}).items():
            button.setEnabled(enabled)
            if button.toolTip() == tr(
                "Preview only: select the detected system to install or change components."
            ):
                button.setToolTip("")
        self._preview_button_states = {}

    def _apply_compatibility_filter(self) -> None:
        self._restore_compatibility_preview_actions()
        actual = self._distribution_group(str(self._tools.get("os_family") or ""))
        choice = str(self.compatibility_filter.currentData() or "detected")
        selected = actual if choice == "detected" else choice
        show_all = selected == "all"
        preview = choice not in {"detected", "all"} and selected != actual
        labels = {
            "steamos": "SteamOS",
            "bazzite": "Bazzite",
            "arch": "Arch / CachyOS / Manjaro",
            "fedora": "Fedora",
            "debian": "Ubuntu / Debian",
            "other": "Other distributions",
        }
        self.acpi_card.setVisible(show_all or selected == "arch")
        self.cyan_card.setVisible(True)
        self.oberon_card.setVisible(True)
        self.gfx_card.setVisible(show_all or selected != "arch")
        self.cachyos_stack_card.setVisible(show_all or selected == "arch")
        self.fsr4_card.setVisible(FSR4_UI_ENABLED)

        if not preview:
            return

        self.gfx_card.set_scope(labels.get(selected, "Compatibility preview"), "blue")
        self.gfx_card.set_status("Preview only", "blue")
        preview_copy = {
            "steamos": "SteamOS 3.8/3.9 provides a reviewed two-stage path: install the matching AMDGPU module, reboot, then install the matched Mesa/RADV runtime.",
            "bazzite": "Bazzite is immutable. Direct kernel/Mesa patching is blocked; use a BC-250 image or a matching rpm-ostree package instead.",
            "arch": "Available only on plain Arch Linux or CachyOS",
            "fedora": "Fedora uses DryhoppedIPA's official current GFX1013 workflow. Control Center adds local safety gates, then leaves kernel and Mesa compatibility checks to upstream.",
            "debian": "Ubuntu and Debian currently expose governor and userspace tools; the GFX1013 kernel/Mesa patch remains a manual upstream path.",
            "other": "This distribution can use common governors when its packages are available. Kernel/Mesa compatibility stays manual until a reviewed path exists.",
        }
        self.gfx_card.detail.setText(tr(preview_copy[selected]))
        self.steamos_graphics_state.setVisible(selected == "steamos")
        self.steamos_fsr4_launch_row.hide()
        if selected == "steamos":
            pills = [
                self.steamos_kernel_status,
                self.steamos_radv_status,
            ]
            if FSR4_UI_ENABLED:
                pills.append(self.steamos_fsr4_status)
            for pill in pills:
                pill.setText(tr("Available on SteamOS"))
                pill.set_tone("blue")
            self.gfx_card.update_action(
                self.gfx_primary_button,
                text="1 · Install SteamOS kernel",
                payload={"action": "steamos_compat", "governor": ""},
                enabled=False,
            )
            self.gfx_card.update_action(
                self.gfx_secondary_button,
                text="2 · Install / repair Mesa RADV",
                payload={"action": "steamos_graphics_install", "governor": ""},
                enabled=False,
            )
            if FSR4_UI_ENABLED:
                self.gfx_card.update_action(
                    self.gfx_tertiary_button,
                    text="3 · Install per-game FSR4",
                    payload={
                        "action": "steamos_graphics_fsr4_install",
                        "governor": "",
                    },
                    enabled=False,
                )
            self.gfx_card.update_action(
                self.gfx_quaternary_button,
                text="Open upstream project",
                payload={"action": "gfx1013_upstream", "governor": ""},
            )
            self.gfx_quinary_button.hide()
        else:
            self.gfx_card.update_action(
                self.gfx_primary_button,
                text="Open upstream project",
                payload={"action": "gfx1013_upstream", "governor": ""},
            )
            for button in (
                self.gfx_secondary_button,
                self.gfx_tertiary_button,
                self.gfx_quaternary_button,
                self.gfx_quinary_button,
            ):
                button.hide()
        if selected == "arch":
            self.cachyos_stack_card.set_status("Available on Arch family", "blue")
        # A filter is allowed to demonstrate coverage, never to run another
        # distribution's installer on the detected host. Keep documentation
        # links usable and disable every mutating preview action.
        for card in (
            self.acpi_card,
            self.cyan_card,
            self.oberon_card,
            self.gfx_card,
            self.cachyos_stack_card,
            self.fsr4_card,
        ):
            for button in card.findChildren(QPushButton):
                action = str(getattr(button, "request_payload", {}).get("action") or "")
                if "upstream" not in action and "diagnostic" not in action:
                    self._preview_button_states[button] = button.isEnabled()
                    button.setEnabled(False)
                    button.setToolTip(
                        tr(
                            "Preview only: select the detected system to install or change components."
                        )
                    )

    def set_state(self, state) -> None:
        # Restore the last authoritative enabled states before new runtime
        # evidence updates the buttons. Otherwise leaving preview mode could
        # reapply an older disabled snapshot over freshly detected components.
        self._restore_compatibility_preview_actions()
        self._last_preparation_state = state
        tools = _mapping(getattr(state, "preparation_tools", {}))
        self._tools = tools
        setup = _mapping(tools.get("system_setup"))
        acpi = _mapping(setup.get("acpi"))
        status_text = {
            "active": "Active",
            "pending-reboot": "Reboot required",
            "not-active": "Not active",
            "incomplete": "Incomplete",
            "managed-elsewhere": "Managed externally",
            "needs-check": "Check status",
        }.get(acpi.get("status"), "Not installed")
        acpi_tone = (
            "green"
            if acpi.get("status") == "active"
            else "orange"
            if acpi.get("status") in {"pending-reboot", "incomplete", "not-active"}
            else "blue"
            if acpi.get("status") == "managed-elsewhere"
            else "gray"
        )
        self.acpi_card.set_status(status_text, acpi_tone)
        reason = str(setup.get("reason") or acpi.get("reason") or "")
        self.acpi_install_button.setEnabled(
            bool(
                setup.get("helper_available")
                and acpi.get("available")
                and not acpi.get("installed")
            )
        )
        self.acpi_remove_button.setEnabled(
            bool(setup.get("helper_available") and acpi.get("installed"))
        )
        self.acpi_install_button.setVisible(not bool(acpi.get("installed")))
        self.acpi_remove_button.setVisible(bool(acpi.get("installed")))
        self.acpi_card.setToolTip(tr(reason))
        capabilities = _mapping(tools.get("prepare_components"))
        fallback = {
            "runtime": bool(getattr(state, "dependencies_ready", False)),
            "governor": bool(getattr(state, "governor_tool_ready", False)),
            "cpu_oc": bool(getattr(state, "cpu_tools_ready", False)),
            "core_unlock": bool(getattr(state, "core_unlock_ready", False)),
            "umr": bool(getattr(state, "umr_ready", False)),
            "cu_manager": bool(getattr(state, "cu_manager_ready", False)),
            "fan_pwm": bool(getattr(state, "nct_ready", False)),
        }
        installed_values = []
        for key, card in self.component_cards.items():
            capability = _mapping(capabilities.get(key))
            if not capability:
                capability = {"available": True, "installed": fallback[key]}
            card.set_capability(capability)
            installed_values.append(bool(capability.get("installed")))
        all_ready = bool(installed_values) and all(installed_values)
        known = (
            bool(tools)
            or bool(getattr(state, "tools_state_available", False))
            or any(installed_values)
        )
        self.status.setText(
            "Operational" if all_ready else "Attention" if known else "Not detected"
        )
        self.status.set_tone("green" if all_ready else "orange" if known else "gray")

        os_label = str(tools.get("os_label") or tr("Not detected"))
        family = str(tools.get("os_family") or "")
        system_identity = (
            os_label
            if family.lower() in os_label.lower()
            else (f"{os_label} · {family}" if family else os_label)
        )
        self.system_label.setText(
            tr_format("Detected system: {distribution}", distribution=system_identity)
        )
        detected = bool(tools.get("os_label") or family)
        self.system_status.setText("Detected" if detected else "Not detected")
        self.system_status.set_tone("green" if detected else "gray")
        self._update_memory_controls(tools)

        family = str(tools.get("os_family") or "").lower()
        detected_governors = _mapping(tools.get("supported_gpu_governors"))
        for identifier, card in (
            ("cyan-skillfish-governor-smu", self.cyan_card),
            ("oberon-governor", self.oberon_card),
        ):
            if card.secondary_button is None:
                continue
            evidence = _mapping(detected_governors.get(identifier))
            installed = bool(evidence.get("detected"))
            active = bool(evidence.get("active"))
            card.set_status(
                "Active" if active else "Installed" if installed else "Not installed",
                "green" if active else "blue" if installed else "gray",
            )
            if card.primary_button is not None:
                card.update_action(
                    card.primary_button,
                    text="Update / repair" if installed else "Install / update",
                    enabled=True,
                )
            card.secondary_button.setEnabled(installed)
            card.secondary_button.setVisible(installed)
            card.secondary_button.setToolTip("" if installed else tr("Not installed"))
        masta = _mapping(tools.get("masta_bc250_stack"))
        masta_supported = bool(
            masta.get("supported", tools.get("masta_bc250_stack_supported"))
        )
        kernel_installed = bool(masta.get("kernel_installed"))
        kernel_active = bool(masta.get("kernel_active"))
        mesa_installed = bool(masta.get("mesa_installed"))
        if not masta_supported:
            self.cachyos_stack_card.set_status("Not compatible", "gray")
        elif kernel_installed and mesa_installed and kernel_active:
            self.cachyos_stack_card.set_status("Full stack installed", "green")
        elif kernel_installed and mesa_installed:
            self.cachyos_stack_card.set_status("Installed · reboot required", "orange")
        elif kernel_installed or mesa_installed:
            self.cachyos_stack_card.set_status("Partially installed", "orange")
        else:
            self.cachyos_stack_card.set_status("Available", "blue")
        self.cachyos_kernel_status.setText(
            tr("Active")
            if kernel_active
            else tr("Installed")
            if kernel_installed
            else tr("Not installed")
        )
        self.cachyos_kernel_status.set_tone(
            "green" if kernel_active else "blue" if kernel_installed else "gray"
        )
        self.cachyos_mesa_status.setText(
            tr("Patched installed") if mesa_installed else tr("Not installed")
        )
        self.cachyos_mesa_status.set_tone("green" if mesa_installed else "gray")
        unsupported_tip = "Available only on plain Arch Linux or CachyOS"
        self.cachyos_stack_card.update_action(
            self.cachyos_kernel_button,
            text="Update / repair kernel" if kernel_installed else "Install kernel",
            enabled=masta_supported,
            tooltip="" if masta_supported else unsupported_tip,
        )
        self.cachyos_stack_card.update_action(
            self.cachyos_mesa_button,
            text="Update / repair Mesa" if mesa_installed else "Install Mesa",
            enabled=masta_supported,
            tooltip="" if masta_supported else unsupported_tip,
        )
        self.cachyos_stack_card.update_action(
            self.cachyos_full_button,
            text="Update / repair full stack"
            if kernel_installed and mesa_installed
            else "Install kernel + Mesa",
            enabled=masta_supported,
            tooltip="" if masta_supported else unsupported_tip,
        )

        gfx_state = _mapping(tools.get("gfx1013_compute"))
        gfx = present_gfx1013(gfx_state, include_fsr4=FSR4_UI_ENABLED)
        reason_key = str(gfx_state.get("reason_key") or "manual-patches-only")
        gfx_scope = {
            "steamos-dedicated-backend": "SteamOS · Dedicated toolkit",
            "fedora-upstream-managed": "Fedora · Official upstream main",
            "arch-family-manual-untested": (
                "Arch / CachyOS · Included in MastaG stack"
                if masta_supported
                else "Arch family · Manual only"
            ),
            "bazzite-release-managed": "Bazzite 44 · Reviewed v0.2.4 release",
            "bazzite-release-kernel-unsupported": "Bazzite 44 · Compatible kernel required",
            "bazzite-release-version-unsupported": "Bazzite · Version not supported",
        }.get(reason_key, "Ubuntu / Debian / other · Manual only")
        self.gfx_card.set_scope(
            gfx_scope,
            "blue"
            if reason_key in {"steamos-dedicated-backend", "fedora-upstream-managed", "bazzite-release-managed"}
            or masta_supported
            else "gray",
        )
        self.gfx_card.set_status(gfx.status, gfx.tone)
        self.gfx_card.detail.setText(" ".join(tr(part) for part in gfx.detail))
        for button in (
            self.gfx_primary_button,
            self.gfx_secondary_button,
            self.gfx_tertiary_button,
            self.gfx_quaternary_button,
            self.gfx_quinary_button,
        ):
            button.hide()
        self.steamos_graphics_state.setVisible(
            reason_key == "steamos-dedicated-backend"
        )
        self._steamos_fsr4_launch_option = ""
        self.steamos_fsr4_launch_row.hide()
        if reason_key == "steamos-dedicated-backend":
            kernel_ready = bool(gfx_state.get("steamos_kernel_ready"))
            kernel_installed = bool(gfx_state.get("steamos_kernel_installed"))
            radv_state = str(
                gfx_state.get("steamos_external_radv_state") or "not-installed"
            )
            radv_current = bool(gfx_state.get("steamos_external_radv_current"))
            fsr4_state = str(
                gfx_state.get("steamos_external_fsr4_state") or "not-installed"
            )
            fsr4_current = bool(gfx_state.get("steamos_external_fsr4_current"))
            self._steamos_fsr4_launch_option = str(
                gfx_state.get("steamos_external_fsr4_launch_option") or ""
            )
            self.steamos_fsr4_launch_row.setVisible(
                FSR4_UI_ENABLED
                and fsr4_current
                and bool(self._steamos_fsr4_launch_option)
            )
            self.steamos_fsr4_copy_button.setText("⧉")
            self.steamos_fsr4_copy_button.setToolTip(
                tr("Copy Steam launch option")
            )
            self.steamos_kernel_status.setText(
                tr("Active")
                if kernel_ready
                else tr("Reboot required")
                if kernel_installed
                else tr("Not installed")
            )
            self.steamos_kernel_status.set_tone(
                "green" if kernel_ready else "orange" if kernel_installed else "gray"
            )
            self.steamos_radv_status.setText(
                tr("Ready")
                if radv_current
                else tr("Repair required")
                if radv_state == "invalid"
                else tr("Not installed")
            )
            self.steamos_radv_status.set_tone(
                "green"
                if radv_current
                else "orange"
                if radv_state == "invalid"
                else "gray"
            )
            self.steamos_fsr4_status.setText(
                tr("Ready")
                if fsr4_current
                else tr("Repair required")
                if fsr4_state == "invalid"
                else tr("Optional")
            )
            self.steamos_fsr4_status.set_tone(
                "green"
                if fsr4_current
                else "orange"
                if fsr4_state == "invalid"
                else "blue"
            )
            self.gfx_card.update_action(
                self.gfx_primary_button,
                text=gfx.compatibility_action,
                payload={"action": "steamos_compat", "governor": ""},
            )
            self.gfx_card.update_action(
                self.gfx_secondary_button,
                text="2 · Update / repair Mesa RADV"
                if radv_state != "not-installed"
                else "2 · Install Mesa RADV",
                payload={"action": "steamos_graphics_install", "governor": ""},
                enabled=kernel_ready,
                tooltip="Reboot into the verified SteamOS AMDGPU module first."
                if not kernel_ready
                else "",
            )
            if FSR4_UI_ENABLED:
                self.gfx_card.update_action(
                    self.gfx_tertiary_button,
                    text="Update per-game FSR4"
                    if fsr4_current
                    else "3 · Install per-game FSR4",
                    payload={
                        "action": "steamos_graphics_fsr4_install",
                        "governor": "",
                    },
                    enabled=kernel_ready and radv_current,
                    tooltip="Install and activate the matched Mesa/RADV stage first."
                    if not (kernel_ready and radv_current)
                    else "",
                )
            self.gfx_card.update_action(
                self.gfx_quaternary_button,
                text="Check full stack",
                payload={"action": "steamos_graphics_status", "governor": ""},
            )
            self.gfx_card.update_action(
                self.gfx_quinary_button,
                text=(
                    "Remove FSR4"
                    if FSR4_UI_ENABLED and fsr4_state != "not-installed"
                    else "Remove Mesa RADV"
                ),
                payload={
                    "action": "steamos_graphics_fsr4_uninstall"
                    if FSR4_UI_ENABLED and fsr4_state != "not-installed"
                    else "steamos_graphics_uninstall",
                    "governor": "",
                },
                visible=(
                    (FSR4_UI_ENABLED and fsr4_state != "not-installed")
                    or radv_state != "not-installed"
                ),
            )
        elif reason_key == "fedora-upstream-managed":
            installed = bool(gfx_state.get("dryhopped_installed"))
            self.gfx_card.update_action(
                self.gfx_primary_button,
                text="Install / update",
                payload={"action": "gfx1013_fedora_install", "governor": ""},
            )
            self.gfx_card.update_action(
                self.gfx_secondary_button,
                text="Uninstall",
                payload={"action": "gfx1013_fedora_uninstall", "governor": ""},
                visible=installed,
            )
            self.gfx_card.update_action(
                self.gfx_tertiary_button if installed else self.gfx_secondary_button,
                text="Open upstream project",
                payload={"action": "gfx1013_upstream", "governor": ""},
            )
        elif reason_key.startswith("bazzite-release-"):
            installed = bool(gfx_state.get("bazzite_async_installed"))
            installer_allowed = bool(gfx_state.get("direct_installer_allowed"))
            self.gfx_card.update_action(
                self.gfx_primary_button,
                text="Repair / update" if installed else "Install / update",
                payload={"action": "gfx1013_bazzite_install", "governor": ""},
                enabled=installer_allowed,
                tooltip="" if installer_allowed else "Requires Bazzite 44 with kernel 7.2.0-ogc4.1 or newer.",
            )
            self.gfx_card.update_action(
                self.gfx_secondary_button,
                text="Uninstall",
                payload={"action": "gfx1013_bazzite_uninstall", "governor": ""},
                visible=installed,
            )
            status_button = (
                self.gfx_tertiary_button if installed else self.gfx_secondary_button
            )
            self.gfx_card.update_action(
                status_button,
                text="Check status" if installed else "Open upstream project",
                payload={
                    "action": "gfx1013_bazzite_status"
                    if installed
                    else "bazzite_async_upstream",
                    "governor": "",
                },
            )
            self.gfx_card.update_action(
                self.gfx_quaternary_button,
                text="Open upstream project",
                payload={"action": "bazzite_async_upstream", "governor": ""},
                visible=installed,
            )
        else:
            if masta_supported:
                if not bool(gfx_state.get("masta_async_compute_ready")):
                    self.gfx_card.set_status("Available in stack below", "blue")
                    self.gfx_card.detail.setText(
                        tr(
                            "Use the matched MastaG kernel and Mesa buttons below. Installing only one half can hang the GPU."
                        )
                    )
            self.gfx_card.update_action(
                self.gfx_primary_button,
                text="View original GFX1013 project"
                if masta_supported
                else "Open upstream manual path",
                payload={"action": "gfx1013_upstream", "governor": ""},
            )

        fsr4 = _mapping(tools.get("fsr4"))
        fsr4_supported = bool(fsr4.get("precompiled_supported"))
        fsr4_experimental = bool(fsr4.get("experimental_precompiled"))
        fsr4_source_supported = bool(fsr4.get("source_build_supported"))
        fsr4_build_mode = str(fsr4.get("build_mode") or "")
        if not fsr4_build_mode and fsr4_source_supported:
            fsr4_build_mode = {
                "bazzite": "bazzite-podman-source",
                "ubuntu": "debian-podman-source",
                "debian": "debian-podman-source",
            }.get(str(tools.get("os_family") or ""), "")
        fsr4_available = bool(
            fsr4.get("installer_available", fsr4_supported or fsr4_experimental)
        )
        fsr4_installed = bool(fsr4.get("installed"))
        fsr4_current = bool(fsr4.get("current"))
        fsr4_state = str(fsr4.get("state") or "not-installed")
        fsr4_kernel_required = bool(fsr4.get("compute_kernel_required"))
        fsr4_kernel_ready = bool(fsr4.get("compute_kernel_ready"))
        self._fsr4_launch_option = str(fsr4.get("steam_launch_option") or "")
        self.fsr4_launch_row.setVisible(
            FSR4_UI_ENABLED
            and fsr4_current
            and bool(self._fsr4_launch_option)
        )
        self.fsr4_copy_button.setToolTip(tr("Copy Steam launch option"))
        self.fsr4_copy_button.setAccessibleName(tr("Copy Steam launch option"))
        source_required = bool(fsr4.get("source_build_required"))
        self.fsr4_card.set_scope(
            "Bazzite · Official Podman source build"
            if fsr4_build_mode == "bazzite-podman-source"
            else "Debian/Ubuntu · Official Podman source build"
            if fsr4_build_mode == "debian-podman-source"
            else "Fedora 44 · GFX1013 · Podman"
            if fsr4_build_mode == "fedora44-podman-source"
            else "Prebuilt: Arch/CachyOS · Source build: other distros",
            "purple" if fsr4_source_supported else "gray",
        )
        self.fsr4_card.set_status(
            "Ready"
            if fsr4_current
            else "Repair required"
            if fsr4_state == "invalid"
            else "Experimental ABI check"
            if fsr4_experimental
            else "Kernel repair required"
            if fsr4_kernel_required and not fsr4_kernel_ready
            else "Source build available"
            if source_required
            else "Available",
            "green"
            if fsr4_current
            else "orange"
            if (
                fsr4_state in {"invalid", "kernel-required"}
                or fsr4_experimental
                or (fsr4_kernel_required and not fsr4_kernel_ready)
            )
            else "blue",
        )
        version = str(fsr4.get("version") or "V3")
        self.fsr4_card.detail.setText(
            tr_format(
                "Official upstream {version} per-game RADV runtime. It stays isolated from system Mesa.",
                version=version,
            )
                if fsr4_supported
                else tr_format(
                    "Official upstream {version} Arch-style runtime. Manjaro is not claimed upstream; installation proceeds only after strict ABI and Vulkan checks.",
                    version=version,
                )
                if fsr4_experimental
                else tr_format(
                    "Official upstream {version} is compiled in its Fedora 44 container with rootless Podman, then Vulkan-tested on this BC-250. System Mesa is never modified.",
                    version=version,
                )
                if fsr4_build_mode == "bazzite-podman-source"
                else tr_format(
                    "Official upstream {version} is compiled in its Fedora 44 container with rootless Podman. Debian/Ubuntu build tools are installed with APT when missing; only a private per-game user runtime is installed.",
                    version=version,
                )
                if fsr4_build_mode == "debian-podman-source"
                else tr_format(
                    "Official upstream {version} is compiled in its Fedora 44 container with rootless Podman and installed as a private per-game runtime. The repaired GFX1013 boot must be active first.",
                    version=version,
                )
                if fsr4_build_mode == "fedora44-podman-source"
                else tr(
                    "This distribution needs the official reproducible Docker source build; no unverified binary is offered."
                )
        )
        self.fsr4_card.update_action(
            self.fsr4_install_button,
            text="Repair per-game FSR4" if fsr4_state == "invalid" else "Update per-game FSR4" if fsr4_current else "Build and install FSR4" if fsr4_source_supported else "Install per-game FSR4",
            enabled=fsr4_available,
            visible=fsr4_available,
        )
        self.fsr4_card.update_action(
            self.fsr4_remove_button,
            text="Remove per-game FSR4",
            visible=fsr4_installed,
        )
        self.fsr4_upstream_button.show()

        quick = _mapping(tools.get("quick_access"))
        if quick:
            ready = bool(quick.get("ready"))
            decky_detected = bool(quick.get("decky_detected"))
            decky_frontend_compatible = bool(
                quick.get("decky_frontend_compatible", True)
            )
            self.decky_card.detail.setText(
                tr(
                    "Quick Access is ready. Restart Game Mode or reload Decky if the panel is not visible yet."
                    if ready
                    else "Decky must be updated because this Steam client uses the renamed initialization API."
                    if decky_detected and not decky_frontend_compatible
                    else "Decky is detected, but the BC250 Quick Access plugin or its protected helper needs installation or repair."
                    if decky_detected
                    else "Decky is optional. It is never installed by generic dependency preparation."
                )
            )
        self._apply_compatibility_filter()


class _FooterActionButton(IconButton):
    """Icon-only action with translated discovery and keyboard accessibility."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.setAccessibleName(tr(text))
        self.setToolTip(tr(text))
        self.setProperty("i18nSourceAccessibleName", text)
        self.setProperty("i18nSourceToolTip", text)
        self.setProperty("dashboardFooterAction", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._refresh_palette()
        apply_shadow(self, blur=4, y=1, alpha=10)
        self._lift = QPropertyAnimation(self.graphicsEffect(), b"blurRadius", self)
        self._lift.setDuration(160)
        self._lift.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _refresh_palette(self) -> None:
        edge = round(22 * theme.ACTIVE_SCALE / 100)
        self.setIconSize(QSize(edge, edge))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self._refresh_palette()

    def _animate_lift(self, active: bool) -> None:
        self._lift.stop()
        self._lift.setStartValue(self.graphicsEffect().blurRadius())
        self._lift.setEndValue(16.0 if active else 4.0)
        self._lift.start()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._animate_lift(True)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._animate_lift(self.hasFocus())

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._animate_lift(True)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._animate_lift(self.underMouse())

    def hideEvent(self, event) -> None:
        self._lift.stop()
        self.graphicsEffect().setBlurRadius(4.0)
        super().hideEvent(event)


class _UpdateBadgeButton(_FooterActionButton):
    """Appears only when a newer release exists, and breathes so it is noticed.

    The other three footer buttons are always there, so a fourth appearing in
    the same row is easy to miss on a glance. A slow pulse on a coloured glow
    reads as "new" without a dialog interrupting anything — and it costs
    nothing while hidden, because the animation is stopped with the widget.
    """

    #: Blur radius the glow travels between, in logical pixels.
    GLOW_MIN = 4.0
    GLOW_MAX = 16.0
    #: Alpha the glow travels between, so it brightens and grows together
    #: instead of just swelling at a constant intensity.
    ALPHA_MIN = 70
    ALPHA_MAX = 210
    PULSE_MS = 1900

    def __init__(self) -> None:
        super().__init__("A newer version is available")
        self.setProperty("updateAvailable", True)
        self.setIcon(QIcon(str(ICON_DIR / "update_badge.png")))
        self._glow_base = QColor(theme.COLORS["blue"])
        # A single QVariantAnimation drives blur and alpha together, so the
        # glow brightens as it grows and dims as it shrinks - one breath,
        # not a shadow that swells at a constant, flat intensity.
        self._pulse = QVariantAnimation(self)
        self._pulse.setDuration(self.PULSE_MS)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse.setStartValue(0.0)
        self._pulse.setKeyValueAt(0.5, 1.0)
        self._pulse.setEndValue(0.0)
        self._pulse.setLoopCount(-1)
        self._pulse.valueChanged.connect(self._apply_pulse)
        self._published = ""
        self.hide()
        self._tint_glow()

    def _tint_glow(self) -> None:
        """A black drop shadow is a shadow; a coloured one is an aura.

        Tinted with the active accent color, so the badge matches whatever
        the user picked in preferences instead of a fixed hue.
        """
        effect = self.graphicsEffect()
        if effect is None:
            return
        effect.setOffset(0, 0)
        self._glow_base = QColor(theme.COLORS["blue"])
        self._apply_pulse(self._pulse.currentValue() or 0.0)

    def _apply_pulse(self, value: object) -> None:
        effect = self.graphicsEffect()
        if effect is None:
            return
        position = float(value or 0.0)
        effect.setBlurRadius(self.GLOW_MIN + (self.GLOW_MAX - self.GLOW_MIN) * position)
        glow = QColor(self._glow_base)
        glow.setAlpha(round(self.ALPHA_MIN + (self.ALPHA_MAX - self.ALPHA_MIN) * position))
        effect.setColor(glow)

    def announce(self, published: str) -> None:
        """Show the badge for a specific version, or hide it for none."""
        published = str(published or "")
        self._published = published
        if not published:
            self.setVisible(False)
            return
        detail = tr_format("Version {version} is available", version=published)
        self.setToolTip(detail)
        self.setAccessibleName(detail)
        # The translated text is built here, so the generic retranslation pass
        # must not overwrite it with the untranslated source string.
        self.setProperty("i18nSourceToolTip", None)
        self.setProperty("i18nSourceAccessibleName", None)
        self.setVisible(True)

    @property
    def published_version(self) -> str:
        return self._published

    def _refresh_palette(self) -> None:
        super()._refresh_palette()
        self._tint_glow()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        self._pulse.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API name
        # ``_FooterActionButton.hideEvent`` resets the blur; stop pulsing first
        # or the animation would immediately overwrite that and keep running
        # against a widget nobody can see.
        self._pulse.stop()
        super().hideEvent(event)

    def _animate_lift(self, active: bool) -> None:
        # Hover lift and the pulse drive the same property. While the badge is
        # breathing, the pulse owns it.
        if self._pulse.state() == QVariantAnimation.State.Running:
            return
        super()._animate_lift(active)


class UpdateCallout(QFrame):
    """A speech bubble that points at the update badge and says what to do.

    A pulsing icon says "look here" and nothing else. This says the rest: that
    a newer version exists, which one, and — the part that actually matters —
    the right way to get it for *this* install. Telling someone who installed
    from the AUR to download a tarball would walk around their package manager.

    It floats as a child of the window rather than sitting in a layout, so it
    can overlap the content beneath it without reserving space or shifting
    anything, and it is drawn rather than styled because a tail pointing at a
    specific widget is not something a stylesheet can express.

    Shown once per session, and again whenever the badge is clicked. The badge
    keeps pulsing either way, so dismissing this is not the same as forgetting.
    """

    #: Height of the triangular tail, in logical pixels.
    TAIL = 8
    #: Half-width of its base.
    TAIL_HALF_WIDTH = 9
    RADIUS = 10

    action_clicked = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("updateCallout")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._tail_x = 0

        self._tail_below = False
        self._root = QVBoxLayout(self)
        # Room for the tail on whichever edge it will be drawn on.
        self._root.setContentsMargins(13, 11 + self.TAIL, 11, 11)
        self._root.setSpacing(3)
        root = self._root

        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel(tr("New update available"))
        self.title.setProperty("updateCalloutTitle", True)
        head.addWidget(self.title, 1)
        self.close_button = QPushButton("")
        self.close_button.setObjectName("updateCalloutClose")
        self.close_button.setIcon(icon("close_gray"))
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setFixedSize(18, 18)
        self.close_button.setToolTip(tr("Close"))
        self.close_button.setProperty("i18nSourceToolTip", "Close")
        self.close_button.clicked.connect(self._dismiss)
        head.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)

        self.detail = QLabel("")
        self.detail.setProperty("updateCalloutDetail", True)
        self.detail.setWordWrap(True)
        root.addWidget(self.detail)

        self.action_button = QPushButton("")
        self.action_button.setObjectName("updateCalloutAction")
        self.action_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_button.clicked.connect(self.action_clicked)
        root.addWidget(self.action_button)
        self.hide()

    # ------------------------------------------------------------- contents

    def set_message(self, *, version: str, detail: str, action: str) -> None:
        self.detail.setText(detail)
        self.action_button.setText(action)
        # Built from a version number, so the generic retranslation pass must
        # not overwrite either with an untranslated source string.
        self.setProperty("updateVersion", version)
        self.detail.setProperty("i18nSourceText", None)
        self.action_button.setProperty("i18nSourceText", None)
        self.adjustSize()

    def retranslate(self) -> None:
        self.title.setText(tr("New update available"))
        self.close_button.setToolTip(tr("Close"))

    # ------------------------------------------------------------ placement

    def _set_tail_side(self, *, below: bool) -> None:
        """Reserve the tail's room on the edge it will be drawn on.

        Margins change the size hint, so this has to settle before the bubble
        is measured and placed.
        """
        if below == self._tail_below and self._root.contentsMargins().top() > 0:
            return
        self._tail_below = below
        top = 11 if below else 11 + self.TAIL
        bottom = 11 + self.TAIL if below else 11
        self._root.setContentsMargins(13, top, 11, bottom)

    def point_at(self, anchor: QWidget) -> bool:
        """Hang off ``anchor`` with the tail pointing at it.

        Below it when there is room, above it when there is not — a bubble that
        clamps itself to the bottom of the window ends up covering the very
        thing its tail is pointing at.

        Returns False when there is no window to float in yet, which happens
        while the dashboard is still being built.
        """
        window = anchor.window()
        if window is None or window is anchor:
            return False
        if self.parentWidget() is not window:
            self.setParent(window)

        top_left = anchor.mapTo(window, QPoint(0, 0))
        centre_x = top_left.x() + anchor.width() // 2
        below_y = top_left.y() + anchor.height() + 4

        # Below if it fits, above if that fits instead, and otherwise not at
        # all. The old rule flipped above whenever below was short and then
        # clamped the result back on screen, which for a badge near the top of
        # the viewport landed the bubble squarely on top of the badge — a
        # label covering the very thing its tail points at.
        self._set_tail_side(below=False)
        self.adjustSize()
        fits_below = below_y + self.height() <= window.height() - 8
        if fits_below:
            y = below_y
        else:
            self._set_tail_side(below=True)
            self.adjustSize()
            above_y = top_left.y() - self.height() - 4
            if above_y < 8:
                # Neither side has room. The badge keeps pulsing on its own,
                # and clicking it asks for the bubble again once there is
                # somewhere to put it.
                self.hide()
                return False
            y = above_y

        # Keep the whole bubble on screen horizontally; the tail then slides
        # within it rather than the bubble hanging off the edge.
        x = max(8, min(centre_x - self.width() // 2, window.width() - self.width() - 8))
        self.move(x, y)
        self._tail_x = max(
            self.RADIUS + self.TAIL_HALF_WIDTH,
            min(centre_x - x, self.width() - self.RADIUS - self.TAIL_HALF_WIDTH),
        )
        self.show()
        self.raise_()
        return True

    # --------------------------------------------------------------- drawing

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._tail_below:
            body = self.rect().adjusted(0, 0, -1, -self.TAIL - 1)
            edge, tip = float(body.bottom()), float(self.rect().bottom())
        else:
            body = self.rect().adjusted(0, self.TAIL, -1, -1)
            edge, tip = float(body.top()), 0.0
        shape = QPainterPath()
        shape.addRoundedRect(float(body.x()), float(body.y()), float(body.width()),
                             float(body.height()), self.RADIUS, self.RADIUS)
        # QPointF, not QPoint: QPolygonF refuses the integer type, and the
        # refusal happens inside paintEvent — a reimplemented C++ virtual,
        # where PyQt6 turns an unhandled exception into qFatal and aborts the
        # whole process rather than logging it.
        tail = QPolygonF([
            QPointF(float(self._tail_x - self.TAIL_HALF_WIDTH), edge),
            QPointF(float(self._tail_x), tip),
            QPointF(float(self._tail_x + self.TAIL_HALF_WIDTH), edge),
        ])
        shape.addPolygon(tail)
        shape = shape.simplified()

        painter.setBrush(QColor(theme.COLORS["panel_raised"]))
        border = QColor(theme.COLORS["blue"])
        painter.setPen(border)
        painter.drawPath(shape)

    # --------------------------------------------------------------- closing

    def _dismiss(self) -> None:
        self.hide()
        self.dismissed.emit()


class DashboardFooter(QWidget):
    """Compact external links embedded in the preparation header."""

    contact_clicked = pyqtSignal()
    support_clicked = pyqtSignal()
    repositories_clicked = pyqtSignal()
    update_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("dashboardHeaderActions", True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)
        # First in the row, ahead of the always-present links: it only exists
        # at all when there is something to act on, so it earns the lead spot.
        self.update_button = _UpdateBadgeButton()
        self.update_button.clicked.connect(self.update_clicked)
        self.layout.addWidget(self.update_button)
        self.repositories_button = _FooterActionButton("Official repositories")
        self.repositories_button.setIcon(icon("github"))
        self.repositories_button.clicked.connect(self.repositories_clicked)
        self.layout.addWidget(self.repositories_button)
        self.contact_button = _FooterActionButton("Report a problem / Contact")
        self.contact_button.setIcon(icon("discord"))
        self.contact_button.clicked.connect(self.contact_clicked)
        self.layout.addWidget(self.contact_button)
        self.support_button = _FooterActionButton("Buy me a coffee")
        self.support_button.setProperty("donation", True)
        # Official, bundled Ko-fi artwork: no network access needed by the UI.
        self.support_button.setIcon(QIcon(str(ICON_DIR / "kofi_cup.png")))
        self.support_button.clicked.connect(self.support_clicked)
        self.layout.addWidget(self.support_button)

    def announce_update(self, published: str) -> None:
        """Show or hide the update badge. Empty string means nothing to show."""
        self.update_button.announce(published)
