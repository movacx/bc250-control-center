"""Proposal-N dashboard widgets backed by the real BC250 preparation state."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWidgets import QPushButton as IconButton

from .. import theme
from ..core.gfx1013_presenter import present_gfx1013
from ..core.preferences import application_settings
from ..i18n import tr, tr_format
from .buttons import WrappingButton as QPushButton
from .responsive import clear_grid
from .system_setup_controls import is_bazzite_host, update_memory_controls
from .widgets import ICON_DIR, PillLabel, apply_shadow, icon


def _label(text: str, property_name: str, *, wrap: bool = True) -> QLabel:
    widget = QLabel(tr(text))
    widget.setProperty(property_name, True)
    widget.setWordWrap(wrap)
    widget.setMinimumWidth(0)
    return widget


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


class _DeckyPreviewOverlay(QWidget):
    """Animated, hardware-inert replica of the BC250 Decky side panel."""

    closed = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("DeckyPreviewOverlay")
        self.setProperty("gamepadOverlay", False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # This preview deliberately owns every colour token.  It mirrors the
        # real Decky plugin rather than inheriting the Control Center's chosen
        # desktop accent/theme.
        self.setStyleSheet("background: rgba(0, 0, 0, 150);")
        self.drawer = QFrame(self)
        self.drawer.setObjectName("DeckyPreviewDrawer")
        self.drawer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.drawer.setStyleSheet("""
            QFrame#DeckyPreviewDrawer { background: #0f0f0f; border-left: 1px solid #343434; }
            QWidget#DeckyPreviewBody, QScrollArea#DeckyPreviewScroll, QScrollArea#DeckyPreviewScroll > QWidget > QWidget { background: #0f0f0f; }
            QFrame[deckyPluginSurface='true'] { background: #171717; border: 1px solid #343434; border-radius: 12px; }
            QFrame[deckySection='true'] { background: transparent; border: none; }
            QFrame[deckyMetric='true'], QFrame[deckyCuMatrix='true'] { background: #1f1f1f; border: 1px solid #343434; border-radius: 6px; }
            QLabel[deckyTitle='true'] { background: transparent; color: #f2f2f2; font-size: 18px; font-weight: 750; }
            QLabel[deckySectionTitle='true'] { background: transparent; color: #b4b4b4; font-size: 10px; font-weight: 700; }
            QLabel[deckyValue='true'] { background: transparent; color: #f2f2f2; font-size: 13px; font-weight: 700; }
            QLabel[deckyMuted='true'] { background: transparent; color: #8e8e8e; font-size: 9px; }
            QPushButton { background: #242424; border: 1px solid #343434; border-radius: 6px; color: #f2f2f2; }
            QPushButton:hover { background: #2c2c2c; }
            QPushButton:pressed { background: #333333; }
            QPushButton[deckyControl='true'] { min-height: 34px; padding: 5px; font-size: 10px; }
            QPushButton[deckyControl='true']:focus, QPushButton[deckyCu='true']:focus { border: 2px solid #6e9fff; }
            QPushButton[deckySelected='true'] { background: #38291d; border: 1px solid #f0a45d; color: #f0a45d; }
            QPushButton[deckyPrimary='true'] { background: #f0a45d; border: 1px solid #f0a45d; color: #38291d; font-weight: 700; }
            QPushButton[deckyDanger='true'] { background: #3a2020; border: 1px solid #3a2020; color: #ff6b64; }
            QPushButton[deckyCu='true'] { background: #1b3224; border: 1px solid #3d784c; border-radius: 5px; color: #5cbf78; min-height: 27px; font-size: 8px; }
            QSlider { background: transparent; min-height: 18px; }
            QSlider::groove:horizontal { height: 4px; background: #424242; border-radius: 2px; }
            /* SliderField is native Decky UI, not a theme.ts token.  Match
               the blue native track visible in the real Quick Access panel. */
            QSlider::sub-page:horizontal { background: #35a8e8; border-radius: 2px; }
            QSlider::handle:horizontal { background: #f2f2f2; width: 16px; margin: -6px 0; border-radius: 8px; }
            QScrollBar:vertical { background: #171717; width: 7px; margin: 2px; }
            QScrollBar::handle:vertical { background: #424242; border-radius: 3px; min-height: 24px; }
            QScrollBar::handle:vertical:hover { background: #5a5a5a; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        root = QVBoxLayout(self.drawer)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(8)
        header = QHBoxLayout()
        close = IconButton("‹")
        close.setFixedSize(34, 34)
        close.setProperty("deckyControl", True)
        close.setProperty("gamepadEntry", True)
        close.setAccessibleName(tr("Close preview"))
        close.clicked.connect(self.close_animated)
        header.addWidget(close)
        title = _label("BC250 Quick Access", "deckyTitle", wrap=True)
        header.addWidget(title, 1)
        root.addLayout(header)

        scroll = QScrollArea()
        scroll.setObjectName("DeckyPreviewScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("DeckyPreviewBody")
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 2, 2, 4)
        surface = QFrame()
        surface.setProperty("deckyPluginSurface", True)
        content = QVBoxLayout(surface)
        content.setContentsMargins(12, 12, 12, 16)
        content.setSpacing(8)
        content.addWidget(self._gpu_section())
        content.addWidget(self._cu_section())
        content.addWidget(self._cpu_section())
        content.addWidget(self._fan_section())
        content.addWidget(self._memory_section())
        note = _label(
            "Interactive preview only · no hardware action is executed.",
            "deckyMuted",
        )
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(note)
        content.addStretch(1)
        body_layout.addWidget(surface)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        self._animation = QPropertyAnimation(self.drawer, b"geometry", self)
        self._animation.setDuration(240)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    @staticmethod
    def _section(title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setProperty("deckySection", True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = _label(title, "deckySectionTitle", wrap=False)
        layout.addWidget(label)
        return frame, layout

    @staticmethod
    def _preview_button(
        text: str,
        *,
        selected: bool = False,
        primary: bool = False,
    ) -> IconButton:
        button = IconButton("\n".join(tr(line) for line in text.splitlines()))
        button.setProperty("deckyControl", True)
        button.setProperty("deckySelected", selected)
        button.setProperty("deckyPrimary", primary)
        button.setToolTip(tr("Preview only · this control does not change hardware."))
        return button

    def _gpu_section(self) -> QFrame:
        frame, layout = self._section(
            f"▣  {tr('GPU')}                                      Cyan"
        )
        profiles = QGridLayout()
        profiles.setSpacing(5)
        live = QFrame()
        live.setProperty("deckyMetric", True)
        live_layout = QVBoxLayout(live)
        live_layout.setContentsMargins(7, 5, 7, 5)
        live_layout.setSpacing(0)
        live_layout.addWidget(_label("GPU live", "deckyMuted", wrap=False))
        live_layout.addWidget(_label("1000 MHz", "deckyValue", wrap=False))
        live_layout.addWidget(_label("Voltage · 899 mV", "deckyMuted", wrap=False))
        profiles.addWidget(live, 0, 0)
        for index, text in enumerate(
            (
                "Balanced\n500–1500 MHz",
                "Gaming\n1000–1850 MHz",
                "Benchmark\n1000–2000 MHz",
            )
        ):
            profiles.addWidget(
                self._preview_button(text, selected=index == 1),
                (index + 1) // 2,
                (index + 1) % 2,
            )
        layout.addLayout(profiles)
        return frame

    def _cu_section(self) -> QFrame:
        frame, layout = self._section(
            f"▦  {tr('Compute Units').upper()}                         40/40 CU"
        )
        matrix = QFrame()
        matrix.setProperty("deckyCuMatrix", True)
        grid = QGridLayout(matrix)
        grid.setContentsMargins(7, 7, 7, 7)
        grid.setSpacing(4)
        for row in range(4):
            for column in range(5):
                button = IconButton(f"{row}.{column}\nD+")
                button.setProperty("deckyCu", True)
                button.setToolTip(
                    tr("Preview only · this control does not change hardware.")
                )
                grid.addWidget(button, row, column)
        layout.addWidget(matrix)
        actions = QHBoxLayout()
        actions.addWidget(self._preview_button("Apply changes", primary=True), 1)
        actions.addWidget(self._preview_button("Save selection"), 1)
        layout.addLayout(actions)
        service_actions = QHBoxLayout()
        service_actions.addWidget(self._preview_button("Install service"), 1)
        remove = self._preview_button("Remove service")
        remove.setProperty("deckyDanger", True)
        service_actions.addWidget(remove, 1)
        layout.addLayout(service_actions)
        return frame

    def _cpu_section(self) -> QFrame:
        frame, layout = self._section(f"ϟ  {tr('CPU')}")
        grid = QGridLayout()
        grid.setSpacing(4)
        for index, (label, value) in enumerate(
            (
                ("CLOCK", "3184 MHz"),
                ("TCTL", "58.5 °C"),
                ("VID EST.", "1172 mV"),
                ("SCALE", "-34"),
            )
        ):
            tile = QFrame()
            tile.setProperty("deckyMetric", True)
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(7, 5, 7, 5)
            tile_layout.setSpacing(1)
            tile_layout.addWidget(_label(label, "deckyMuted", wrap=False))
            tile_layout.addWidget(_label(value, "deckyValue", wrap=False))
            grid.addWidget(tile, index // 2, index % 2)
        layout.addLayout(grid)
        layout.addWidget(
            _label(
                "SMU detector · thermal limit 90°C · calibrates under load",
                "deckyMuted",
            )
        )
        for label, value, minimum, maximum in (
            ("Target frequency · 3850 MHz", 3850, 3500, 4200),
            ("Maximum VID · 1150 mV", 1150, 950, 1325),
        ):
            layout.addWidget(_label(label, "deckyMuted", wrap=False))
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(minimum, maximum)
            slider.setValue(value)
            slider.setToolTip(
                tr("Preview only · this control does not change hardware.")
            )
            layout.addWidget(slider)
        manual = self._preview_button("Manual live scale · Off")
        manual.setStyleSheet("text-align: left; padding-left: 9px;")
        layout.addWidget(manual)
        layout.addWidget(_label("Manual scale · -34", "deckyMuted", wrap=False))
        scale = QSlider(Qt.Orientation.Horizontal)
        scale.setRange(-50, 0)
        scale.setValue(-34)
        scale.setToolTip(tr("Preview only · this control does not change hardware."))
        layout.addWidget(scale)
        layout.addWidget(self._preview_button("Apply automatic profile", primary=True))
        service_actions = QHBoxLayout()
        service_actions.addWidget(self._preview_button("Install service"), 1)
        remove = self._preview_button("Remove service")
        remove.setProperty("deckyDanger", True)
        service_actions.addWidget(remove, 1)
        layout.addLayout(service_actions)
        return frame

    def _fan_section(self) -> QFrame:
        frame, layout = self._section(f"◉  {tr('SYSTEM FANS')}")
        layout.addWidget(
            self._preview_button(
                f"PWM 2 · Pump Fan · {tr('Detected')}                  ▾"
            )
        )
        layout.addWidget(_label("Observed speed · 1840 RPM", "deckyMuted", wrap=False))
        speed = QSlider(Qt.Orientation.Horizontal)
        speed.setRange(20, 100)
        speed.setValue(60)
        speed.setToolTip(tr("Preview only · this control does not change hardware."))
        layout.addWidget(speed)
        actions = QHBoxLayout()
        actions.addWidget(self._preview_button("Apply", primary=True), 1)
        actions.addWidget(self._preview_button("Automatic"), 1)
        layout.addLayout(actions)
        return frame

    def _memory_section(self) -> QFrame:
        frame, layout = self._section(
            f"▣  {tr('MEMORY')}                              {tr('READ ONLY')}"
        )
        layout.addWidget(
            self._preview_button(
                f"ZRAM 8 GiB · ZSWAP {tr('Disabled')}                  ▾"
            )
        )
        return frame

    def show_animated(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        # ``finished`` is connected to the hide callback only while animating
        # out.  Remove that one-shot connection before an entrance animation;
        # otherwise reopening immediately hides the overlay when the entrance
        # reaches its final geometry.
        try:
            self._animation.finished.disconnect(self._finish_close)
        except TypeError:
            pass
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        width = min(410, max(330, round(parent.width() * 0.32)))
        end = self.rect().adjusted(self.width() - width, 0, 0, 0)
        start = end.translated(width, 0)
        self._animation.stop()
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self._animation.start()
        QTimer.singleShot(
            250,
            lambda: self.drawer.findChild(IconButton).setFocus(
                Qt.FocusReason.OtherFocusReason
            ),
        )

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
        self.closed.emit()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not self._animation.state() == QPropertyAnimation.State.Running:
            width = min(410, max(330, round(self.width() * 0.32)))
            self.drawer.setGeometry(self.width() - width, 0, width, self.height())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self.drawer.geometry().contains(event.position().toPoint()):
            self.close_animated()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in {Qt.Key.Key_Escape, Qt.Key.Key_Back}:
            self.close_animated()
            event.accept()
            return
        super().keyPressEvent(event)


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


class DashboardMetricTile(QFrame):
    def __init__(self, label: str, value: str = "Not detected", detail: str = ""):
        super().__init__()
        self.setProperty("dashboardMetricTile", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setFixedHeight(80)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.label = _label(label, "dashboardMetricLabel")
        self.value = _label(value, "dashboardMetricValue")
        self.detail = _label(detail, "dashboardMetricDetail")
        self.detail.setVisible(bool(detail))
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_value(self, value: str) -> None:
        self.value.setText(tr(value))

    def set_label(self, label: str) -> None:
        self.label.setText(tr(label))

    def set_detail(self, detail: str) -> None:
        self.detail.setText(tr(detail))
        self.detail.setVisible(bool(detail))


class DashboardCoreSummary(QFrame):
    """A responsive overview of the physical CPU-core samples."""

    def __init__(self) -> None:
        super().__init__()
        self.setProperty("dashboardMetricTile", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        self.root = layout
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(7)
        header = QHBoxLayout()
        header.setSpacing(8)
        self.label = _label("Available CPU cores", "dashboardMetricLabel", wrap=True)
        self.value = _label("Not detected", "dashboardMetricValue", wrap=False)
        self.detail = _label("Detected by the OS", "dashboardMetricDetail", wrap=False)
        header.addWidget(self.label)
        header.addWidget(self.value)
        header.addStretch(1)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.detail)
        layout.addLayout(header)
        self.core_grid = QGridLayout()
        self.core_grid.setContentsMargins(0, 0, 0, 0)
        self.core_grid.setHorizontalSpacing(6)
        self.core_grid.setVerticalSpacing(6)
        self.core_labels: list[QLabel] = []
        self.core_frequency_labels: list[QLabel] = []
        self.core_usage_labels: list[QLabel] = []
        self.core_separators: list[QLabel] = []
        self.core_cells: list[QFrame] = []
        for index in range(8):
            cell = QFrame()
            cell.setProperty("dashboardCoreCell", True)
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(8, 5, 8, 5)
            cell_layout.setSpacing(1)
            name = _label(f"N{index + 1}", "dashboardCoreName", wrap=False)
            metrics = QHBoxLayout()
            metrics.setContentsMargins(0, 0, 0, 0)
            metrics.setSpacing(4)
            frequency = _label("-- GHz", "dashboardCoreFrequency", wrap=False)
            separator = _label("·", "dashboardCoreSeparator", wrap=False)
            usage = _label("--%", "dashboardCoreUsage", wrap=False)
            usage.setToolTip(
                tr_format("CPU core {core} usage: {usage}%", core=index + 1, usage="--")
            )
            metrics.addWidget(frequency)
            metrics.addWidget(separator)
            metrics.addWidget(usage)
            metrics.addStretch(1)
            cell_layout.addWidget(name)
            cell_layout.addLayout(metrics)
            self.core_cells.append(cell)
            self.core_labels.append(name)
            self.core_frequency_labels.append(frequency)
            self.core_usage_labels.append(usage)
            self.core_separators.append(separator)
        layout.addLayout(self.core_grid)
        self._visible_core_count = 8
        self._rendered_core_count = 0
        self._columns = 0
        self._reflow(1000)

    def set_core_count(self, count: int) -> None:
        self._visible_core_count = min(8, max(1, int(count or 8)))
        self._reflow(self.width())

    def _reflow(self, width: int) -> None:
        available = self._visible_core_count
        columns = min(available, 8 if width >= 1100 else 4 if width >= 640 else 2)
        if (
            columns == self._columns
            and available == self._rendered_core_count
            and self.core_grid.count()
        ):
            return
        self._columns = columns
        self._rendered_core_count = available
        for cell in self.core_cells:
            self.core_grid.removeWidget(cell)
        for index, cell in enumerate(self.core_cells):
            visible = index < available
            cell.setVisible(visible)
            if visible:
                row, column = divmod(index, columns)
                self.core_grid.addWidget(cell, row, column)
        # Eight physical positions are always rendered.  Every one needs the
        # same stretch factor; leaving N7/N8 at the layout default shrinks
        # those two cells and breaks the visual rhythm of the strip.
        for column in range(8):
            self.core_grid.setColumnStretch(column, 1 if column < columns else 0)
        rows = (available + columns - 1) // columns
        self.setFixedHeight(91 if rows == 1 else 135 if rows == 2 else 179)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow(event.size().width())

    def set_value(self, value: str) -> None:
        self.value.setText(tr(value))

    def set_detail(self, detail: str) -> None:
        self.detail.setText(tr(detail))
        self.detail.setVisible(bool(detail))

    def set_core_metrics(
        self, frequencies_mhz: Iterable[object], usages: Iterable[object]
    ) -> None:
        frequencies = list(frequencies_mhz)
        samples = list(usages)
        measured_count = max(len(frequencies), len(samples))
        for index, (frequency_item, usage_item, separator) in enumerate(
            zip(
                self.core_frequency_labels,
                self.core_usage_labels,
                self.core_separators,
                strict=True,
            )
        ):
            try:
                usage = max(0, min(100, round(float(samples[index]))))
            except (IndexError, TypeError, ValueError):
                usage = None
            try:
                frequency = max(0.0, float(frequencies[index])) / 1000
            except (IndexError, TypeError, ValueError):
                frequency = None
            missing_slot = measured_count > 0 and index >= measured_count
            frequency_item.setText(
                f"{frequency:.2f} GHz"
                if frequency
                else tr("Hidden / offline")
                if missing_slot
                else "-- GHz"
            )
            separator.setVisible(not missing_slot)
            usage_item.setVisible(not missing_slot)
            usage_item.setText(f"{usage}%" if usage is not None else "--%")
            usage_item.setToolTip(
                tr_format(
                    "CPU core {core} usage: {usage}%",
                    core=index + 1,
                    usage=usage if usage is not None else "--",
                )
            )

    def set_label(self, label: str) -> None:
        self.label.setText(tr(label))


class DashboardThermalStrip(QFrame):
    """A responsive row of CPU, GPU, and board temperatures."""

    LABELS = ("GPU", "CPU", "M.2", "Board", "VRM")

    def __init__(self) -> None:
        super().__init__()
        self.setProperty("dashboardMetricTile", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(12, 8, 12, 8)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(2)
        self.labels: list[QLabel] = []
        self.values: list[QLabel] = []
        for text in self.LABELS:
            label = _label(text, "dashboardMetricLabel", wrap=False)
            value = _label("Not detected", "dashboardMetricValue", wrap=False)
            label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            value.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.labels.append(label)
            self.values.append(value)
        self._columns = 0
        self._reflow(1000)

    def set_temperatures(self, values: Iterable[str]) -> None:
        for label, value in zip(self.values, values, strict=True):
            label.setText(tr(value))

    def _reflow(self, width: int) -> None:
        # Keep the five sensors in one clear scan line when the hero has room;
        # progressively fold them into balanced rows on narrow windows.
        columns = 5 if width >= 450 else 3 if width >= 360 else 2
        if columns == self._columns:
            return
        self._columns = columns
        for widget in (*self.labels, *self.values):
            self.grid.removeWidget(widget)
        for index, (label, value) in enumerate(
            zip(self.labels, self.values, strict=True)
        ):
            group_row, column = divmod(index, columns)
            row = group_row * 2
            self.grid.addWidget(label, row, column)
            self.grid.addWidget(value, row + 1, column)
        for column in range(5):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow(event.size().width())


class DashboardTechnicalStrip(QFrame):
    """Five compact live diagnostics aligned with the thermal sensor strip."""

    LABELS = ("GPU power", "MCLK", "Hotspot", "GTT", "DPM mode")

    def __init__(self) -> None:
        super().__init__()
        self.setProperty("dashboardMetricTile", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(12, 7, 12, 7)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(2)
        self.labels: list[QLabel] = []
        self.values: list[QLabel] = []
        for text in self.LABELS:
            label = _label(text, "dashboardMetricLabel", wrap=False)
            value = _label("Not detected", "dashboardMetricValue", wrap=False)
            self.labels.append(label)
            self.values.append(value)
        self._columns = 0
        self._reflow(1000)

    def set_values(self, values: Iterable[str]) -> None:
        for label, value in zip(self.values, values, strict=True):
            label.setText(tr(value))

    def _reflow(self, width: int) -> None:
        columns = 5 if width >= 450 else 3 if width >= 330 else 2
        if columns == self._columns:
            return
        self._columns = columns
        for widget in (*self.labels, *self.values):
            self.grid.removeWidget(widget)
        for index, (label, value) in enumerate(
            zip(self.labels, self.values, strict=True)
        ):
            group_row, column = divmod(index, columns)
            row = group_row * 2
            self.grid.addWidget(label, row, column)
            self.grid.addWidget(value, row + 1, column)
        for column in range(5):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow(event.size().width())


class DashboardEvidenceRow(QWidget):
    def __init__(
        self, label: str, value: str = "Not detected", *, compact: bool = False
    ) -> None:
        super().__init__()
        self.setProperty("dashboardEvidenceRow", True)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4 if compact else 7, 0, 4 if compact else 7)
        row.setSpacing(10)
        self.label = _label(label, "dashboardEvidenceLabel")
        self.value = _label(value, "dashboardEvidenceValue")
        self.value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.label, 1)
        row.addWidget(self.value)

    def set_value(self, value: str) -> None:
        self.value.setText(tr(value))


class DashboardGpuHero(QFrame):
    """Large physical-clock readout and independent governor evidence."""

    activated = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = application_settings()
        self.setProperty("dashboardHero", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        apply_shadow(self, blur=18, y=3, alpha=14)

        self.root = QGridLayout(self)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setHorizontalSpacing(0)
        self.root.setVerticalSpacing(0)

        self.instrument = QWidget()
        instrument_layout = QVBoxLayout(self.instrument)
        instrument_layout.setContentsMargins(16, 14, 16, 14)
        instrument_layout.setSpacing(8)
        gpu_heading = QHBoxLayout()
        self.heading_icon = QLabel()
        self.heading_icon.setPixmap(icon("gpu_purple").pixmap(22, 22))
        self.heading_icon.setFixedSize(24, 24)
        gpu_heading.addWidget(self.heading_icon)
        gpu_heading.addWidget(_label("GPU Governor", "dashboardCardTitle"), 1)
        instrument_layout.addLayout(gpu_heading)

        self.readout = QWidget()
        self.readout_grid = QGridLayout(self.readout)
        self.readout_grid.setContentsMargins(0, 7, 0, 4)
        self.readout_grid.setHorizontalSpacing(16)
        self.readout_grid.setVerticalSpacing(10)

        frequency = QWidget()
        frequency_layout = QVBoxLayout(frequency)
        frequency_layout.setContentsMargins(0, 0, 0, 0)
        frequency_layout.setSpacing(7)
        frequency_layout.addWidget(
            _label("Current hardware frequency", "dashboardFrequencyEyebrow")
        )
        frequency_row = QHBoxLayout()
        frequency_row.setSpacing(10)
        self.frequency_value = _label("--", "dashboardFrequencyValue", wrap=False)
        self.frequency_unit = _label("MHz", "dashboardFrequencyUnit", wrap=False)
        frequency_row.addWidget(self.frequency_value)
        frequency_row.addWidget(
            self.frequency_unit, alignment=Qt.AlignmentFlag.AlignBottom
        )
        frequency_row.addStretch(1)
        frequency_layout.addLayout(frequency_row)
        self.readout_grid.addWidget(frequency, 0, 0)

        self.metrics_host = QWidget()
        metrics_grid = QGridLayout(self.metrics_host)
        metrics_grid.setContentsMargins(0, 0, 0, 0)
        metrics_grid.setHorizontalSpacing(8)
        metrics_grid.setVerticalSpacing(8)
        metrics_grid.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.governor_metric = DashboardMetricTile("Governor", "Not detected")
        self.load_metric = DashboardMetricTile("GPU load", "Not detected")
        self.thermal_strip = DashboardThermalStrip()
        self.technical_strip = DashboardTechnicalStrip()
        metrics_grid.addWidget(self.thermal_strip, 0, 0, 1, 2)
        metrics_grid.addWidget(self.technical_strip, 1, 0, 1, 2)
        metrics_grid.setColumnStretch(0, 1)
        metrics_grid.setColumnStretch(1, 1)
        self.readout_grid.addWidget(self.metrics_host, 0, 1)
        self.readout_grid.setColumnStretch(0, 5)
        self.readout_grid.setColumnStretch(1, 7)
        instrument_layout.addWidget(self.readout, 1)

        self.summary_host = QWidget()
        self.summary_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.summary_grid = QGridLayout(self.summary_host)
        self.summary_grid.setContentsMargins(0, 0, 0, 0)
        self.summary_grid.setHorizontalSpacing(8)
        self.summary_grid.setVerticalSpacing(8)
        self.gpu_summary = DashboardMetricTile("GPU", "BC250")
        self.vram_summary = DashboardMetricTile("VRAM", "Not detected")
        self.cores_summary = DashboardCoreSummary()
        for index, item in enumerate(
            (self.gpu_summary, self.vram_summary, self.cores_summary)
        ):
            self.summary_grid.addWidget(item, 0, index)
            self.summary_grid.setColumnStretch(index, 1)
        instrument_layout.addWidget(self.summary_host)

        self.evidence = QFrame()
        self.evidence.setProperty("dashboardEvidence", True)
        evidence_layout = QVBoxLayout(self.evidence)
        evidence_layout.setContentsMargins(16, 14, 16, 14)
        evidence_layout.setSpacing(6)
        evidence_layout.addWidget(_label("GPU configuration", "dashboardCardTitle"))
        evidence_layout.addWidget(self.governor_metric)
        self.gpu_voltage_metric = DashboardMetricTile("GPU voltage", "Not detected")
        live_metrics = QHBoxLayout()
        live_metrics.setContentsMargins(0, 0, 0, 0)
        live_metrics.setSpacing(6)
        live_metrics.addWidget(self.load_metric, 1)
        live_metrics.addWidget(self.gpu_voltage_metric, 1)
        evidence_layout.addLayout(live_metrics)
        self.range_row = DashboardEvidenceRow("Requested range")
        self.accepted_row = DashboardEvidenceRow("Accepted maximum")
        self.evidence_rows = (
            self.range_row,
            self.accepted_row,
        )
        for item in self.evidence_rows:
            evidence_layout.addWidget(item)
        evidence_layout.addStretch(1)
        self.button = QPushButton(tr("Configure Governor"))
        self.button.setProperty("dashboardCardAction", True)
        self.button.clicked.connect(lambda: self.activated.emit("gpu"))
        evidence_layout.addWidget(self.button)

        self.status = PillLabel("Not detected", "gray")
        self.status.hide()
        self._wide = True
        self._content_wide: bool | None = None
        self._reflow(1100)

    def _reflow(self, width: int) -> None:
        # The evidence column has a 270 px minimum width.  Keeping it beside
        # the instrument on a merely medium window leaves the eight-core grid
        # with a narrow two-column layout and a large, visually wasted area in
        # the evidence card.  Stack it below early enough for the core samples
        # to retain a readable four-column grid.
        wide = width >= 980
        if wide == self._wide and self.root.count():
            return
        self._wide = wide
        clear_grid(self.root)
        if wide:
            self.setMinimumHeight(0)
            self.root.addWidget(self.instrument, 0, 0)
            self.root.addWidget(self.evidence, 0, 1)
            self.root.setColumnStretch(0, 1)
            self.evidence.setMinimumWidth(270)
            self.evidence.setMaximumWidth(285)
        else:
            self.setMinimumHeight(0)
            self.evidence.setMinimumWidth(0)
            self.evidence.setMaximumWidth(16_777_215)
            self.root.addWidget(self.instrument, 0, 0)
            self.root.addWidget(self.evidence, 1, 0)
            self.root.setColumnStretch(0, 1)
        self._reflow_content(width)

    def _reflow_content(self, width: int) -> None:
        # Width passed here belongs to the entire hero; reserve the evidence
        # column before choosing the layout of its left-hand instrument.
        content_wide = width >= (980 if self._wide else 620)
        if content_wide == self._content_wide:
            return
        self._content_wide = content_wide
        self.readout_grid.removeWidget(self.metrics_host)
        if content_wide:
            self.readout_grid.addWidget(self.metrics_host, 0, 1)
            self.readout_grid.setColumnStretch(0, 5)
            self.readout_grid.setColumnStretch(1, 7)
        else:
            self.readout_grid.addWidget(self.metrics_host, 1, 0)
            self.readout_grid.setColumnStretch(0, 1)
            self.readout_grid.setColumnStretch(1, 0)
        # The constructor initially creates three summary tiles.  Reset all
        # three columns before the two-column layout so no invisible stretch
        # column can steal the right third of the available width.
        clear_grid(self.summary_grid, reset_columns=3, reset_rows=3)
        if content_wide:
            self.summary_grid.addWidget(self.gpu_summary, 0, 0)
            self.summary_grid.addWidget(self.vram_summary, 0, 1)
            self.summary_grid.addWidget(self.cores_summary, 1, 0, 1, 2)
        else:
            for row, item in enumerate(
                (self.gpu_summary, self.vram_summary, self.cores_summary)
            ):
                self.summary_grid.addWidget(item, row, 0)
        for column in range(2 if content_wide else 1):
            self.summary_grid.setColumnStretch(column, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow(event.size().width())
        self._reflow_content(event.size().width())


class DashboardModuleCard(QFrame):
    activated = pyqtSignal(str)
    action_requested = pyqtSignal(str)

    def __init__(
        self,
        key: str,
        title: str,
        subtitle: str,
        _icon_name: str,
        tone: str,
        headline_unit: str,
        metrics: Iterable[str],
        button_text: str,
        *,
        secondary_action: tuple[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.key = key
        self.setProperty("dashboardModule", True)
        self.setProperty("tone", tone)
        self.setMinimumHeight(0)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 11, 14, 11)
        root.setSpacing(5)

        heading = QHBoxLayout()
        self.heading_layout = heading
        self.heading_icon = QLabel()
        self.heading_icon.setPixmap(icon(_icon_name).pixmap(22, 22))
        self.heading_icon.setFixedSize(24, 24)
        heading.addWidget(self.heading_icon, alignment=Qt.AlignmentFlag.AlignTop)
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        text_box.addWidget(_label(title, "dashboardCardTitle"))
        if subtitle:
            text_box.addWidget(_label(subtitle, "dashboardCardSubtitle"))
        heading.addLayout(text_box, 1)
        self.status = PillLabel("Not detected", "gray")
        heading.addWidget(self.status, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(heading)

        headline = QHBoxLayout()
        headline.setSpacing(5)
        self.headline = _label("--", "dashboardModuleHeadline", wrap=False)
        self.headline_unit = _label(headline_unit, "dashboardModuleUnit", wrap=False)
        headline.addWidget(self.headline)
        headline.addWidget(self.headline_unit, alignment=Qt.AlignmentFlag.AlignBottom)
        headline.addStretch(1)
        root.addLayout(headline)

        self.metric_rows: list[DashboardEvidenceRow] = []
        for metric in metrics:
            item = DashboardEvidenceRow(metric, compact=True)
            self.metric_rows.append(item)
            root.addWidget(item)
        root.addStretch(1)

        self.actions = QGridLayout()
        self.actions.setContentsMargins(0, 2, 0, 0)
        self.actions.setHorizontalSpacing(8)
        self.actions.setVerticalSpacing(7)
        self.primary_button = QPushButton(tr(button_text))
        self.primary_button.setProperty("dashboardCardAction", True)
        self.primary_button.clicked.connect(lambda: self.activated.emit(self.key))
        self.action_buttons = [self.primary_button]
        if secondary_action:
            action_key, action_text = secondary_action
            self.secondary_button = QPushButton(tr(action_text))
            self.secondary_button.setProperty("dashboardCardAction", True)
            self.secondary_button.clicked.connect(
                lambda: self.action_requested.emit(action_key)
            )
            self.action_buttons.append(self.secondary_button)
        else:
            self.secondary_button = None
        self._actions_wide: bool | None = None
        self._reflow_actions(1000)
        root.addLayout(self.actions)

    def set_headline(self, value: str, unit: str | None = None) -> None:
        self.headline.setText(tr(value))
        if unit is not None:
            self.headline_unit.setText(tr(unit))

    def set_metric(self, index: int, value: str) -> None:
        if 0 <= index < len(self.metric_rows):
            self.metric_rows[index].set_value(value)

    def set_metric_label(self, index: int, label: str) -> None:
        if 0 <= index < len(self.metric_rows):
            self.metric_rows[index].label.setText(tr(label))

    def _reflow_actions(self, width: int) -> None:
        # The persistent support rail also needs room on narrow windows. Put
        # translated status badges below the heading instead of clipping them.
        self.heading_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if width < 340
            else QBoxLayout.Direction.LeftToRight
        )
        self.heading_layout.setAlignment(
            self.status, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        wide = len(self.action_buttons) == 1 or width >= 360
        if wide == self._actions_wide and self.actions.count():
            return
        self._actions_wide = wide
        clear_grid(self.actions, reset_columns=2, reset_rows=2)
        for index, button in enumerate(self.action_buttons):
            row, column = (0, index) if wide else (index, 0)
            self.actions.addWidget(button, row, column)
        for column in range(len(self.action_buttons) if wide else 1):
            self.actions.setColumnStretch(column, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow_actions(event.size().width())


class PreparationComponentCard(QFrame):
    def __init__(self, key: str, title: str, detail: str) -> None:
        super().__init__()
        self.key = key
        self.setProperty("dashboardComponentCard", True)
        self.setMinimumWidth(0)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(10)
        self.setMinimumHeight(42)
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
        self.checkbox = QPushButton()
        self.checkbox.setProperty("dashboardComponentCheck", True)
        self.checkbox.setCheckable(True)
        self.checkbox.setFixedSize(26, 26)
        self.checkbox.setAccessibleName(tr(title))
        self.checkbox.setChecked(True)
        self.checkbox.setIconSize(QSize(16, 16))
        self.checkbox.toggled.connect(self._update_check_icon)
        self._update_check_icon(True)
        row.addWidget(self.checkbox, alignment=Qt.AlignmentFlag.AlignVCenter)

    def _update_check_icon(self, checked: bool) -> None:
        self.checkbox.setIcon(icon("check_green") if checked else QIcon())

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
        self.style().unpolish(self)
        self.style().polish(self)


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
        return button

    @staticmethod
    def update_action(
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
        if payload is not None:
            button.request_payload = dict(payload)
        button.setEnabled(enabled)
        button.setVisible(visible)
        button.setToolTip(tr(tooltip) if tooltip else "")

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
            ("Components", "Compatibility", "Decky", "Drivers")
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
        self._memory_controls_wide: str | None = None
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
        layout.addWidget(self.components_host)

        self.memory_panel = QFrame()
        self.memory_panel.setProperty("dashboardMemoryPanel", True)
        memory_layout = QVBoxLayout(self.memory_panel)
        memory_layout.setContentsMargins(12, 10, 12, 10)
        memory_layout.setSpacing(8)
        memory_header = QHBoxLayout()
        self.memory_header = memory_header
        memory_header.addWidget(_label("Memory & Swap", "dashboardComponentTitle"))
        self.memory_detail = _label("Not detected", "dashboardMemoryDetail")
        self.memory_detail.setAlignment(Qt.AlignmentFlag.AlignLeft)
        memory_header.addStretch(1)
        self.memory_scope = PillLabel("Bazzite only", "gray")
        memory_header.addWidget(self.memory_scope)
        memory_layout.addLayout(memory_header)
        memory_layout.addWidget(self.memory_detail)

        controls = QGridLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setHorizontalSpacing(8)
        controls.setVerticalSpacing(10)
        self.memory_swap_label = _label(
            "Swap and compression", "dashboardMemoryControlLabel"
        )
        self.memory_policy_combo = QComboBox()
        self.memory_policy_combo.setProperty("dashboardMemoryCombo", True)
        for label, value in (
            ("Keep Bazzite default (ZRAM)", "current"),
            ("Recommended · ZRAM + 16 GiB emergency swap", "zram-swap-16"),
            ("Advanced · ZSWAP + 16 GiB swapfile", "zswap-16"),
            ("Advanced heavy loads · ZSWAP + 32 GiB swapfile", "zswap-32"),
        ):
            self.memory_policy_combo.addItem(tr(label), value)
        self.memory_swap_apply_button = QPushButton(tr("Apply Swap"))
        self.memory_swap_apply_button.setProperty("dashboardCardAction", True)
        self.memory_swap_apply_button.clicked.connect(self._request_memory_swap)
        self.memory_ttm_label = _label(
            "Dynamic GPU Memory Limit (TTM)", "dashboardMemoryControlLabel"
        )
        self.ttm_limit_combo = QComboBox()
        self.ttm_limit_combo.setProperty("dashboardMemoryCombo", True)
        self.ttm_limit_combo.addItem(tr("Keep current TTM limit"), 0)
        self.ttm_limit_combo.addItem(tr("Kernel default (remove BC250 TTM limit)"), -1)
        for target in (8, 10, 12):
            self.ttm_limit_combo.addItem(
                tr_format("Limit GPU allocations to {size} GiB", size=target), target
            )
        self.memory_ttm_apply_button = QPushButton(tr("Apply TTM"))
        self.memory_ttm_apply_button.setProperty("dashboardCardAction", True)
        self.memory_ttm_apply_button.clicked.connect(self._request_memory_ttm)
        self.memory_controls = controls
        memory_layout.addLayout(controls)
        layout.addWidget(self.memory_panel)
        layout.addStretch(1)
        return page

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
        self.compatibility_detected_badge = PillLabel("Detecting distribution", "gray")
        filter_layout.addWidget(self.compatibility_detected_badge)
        layout.addWidget(self.compatibility_filter_panel)
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
        for label, pill in (
            ("Kernel / AMDGPU", self.steamos_kernel_status),
            ("Mesa / RADV", self.steamos_radv_status),
            ("FSR4 per game", self.steamos_fsr4_status),
        ):
            steamos_state_layout.addWidget(
                _label(label, "dashboardCompatibilityLabel", wrap=False)
            )
            steamos_state_layout.addWidget(pill)
        steamos_state_layout.addStretch(1)
        self.gfx_card.layout().insertWidget(2, self.steamos_graphics_state)
        self.steamos_graphics_state.hide()
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
            dialog.destroyed.connect(
                lambda: setattr(self, "_decky_screenshot_dialog", None)
            )
            self._decky_screenshot_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

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
        tab_columns = 4 if width >= 560 else 2
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
        for button in (self.memory_swap_apply_button, self.memory_ttm_apply_button):
            button.setMinimumWidth(
                min(max(0, (width - 64) // 3), IconButton.sizeHint(button).width())
            )
        self.memory_header.setDirection(
            QBoxLayout.Direction.TopToBottom
            if width < 440
            else QBoxLayout.Direction.LeftToRight
        )
        self.memory_header.setAlignment(self.memory_scope, Qt.AlignmentFlag.AlignLeft)
        component_columns = (
            4 if width >= 1280 else 3 if width >= 980 else 2 if width >= 650 else 1
        )
        if tab_columns != self._tab_columns:
            self._tab_columns = tab_columns
            clear_grid(self.tabs_grid, reset_columns=4, reset_rows=2)
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
        self._reflow_memory_controls(width)

    def _reflow_memory_controls(self, width: int) -> None:
        mode = "paired" if width >= 1100 else "rows" if width >= 660 else "stacked"
        if mode == self._memory_controls_wide:
            return
        self._memory_controls_wide = mode
        clear_grid(self.memory_controls, reset_columns=4, reset_rows=4)
        if mode == "paired":
            for column, (label, combo, button) in enumerate(
                (
                    (
                        self.memory_swap_label,
                        self.memory_policy_combo,
                        self.memory_swap_apply_button,
                    ),
                    (
                        self.memory_ttm_label,
                        self.ttm_limit_combo,
                        self.memory_ttm_apply_button,
                    ),
                )
            ):
                self.memory_controls.addWidget(label, 0, column * 2, 1, 2)
                self.memory_controls.addWidget(combo, 1, column * 2)
                self.memory_controls.addWidget(button, 1, column * 2 + 1)
                self.memory_controls.setColumnStretch(column * 2, 1)
        elif mode == "rows":
            for row, (label, combo, button) in enumerate(
                (
                    (
                        self.memory_swap_label,
                        self.memory_policy_combo,
                        self.memory_swap_apply_button,
                    ),
                    (
                        self.memory_ttm_label,
                        self.ttm_limit_combo,
                        self.memory_ttm_apply_button,
                    ),
                )
            ):
                self.memory_controls.addWidget(label, row, 0)
                self.memory_controls.addWidget(combo, row, 1)
                self.memory_controls.addWidget(button, row, 2)
            self.memory_controls.setColumnStretch(1, 1)
        else:
            for row, (label, combo, button) in enumerate(
                (
                    (
                        self.memory_swap_label,
                        self.memory_policy_combo,
                        self.memory_swap_apply_button,
                    ),
                    (
                        self.memory_ttm_label,
                        self.ttm_limit_combo,
                        self.memory_ttm_apply_button,
                    ),
                )
            ):
                base_row = row * 2
                self.memory_controls.addWidget(label, base_row, 0, 1, 2)
                self.memory_controls.addWidget(combo, base_row + 1, 0)
                self.memory_controls.addWidget(button, base_row + 1, 1)
            self.memory_controls.setColumnStretch(0, 1)

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

    def _update_memory_controls(self, tools: Mapping[str, object]) -> None:
        actionable = is_bazzite_host(tools)
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
        if update_memory_controls(self, tools):
            return
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

    def _forward_dependency_action(self, payload: object) -> None:
        values = dict(payload) if isinstance(payload, Mapping) else {}
        values.setdefault("selected_components", self.selected_components)
        self.dependency_action_requested.emit(values)

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
        actual_label = str(
            self._tools.get("os_label") or labels.get(actual) or tr("Not detected")
        )
        self.compatibility_detected_badge.setText(
            tr_format("Detected: {distribution}", distribution=actual_label)
        )
        self.compatibility_detected_badge.set_tone("blue" if preview else "green")

        self.acpi_card.setVisible(show_all or selected == "arch")
        self.cyan_card.setVisible(True)
        self.oberon_card.setVisible(True)
        self.gfx_card.setVisible(True)
        self.cachyos_stack_card.setVisible(show_all or selected == "arch")
        # SteamOS exposes the same upstream FSR4 profile in the matched stack
        # card, avoiding two independent buttons for one runtime.
        self.fsr4_card.setVisible(show_all or selected != "steamos")

        if not preview:
            return

        self.gfx_card.set_scope(labels.get(selected, "Compatibility preview"), "blue")
        self.gfx_card.set_status("Preview only", "blue")
        preview_copy = {
            "steamos": "SteamOS 3.8/3.9 provides a reviewed two-stage path: install the matching AMDGPU module, reboot, then install the matched Mesa/RADV runtime. FSR4 remains optional per game.",
            "bazzite": "Bazzite is immutable. Direct kernel/Mesa patching is blocked; use a BC-250 image or a matching rpm-ostree package instead.",
            "arch": "Plain Arch and CachyOS can use the matched MastaG kernel/Mesa stack. Manjaro is limited to the experimental ABI-gated FSR4 runtime.",
            "fedora": "Fedora uses DryhoppedIPA's official current GFX1013 workflow. Control Center adds local safety gates, then leaves kernel and Mesa compatibility checks to upstream.",
            "debian": "Ubuntu and Debian currently expose governor and userspace tools; the GFX1013 kernel/Mesa patch remains a manual upstream path.",
            "other": "This distribution can use common governors when its packages are available. Kernel/Mesa compatibility stays manual until a reviewed path exists.",
        }
        self.gfx_card.detail.setText(tr(preview_copy[selected]))
        self.steamos_graphics_state.setVisible(selected == "steamos")
        if selected == "steamos":
            for pill in (
                self.steamos_kernel_status,
                self.steamos_radv_status,
                self.steamos_fsr4_status,
            ):
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
            self.gfx_card.update_action(
                self.gfx_tertiary_button,
                text="3 · Install per-game FSR4",
                payload={"action": "steamos_graphics_fsr4_install", "governor": ""},
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
        gfx = present_gfx1013(gfx_state)
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
            self.gfx_card.update_action(
                self.gfx_tertiary_button,
                text="Update per-game FSR4"
                if fsr4_current
                else "3 · Install per-game FSR4",
                payload={"action": "steamos_graphics_fsr4_install", "governor": ""},
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
                text="Remove FSR4"
                if fsr4_state != "not-installed"
                else "Remove Mesa RADV",
                payload={
                    "action": "steamos_graphics_fsr4_uninstall"
                    if fsr4_state != "not-installed"
                    else "steamos_graphics_uninstall",
                    "governor": "",
                },
                visible=(
                    fsr4_state != "not-installed" or radv_state != "not-installed"
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
                    else "gfx1013_upstream",
                    "governor": "",
                },
            )
            self.gfx_card.update_action(
                self.gfx_quaternary_button,
                text="Open upstream project",
                payload={"action": "gfx1013_upstream", "governor": ""},
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
        fsr4_available = bool(
            fsr4.get("installer_available", fsr4_supported or fsr4_experimental)
        )
        fsr4_installed = bool(fsr4.get("installed"))
        fsr4_current = bool(fsr4.get("current"))
        fsr4_state = str(fsr4.get("state") or "not-installed")
        source_required = bool(fsr4.get("source_build_required"))
        self.fsr4_card.set_scope(
            "Bazzite · Official Podman source build"
            if fsr4_source_supported
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
            else "Source build available"
            if source_required
            else "Available",
            "green" if fsr4_current else "orange" if fsr4_state == "invalid" or fsr4_experimental else "blue",
        )
        version = str(fsr4.get("version") or "V3")
        self.fsr4_card.detail.setText(
            tr(
                f"Official upstream {version} per-game RADV runtime. It stays isolated from system Mesa."
                if fsr4_supported
                else f"Official upstream {version} Arch-style runtime. Manjaro is not claimed upstream; installation proceeds only after strict ABI and Vulkan checks."
                if fsr4_experimental
                else f"Official upstream {version} is compiled in its Fedora 44 container with rootless Podman, then Vulkan-tested on this BC-250. System Mesa is never modified."
                if fsr4_source_supported
                else "This distribution needs the official reproducible Docker source build; no unverified binary is offered."
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
            self.decky_card.detail.setText(
                tr(
                    "Quick Access is ready. Restart Game Mode or reload Decky if the panel is not visible yet."
                    if ready
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


class DashboardFooter(QWidget):
    """Compact external links embedded in the preparation header."""

    contact_clicked = pyqtSignal()
    support_clicked = pyqtSignal()
    repositories_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("dashboardHeaderActions", True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)
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
