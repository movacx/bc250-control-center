"""Proposal-N dashboard widgets backed by the real BC250 preparation state."""

from __future__ import annotations

import re
import shlex
import textwrap
from collections.abc import Iterable, Mapping
from pathlib import Path

from PyQt6.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWidgets import QPushButton as IconButton

from bc250cc.infrastructure.system_setup import CU_UNLOCK_OPTION, HIDE_BOOT_MESSAGES_OPTION
from bc250cc.infrastructure.terminal_repository import TerminalRepository

from .. import theme
from ..core.preferences import application_settings
from ..i18n import tr, tr_format
from .buttons import WrappingButton as QPushButton
from .dashboard_instruments import HeadingLabel
from .page_widgets import SectionCard
from .style_state import repolish
from .system_setup_controls import (
    bazzite_ui_preview_enabled,
    is_bazzite_host,
    is_steamos_host,
    update_memory_controls,
)
from .wheel_guard import GuardedComboBox
from .widgets import IconBadge, InfoDialog, PillLabel
from .widgets import icon as theme_icon


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


class _PreparationTabButton(QPushButton):
    """A preparation tab whose label is drawn literally.

    A push button reads "&" as a keyboard mnemonic, so "Memory & Swap" showed
    as "Memory _Swap". The label keeps its catalogue source and escapes the
    ampersand on every write, including the live language change.
    """

    def __init__(self, source_text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.source_text = source_text
        self.setText(tr(source_text))

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API name
        super().setText(str(text).replace("&&", "&").replace("&", "&&"))


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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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

    def gamepad_activate(self) -> None:
        """A chooses this policy, exactly like a click."""
        if self.isEnabled():
            self.clicked.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.gamepad_activate()
            event.accept()
            return
        super().keyPressEvent(event)


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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:
        return QSize(280, 34)

    def _step(self, delta: int) -> bool:
        """Move to the next enabled stop in that direction, if there is one."""
        index = self._combo.currentIndex() + delta
        while 0 <= index < self._combo.count():
            if self._is_enabled(index):
                self._combo.setCurrentIndex(index)
                return True
            index += delta
        return False

    def gamepad_direction(self, direction: str) -> bool:
        """Left/right walk the stops; at either end focus moves on."""
        if direction == "left":
            return self._step(-1)
        if direction == "right":
            return self._step(1)
        return False

    def gamepad_activate(self) -> None:
        """A steps forward and wraps, so the line is usable with one button."""
        if not self._step(1):
            for index in range(self._combo.count()):
                if self._is_enabled(index):
                    self._combo.setCurrentIndex(index)
                    break

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self._step(-1 if event.key() == Qt.Key.Key_Left else 1)
            event.accept()
            return
        super().keyPressEvent(event)

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


class _DeckyScreenshotDialog(QDialog):
    """Static Decky screenshot preview."""

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

    def widget(self, index: int) -> QWidget | None:
        return self._pages[index] if 0 <= index < len(self._pages) else None

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt API name
        page = self.currentWidget()
        return page is not None and page.hasHeightForWidth()

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt API name
        page = self.currentWidget()
        return page.heightForWidth(width) if page is not None else -1

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        # The stack is capped at its hint (Maximum policy); at a narrow width
        # wrapped content needs more than the hint measured at full width.
        hint = super().sizeHint()
        page = self.currentWidget()
        if page is not None and self.width() > 0 and page.hasHeightForWidth():
            hint.setHeight(max(hint.height(), page.heightForWidth(self.width())))
        return hint

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
        self._ready = True
        self._external = False
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
        self._ready = bool(ready)
        self._sync_actions()

    def set_external(self, external: bool) -> None:
        """Another program is taking these readings; offer neither action."""
        self._external = bool(external)
        self._sync_actions()

    def _sync_actions(self) -> None:
        if not self._live_action:
            return
        offered = not self._external
        self.live_button.setVisible(offered and self._ready)
        self.prepare_button.setVisible(offered and not self._ready)

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
        # The card is the controller stop, not the 16 px box at its edge: the
        # D-pad then moves card to card along the grid, and A toggles it.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.checkbox.setProperty("gamepadSkip", True)
        self.checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setProperty("gamepadBadgeInset", 26)
        # Left/right walk the cards in order, so a move along a row never
        # jumps to a panel above or below that happens to be closer.
        self.setProperty("gamepadHorizontalGroup", "preparation-components")

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.checkbox.isEnabled():
            self.checkbox.click()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def gamepad_activate(self) -> None:
        if self.checkbox.isEnabled():
            self.checkbox.click()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.gamepad_activate()
            event.accept()
            return
        super().keyPressEvent(event)

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


#: FSR4 states in which OptiScaler (OptiScaler Client's) is in the game.
_OPTISCALER_IN_GAME = frozenset({"needs-launch-option", "ready", "other-launcher", "unknown-adapter"})


#: OptiScaler Client's record per state, when the game table has no FSR4
#: reading of its own (the client is not installed): (text, tone).
_FSR4_RECORD_CELL = {
    "intact": ("OptiScaler installed", ""),
    "partial": ("OptiScaler installed", ""),
    "removed": ("Record left", "orange"),
    "changed": ("Check the files", "orange"),
    "helixsr": ("OptiScaler installed", ""),
    "pending": ("Interrupted", "orange"),
    "interrupted": ("Interrupted", "orange"),
    "backup-broken": ("Check the files", "orange"),
    "unsupported": ("Check the files", "orange"),
}


def _undo_rows(row_for, installations: Iterable[Mapping], backups: Iterable[Mapping]) -> None:
    """What OptiScaler Client recorded per game, and Control Center's backups.

    Any game the client recorded gets "Remove OptiScaler, keep a backup",
    whichever way it was added; a game whose files are already gone gets
    "Clear the client's record", which is what keeps the client from
    installing it again. The newest backup of a game the client no longer
    records gets "Put OptiScaler back".
    """
    copy = PreparationSidebar._FSR4_UNDO_COPY
    recorded: set[str] = set()
    for record in installations:
        state = str(record.get("state") or "unsupported")
        key = str(record.get("key") or "")
        if state == "missing" or not key:
            continue  # the game is gone; nothing in the table to act on
        appid = str(record.get("appid") or "")
        row = row_for(appid, str(record.get("name") or appid))
        recorded.add(appid or row["name"])
        row["fsr4_recorded"] = state != "removed"
        if state == "interrupted":
            # Control Center's own removal was cut short: its backup goes back first.
            action = ("Put OptiScaler back", f"fsr4_backup_restore:{record.get('backup')}", True)
        else:
            label = "Clear the client's record" if state == "removed" else "Remove OptiScaler, keep a backup"
            action = (label, f"fsr4_undo:{key}", bool(record.get("removable")))
        note = tr(copy.get(state, copy["unsupported"]))
        linked = str(record.get("linked_path") or "")
        if linked and record.get("removable"):
            note = f"{tr_format(copy['linked'], link=linked)} {note}"
        cell = row["fsr4"]
        if cell is None or state in {"removed", "interrupted"}:
            text, tone = _FSR4_RECORD_CELL.get(state, _FSR4_RECORD_CELL["unsupported"])
            row["fsr4"] = (text, tone, note, (*(cell[3] if cell else ()), action))
        else:
            row["fsr4"] = (cell[0], cell[1], f"{cell[2]} {note}", (*cell[3], action))
    for backup in backups:
        appid = str(backup.get("appid") or "")
        name = str(backup.get("name") or appid)
        # An interrupted one too: cut short at the very end, it holds the record.
        if (appid or name) in recorded or backup.get("state") not in {"ready", "interrupted"}:
            continue
        recorded.add(appid or name)
        row = row_for(appid, name)
        note = tr_format(copy["backup"], date=str(backup.get("created") or "")[:10],
                         path=str(backup.get("path") or ""))
        action = ("Put OptiScaler back", f"fsr4_backup_restore:{backup.get('id')}", True)
        cell = row["fsr4"]
        if cell is None:
            row["fsr4"] = ("In a backup", "", note, (action,))
        else:
            row["fsr4"] = (cell[0], cell[1], f"{cell[2]} {note}", (*cell[3], action))


def game_matrix_rows(
    helixsr_games: list[Mapping],
    fsr4_games: list[Mapping],
    *,
    helixsr_ready: bool,
    scaler_games: Iterable[Mapping] = (),
    scaler_ready: bool = False,
    fg_ready: bool = False,
    fsr4_installations: Iterable[Mapping] = (),
    fsr4_backups: Iterable[Mapping] = (),
) -> list[dict]:
    """One row per Steam game, with what HelixSR and FSR4 each do in it.

    A cell is ``(text, tone, tooltip, actions)``; ``actions`` holds
    ``(label, action, enabled)``. Rows that need the reader come first, then
    working ones, then the rest, each by name.
    """
    rows: dict[str, dict] = {}

    def row_for(appid: str, name: str) -> dict:
        key = appid or name
        row = rows.setdefault(key, {"appid": appid, "name": name, "helixsr": None, "fsr4": None})
        row["name"] = row["name"] or name
        return row

    by_game: dict[str, list[Mapping]] = {}
    for game in helixsr_games:
        appid = str(game.get("appid") or "")
        row = row_for(appid, str(game.get("name") or appid))
        if game.get("folder"):
            # Added by hand from outside Steam: the folder it came from.
            row["folder"] = str(game["folder"])
            row["folder_detail"] = (
                "OptiScaler added by hand" if game.get("kind") == "optiscaler" else "Outside Steam"
            )
        by_game.setdefault(appid or str(game.get("name")), []).append(game)
    for key, entries in by_game.items():
        def first(state: str, entries=entries):
            return next((g for g in entries if g.get("state") == state), None)

        appid = rows[key]["appid"]
        chosen = first("installed") or first("restored") or first("missing")
        if chosen is not None:
            optiscaler = chosen.get("kind") == "optiscaler"
            state = chosen.get("state")
            copy = (PreparationSidebar._HELIXSR_OPTISCALER_COPY if optiscaler
                    else PreparationSidebar._HELIXSR_GAME_COPY)[state]
            if state == "installed":
                text, tone = ("Active via OptiScaler" if optiscaler else "Active"), "green"
            elif state == "missing":
                text, tone = "Game not found", "orange"
            else:
                text, tone = ("OptiScaler changed" if optiscaler else "Original file back"), "orange"
            route = "opti" if optiscaler else "game"
            actions = (("Remove HelixSR", f"helixsr_{route}_remove:{appid}", True),)
            if state == "installed" and chosen.get("network_missing"):
                # Without them HelixSR only does its simple upscale; the
                # update copies the installed release's files back.
                text, tone = "Network files missing", "orange"
                copy = PreparationSidebar._HELIXSR_NETWORK_MISSING_COPY
                actions = (("Update HelixSR", f"helixsr_game_update:{appid}", helixsr_ready), *actions)
            elif state == "installed" and chosen.get("outdated"):
                # Still working with the release it was given; one click
                # brings it the one installed here, newer or picked older.
                text = "Update available" if chosen.get("older", True) else "Other version"
                tone = "orange"
                actions = (("Update HelixSR", f"helixsr_game_update:{appid}", helixsr_ready), *actions)
            rows[key]["helixsr"] = (text, tone, copy, actions)
            continue
        # Where OptiScaler is in the game, HelixSR goes through it: OptiScaler
        # loads the FidelityFX DLLs of its own folder, so a replaced game DLL
        # would never run.
        chosen = next((g for g in entries if g.get("kind") == "optiscaler"), entries[0])
        optiscaler = chosen.get("kind") == "optiscaler"
        copy = (PreparationSidebar._HELIXSR_OPTISCALER_COPY if optiscaler
                else PreparationSidebar._HELIXSR_GAME_COPY)["available"]
        route = "opti" if optiscaler else "game"
        rows[key]["helixsr"] = (
            "Via OptiScaler" if optiscaler else "", "", copy,
            (("Add HelixSR", f"helixsr_{route}_install:{appid}", helixsr_ready),),
        )
    fsr4_copy = PreparationSidebar._FSR4_MATRIX_COPY
    for game in fsr4_games:
        appid = str(game.get("appid") or "")
        row = row_for(appid, str(game.get("name") or appid))
        state = str(game.get("state") or "not-installed")
        text, tone = fsr4_copy.get(state, fsr4_copy["not-installed"])
        detail = PreparationSidebar._FSR4_GAME_COPY.get(
            state, PreparationSidebar._FSR4_GAME_COPY["not-installed"]
        )[2]
        tooltip = tr_format(
            detail,
            dll=str(game.get("adapter") or "dxgi.dll").removesuffix(".dll"),
            link=str(game.get("linked_path") or ""),
            path=str(game.get("real_path") or ""),
        )
        executable = str(game.get("suggested_executable") or "")
        if state == "not-installed" and executable:
            tooltip = f"{tooltip} {tr_format('If it asks for the executable, choose {path}.', path=executable)}"
        actions = ()
        if state == "needs-launch-option" and game.get("steam"):
            actions = (("Add FSR4 to Steam", f"fsr4_steam_option:{appid}", True),)
        row["fsr4"] = (text, tone, tooltip, actions)
        row["fsr4_state"] = state
    _undo_rows(row_for, fsr4_installations, fsr4_backups)
    scaler_copy = PreparationSidebar._HELIXSR_SCALER_COPY
    for game in scaler_games:
        appid = str(game.get("appid") or "")
        state = str(game.get("state") or "available")
        if not appid or (state == "available" and not scaler_ready):
            continue
        row = row_for(appid, str(game.get("name") or appid))
        remove = ("Remove HelixSR Scaler", f"helixsr_scaler_remove:{appid}", True)
        if state == "installed":
            actions: list[tuple[str, str, bool]] = []
            text, tone, copy = "Active via HelixSR Scaler", "green", scaler_copy["installed"]
            if game.get("outdated"):
                # Still working with the release it was given; one click
                # brings it the installed one, keeping this one to go back to.
                text, tone = ("Update available" if game.get("older", True) else "Other version"), "orange"
                copy = tr_format(scaler_copy["outdated"], version=str(game.get("version") or "?"))
                actions.append(("Update HelixSR", f"helixsr_scaler_update:{appid}", scaler_ready))
            if game.get("frame_generation"):
                actions.append(("Turn off frame generation", f"helixsr_scaler_fg_off:{appid}", True))
            elif game.get("fg_possible") is not False:
                # False: HelixSR's bridge found no DLSS Frame Generation in the
                # game, nothing to switch on. None: it could not tell, and
                # refuses on its own if not.
                actions.append(("Turn on frame generation", f"helixsr_scaler_fg_on:{appid}", fg_ready))
            if game.get("previous"):
                actions.append(("Go back to the previous version", f"helixsr_scaler_rollback:{appid}", True))
            row["helixsr"] = (text, tone, copy, (*actions, remove))
            continue
        if state in {"restored", "missing"}:
            text = "HelixSR Scaler changed" if state == "restored" else "Game not found"
            row["helixsr"] = (text, "orange", scaler_copy[state], (remove,))
            continue
        cell = row["helixsr"]
        # HelixSR is in the game another way, or OptiScaler Client's
        # OptiScaler is: a game has one of each.
        if cell and any(label.startswith("Remove") for label, _action, _enabled in cell[3]):
            continue
        if (row.get("fsr4_state") in _OPTISCALER_IN_GAME or row.get("fsr4_recorded")
                or (cell and cell[0] == "Via OptiScaler")):
            continue
        add = ("Add HelixSR Scaler", f"helixsr_scaler_install:{appid}", True)
        row["helixsr"] = (*cell[:3], (*cell[3], add)) if cell else ("", "", scaler_copy["available"], (add,))

    def rank(row: dict) -> tuple:
        tones = {cell[1] for cell in (row["helixsr"], row["fsr4"]) if cell}
        order = 0 if "orange" in tones else 1 if "green" in tones else 2
        return order, row["name"].lower()

    return sorted(rows.values(), key=rank)


class PreparationInfoCard(QFrame):
    action_requested = pyqtSignal(object)

    #: Colour is kept for the three states that ask something of the reader:
    #: working, needs attention, broken. Everything else (where a card applies,
    #: available, not installed, checking) is neutral, so a column of badges
    #: does not compete for attention.
    _STATUS_TONES = frozenset({"green", "orange", "red"})
    _DISCLOSURE_WIDTH = 18
    _STATUS_COLUMN_WIDTH = 124

    @classmethod
    def _status_tone(cls, tone: str) -> str:
        return tone if tone in cls._STATUS_TONES else "gray"

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
        self._body: QWidget | None = None
        self._toggle: QToolButton | None = None
        self._auto_expanded_for = ""
        self.status = PillLabel(status_text or "Not detected", self._status_tone(status_tone))
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
        # ``isHidden`` and not ``isVisibleTo(self)``: a collapsed row hides its
        # whole body, which would make every button here look hidden and leave
        # its accent and width stale until the row is opened.
        buttons = [button for button in buttons if button is not None and not button.isHidden()]
        primary_gets_accent = (
            len(buttons) >= 2
            and bool(buttons[-1].property("linkAction"))
            and not buttons[0].property("linkAction")
            and not buttons[0].property("dangerAction")
        )
        for index, button in enumerate(buttons):
            # A link takes the room it needs and no more, so it does not sit
            # centred in an empty half of the row.
            is_link = bool(button.property("linkAction"))
            accented = index == 0 and primary_gets_accent
            # Every state refresh comes through here for every button of
            # every card; restyling the ones whose look did not change made
            # switching pages stutter. linkAction is in the key because
            # update_action sets it just before calling this.
            look = (is_link, accented, bool(button.property("dangerAction")))
            if getattr(button, "_bc250_action_look", None) == look:
                continue
            button._bc250_action_look = look
            self.actions.setStretchFactor(button, 0 if is_link else 1)
            # The same button swaps between an action and a link as the state
            # changes, so the alignment is set both ways, never left behind.
            self.actions.setAlignment(
                button, Qt.AlignmentFlag.AlignLeft if is_link else Qt.AlignmentFlag(0)
            )
            button.setProperty("accented", accented)
            repolish(button)

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
        self.status.set_tone(self._status_tone(tone))
        self.status.show()
        # A card that needs the reader opens itself, once per problem: a
        # reader who closes it again is not reopened on every refresh.
        if self._body is not None and tone in {"orange", "red"}:
            if self._auto_expanded_for != tone:
                self._auto_expanded_for = tone
                self.set_expanded(True)
        elif tone not in {"orange", "red"}:
            self._auto_expanded_for = ""

    def make_collapsible(self) -> None:
        """Show only the title row; the description and actions open on demand.

        Everything below the header moves into one body widget, so the code
        that shows, hides and rewrites those widgets keeps working unchanged.
        """
        if self._body is not None:
            return
        layout = self.layout()
        body = QWidget()
        body_layout = QVBoxLayout(body)
        # Lined up under the title, not under the chevron.
        body_layout.setContentsMargins(self._DISCLOSURE_WIDTH + 7, 0, 0, 0)
        body_layout.setSpacing(layout.spacing())
        while layout.count() > 1:
            item = layout.takeAt(1)
            if item.widget() is not None:
                body_layout.addWidget(item.widget())
            elif item.layout() is not None:
                body_layout.addLayout(item.layout())
        layout.addWidget(body)
        toggle = QToolButton()
        toggle.setProperty("dashboardDisclosure", True)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.setAutoRaise(True)
        toggle.setFixedSize(self._DISCLOSURE_WIDTH, 24)
        toggle.clicked.connect(lambda: self.set_expanded(not self.is_expanded()))
        header = layout.itemAt(0).layout()
        header.insertWidget(0, toggle)
        # One row shape for every card: where a card applies is quiet text,
        # and the status sits in a column of one width, so the states line up
        # down the page instead of following each scope's length.
        self.scope.setStyleSheet(
            f"PillLabel {{ color:{theme.COLORS['subtle']}; background:transparent; border:none; }}"
        )
        self.status.setMinimumWidth(self._STATUS_COLUMN_WIDTH)
        layout.setContentsMargins(12, 8, 12, 8)
        self._body, self._toggle = body, toggle
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_expanded(False)

    def is_expanded(self) -> bool:
        return self._body is not None and not self._body.isHidden()

    def set_expanded(self, expanded: bool) -> None:
        if self._body is None or self._toggle is None:
            return
        self._body.setVisible(bool(expanded))
        self._toggle.setText("⌄" if expanded else "›")
        self._toggle.setAccessibleName(
            tr("Hide details") if expanded else tr("Show details")
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        # The title row toggles; clicks inside the body belong to its buttons.
        if (
            self._body is not None
            and event.button() == Qt.MouseButton.LeftButton
            and event.position().y() <= self.layout().itemAt(0).geometry().bottom() + 6
        ):
            self.set_expanded(not self.is_expanded())
            event.accept()
            return
        super().mousePressEvent(event)

    def set_scope(self, text: str, tone: str = "gray") -> None:
        # Where a card applies is a label, never a state: always neutral.
        self.scope.setText(tr(text))
        self.scope.show()


class _StatTile(QFrame):
    """One figure of an upscaler card: a small label over its value."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self.setProperty("statTile", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 2, 14, 2)
        layout.setSpacing(2)
        self.label = _label(label, "statLabel", wrap=False)
        self.value = QLabel("—")
        self.value.setProperty("statValue", True)
        self.value.setProperty("tone", "")
        layout.addWidget(self.label)
        layout.addWidget(self.value)

    def set_value(self, value: str) -> None:
        self.value.setText(tr(value))

    def set_tone(self, tone: str) -> None:
        if self.value.property("tone") != tone:
            self.setProperty("tone", tone)
            self.value.setProperty("tone", tone)
            repolish(self.value)


class _UpscalerSection(SectionCard):
    """One upscaler on the Upscaling tab, built like the GPU page's cards.

    The head carries the name, the release and the state; the body a few
    readings, each a label on the left and its value or control on the
    right; the footer the next step as the one solid button, with what is
    done rarely (reinstall, rebuild, remove) behind More. Both upscalers'
    cards are built alike so they line up side by side. Their games are
    rows of the shared games table.
    """

    TONES = {"green": "good", "orange": "warning", "red": "danger"}

    def __init__(self, title: str, subtitle: str, engine: str) -> None:
        # Compact, as the other tabs' cards: margins, spacing and buttons.
        super().__init__(title, subtitle, icon_name="", compact=True)
        self.setProperty("upscalerSection", True)
        self.setProperty("upscalerEngine", engine)
        # Name, description and guide button sit on a darker title band.
        self.root.removeItem(self._header_grid)
        self._header_grid.setParent(None)
        self._header_grid.setContentsMargins(14, 11, 14, 11)
        self.header_band = QFrame()
        self.header_band.setProperty("upscalerHead", True)
        self.header_band.setLayout(self._header_grid)
        self.root.insertWidget(0, self.header_band)
        # The band runs edge to edge as the card's head and is its own
        # separator: the card's padding moves to the body below it.
        self.root.setContentsMargins(0, 0, 0, 12)
        self.body.setContentsMargins(14, 0, 14, 0)
        self._divider.hide()
        # The release sits beside the name, in the console face.
        title_box = self._title_host.layout()
        title_label = title_box.itemAt(0).widget()
        title_box.removeWidget(title_label)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        # Name and release on one centre line.
        title_row.addWidget(title_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.version = QLabel("")
        self.version.setProperty("engineVersion", True)
        self.version.setProperty("i18nLiteral", True)
        title_row.addWidget(self.version, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)
        title_box.insertLayout(0, title_row)
        self._version_in_header = False
        # The readings as one strip of small figures, side by side: a card
        # with two and a card with three stay the same height.
        self.facts = QFrame()
        self.facts.setProperty("upscalerStats", True)
        self._stats = QHBoxLayout(self.facts)
        self._stats.setContentsMargins(0, 0, 0, 0)
        self._stats.setSpacing(0)
        self.rows: dict[str, _StatTile] = {}
        self.body.addWidget(self.facts)
        self.notice = _label("", "fieldHint")
        self.notice.hide()
        self.body.addWidget(self.notice)
        self.extra = QVBoxLayout()
        self.extra.setSpacing(10)
        self.body.addLayout(self.extra)
        self.body.addStretch(1)
        self.footer_panel = QFrame()
        self.footer_panel.setProperty("configurationFooter", True)
        self.footer = QGridLayout(self.footer_panel)
        self.footer.setContentsMargins(0, 6, 0, 0)
        self.footer.setHorizontalSpacing(8)
        self.footer.setVerticalSpacing(8)
        self.body.addWidget(self.footer_panel)
        # What is done rarely: listed behind More. The buttons themselves
        # stay the cards' (text, state, payload), kept out of sight here.
        self._menu_holder = QWidget(self)
        self._menu_holder.hide()
        self._menu_buttons: list[QPushButton] = []
        self.more_button = QPushButton(tr("More"))
        self.more_button.setProperty("compactAction", True)
        self.more_button.setProperty("menuAction", True)
        self.more_button.setIcon(theme_icon("chevron_down_gray"))
        self.more_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.more_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more_button.setAccessibleName(tr("More actions"))
        self.more_button.clicked.connect(self._open_menu)
        self.more_button.hide()

    def set_header_control(self, control: QWidget) -> None:
        """A control in the head, before the guide: the version picker. The
        release then shows there, not again beside the name."""
        self._header_buttons.insert(0, control)
        self._version_in_header = True
        self.version.hide()
        self._layout_header(force=True)

    def set_status(self, text: str, tone: str = "") -> None:
        """The state, as the strip's first figure."""
        if text:
            self.set_fact("state", "State", text, tone)
            # Always first, whenever it was set.
            self._stats.removeWidget(self.rows["state"])
            self._stats.insertWidget(0, self.rows["state"], 1)
            self._mark_first()
        else:
            self.remove_fact("state")

    def set_version(self, version: str) -> None:
        self.version.setText(version)
        self.version.setVisible(bool(version) and not self._version_in_header)

    def set_fact(self, key: str, label: str, value: str, tone: str = "") -> None:
        """A figure of the strip, added the first time it is set."""
        row = self.rows.get(key)
        if row is None:
            row = _StatTile(label)
            self.rows[key] = row
            self._stats.addWidget(row, 1)
        row.set_value(value)
        row.set_tone(self.TONES.get(tone, ""))
        row.setVisible(True)
        self._mark_first()

    def remove_fact(self, key: str) -> None:
        """Hide a figure that no longer applies (it comes back with set_fact)."""
        row = self.rows.get(key)
        if row is not None:
            row.setVisible(False)
            self._mark_first()

    def _mark_first(self) -> None:
        """Only the figures after the first are set off by a rule."""
        first = True
        for index in range(self._stats.count()):
            tile = self._stats.itemAt(index).widget()
            if tile is None or tile.isHidden():
                continue
            if tile.property("statFirst") != first:
                tile.setProperty("statFirst", first)
                # The first figure lines up with the card's edge, as the footer does.
                tile.layout().setContentsMargins(0 if first else 14, 2, 14, 2)
                repolish(tile)
            first = False

    def set_notice(self, text: str) -> None:
        self.notice.setText(tr(text))
        self.notice.setVisible(bool(text))

    def set_actions(
        self,
        secondary: list[QPushButton],
        primary: QPushButton | None,
        more: list[QPushButton] = (),
    ) -> None:
        """The footer: More first, then ``secondary``, ``primary`` at the end.

        ``more`` lists buttons whose action is offered in the More menu while
        they are not hidden; the menu shows their text and runs their click.
        """
        self._menu_buttons = list(more)
        for button in self._menu_buttons:
            if button.parent() is not self._menu_holder:
                button.setParent(self._menu_holder)
            if button.objectName():
                # A former next step listed in More is an ordinary entry now.
                button.setObjectName("")
        for button in (*secondary, *([primary] if primary else [])):
            name = "PrimaryAction" if button is primary else ""
            if button.objectName() != name:
                button.setObjectName(name)
                button.style().unpolish(button)
                button.style().polish(button)
        self.more_button.setVisible(any(not button.isHidden() for button in self._menu_buttons))
        self._footer_buttons = ([self.more_button, *secondary], primary)
        self._lay_footer(force=True)

    def _open_menu(self) -> None:
        """The rare actions, as a menu under More; removals last, set apart."""
        menu = QMenu(self.more_button)
        menu.setProperty("upscalingMenu", True)
        shown = [button for button in self._menu_buttons if not button.isHidden()]
        plain = [b for b in shown if not b.property("dangerAction")]
        danger = [b for b in shown if b.property("dangerAction")]
        for group in (plain, danger):
            if group and not menu.isEmpty():
                menu.addSeparator()
            for button in group:
                action = menu.addAction(button.text())
                action.setEnabled(button.isEnabled())
                action.setToolTip(button.toolTip())
                action.triggered.connect(lambda _checked=False, source=button: source.click())
        # Shown, not run: nothing waits on the menu, and it stays referenced.
        self._menu = menu
        menu.popup(self.more_button.mapToGlobal(self.more_button.rect().bottomLeft()))

    def _lay_footer(self, *, force: bool = False) -> None:
        """One row while it fits; otherwise the next step moves to a row of
        its own, on the right. A label is never wrapped or cut."""
        secondary, primary = getattr(self, "_footer_buttons", ([], None))
        shown = [b for b in (*secondary, *([primary] if primary else [])) if not b.isHidden()]
        for button in shown:
            button.setMinimumWidth(IconButton.sizeHint(button).width())
        needed = sum(b.minimumWidth() for b in shown) + self.footer.horizontalSpacing() * len(shown)
        width = self.footer_panel.width()
        wrapped = bool(primary is not None and len(shown) > 1 and 0 < width < needed)
        if not force and wrapped == getattr(self, "_footer_wrapped", False):
            return
        self._footer_wrapped = wrapped
        while self.footer.count():
            self.footer.takeAt(0)
        for column in range(self.footer.columnCount() + 2):
            self.footer.setColumnStretch(column, 0)
        column = 0
        for button in secondary:
            self.footer.addWidget(button, 0, column)
            column += 1
        self.footer.setColumnStretch(column, 1)
        if primary is not None:
            if wrapped:
                self.footer.addWidget(primary, 1, 0, 1, column + 2, Qt.AlignmentFlag.AlignRight)
            else:
                self.footer.addWidget(primary, 0, column + 1)
        self.footer_panel.setVisible(bool(shown))

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._lay_footer()


class _FittedLineEdit(QLineEdit):
    """A read-only field that asks for the width of its whole text and gives
    way below it on a narrow window, instead of widening the page."""

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        hint = super().sizeHint()
        return QSize(max(hint.width(), self.fontMetrics().horizontalAdvance(self.text()) + 40), hint.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return QSize(120, super().minimumSizeHint().height())


class _UpscalingGames(SectionCard):
    """Every game against both upscalers, as one table across the page.

    Rows are games (Steam's and folders added by hand); each upscaler has a
    column with the game's state and, at its right edge, its control: the
    HelixSR switch, or FSR4's fix when one is ours. A search narrows a long
    library; the header adds a folder from outside Steam.
    """

    action_requested = pyqtSignal(object)
    TONES = _UpscalerSection.TONES
    #: Game | one column per upscaler | the row's actions.
    STRETCH = (5, 4, 5)
    #: The upscalers in the cards' order above the table.
    COLUMNS = (("fsr4", "FSR4 INT8"), ("helixsr", "HelixSR"))

    def __init__(self) -> None:
        super().__init__(
            "Games",
            "Steam games and folders you added, with each upscaler's state.",
            icon_name="",
        )
        self.setProperty("upscalingGames", True)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search games"))
        self.search.setClearButtonEnabled(True)
        self.search.setProperty("gameSearch", True)
        self.search.textChanged.connect(self._filter)
        self.body.addWidget(self.search)
        self.table = QFrame()
        self.table.setProperty("gameTable", True)
        self.grid = QGridLayout(self.table)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(0)
        self.body.addWidget(self.table)
        self.empty = _label("", "fieldHint")
        self.empty.hide()
        self.body.addWidget(self.empty)
        self._signature: object = None
        self._rows: list[tuple[str, list[QWidget]]] = []
        #: The action buttons of each row, by game key.
        self.controls: dict[str, list[QPushButton]] = {}

    #: Room the title keeps beside the header's controls.
    TITLE_ROOM = 320

    def _layout_header_buttons(self, compact: bool) -> None:
        """The launch option and the buttons on one row while they fit beside
        the title; otherwise the launch option takes a row of its own."""
        controls = [widget for widget in self._header_buttons if not widget.isHidden()]
        needed = sum(widget.sizeHint().width() for widget in controls) + 7 * len(controls)
        if compact or len(controls) < 2 or self.width() - self.TITLE_ROOM >= needed:
            super()._layout_header_buttons(compact)
            return
        while self.header_actions.count():
            self.header_actions.takeAt(0)
        first, rest = self._header_buttons[0], self._header_buttons[1:]
        self.header_actions.addWidget(first, 0, 0, 1, len(rest) + 1)
        # The buttons sit together on the right, under the launch option.
        for column in range(len(rest) + 1):
            self.header_actions.setColumnStretch(column, 1 if column == 0 else 0)
        for column, button in enumerate(rest, start=1):
            button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            button.setMinimumWidth(int(button.property("headerActionWidth") or 0))
            self.header_actions.addWidget(button, 1, column)
        self._header_actions_host.setVisible(True)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._layout_header_buttons(self._header_compact)

    @staticmethod
    def _head(text: str, column: int) -> HeadingLabel:
        label = HeadingLabel()
        label.source_text = text
        label.setText(tr(text))
        label.setProperty("gameColumn", True)
        label.setContentsMargins(14 if column == 0 else 0, 0, 0, 0)
        return label

    def set_rows(self, rows: list[dict], empty: str, columns: tuple[str, ...] = ("fsr4", "helixsr")) -> None:
        """``rows``: ``{key, name, detail, tooltip, helixsr, fsr4}``; a tool's
        cell is ``None`` or ``{text, tone, tooltip, actions}``. ``columns``
        names the upscalers shown, each set up on this PC."""
        signature = (tr("Games"), empty, columns, repr(rows))
        if signature == self._signature:
            return
        self._signature = signature
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                # Hidden at once: deleteLater waits for the event loop.
                item.widget().hide()
                item.widget().deleteLater()
        self._rows, self.controls = [], {}
        tools = [(key, title) for key, title in self.COLUMNS if key in columns]
        self._tools = [key for key, _title in tools]
        last = len(tools) + 1
        for column in range(5):
            self.grid.setColumnStretch(column, 0)
        stretches = (self.STRETCH[0], *(self.STRETCH[1] for _tool in tools), self.STRETCH[2])
        for column, stretch in enumerate(stretches):
            self.grid.setColumnStretch(column, stretch)
        if rows:
            # A header band behind the column names, edge to edge.
            band = QFrame()
            band.setProperty("gameTableHead", True)
            self.grid.addWidget(band, 0, 0, 1, last + 1)
            for column, text in enumerate(("Game", *(title for _key, title in tools))):
                self.grid.addWidget(self._head(text, column), 0, column)
        line = 1
        for index, row in enumerate(rows):
            name = QWidget()
            name_box = QVBoxLayout(name)
            name_box.setContentsMargins(14, 8, 0, 8)
            name_box.setSpacing(1)
            title = _label(row["name"], "gameName")
            title.setText(row["name"])
            title.setProperty("i18nLiteral", True)
            name_box.addWidget(title)
            if row.get("detail"):
                name_box.addWidget(_label(row["detail"], "gameDetail"))
            name.setToolTip(row.get("tooltip") or "")
            widgets = [name]
            self.grid.addWidget(name, line, 0)
            for column, (key, _title) in enumerate(tools, start=1):
                cell = self._cell(row[key])
                self.grid.addWidget(cell, line, column)
                widgets.append(cell)
            actions = self._actions(row)
            self.grid.addWidget(actions, line, last)
            widgets.append(actions)
            if index < len(rows) - 1:
                # The table's own border closes the last row.
                rule = self._rule()
                self.grid.addWidget(rule, line + 1, 0, 1, last + 1)
                widgets.append(rule)
            self._rows.append((row["name"].casefold(), widgets))
            line += 2
        self.search.setVisible(len(rows) > 8)
        self._empty_text = tr(empty)
        self._filter()

    @staticmethod
    def _rule() -> QFrame:
        rule = QFrame()
        rule.setProperty("instrumentHairline", True)
        rule.setFixedHeight(1)
        return rule

    def _cell(self, cell) -> QLabel:
        state = QLabel("—" if cell is None else tr(cell["text"]))
        state.setProperty("gameState", True)
        state.setProperty("tone", "" if cell is None else self.TONES.get(cell["tone"], ""))
        state.setWordWrap(True)
        if cell is not None:
            state.setToolTip(tr(cell["tooltip"]))
        return state

    def _actions(self, row: dict) -> QWidget:
        """The row's buttons, right-aligned in the last column."""
        host = QWidget()
        box = QHBoxLayout(host)
        box.setContentsMargins(0, 6, 14, 6)
        box.setSpacing(6)
        box.addStretch(1)
        buttons = []
        overflow: list[tuple[str, str, bool]] = []
        for tool in getattr(self, "_tools", ("fsr4", "helixsr")):
            for label, action, enabled in (row[tool] or {}).get("actions") or ():
                if label.startswith(self.OVERFLOW):
                    # Removing and going back are rare: behind the row's menu.
                    overflow.append((label, action, enabled))
                    continue
                if label in self.FG_TOGGLE:
                    # One switch for frame generation, checked while it is on.
                    # While on it names what pressing it does, so it is not
                    # read as a state label.
                    active = label == "Turn off frame generation"
                    button = QPushButton(tr("Turn off frame generation" if active else "Frame generation"))
                    button.setProperty("toggleAction", True)
                    button.setCheckable(True)
                    button.setChecked(active)
                    button.setToolTip(tr(label))
                else:
                    button = QPushButton(tr(label))
                button.setProperty("compactAction", True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setEnabled(bool(enabled))
                button.clicked.connect(
                    lambda _checked=False, value=action, source=button: self._row_action(value, source)
                )
                box.addWidget(button)
                buttons.append(button)
        if overflow:
            more = QPushButton("⋯")
            more.setProperty("compactAction", True)
            more.setProperty("iconAction", True)
            more.setCursor(Qt.CursorShape.PointingHandCursor)
            more.setToolTip(tr("More actions"))
            more.setAccessibleName(tr("More actions"))
            more.setProperty("rowActions", [label for label, _action, _enabled in overflow])
            more.clicked.connect(lambda _checked=False, source=more, items=tuple(overflow): self._row_menu(source, items))
            box.addWidget(more)
            buttons.append(more)
        self.controls[row["key"]] = buttons
        return host

    #: Row actions offered behind the row's menu rather than as buttons.
    OVERFLOW = ("Remove", "Go back")
    #: The two labels of HelixSR Scaler's frame-generation switch.
    FG_TOGGLE = frozenset({"Turn on frame generation", "Turn off frame generation"})

    def _row_action(self, action: str, source: QPushButton) -> None:
        if source.isCheckable():
            # The switch shows the state the game has until the change lands.
            source.setChecked(not source.isChecked())
        self.action_requested.emit({"action": action, "governor": ""})

    def _row_menu(self, source: QPushButton, items: tuple) -> None:
        menu = QMenu(source)
        menu.setProperty("upscalingMenu", True)
        for label, action, enabled in items:
            entry = menu.addAction(tr(label))
            entry.setEnabled(bool(enabled))
            entry.triggered.connect(
                lambda _checked=False, value=action: self.action_requested.emit({"action": value, "governor": ""})
            )
        self._menu = menu
        menu.popup(source.mapToGlobal(source.rect().bottomRight()) - QPoint(menu.sizeHint().width(), 0))

    def _filter(self) -> None:
        query = self.search.text().strip().casefold()
        shown = 0
        for name, widgets in self._rows:
            visible = query in name
            shown += visible
            for widget in widgets:
                widget.setVisible(visible)
        self.table.setVisible(shown > 0)
        if not self._rows:
            self.empty.setText(self._empty_text)
        else:
            self.empty.setText(tr("No game matches the search."))
        self.empty.setVisible(shown == 0 and bool(self.empty.text()))


class _HelixSRSettings(SectionCard):
    """HelixSR's helixsr.ini, as a form on the Upscaling tab.

    One set of settings for every game: saving writes them next to HelixSR
    in each game that has it, and every game it is added to later gets them.
    Only the keys below are written; the rest of the file keeps HelixSR's own
    defaults and comments. Grouped as helixsr.ini groups them, each setting
    with what it does written under its name.
    """

    save_requested = pyqtSignal(object)

    #: Settings whose value is a number, offered as steps.
    NUMBERS = frozenset({
        "Sharpening.Sharpness", "Sharpening.MotionThreshold",
        "Sharpening.MotionLimit", "Sharpening.MotionReduction",
    })
    _TENTHS = tuple((f"{step / 10:g}", f"{step / 10:.1f}") for step in range(11))
    _PIXELS = tuple((f"{value:g}", f"{value:g} px") for value in (0.5, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64))

    #: (group, ((setting, label, hint, choices as (value, label)), ...));
    #: no choices: a check box.
    GROUPS = (
        ("Sharpening", (
            ("Sharpening.Sharpener", "Sharpening",
             "Off leaves the image as DLSS's network makes it, as DLSS does. NVIDIA is the driver's Image Sharpening filter, AMD RCAS is FSR's. Releases before 1.7 always use AMD RCAS.",
             (("off", "Off"), ("nvidia", "NVIDIA"), ("rcas", "AMD RCAS"))),
            ("Sharpening.Sharpness", "Sharpening strength",
             "Used while a filter is on, and when the game's slider sends none. 0 is none, 1 the strongest.",
             _TENTHS),
            ("Sharpening.UseGameSlider", "Follow the game's slider",
             "Uses the game's FSR sharpness slider instead of the strength above, when the game has one.", ()),
            ("Sharpening.MotionAdaptive", "Less sharpening in motion",
             "Fast-moving pixels get less sharpening, which avoids shimmering edges.", ()),
            ("Sharpening.MotionThreshold", "Motion where it starts",
             "Pixels a point moves per frame before the sharpening starts to drop.", _PIXELS),
            ("Sharpening.MotionLimit", "Motion where it is complete",
             "Pixels per frame from which the full reduction applies.", _PIXELS),
            ("Sharpening.MotionReduction", "Reduction in fast motion",
             "Share of the sharpening taken away at that speed: 0 keeps it all, 1 removes it.", _TENTHS),
        )),
        ("Network", (
            ("Upscaling.NetworkResolution", "Network resolution",
             "Auto runs the network at a smaller size in Ultra Performance, with the same image at about a third less GPU time. Fast does the same in Performance and Balanced, a little softer. Full always uses the screen size.",
             (("auto", "Auto"), ("fast", "Fast"), ("full", "Full"))),
            ("ModelE.Network", "Network",
             "Auto uses the main network at every quality mode, which is the faster choice on this GPU. As DLSS picks the Ultra Performance network above a 2.5 ratio, as NVIDIA does.",
             (("auto", "Auto"), ("nvidia", "As DLSS"), ("main", "Main"), ("ultraperformance", "Ultra Performance"))),
            ("Upscaling.Int8", "8-bit network",
             "HelixSR 1.9 and newer. Auto runs most of the network with 8-bit math on GPUs that are fast at it, a little faster with a nearly identical image. Turn it off if something looks wrong.",
             (("auto", "Auto"), ("on", "On"), ("off", "Off"))),
            ("Upscaling.FastOutput", "Fast output",
             "HelixSR 2.0 and newer. Faster builds of the network's last step, with an identical image: about 15 to 18% less GPU time at DLAA and Ultra Quality. Turn it off only if a game shows a problem with it.",
             (("on", "On"), ("off", "Off"))),
        )),
        ("Compatibility", (
            ("Compatibility.WaveSize", "Wave size",
             "Auto picks 32 on this GPU. 64 gives the same image about 5% slower; use it only if a game shows a broken image.",
             (("auto", "Auto"), ("32", "32"), ("64", "64"))),
            ("ModelE.UseReactiveMask", "Use the game's reactive mask",
             "Favours the new frame over history on particles and animated textures. Try it if those leave trails.", ()),
            ("ModelE.DilateDisplayMotionVectors", "Dilate display motion vectors",
             "For games that send display-resolution motion vectors: try it if moving edges ghost. Costs about 0.1 ms at 1080p.", ()),
            ("ModelE.MotionVectorFrontEnd", "Convert motion vectors first",
             "Turns render-resolution motion vectors into display-resolution ones before the network. HelixSR already does it when a game's vectors include the jitter; try it if motion looks wrong.", ()),
            ("ModelE.InvertJitter", "Mirrored jitter",
             "Only for a game whose image shakes because its jitter comes out mirrored.", ()),
            ("ModelE.InvertMotionVectors", "Mirrored motion vectors",
             "Only for a game whose moving objects smear because its motion vectors come out mirrored.", ()),
            ("Log.Enabled", "Write helixsr.log",
             "HelixSR writes what it does next to its DLL in each game: useful when a game misbehaves.", ()),
        )),
    )

    def __init__(self) -> None:
        super().__init__(
            "HelixSR settings",
            "Saved into every game that has HelixSR, and into every game you add it to. In games with HelixSR Scaler, sharpening is set in its own menu (Insert).",
            icon_name="",
        )
        self.setProperty("helixsrSettings", True)
        self.controls: dict[str, QWidget] = {}
        self._defaults: dict[str, object] = {}
        self._saved: dict[str, object] = {}
        #: Releases before 1.9 ignore Upscaling.Int8, and before 2.0
        #: Upscaling.FastOutput; their rows stay but are off.
        self._int8_supported = True
        self._fast_output_supported = True
        # One list, as on the Compatibility tab: a row per group that opens
        # on demand, with what it is set to on the closed row.
        self.groups_box = QFrame()
        self.groups_box.setProperty("dashboardCompatibilityGroupBox", True)
        groups_layout = QVBoxLayout(self.groups_box)
        groups_layout.setContentsMargins(0, 0, 0, 0)
        groups_layout.setSpacing(0)
        #: Each group's (title row, chevron, body, summary label, fields).
        self.groups: dict[str, tuple[QWidget, QToolButton, QWidget, QLabel, tuple]] = {}
        self._numbers = set(self.NUMBERS)
        self._groups_layout = groups_layout
        self._dynamic_groups: list[str] = []
        self._release_signature: tuple | None = None
        for index, (title, fields) in enumerate(self.GROUPS):
            groups_layout.addWidget(self._group(title, fields, first=index == 0))
        self.body.addWidget(self.groups_box)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.defaults_button = QPushButton(tr("Restore defaults"))
        self.defaults_button.setProperty("compactAction", True)
        self.defaults_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.defaults_button.clicked.connect(lambda: self._show(self._defaults))
        footer.addWidget(self.defaults_button)
        footer.addStretch(1)
        self.hint = _label("", "fieldHint", wrap=False)
        footer.addWidget(self.hint)
        # The saved settings again, into every game: after a game update put
        # its own helixsr.ini back, or for a game that was open at the save.
        # Saving needs a change, so without this those games had no way in.
        self._games_with_helixsr = 0
        self.reapply_button = QPushButton(tr("Apply to games again"))
        self.reapply_button.setProperty("compactAction", True)
        self.reapply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reapply_button.setToolTip(tr(
            "Writes the saved settings again into every game that has HelixSR: after a game "
            "update replaced them, or for a game that was open when you saved."
        ))
        self.reapply_button.clicked.connect(self._reapply)
        footer.addWidget(self.reapply_button)
        self.save_button = QPushButton(tr("Save settings"))
        self.save_button.setObjectName("PrimaryAction")
        self.save_button.setProperty("compactAction", True)
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self._save)
        footer.addWidget(self.save_button)
        self.body.addLayout(footer)
        self._changed()

    def _group(self, title: str, fields, *, first: bool = False) -> QWidget:
        """A group as a list row: the title row opens its settings, each with
        its name and what it does, the control on the right."""
        group = QFrame()
        group.setProperty("settingsGroupRow", True)
        group.setProperty("listFirst", first)
        outer = QVBoxLayout(group)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # The title row is a darker band, edge to edge.
        head = QFrame()
        head.setProperty("settingsGroupHead", True)
        head.setProperty("listFirst", first)
        head.setCursor(Qt.CursorShape.PointingHandCursor)
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(12, 9, 12, 9)
        head_layout.setSpacing(7)
        toggle = QToolButton()
        toggle.setProperty("dashboardDisclosure", True)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.setAutoRaise(True)
        toggle.setFixedSize(18, 24)
        head_layout.addWidget(toggle)
        head_layout.addWidget(_label(title, "dashboardComponentTitle", wrap=False))
        head_layout.addStretch(1)
        summary = QLabel("")
        summary.setProperty("settingsSummary", True)
        summary.setProperty("i18nLiteral", True)
        head_layout.addWidget(summary)
        outer.addWidget(head)
        body = QWidget()
        rows = QVBoxLayout(body)
        rows.setContentsMargins(37, 0, 12, 8)
        rows.setSpacing(0)
        outer.addWidget(body)
        toggle.clicked.connect(lambda _checked=False, key=title: self.set_group_expanded(key, not self.is_group_expanded(key)))
        head.mousePressEvent = lambda event, key=title: (
            self.set_group_expanded(key, not self.is_group_expanded(key))
            if event.button() == Qt.MouseButton.LeftButton else None
        )
        self.groups[title] = (head, toggle, body, summary, fields)
        for name, label, hint, options in fields:
            row = QWidget()
            row.setProperty("settingRow", True)
            grid = QGridLayout(row)
            grid.setContentsMargins(0, 7, 0, 7)
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(1)
            caption = _label(label, "readingLabel")
            grid.addWidget(caption, 0, 0)
            grid.addWidget(_label(hint, "settingHint"), 1, 0)
            if options:
                control = GuardedComboBox()
                control.setFixedWidth(150)
                for value, text in options:
                    control.addItem(tr(text) if not text[:1].isdigit() else text, value)
                control.currentIndexChanged.connect(self._changed)
            else:
                control = QCheckBox()
                control.toggled.connect(self._changed)
            control.setAccessibleName(tr(label))
            control.setToolTip(tr(hint))
            grid.addWidget(control, 0, 1, 2, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.setColumnStretch(0, 1)
            rows.addWidget(row)
            self.controls[name] = control
        self.set_group_expanded(title, False)
        return group

    #: HelixSR Scaler's settings this form can name; others show their key.
    SCALER_COPY = {
        "HelixSR.WaveSize": ("Wave size", "The same as above, for games with HelixSR Scaler.", {"auto": "Auto"}),
        "HelixSR.FGPreset": (
            "Frame generation quality",
            "Light mode is NVIDIA's lighter frame generation and runs faster. Full is NVIDIA's full frame generation.",
            {"c": "Light mode", "full": "Full"},
        ),
        "HelixSR.QuickFlow": (
            "QuickFlow", "Faster frame generation. Only with Full quality.",
            {"off": "Off", "fast": "Fast", "fastest": "Fastest"},
        ),
    }

    def set_release_settings(self, scaler: list, extra: list, *, scaler_games: int) -> None:
        """The groups the installed release brings: HelixSR Scaler's own
        settings while a game has it, and any helixsr.ini setting this form
        does not know yet, as HelixSR's own comment describes it."""
        scaler = [dict(row) for row in scaler or () if isinstance(row, Mapping)] if scaler_games else []
        extra = [dict(row) for row in extra or () if isinstance(row, Mapping) and row.get("kind") != "text"]
        signature = (
            tuple((row["id"], tuple(row.get("choices") or ())) for row in scaler),
            tuple((row["id"], row.get("kind"), tuple(row.get("choices") or ())) for row in extra),
        )
        if signature == self._release_signature:
            return
        self._release_signature = signature
        for title in self._dynamic_groups:
            head, _toggle, _body, _summary, fields = self.groups.pop(title)
            group = head.parentWidget()
            group.hide()
            group.setParent(None)
            group.deleteLater()
            for name, *_rest in fields:
                self.controls.pop(name, None)
                self._numbers.discard(name)
        self._dynamic_groups = []
        if scaler:
            fields = []
            for row in scaler:
                key = str(row.get("name") or row["id"]).split(".", 1)[-1]
                label, hint, names = self.SCALER_COPY.get(str(row.get("name")), (key, "", {}))
                fields.append((row["id"], label, hint, tuple((c, names.get(c, c)) for c in row["choices"])))
            self._add_group("HelixSR Scaler", tuple(fields))
        if extra:
            fields = []
            for row in extra:
                label = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(row.get("key") or row["id"]))
                if row.get("kind") == "bool":
                    options = ()
                elif row.get("kind") == "float":
                    low, high = (float(v) for v in row["choices"])
                    options = tuple((f"{low + (high - low) * step / 10:g}",) * 2 for step in range(11))
                    self._numbers.add(row["id"])
                else:
                    options = tuple((c, c) for c in row.get("choices") or ())
                fields.append((row["id"], label, str(row.get("help") or ""), options))
            self._add_group("Other settings in this release", tuple(fields))
        if self._saved or self._defaults:
            self._show({**self._defaults, **self._saved})

    def _add_group(self, title: str, fields: tuple) -> None:
        self._groups_layout.addWidget(self._group(title, fields))
        self._dynamic_groups.append(title)

    def is_group_expanded(self, title: str) -> bool:
        return not self.groups[title][2].isHidden()

    def set_group_expanded(self, title: str, expanded: bool) -> None:
        _head, toggle, body, _summary, _fields = self.groups[title]
        body.setVisible(bool(expanded))
        toggle.setText("⌄" if expanded else "›")
        toggle.setAccessibleName(tr("Hide details") if expanded else tr("Show details"))

    def _summaries(self) -> None:
        """On each closed row, what its settings are set to now."""
        for _title, (_head, _toggle, _body, summary, fields) in self.groups.items():
            parts = []
            switched = 0
            for name, _label, _hint, options in fields:
                control = self.controls.get(name)
                if control is None:
                    continue
                if isinstance(control, QCheckBox):
                    switched += control.isChecked() and control.isEnabled()
                elif control.isEnabled():
                    parts.append(control.currentText())
            if switched:
                parts.append(tr_format("{count} switched on", count=switched))
            summary.setText(" · ".join(parts))

    def values(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for name, control in self.controls.items():
            if isinstance(control, QCheckBox):
                values[name] = control.isChecked()
            else:
                data = control.currentData()
                values[name] = float(data) if name in self._numbers else data
        return values

    def set_int8_supported(self, supported: bool) -> None:
        """Whether the release in use reads Upscaling.Int8 (1.9 and newer)."""
        supported = bool(supported)
        if supported != self._int8_supported:
            self._int8_supported = supported
            self._changed()

    def set_fast_output_supported(self, supported: bool) -> None:
        """Whether the release in use reads Upscaling.FastOutput (2.0 and newer)."""
        supported = bool(supported)
        if supported != self._fast_output_supported:
            self._fast_output_supported = supported
            self._changed()

    def set_settings(self, saved: Mapping[str, object], defaults: Mapping[str, object]) -> None:
        """The saved settings; a form the user is changing is left alone."""
        saved, defaults = dict(saved), dict(defaults)
        dirty = self._saved and self.values() != self._saved
        self._defaults = defaults or self._defaults
        if saved == self._saved:
            return
        self._saved = saved
        if not dirty:
            self._show(saved)
        self._changed()

    def _show(self, values: Mapping[str, object]) -> None:
        for name, control in self.controls.items():
            if name not in values:
                continue
            value = values[name]
            control.blockSignals(True)
            if isinstance(control, QCheckBox):
                control.setChecked(bool(value))
            else:
                text = f"{float(value):g}" if name in self._numbers else str(value)
                index = control.findData(text)
                if index < 0 and name in self._numbers:
                    # A value saved by hand between two steps stays as it is.
                    control.addItem(f"{float(value):g}", text)
                    index = control.count() - 1
                control.setCurrentIndex(max(index, 0))
            control.blockSignals(False)
        self._changed()

    def set_game_count(self, count: int) -> None:
        """How many games have HelixSR, so reapplying is offered only with one."""
        self._games_with_helixsr = max(0, int(count or 0))
        self._changed()

    def _reapply(self) -> None:
        self.save_requested.emit(dict(self._saved))
        self.hint.setText(tr("Applied"))
        self.hint.show()
        QTimer.singleShot(2500, self._changed)

    def _save(self) -> None:
        """Hand the values over and say so at once.

        This tab does not get the refreshed state right after the save, so
        the form takes what it sent as saved; a failed save opens its own
        error, and the next refresh shows what was really kept.
        """
        values = self.values()
        self.save_requested.emit(values)
        self._saved = dict(values)
        self._changed()
        self.hint.setText(tr("Saved"))
        self.hint.show()
        QTimer.singleShot(2500, self._changed)

    def _changed(self, *_args) -> None:
        values = self.values()
        # Each control is live only while it changes something.
        sharpening = values["Sharpening.Sharpener"] != "off"
        for name in ("Sharpening.Sharpness", "Sharpening.UseGameSlider", "Sharpening.MotionAdaptive"):
            self.controls[name].setEnabled(sharpening)
        in_motion = sharpening and bool(values["Sharpening.MotionAdaptive"])
        for name in ("Sharpening.MotionThreshold", "Sharpening.MotionLimit", "Sharpening.MotionReduction"):
            self.controls[name].setEnabled(in_motion)
        if "Upscaling.Int8" in self.controls:
            self.controls["Upscaling.Int8"].setEnabled(self._int8_supported)
        if "Upscaling.FastOutput" in self.controls:
            self.controls["Upscaling.FastOutput"].setEnabled(self._fast_output_supported)
        # HelixSR Scaler runs QuickFlow only with the full preset.
        if "Scaler:HelixSR.QuickFlow" in self.controls and "Scaler:HelixSR.FGPreset" in self.controls:
            self.controls["Scaler:HelixSR.QuickFlow"].setEnabled(values["Scaler:HelixSR.FGPreset"] == "full")
        # The reduction fades in between the two speeds: the start comes first.
        ordered = values["Sharpening.MotionThreshold"] < values["Sharpening.MotionLimit"]
        # Only the settings on the form count: the saved ones also hold
        # HelixSR Scaler's while no game has it and its group is not shown.
        changed = bool(self._saved) and any(values[name] != self._saved.get(name) for name in values)
        self.save_button.setEnabled(changed and ordered)
        if hasattr(self, "reapply_button"):
            self.reapply_button.setEnabled(bool(self._saved) and not changed and self._games_with_helixsr > 0)
        self.defaults_button.setEnabled(
            bool(self._defaults) and any(values[name] != self._defaults.get(name) for name in values)
        )
        if not ordered:
            message = "The motion where it starts must be below the motion where it is complete."
        else:
            message = "Unsaved changes." if changed else ""
        self.hint.setText(tr(message) if message else "")
        self.hint.setVisible(bool(message))
        if hasattr(self, "groups"):
            self._summaries()


from .preparation_pages import PreparationPagesMixin  # noqa: E402  (needs names defined above, so imported here)
from .preparation_render import PreparationRenderMixin  # noqa: E402  (needs names defined above, so imported here)


class PreparationSidebar(PreparationRenderMixin, PreparationPagesMixin, QFrame):
    """Compact in-dashboard adaptation of DependencyPreparationDialog."""

    prepare_requested = pyqtSignal(object)
    dependency_action_requested = pyqtSignal(object)
    driver_support_requested = pyqtSignal(str)
    #: The key (TAB_KEYS) of the tab just selected, by a click or by code.
    tab_selected = pyqtSignal(str)

    COMPONENTS = (
        ("runtime", "Base dependencies", "Runtime files and packages."),
        ("governor", "Selected GPU governor", "Cyan or Oberon setup."),
        ("cpu_oc", "CPU OC tools", "bc250_smu_oc support."),
        ("core_unlock", "CPU Core Unlock source", "Experimental source."),
        ("umr", "UMR database", "Required for 40CU."),
        ("cu_manager", "40CU manager", "CU routing and restore."),
        ("fan_pwm", "NCT sensors and PWM", "Fan control route."),
    )

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings=None,
        standalone: bool = False,
    ) -> None:
        """``standalone`` is the copy on the Additional settings page.

        It carries Compatibility, Memory & Swap and Drivers, and opens on
        Compatibility. Components and Decky stay on the Dashboard.
        """
        super().__init__(parent)
        self._settings = settings or application_settings()
        self._standalone = bool(standalone)
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
        heading_copy.addWidget(
            _label(
                "Additional settings" if self._standalone else "Prepare BC250 system",
                "dashboardCardTitle",
            )
        )
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
        # Stack order (TAB_KEYS) is append-only so saved indices keep their
        # meaning; the row shows the tabs in TAB_ORDER.
        for index, text in enumerate(
            ("Components", "Compatibility", "Memory & Swap", "Decky", "Drivers", "Upscaling")
        ):
            button = _PreparationTabButton(text)
            button.setCheckable(True)
            button.setProperty("dashboardPreparationTab", True)
            button.setProperty("gamepadHorizontalGroup", "preparation-tabs")
            button.setProperty("gamepadHorizontalIndex", self.TAB_ORDER.index(index))
            button.clicked.connect(
                lambda _checked=False, value=index: self.select_tab(value)
            )
            self.tab_buttons.append(button)
        # The Dashboard keeps the tabs that act on the machine as a whole:
        # Components and Decky. Compatibility, Memory & Swap and Drivers live
        # on the Additional settings page, which shows a copy of this panel
        # with those three tabs, without Components and without Decky. The pages behind the
        # hidden buttons stay built so the state they read keeps flowing.
        self._hidden_tabs = frozenset({0, 3}) if self._standalone else frozenset({1, 2, 4, 5})
        for hidden in self._hidden_tabs:
            self.tab_buttons[hidden].hide()
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
        self.stack.addWidget(self._upscaling_page())
        root.addWidget(self.stack, 1)

        footer = QWidget()
        self.prepare_footer = footer
        footer.setProperty("dashboardPreparationFooter", True)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(7)
        self.prepare_button = QPushButton(tr("Prepare selected"))
        self.prepare_button.setProperty("gamepadHorizontalGroup", "preparation-components")
        self.prepare_button.setProperty("gamepadHorizontalIndex", 999)
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
        self.select_tab(min(set(range(len(self.tab_buttons))) - self._hidden_tabs))
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
        steamos = is_steamos_host(getattr(self, "_tools_snapshot", None) or {})
        for index, row in enumerate(self.memory_option_rows):
            value = str(combo.itemData(index) or "")
            if steamos and value == "swap-16":
                # SteamOS keeps its own ZRAM in front of this swapfile.
                value = "zram-swap-16"
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
            "{ sysctl vm.swappiness vm.page-cluster 2>/dev/null || true; } | sed 's/^/  /'\n"
            "for bc250_knob in enabled compressor zpool max_pool_percent shrinker_enabled; do "
            "bc250_file=/sys/module/zswap/parameters/$bc250_knob; "
            "[ -r \"$bc250_file\" ] && printf '  zswap.%s = %s\\n' \"$bc250_knob\" \"$(cat \"$bc250_file\")\"; "
            "done\n"
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
        panel.setProperty("dashboardBootPanel", True)
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

    def _bazzite_smt_panel(self) -> QFrame:
        """``nosmt`` on Bazzite, where the kernel options go through rpm-ostree."""
        panel = QFrame()
        self.smt_panel = panel
        panel.setProperty("dashboardMemoryPanel", True)
        panel.setProperty("dashboardBootPanel", True)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QBoxLayout(QBoxLayout.Direction.LeftToRight, panel)
        self.smt_layout = root
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        copy = QVBoxLayout()
        copy.setSpacing(4)
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(_label("Simultaneous multithreading (SMT)", "dashboardComponentTitle"))
        self.smt_status = PillLabel("Not detected", "gray")
        header.addWidget(self.smt_status)
        header.addStretch(1)
        copy.addLayout(header)
        self.smt_detail = _label(
            "The CPU runs one thread per core: 6 or 8 threads instead of 12 or 16. Some games run smoother, others slower; measure yours. The change applies after reboot and can be restored from Control Center.",
            "dashboardMemoryDetail",
        )
        self.smt_detail.setWordWrap(True)
        copy.addWidget(self.smt_detail)
        root.addLayout(copy, 1)

        self.smt_apply_button = QPushButton(tr("Disable SMT"))
        self.smt_apply_button.setProperty("dashboardCardAction", True)
        self.smt_apply_button.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.smt_apply_button.clicked.connect(self._request_smt_boot)
        self._smt_boot_action = "disable"
        root.addWidget(self.smt_apply_button)
        panel.hide()
        return panel

    def _bazzite_boot_messages_panel(self) -> QFrame:
        """Hide the kernel's boot messages (the RDSEED warning) on Bazzite."""
        panel = QFrame()
        self.boot_messages_panel = panel
        panel.setProperty("dashboardMemoryPanel", True)
        panel.setProperty("dashboardBootPanel", True)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QBoxLayout(QBoxLayout.Direction.LeftToRight, panel)
        self.boot_messages_layout = root
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        copy = QVBoxLayout()
        copy.setSpacing(4)
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(_label("Boot messages (hides the RDSEED warning)", "dashboardComponentTitle"))
        self.boot_messages_status = PillLabel("Not detected", "gray")
        header.addWidget(self.boot_messages_status)
        header.addStretch(1)
        copy.addLayout(header)
        self.boot_messages_detail = _label(
            "The BC-250's CPU makes the kernel print an RDSEED warning at every boot. This hides all kernel messages on screen while the system starts; they stay in dmesg.",
            "dashboardMemoryDetail",
        )
        self.boot_messages_detail.setWordWrap(True)
        copy.addWidget(self.boot_messages_detail)
        root.addLayout(copy, 1)

        self.boot_messages_apply_button = QPushButton(tr("Hide boot messages"))
        self.boot_messages_apply_button.setProperty("dashboardCardAction", True)
        self.boot_messages_apply_button.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.boot_messages_apply_button.clicked.connect(self._request_boot_messages)
        self._boot_messages_action = "hide"
        root.addWidget(self.boot_messages_apply_button)
        panel.hide()
        return panel

    def _steamos_readonly_panel(self) -> QFrame:
        """SteamOS' read-only root, beside Bazzite's mitigations switch."""
        panel = QFrame()
        self.readonly_panel = panel
        panel.setProperty("dashboardMemoryPanel", True)
        panel.setProperty("dashboardBootPanel", True)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root = QBoxLayout(QBoxLayout.Direction.LeftToRight, panel)
        self.readonly_layout = root
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)
        copy = QVBoxLayout()
        copy.setSpacing(4)
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(_label("SteamOS read-only mode", "dashboardComponentTitle", wrap=False))
        self.readonly_status = PillLabel("Checking", "gray")
        header.addWidget(self.readonly_status)
        header.addStretch(1)
        copy.addLayout(header)
        detail = _label(
            "SteamOS keeps its system files read-only so an update can replace them whole. Installing packages needs it off; the next SteamOS update turns it back on and removes what was installed.",
            "dashboardMemoryDetail",
        )
        detail.setWordWrap(True)
        copy.addWidget(detail)
        root.addLayout(copy, 1)
        self.readonly_button = QPushButton(tr("Disable read-only mode"))
        self.readonly_button.setProperty("dashboardCardAction", True)
        self.readonly_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.readonly_button.clicked.connect(self._request_steamos_readonly)
        self._readonly_action = "disable"
        root.addWidget(self.readonly_button)
        panel.hide()
        return panel

    _KERNEL_STATE_WIDTH = 124
    _KERNEL_ACTION_WIDTH = 176
    _KERNEL_ROW_HEIGHT = 46

    #: The two boot options, in the order the panel shows them.
    KERNEL_OPTION_ROWS = (
        ("mitigations=off", "CPU security mitigations", "Disable mitigations", "Restore mitigations"),
        ("nosmt", "Simultaneous multithreading (SMT)", "Disable SMT", "Restore SMT"),
        (CU_UNLOCK_OPTION, "Compute Units unlock (kernel)", "Unlock all 40 CUs", "Restore CU lock"),
        (HIDE_BOOT_MESSAGES_OPTION, "Boot messages (hides the RDSEED warning)", "Hide boot messages", "Show boot messages"),
    )
    #: Options that give something up, and so are drawn as a warning. Unlocking
    #: compute units gives nothing up: it is the BC-250 kernel's own method.
    #: Hiding boot messages risks nothing for the board; it is explained in its
    #: confirmation, not painted red.
    KERNEL_OPTION_NEUTRAL = frozenset({CU_UNLOCK_OPTION, HIDE_BOOT_MESSAGES_OPTION})


    def _request_smt_live(self) -> None:
        self.dependency_action_requested.emit(
            {
                "action": "smt_live",
                "governor": "",
                "selected_components": self.selected_components,
                "smt_mode": self._smt_live_target,
            }
        )

    def _request_kernel_option(self, option: str) -> None:
        arguments = _mapping(self._kernel_options_state.get("arguments"))
        managed = {key for key, value in arguments.items() if _mapping(value).get("managed")}
        wanted = managed - {option} if option in managed else managed | {option}
        self.dependency_action_requested.emit(
            {
                "action": "kernel_options_set",
                "governor": "",
                "selected_components": self.selected_components,
                "kernel_options": sorted(wanted),
                "kernel_option_changed": option,
            }
        )

    def _update_kernel_options_control(self, tools: Mapping[str, object]) -> None:
        setup = _mapping(tools.get("system_setup"))
        state = _mapping(setup.get("kernel_options"))
        self._kernel_options_state = dict(state)
        available = bool(setup.get("helper_available") and state.get("available"))
        self.kernel_options_panel.setVisible(available)
        if not available:
            return
        arguments = _mapping(state.get("arguments"))
        allowed = set(state.get("allowed") or (option for option, *_ in self.KERNEL_OPTION_ROWS))
        cu_item = _mapping(arguments.get(CU_UNLOCK_OPTION))
        # Only a kernel that has the parameter can use the unlock. A row that
        # was staged, or set by hand, stays so that it can still be taken back.
        cu_visible = CU_UNLOCK_OPTION in allowed and bool(
            _mapping(state.get("cu_unlock")).get("supported")
            or cu_item.get("managed")
            or cu_item.get("configured")
            or cu_item.get("external")
        )
        self.kernel_cu_note.setVisible(cu_visible)
        self.kernel_cu_heat.setVisible(cu_visible)
        for option, _title, disable_text, restore_text in self.KERNEL_OPTION_ROWS:
            name, pill, button = self.kernel_option_controls[option]
            item = _mapping(arguments.get(option))
            row_visible = option in allowed and (option != CU_UNLOCK_OPTION or cu_visible)
            if option == CU_UNLOCK_OPTION or option not in allowed:
                for widget in (name, pill, button, self.kernel_option_rules.get(option)):
                    if widget is not None:
                        widget.setVisible(row_visible and (widget is not pill))
                # A hidden row still kept its minimum height and left an empty
                # band under SMT wherever the kernel has no CU unlock.
                self.kernel_option_grid.setRowMinimumHeight(
                    self.kernel_option_rows[option], self._KERNEL_ROW_HEIGHT if row_visible else 0
                )
            if not row_visible:
                continue
            if item.get("external"):
                status, tone = "Set outside Control Center", "blue"
            elif bool(item.get("configured")) != bool(item.get("active")):
                status, tone = "Reboot required", "orange"
            elif item.get("active"):
                status, tone = "Disabled", "orange"
            else:
                status, tone = "Enabled", "green"
            pill.setText(tr(status))
            pill.set_tone(tone)
            # Enabled / Disabled is already what the button says ("Disable SMT"
            # means it is on, "Restore SMT" that it is off). The pill is kept
            # only for what the button cannot say: a pending reboot, or an
            # option set outside Control Center.
            pill.setVisible(status not in {"Enabled", "Disabled"} and (option != CU_UNLOCK_OPTION or cu_visible))
            managed = bool(item.get("managed"))
            button.setText(tr(restore_text if managed else disable_text))
            button.setProperty("dangerAction", not managed and option not in self.KERNEL_OPTION_NEUTRAL)
            button.style().unpolish(button)
            button.style().polish(button)
            button.setEnabled(not item.get("external"))
        smt = _mapping(state.get("smt"))
        live = bool(smt.get("supported")) and "nosmt" in allowed
        self.smt_live_rule.setVisible(live)
        self.smt_live_row.setVisible(live)
        if live:
            is_on = str(smt.get("control") or "") == "on"
            self._smt_live_target = "off" if is_on else "on"
            self.smt_live_pill.setText(tr("Enabled" if is_on else "Disabled"))
            self.smt_live_pill.set_tone("green" if is_on else "orange")
            # The button says it ("Turn SMT off now" means it is on).
            self.smt_live_pill.setVisible(False)
            self.smt_live_button.setText(tr("Turn SMT off now" if is_on else "Turn SMT on now"))

    def _request_steamos_readonly(self) -> None:
        self.dependency_action_requested.emit(
            {
                "action": f"steamos_readonly_{self._readonly_action}",
                "governor": "",
                "selected_components": self.selected_components,
            }
        )

    def _update_steamos_readonly_control(self, tools: Mapping[str, object]) -> None:
        state = _mapping(tools.get("steamos_readonly"))
        available = bool(state.get("available"))
        self.readonly_panel.setVisible(available)
        if not available:
            return
        mode = str(state.get("state") or "unknown")
        status, tone = {
            "enabled": ("Protected", "green"),
            "disabled": ("Writable", "orange"),
        }.get(mode, ("Unknown", "gray"))
        self.readonly_status.setText(tr(status))
        self.readonly_status.set_tone(tone)
        # Protected / Writable is what the button says ("Disable read-only
        # mode" means it is protected); only an unknown state is worth a pill.
        self.readonly_status.setVisible(mode not in {"enabled", "disabled"})
        self._readonly_action = "enable" if mode == "disabled" else "disable"
        self.readonly_button.setText(
            tr("Turn read-only back on" if self._readonly_action == "enable" else "Disable read-only mode")
        )
        self.readonly_button.setEnabled(mode in {"enabled", "disabled"})








    @staticmethod
    def _adopt(button: QPushButton, role: str) -> None:
        """Give a card's action button the page style: ``role`` is
        ``compactAction`` (grey), ``accentAction`` (blue tint) or, when the
        footer makes it the next step, the solid blue ``PrimaryAction``."""
        danger = bool(button.property("dangerAction"))
        for name in ("dashboardCardAction", "accented", "linkAction", "compactAction", "accentAction"):
            button.setProperty(name, False)
        if not danger:
            button.setProperty(role, True)
        button.setMinimumHeight(28)
        button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        button.style().unpolish(button)
        button.style().polish(button)

    def _organise_compatibility(self, layout: QVBoxLayout) -> None:
        """Additional settings: one list per topic, a title row per tool.

        Each group is a single surface with the tools as rows divided by thin
        lines; the description and actions of a row open on demand.
        """
        self.compatibility_groups = (
            ("System", (self.acpi_card,)),
            ("GPU governor", (self.cyan_card, self.oberon_card)),
            # Mesa first: it is what leaves the desktop on the CPU, whatever the kernel does.
            ("Kernel and graphics", (self.mesa_card, self.gfx_card, *self.cachyos_cards)),
            ("Video", (self.vaapi_card,)),
        )
        layout.setSpacing(0)
        # Boot options: the panels that used to sit above the component list.
        layout.insertSpacing(layout.count() - 1, 12)
        layout.insertWidget(layout.count() - 1, self._boot_holder)
        self._compatibility_headings = []
        for title, cards in self.compatibility_groups:
            # The earliest of its cards, whatever order they are listed in.
            index = min(layout.indexOf(card) for card in cards)
            box = QFrame()
            box.setProperty("dashboardCompatibilityGroupBox", True)
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(0, 0, 0, 0)
            box_layout.setSpacing(0)
            for card in cards:
                layout.removeWidget(card)
                card.setProperty("listRow", True)
                card.make_collapsible()
                # State rows (Kernel / Mesa pills) line up with the title.
                for frame in card.findChildren(QFrame):
                    if frame.property("dashboardCompatibilityState") and frame.layout():
                        margins = frame.layout().contentsMargins()
                        frame.layout().setContentsMargins(0, margins.top(), 0, margins.bottom())
                box_layout.addWidget(card)
            heading = _label(title, "dashboardCompatibilityGroup", wrap=False)
            layout.insertWidget(index, heading)
            layout.insertWidget(index + 1, box)
            self._compatibility_headings.append((heading, box, cards))
        self._refresh_compatibility_summary()

    def _refresh_compatibility_summary(self) -> None:
        """Hide a group whose tools are all hidden; keep one rule above each row but the first."""
        if not self._standalone or not hasattr(self, "_compatibility_headings"):
            return
        self._boot_holder.setVisible(any(not panel.isHidden() for panel in self._boot_panels))
        for heading, box, cards in self._compatibility_headings:
            shown = [card for card in cards if not card.isHidden()]
            heading.setVisible(bool(shown))
            box.setVisible(bool(shown))
            for card in cards:
                first = bool(shown) and card is shown[0]
                if card.property("listFirst") != first:
                    card.setProperty("listFirst", first)
                    card.style().unpolish(card)
                    card.style().polish(card)


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



    def _forward_accessory_action(self, payload: object) -> None:
        values = dict(payload) if isinstance(payload, Mapping) else {}
        accessory, operation = str(values.get("accessory") or ""), str(values.get("op") or "")
        if accessory and operation:
            self.driver_support_requested.emit(f"{accessory}:{operation}")

    #: What each state reads as, per accessory: status, tone and the label
    #: of the install button (empty hides it).
    _ACCESSORY_STATES = {
        "unsupported": ("Not available here", "gray", ""),
        "not-installed": ("Not installed", "gray", "Install"),
        "reboot-required": ("Restart required", "orange", ""),
        "update-available": ("Update available", "blue", "Update"),
        # Once it works, opening it is what the owner came for; a reinstall
        # is Remove and Install.
        "relogin-required": ("Log out to finish", "orange", ""),
        "installed": ("Installed", "blue", ""),
        "active": ("Active", "green", ""),
        "managed-elsewhere": ("Installed another way", "blue", ""),
    }
    _ACCESSORY_NOTES = {
        ("thermalright", "unsupported"): "TRCC publishes packages for Arch, CachyOS, Manjaro, Fedora, Bazzite, Debian and Ubuntu. SteamOS is not covered yet.",
        ("thermalright", "reboot-required"): "TRCC is in the next deployment. Restart, then open the configuration once and save a theme.",
        ("thermalright", "installed"): "Open the configuration once and save a theme; the display then follows it by itself.",
        ("corsair", "unsupported"): "OpenLinkHub is published for x86_64 only.",
        ("corsair", "relogin-required"): "Installed. Log out and back in (or restart) once, so this account can reach the Corsair devices.",
        ("corsair", "managed-elsewhere"): "OpenLinkHub is already installed on this system outside Control Center, so it is left as it is.",
        ("hdmi_ac3", "unsupported"): "Needs PipeWire with WirePlumber 0.5 or newer and the BC-250 HDMI audio function.",
        ("hdmi_ac3", "reboot-required"): "The encoder is in the next deployment. Restart, then press Install again to switch the output to 5.1.",
        ("hdmi_ac3", "installed"): "Configured, but another output is in use. Press Use 5.1 output to switch back to it.",
        ("hdmi_ac3", "managed-elsewhere"): "Another toolkit already switches the AC-3 profile on, so it is left as it is.",
        ("hdmi_cec", "unsupported"): "The running kernel was built without CEC over DisplayPort.",
    }
    #: What the configure button reads as, per accessory; empty hides it.
    _ACCESSORY_CONFIGURE = {
        "thermalright": "Open configuration",
        "corsair": "Open control panel",
        "hdmi_ac3": "",
        "hdmi_cec": "Open TV control",
    }


    #: Stable names for the tabs, in order. The guided tour used to address
    #: them by position and pointed at the wrong one after "Memory & Swap"
    #: was inserted in the middle.
    TAB_KEYS = ("components", "compatibility", "memory", "decky", "drivers", "upscaling")
    #: Upscaling sits next to Compatibility, where its tools used to live.
    TAB_ORDER = (0, 1, 5, 2, 3, 4)

    def tab_index(self, key: str) -> int:
        return self.TAB_KEYS.index(key) if key in self.TAB_KEYS else -1

    def select_tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.prepare_footer.setVisible(index == 0)
        for button_index, button in enumerate(self.tab_buttons):
            button.setChecked(button_index == index)
            button.style().unpolish(button)
            button.style().polish(button)
        if 0 <= index < len(self.TAB_KEYS):
            self.tab_selected.emit(self.TAB_KEYS[index])

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

    def _request_smt_boot(self) -> None:
        self.dependency_action_requested.emit(
            {
                "action": f"bazzite_smt_{self._smt_boot_action}",
                "governor": "",
                "selected_components": self.selected_components,
            }
        )

    def _update_smt_boot_control(
        self, tools: Mapping[str, object], *, actionable: bool
    ) -> None:
        state = _mapping(tools.get("bazzite_smt"))
        configured = bool(state.get("configured"))
        managed = bool(state.get("managed"))
        available = bool(state.get("available"))
        self.smt_panel.setVisible(actionable)
        # Only a pending reboot is worth a pill: the button says the rest.
        self.smt_status.setVisible(actionable and bool(state.get("reboot_required")))
        if not actionable:
            return
        self.smt_status.setText(tr("Reboot required"))
        self.smt_status.set_tone("orange")
        self._smt_boot_action = "restore" if managed else "disable"
        self.smt_apply_button.setText(
            tr(
                "Managed externally"
                if configured and not managed
                else "Restore SMT"
                if self._smt_boot_action == "restore"
                else "Disable SMT"
            )
        )
        self.smt_apply_button.setProperty("dangerAction", False)
        self.smt_apply_button.setEnabled(available and (not configured or managed))
        self.smt_apply_button.setToolTip(
            tr("Set outside Control Center") if configured and not managed else ""
        )

    def _request_boot_messages(self) -> None:
        self.dependency_action_requested.emit(
            {
                "action": f"bazzite_boot_messages_{self._boot_messages_action}",
                "governor": "",
                "selected_components": self.selected_components,
            }
        )

    def _update_boot_messages_control(
        self, tools: Mapping[str, object], *, actionable: bool
    ) -> None:
        state = _mapping(tools.get("bazzite_boot_messages"))
        configured = bool(state.get("configured"))
        managed = bool(state.get("managed"))
        available = bool(state.get("available"))
        self.boot_messages_panel.setVisible(actionable)
        # Same rule as the other boot options: only a pending reboot is shown.
        self.boot_messages_status.setVisible(actionable and bool(state.get("reboot_required")))
        if not actionable:
            return
        if state.get("reboot_required"):
            status, tone = tr("Reboot required"), "orange"
        elif configured:
            status, tone = tr("Hidden"), "orange"
        else:
            status = tr("Shown") if available else tr("Not detected")
            tone = "green" if available else "gray"
        self.boot_messages_status.setText(status)
        self.boot_messages_status.set_tone(tone)

        self._boot_messages_action = "restore" if managed else "hide"
        self.boot_messages_apply_button.setText(
            tr(
                "Managed externally"
                if configured and not managed
                else "Show boot messages"
                if self._boot_messages_action == "restore"
                else "Hide boot messages"
            )
        )
        self.boot_messages_apply_button.setEnabled(
            available and (not configured or managed)
        )
        self.boot_messages_apply_button.setToolTip(
            tr("loglevel=0 was configured outside Control Center and is preserved.")
            if configured and not managed
            else tr(
                "The BC-250's CPU makes the kernel print an RDSEED warning at every boot. This hides all kernel messages on screen while the system starts; they stay in dmesg."
            )
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
        # Enabled / Disabled is what the button already says ("Disable
        # mitigations" means they are on). The pill stays only for what the
        # button cannot say: a reboot that is still pending.
        self.mitigations_status.setVisible(actionable and bool(state.get("reboot_required")))
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
        self._update_boot_messages_control(tools, actionable=actionable)
        self._update_smt_boot_control(tools, actionable=actionable)
        self._update_steamos_readonly_control(tools)
        self._update_kernel_options_control(tools)
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




    _FSR4_GAME_COPY = {
        "ready": ("Ready", "green",
                  "In the game choose DLSS, FSR or XeSS, then press Insert to open OptiScaler."),
        "needs-launch-option": ("Launch option missing", "orange",
                                "OptiScaler is installed, but Steam does not load it yet. Close Steam, then add the launch option."),
        "not-installed": ("Not installed", "gray",
                          "In the client, select this game and press Install / update selected."),
        "other-launcher": ("Launcher setting needed", "blue",
                           "Add WINEDLLOVERRIDES with {dll}=n,b in the launcher that runs this game; the guide shows where."),
        "unknown-adapter": ("Check the adapter", "orange",
                            "OptiScaler is in this game under a file name this panel does not recognise; see the guide."),
        "linked-folder": ("Linked folder", "orange",
                          "OptiScaler Client refuses folders reached through a link ({link}). Add this library again in its launcher from the real folder: {path}"),
    }

    #: Per game and state: the tooltip with the full story.
    _HELIXSR_GAME_COPY = {
        "installed": "In the game, choose AMD FSR as the upscaler. Remove puts the game's own file back.",
        "restored": "A game update or Steam's file check put the game's own FSR file back. Remove cleans up; add HelixSR again if you want it.",
        "available": "Add HelixSR to replace this game's FSR 3.1 upscaler. The original file is kept as a backup.",
        "missing": "The game's folder is gone: it was uninstalled or moved. Remove HelixSR forgets it here.",
    }
    _HELIXSR_SCALER_COPY = {
        "installed": "In the game choose DLSS; Insert opens HelixSR Scaler's menu. Frame generation runs in games with DLSS Frame Generation: turn it on here, then in the game. Remove puts every file it replaced back.",
        "restored": "A game update or Steam's file check changed HelixSR Scaler's files. Remove cleans up; add it again if you want it.",
        "available": "HelixSR Scaler is HelixSR inside its own OptiScaler: the game's DLSS option runs HelixSR, with DLSS frame generation if you turn it on. Not for online games or games with anti-cheat.",
        "missing": "The game's folder is gone: it was uninstalled or moved. Remove forgets it here.",
        "outdated": "This game has HelixSR Scaler {version}. Update HelixSR gives it the installed release and keeps {version} to go back to.",
    }
    _HELIXSR_NETWORK_MISSING_COPY = (
        "HelixSR is in this game but its network files are not, so it only does a simple upscale. Update HelixSR copies them back."
    )
    _HELIXSR_OPTISCALER_COPY = {
        "installed": "In the game choose DLSS, FSR or XeSS, press Insert and pick FSR HelixSR in OptiScaler's upscaler menu. Remove puts OptiScaler's settings back.",
        "restored": "OptiScaler's settings no longer point to HelixSR, usually after OptiScaler Client updated or restored this game. Remove cleans up HelixSR's folder.",
        "available": "OptiScaler is in this game, so HelixSR can upscale through it, even when the game only offers DLSS or XeSS.",
        "missing": "The game's folder is gone: it was uninstalled or moved. Remove HelixSR forgets it here.",
    }

    #: OptiScaler Client's own record of a game, per state: the tooltip.
    _FSR4_UNDO_COPY = {
        "intact": "OptiScaler Client installed these files. Remove OptiScaler, keep a backup moves them into a backup folder and puts back any game file they replaced; Put OptiScaler back returns them.",
        "partial": "Some of OptiScaler's files were deleted by hand. Remove OptiScaler, keep a backup moves the rest into a backup folder and clears the client's record.",
        "removed": "OptiScaler's files are gone, but OptiScaler Client still records them, so it refuses to install, update or restore this game. Clear the client's record to start again; the record is kept in a backup folder.",
        "changed": "Some of OptiScaler's files changed after the client installed them (a game update or a hand edit). Nothing was touched.",
        "helixsr": "HelixSR uses this game's OptiScaler. Remove HelixSR from it first.",
        "pending": "OptiScaler Client was interrupted in this game. Open the client and use Restore / recover selected first.",
        "backup-broken": "OptiScaler Client's copy of a game file changed, so the game's own file could not come back. Nothing was touched.",
        "unsupported": "This installation record is not one Control Center can read. Nothing was touched.",
        "interrupted": "Control Center was interrupted while taking OptiScaler out of this game. Put OptiScaler back returns the files it had already moved; then try again.",
        "linked": "OptiScaler Client recorded this game through a linked folder ({link}), so its own Restore cannot undo it. This panel can.",
        "backup": "Control Center took OptiScaler out of this game on {date}. Put OptiScaler back returns it as it was. The backup is in {path}.",
    }

    #: FSR4 per game, as the game table shows it: (text, tone).
    _FSR4_MATRIX_COPY = {
        "ready": ("Active", "green"),
        "needs-launch-option": ("Steam option missing", "orange"),
        "not-installed": ("Not installed", ""),
        "other-launcher": ("Set up in launcher", ""),
        "unknown-adapter": ("Check the adapter", "orange"),
        "linked-folder": ("Linked folder", "orange"),
    }



    def _match_upscaler_headers(self) -> None:
        """Side by side, both cards start their readings on the same line."""
        sections = (self.fsr4_section, self.helixsr_section)
        side_by_side = self.upscaling_row.direction() == QBoxLayout.Direction.LeftToRight
        heights = [section._title_host.sizeHint().height() for section in sections]
        for section in sections:
            section._title_host.setMinimumHeight(max(heights) if side_by_side else 0)

    @staticmethod
    def _games_reading(active: int, total: int, installed: bool) -> str:
        """Games where the upscaler works, of the games it can go into."""
        return f"{active} / {total}" if installed else "—"


    def _select_fsr4_release(self, index: int) -> None:
        tag = str(self.fsr4_version_combo.itemData(index) or "")
        fsr4 = _mapping(_mapping(getattr(self, "_fsr4_view", {})).get("state"))
        if tag and tag != str(fsr4.get("tag") or ""):
            self._forward_dependency_action({"action": f"fsr4_select:{tag}", "governor": ""})

    def _select_helixsr_release(self, index: int) -> None:
        tag = str(self.helixsr_version_combo.itemData(index) or "")
        helixsr = _mapping(_mapping(getattr(self, "_helixsr_view", {})).get("state"))
        if tag and tag != str(helixsr.get("tag") or ""):
            self._forward_dependency_action({"action": f"helixsr_select:{tag}", "governor": ""})





    def _copy_row(self, label: str, action: str, value) -> tuple[QFrame, IconButton]:
        """A compact "label ··· ⧉" row that copies ``value()`` when pressed."""
        row = QFrame()
        row.setProperty("fsr4LaunchOption", True)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 5, 6, 5)
        row_layout.setSpacing(7)
        row_layout.addWidget(_label(label, "dashboardCompatibilityLabel", wrap=False))
        row_layout.addStretch(1)
        button = IconButton("⧉")
        button.setProperty("fsr4LaunchCopy", True)
        button.setFixedSize(30, 30)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAccessibleName(tr(action))
        button.setToolTip(tr(action))

        def copy() -> None:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(value())
            button.setText("✓")
            button.setToolTip(tr("Copied"))

            def restore() -> None:
                button.setText("⧉")
                button.setToolTip(tr(action))

            QTimer.singleShot(1600, restore)

        button.clicked.connect(copy)
        row_layout.addWidget(button)
        row.hide()
        return row, button

    def _copy_fsr4_launch_option(self) -> None:
        if not self._fsr4_launch_option:
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._fsr4_launch_option)
        self.fsr4_copy_button.setText(tr("Copied"))
        self.fsr4_copy_button.setToolTip(tr("Copied"))
        QTimer.singleShot(1600, self._restore_fsr4_copy_button)

    def _restore_fsr4_copy_button(self) -> None:
        self.fsr4_copy_button.setText(tr("Copy"))
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




from .dashboard_footer import (  # noqa: E402,F401  (re-exported: pages and tests import them from here)
    DashboardFooter,
    UpdateCallout,
    _FooterActionButton,
    _GlowingFooterButton,
    _ReportButton,
    _UpdateBadgeButton,
)
