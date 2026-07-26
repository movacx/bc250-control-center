from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import theme as theme_module
from ..i18n import localize_widget_tree, tr
from ..theme import COLORS, application_stylesheet, palette_color, semantic_color_key
from .dialogs import center_dialog, enable_adaptive_dialog


ICON_DIR = Path(__file__).resolve().parents[1] / "theme" / "icons"


def icon(name: str) -> QIcon:
    return QIcon(str(ICON_DIR / f"{name}.svg"))


def apply_shadow(widget: QWidget, *, blur: int = 26, y: int = 6, alpha: int = 18) -> None:
    """Apply one restrained enterprise-style elevation effect."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y)
    shadow.setColor(QColor(0, 0, 0, min(90, alpha * 2) if theme_module.ACTIVE_MODE == "dark" else alpha))
    widget.setGraphicsEffect(shadow)


class IconBadge(QFrame):
    def __init__(
        self,
        icon_name: str,
        background: str,
        size: int = 42,
        parent: QWidget | None = None,
        *,
        radius: int | None = None,
    ):
        super().__init__(parent)
        self._icon_name = icon_name
        self._background_source = background
        self._preferred_color = self._infer_color_key(icon_name, background)
        self._corner_radius = size // 2 if radius is None else radius
        self.setFixedSize(size, size)
        layout = QHBoxLayout(self)
        inset = max(8, round(size * 0.22))
        layout.setContentsMargins(inset, inset, inset, inset)
        self.icon_label = QLabel()
        self.icon_label.setPixmap(icon(icon_name).pixmap(size - (inset * 2), size - (inset * 2)))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)
        self._refresh_palette()

    @staticmethod
    def _infer_color_key(icon_name: str, background: object) -> str:
        explicit = semantic_color_key(background)
        if explicit and explicit.endswith("_soft"):
            return explicit
        name = str(icon_name or "").lower()
        for tone in ("purple", "orange", "green", "cyan", "red", "blue"):
            if tone in name:
                return f"{tone}_soft"
        if any(token in name for token in ("gray", "grey", "vram", "power", "refresh", "logs")):
            return "neutral_soft"
        return explicit or "blue_soft"

    def _refresh_palette(self) -> None:
        background = palette_color(self._background_source, self._preferred_color)
        self.setStyleSheet(
            f"background:{background}; border:1px solid {COLORS['icon_border']}; "
            f"border-radius:{self._corner_radius}px;"
        )


class PillLabel(QLabel):
    def __init__(self, text: str, tone: str = "green", parent: QWidget | None = None):
        super().__init__(tr(text), parent)
        self._tone = tone
        self.setProperty("pill", True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._refresh_palette()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API name
        super().setText(tr(text))

    def set_tone(self, tone: str) -> None:
        self._tone = tone
        self._refresh_palette()

    def _refresh_palette(self) -> None:
        tone = self._tone if self._tone in {"green", "blue", "purple", "orange", "red"} else "gray"
        if tone == "gray":
            foreground, background, border = COLORS["muted"], COLORS["neutral_soft"], COLORS["neutral_border"]
        else:
            foreground = COLORS[tone]
            background = COLORS[f"{tone}_soft"]
            border = COLORS[f"{tone}_border"]
        self.setStyleSheet(f"color:{foreground}; background:{background}; border:1px solid {border};")


class MetricCell(QWidget):
    def __init__(self, label: str, value: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        self.label = QLabel(tr(label))
        self.label.setProperty("metricLabel", True)
        self.value = QLabel(tr(value))
        self.value.setProperty("metricValue", True)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.label)
        layout.addWidget(self.value)

    def set_value(self, value: str) -> None:
        self.value.setText(tr(value))

    def set_label(self, label: str) -> None:
        self.label.setText(tr(label))


class ModuleCard(QFrame):
    activated = pyqtSignal(str)

    def __init__(
        self,
        key: str,
        title: str,
        icon_name: str,
        icon_background: str,
        status: str,
        status_tone: str,
        metrics: Iterable[tuple[str, str]],
        button_text: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.key = key
        self.setProperty("card", True)
        self.setProperty("moduleCard", True)
        self.setMinimumHeight(292)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        apply_shadow(self, blur=22, y=4, alpha=18)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(22, 20, 22, 19)
        root.setSpacing(16)
        outer.addWidget(body, 1)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(IconBadge(icon_name, icon_background, 42, radius=12))
        title_label = QLabel(tr(title))
        title_label.setProperty("cardTitle", True)
        title_label.setWordWrap(True)
        title_label.setMinimumWidth(0)
        header.addWidget(title_label)
        header.addStretch(1)
        self.status = PillLabel(tr(status), status_tone)
        header.addWidget(self.status)
        root.addLayout(header)

        divider = QFrame()
        divider.setObjectName("CardDivider")
        divider.setFixedHeight(1)
        root.addWidget(divider)

        self.metrics_layout = QGridLayout()
        self.metrics_layout.setContentsMargins(0, 3, 0, 0)
        self.metrics_layout.setHorizontalSpacing(26)
        self.metrics_layout.setVerticalSpacing(18)
        self.metric_cells: list[MetricCell] = []
        for index, (label, value) in enumerate(metrics):
            cell = MetricCell(label, value)
            self.metric_cells.append(cell)
            self.metrics_layout.addWidget(cell, index // 2, index % 2)
        self.metrics_layout.setColumnStretch(0, 1)
        self.metrics_layout.setColumnStretch(1, 1)
        root.addLayout(self.metrics_layout)
        root.addStretch(1)

        self._progress_color_source: str | None = None
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        root.addWidget(self.progress)

        self.button = QPushButton(tr(button_text))
        self.button.setProperty("cardAction", True)
        self.button.setMinimumHeight(38)
        self.button.setIcon(icon("chevron_right_gray"))
        self.button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.clicked.connect(lambda: self.activated.emit(self.key))
        root.addWidget(self.button)

    def set_progress(self, value: int, color: str | None = None) -> None:
        self.progress.show()
        self.progress.setValue(max(0, min(100, value)))
        if color is not None:
            self._progress_color_source = color
        self._refresh_palette()

    def _refresh_palette(self) -> None:
        if self._progress_color_source:
            color = palette_color(self._progress_color_source, "blue")
            self.progress.setStyleSheet(
                f"QProgressBar{{background:{COLORS['progress_track']};border:none;border-radius:4px;min-height:7px;max-height:7px;}}"
                f"QProgressBar::chunk{{background:{color};border-radius:4px;}}"
            )

    def set_metric(self, index: int, value: str) -> None:
        if 0 <= index < len(self.metric_cells):
            self.metric_cells[index].set_value(value)

    def set_metric_label(self, index: int, label: str) -> None:
        if 0 <= index < len(self.metric_cells):
            self.metric_cells[index].set_label(label)


class ReadinessRow(QWidget):
    def __init__(self, text: str, ready: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.text = text
        self._ready = bool(ready)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(8)
        marker_wrap = QFrame()
        marker_wrap.setObjectName("ReadinessMarker")
        marker_wrap.setFixedSize(26, 26)
        marker_layout = QHBoxLayout(marker_wrap)
        marker_layout.setContentsMargins(5, 5, 5, 5)
        self.marker = QLabel()
        self.marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marker_layout.addWidget(self.marker)
        self.label = QLabel(tr(text))
        self.label.setProperty("rowLabel", True)
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(0)
        self.state = QLabel()
        self.state.setProperty("readinessState", True)
        layout.addWidget(marker_wrap)
        layout.addWidget(self.label)
        layout.addStretch(1)
        layout.addWidget(self.state)
        self.set_ready(ready)

    def set_ready(self, ready: bool) -> None:
        self._ready = bool(ready)
        self.marker.setPixmap(icon("check_green" if self._ready else "warning_orange").pixmap(15, 15))
        self.state.setText(tr("Operational" if self._ready else "Attention"))
        self._refresh_palette()

    def _refresh_palette(self) -> None:
        self.state.setStyleSheet(
            f"color:{COLORS['green'] if self._ready else COLORS['orange']}; font-weight:750;"
        )


class ReadinessCard(QFrame):
    prepare_clicked = pyqtSignal()

    def __init__(self, rows: Iterable[tuple[str, bool]], parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("sectionCard", True)
        self.setMinimumHeight(274)
        apply_shadow(self, blur=20, y=4, alpha=16)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(22, 20, 22, 18)
        self.layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(IconBadge("shield_green", COLORS["green_soft"], 42, radius=12))
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        title = QLabel(tr("System Readiness"))
        title.setProperty("cardTitle", True)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("ReadinessSubtitle")
        text_box.addWidget(title)
        text_box.addWidget(self.subtitle)
        header.addLayout(text_box)
        header.addStretch(1)
        self.layout.addLayout(header)

        self.rows_host = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setContentsMargins(0, 3, 0, 2)
        self.rows_layout.setSpacing(0)
        self.layout.addWidget(self.rows_host)
        self.rows: list[ReadinessRow] = []
        self._all_ready = False

        self.layout.addStretch(1)
        button = QPushButton(tr("Prepare Dependencies"))
        button.setProperty("cardAction", True)
        button.setIcon(icon("download_blue"))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(self.prepare_clicked)
        self.layout.addWidget(button)
        self.set_rows(rows)

    def set_rows(self, rows: Iterable[tuple[str, bool]]) -> None:
        values = list(rows)
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.rows.clear()
        self._all_ready = all(ready for _, ready in values)
        self.subtitle.setText(tr("All critical services operational" if self._all_ready else "Review required components"))
        self._refresh_palette()
        for index, (text, ready) in enumerate(values):
            row = ReadinessRow(text, ready)
            self.rows.append(row)
            self.rows_layout.addWidget(row)
            if index < len(values) - 1:
                divider = QFrame()
                divider.setObjectName("ListDivider")
                divider.setFixedHeight(1)
                self.rows_layout.addWidget(divider)

    def _refresh_palette(self) -> None:
        self.subtitle.setStyleSheet(
            f"color:{COLORS['green'] if self._all_ready else COLORS['orange']}; font-weight:700;"
        )



class QuickActionButton(QFrame):
    clicked = pyqtSignal()

    def __init__(self, title: str, subtitle: str, icon_name: str, tone: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("quickActionRow", True)
        self.setProperty("hovered", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(58)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(11)
        soft = {
            "blue": COLORS["blue_soft"],
            "orange": COLORS["orange_soft"],
            "gray": "neutral_soft",
        }.get(tone, COLORS["blue_soft"])
        row.addWidget(IconBadge(icon_name, soft, 36, radius=10))
        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        title_label = QLabel(tr(title))
        title_label.setProperty("actionTitle", True)
        title_label.setWordWrap(True)
        title_label.setMinimumWidth(0)
        subtitle_label = QLabel(tr(subtitle))
        subtitle_label.setProperty("actionSubtitle", True)
        subtitle_label.setWordWrap(True)
        subtitle_label.setMinimumWidth(0)
        text_box.addWidget(title_label)
        text_box.addWidget(subtitle_label)
        row.addLayout(text_box, 1)
        arrow = QLabel()
        arrow.setPixmap(icon("chevron_right_gray").pixmap(16, 16))
        row.addWidget(arrow)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.setProperty("hovered", True)
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.setProperty("hovered", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)

    def gamepad_activate(self) -> None:
        self.clicked.emit()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class QuickActionsCard(QFrame):
    action_clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("sectionCard", True)
        self.setMinimumHeight(274)
        apply_shadow(self, blur=20, y=4, alpha=16)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(9)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(IconBadge("bolt_blue", COLORS["blue_soft"], 42, radius=12))
        heading = QVBoxLayout()
        heading.setSpacing(2)
        title = QLabel(tr("Quick Actions"))
        title.setProperty("cardTitle", True)
        subtitle = QLabel(tr("Common controls and diagnostics"))
        subtitle.setProperty("sectionSubtitle", True)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch(1)
        layout.addLayout(header)

        actions = [
            ("apply_profile", "Apply CPU Profile", "Activate the current safe tuning profile", "rocket_blue", "blue"),
            ("prepare_pwm", "Prepare Fan PWM", "Initialize Pump Fan J4003 control", "fan_orange", "orange"),
            ("open_logs", "Open Logs", "Review events and system diagnostics", "logs_gray", "gray"),
        ]
        for key, title_text, subtitle_text, icon_name, tone in actions:
            button = QuickActionButton(title_text, subtitle_text, icon_name, tone)
            button.clicked.connect(lambda action=key: self.action_clicked.emit(action))
            layout.addWidget(button)
        layout.addStretch(1)


class ActivityRow(QWidget):
    def __init__(self, activity, parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 7, 0, 7)
        row.setSpacing(10)
        self.dot = QFrame()
        self.dot.setFixedSize(9, 9)
        self._tone = "green" if activity.level not in {"warning", "error", "critical"} else "orange"
        self._refresh_palette()
        text = QLabel(tr(activity.title))
        text.setProperty("activityText", True)
        text.setWordWrap(True)
        text.setMinimumWidth(0)
        when = QLabel(tr(activity.when))
        when.setProperty("activityTime", True)
        row.addWidget(self.dot)
        row.addWidget(text, 1)
        row.addWidget(when)

    def _refresh_palette(self) -> None:
        self.dot.setStyleSheet(f"background:{COLORS[self._tone]}; border:none; border-radius:4px;")



class ActivityCard(QFrame):
    view_all_clicked = pyqtSignal()

    def __init__(self, activities, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("sectionCard", True)
        self.setMinimumHeight(274)
        apply_shadow(self, blur=20, y=4, alpha=16)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(22, 20, 22, 18)
        self.root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(IconBadge("activity_purple", COLORS["purple_soft"], 42, radius=12))
        heading = QVBoxLayout()
        heading.setSpacing(2)
        title = QLabel(tr("Recent Activity"))
        title.setProperty("cardTitle", True)
        subtitle = QLabel(tr("Latest hardware and service events"))
        subtitle.setProperty("sectionSubtitle", True)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch(1)
        view_all = QPushButton(tr("View All"))
        view_all.setProperty("compactAction", True)
        view_all.setIcon(icon("chevron_right_gray"))
        view_all.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        view_all.setCursor(Qt.CursorShape.PointingHandCursor)
        view_all.clicked.connect(self.view_all_clicked)
        header.addWidget(view_all)
        self.root.addLayout(header)

        self.activities_host = QWidget()
        self.activities_layout = QVBoxLayout(self.activities_host)
        self.activities_layout.setContentsMargins(0, 2, 0, 0)
        self.activities_layout.setSpacing(0)
        self.root.addWidget(self.activities_host)
        self.root.addStretch(1)
        self.set_activities(activities)

    def set_activities(self, activities) -> None:
        while self.activities_layout.count():
            item = self.activities_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        values = list(activities)[:5]
        if not values:
            empty = QLabel(tr("No recent activity"))
            empty.setProperty("sectionSubtitle", True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self.activities_layout.addWidget(empty)
            return
        for index, activity in enumerate(values):
            self.activities_layout.addWidget(ActivityRow(activity))
            if index < len(values) - 1:
                divider = QFrame()
                divider.setObjectName("ListDivider")
                divider.setFixedHeight(1)
                self.activities_layout.addWidget(divider)


class SummaryMetric(QWidget):
    """One compact item in the Dashboard hardware summary bar."""

    def __init__(self, icon_name: str, label: str, value: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(12)
        row.addWidget(IconBadge(icon_name, "neutral_soft", 36, radius=10))

        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        self.label = QLabel(tr(label))
        self.label.setObjectName("SummaryLabel")
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(0)
        self.value = QLabel(tr(value))
        self.value.setObjectName("SummaryValue")
        self.value.setWordWrap(True)
        self.value.setMinimumWidth(0)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_box.addWidget(self.label)
        text_box.addWidget(self.value)
        row.addLayout(text_box, 1)

    def set_value(self, value: str) -> None:
        self.value.setText(tr(value))

    def set_label(self, label: str) -> None:
        self.label.setText(tr(label))


class SystemSummaryBar(QFrame):
    """Hardware summary strip that reflows from four columns down to one."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SystemSummaryBar")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        apply_shadow(self, blur=18, y=3, alpha=14)

        self.layout_grid = QGridLayout(self)
        self.layout_grid.setContentsMargins(16, 10, 16, 10)
        self.layout_grid.setHorizontalSpacing(10)
        self.layout_grid.setVerticalSpacing(8)

        self.gpu = SummaryMetric("gpu_gray", "GPU", "BC250")
        self.vram = SummaryMetric("vram_gray", "VRAM", "Not detected")
        self.power = SummaryMetric("power_gray", "Board power", "Not detected")
        self.uptime = SummaryMetric("uptime_gray", "Uptime", "Not detected")
        self.items = [self.gpu, self.vram, self.power, self.uptime]
        self._columns = 0
        self._reflow(1200)

    def _reflow(self, width: int) -> None:
        columns = 4 if width >= 980 else 2 if width >= 520 else 1
        if columns == self._columns and self.layout_grid.count():
            return
        self._columns = columns
        while self.layout_grid.count():
            # Preserve parentage so the metrics do not blink while moving to a
            # new row during a live window resize.
            self.layout_grid.takeAt(0)
        for index, item in enumerate(self.items):
            self.layout_grid.addWidget(item, index // columns, index % columns)
        for column in range(4):
            self.layout_grid.setColumnStretch(column, 1 if column < columns else 0)
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._reflow(event.size().width())

    def set_values(
        self,
        *,
        gpu: str,
        vram: str,
        power: str,
        uptime: str,
        power_label: str = "SoC package power",
        power_tooltip: str = "",
    ) -> None:
        self.gpu.set_value(gpu)
        self.vram.set_value(vram)
        self.power.set_label(power_label)
        self.power.set_value(power)
        self.power.setToolTip(tr(power_tooltip) if power_tooltip else "")
        self.uptime.set_value(uptime)


class InfoDialog(QDialog):
    """Compact frameless modal used by the control center.

    The dialog deliberately avoids the native KDE title bar and the nested
    panel-within-a-window appearance.
    """

    def __init__(
        self,
        title: str,
        message: str,
        icon_name: str = "info_blue",
        parent: QWidget | None = None,
        *,
        eyebrow: str = "CONTROL CENTER",
        button_text: str = "Close",
        notice: str = "No hardware changes will be made.",
        tone: str = "blue",
    ):
        title = tr(title)
        message = tr(message)
        eyebrow = tr(eyebrow)
        button_text = tr(button_text)
        notice = tr(notice)
        super().__init__(parent)
        self.setObjectName("InfoDialog")
        self.setModal(True)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(application_stylesheet())
        enable_adaptive_dialog(self, preferred_width=560, minimum_width=380, minimum_height=220)

        tones = {
            "blue": (COLORS["blue"], COLORS["blue_soft"]),
            "purple": (COLORS["purple"], COLORS["purple_soft"]),
            "orange": (COLORS["orange"], COLORS["orange_soft"]),
            "green": (COLORS["green"], COLORS["green_soft"]),
            "red": (COLORS["red"], COLORS["red_soft"]),
            "gray": (COLORS["muted"], COLORS["neutral_soft"]),
        }
        accent, soft = tones.get(tone, tones["blue"])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)

        card = QFrame()
        card.setObjectName("ControlDialogCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(20, 33, 61, 55))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(13)
        header.addWidget(IconBadge(icon_name, soft, 44))

        heading = QVBoxLayout()
        heading.setSpacing(2)
        eyebrow_label = QLabel(eyebrow)
        eyebrow_label.setObjectName("DialogEyebrow")
        eyebrow_label.setWordWrap(True)
        eyebrow_label.setStyleSheet(f"color:{accent};")
        title_label = QLabel(tr(title))
        title_label.setObjectName("DialogTitle")
        title_label.setWordWrap(True)
        heading.addWidget(eyebrow_label)
        heading.addWidget(title_label)
        header.addLayout(heading, 1)

        close_button = QPushButton()
        close_button.setObjectName("DialogClose")
        close_button.setIcon(icon("close_gray"))
        close_button.setFixedSize(34, 34)
        close_button.setToolTip(tr("Close"))
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.reject)
        header.addWidget(close_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background:{COLORS['border_soft']}; border:none;")
        layout.addWidget(divider)

        content_scroll = QScrollArea()
        content_scroll.setObjectName("DialogContentScroll")
        content_scroll.setWidgetResizable(True)
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content_scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        content_scroll.setMinimumHeight(84)
        content_scroll.setMaximumHeight(420)
        content = QWidget()
        content.setObjectName("DialogContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        body = QLabel(message)
        body.setObjectName("DialogBody")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_layout.addWidget(body)

        if notice:
            notice_frame = QFrame()
            notice_frame.setObjectName("DialogNotice")
            notice_layout = QHBoxLayout(notice_frame)
            notice_layout.setContentsMargins(12, 10, 12, 10)
            notice_layout.setSpacing(9)
            notice_icon = QLabel()
            notice_icon.setPixmap(icon("info_blue").pixmap(18, 18))
            notice_text = QLabel(notice)
            notice_text.setObjectName("DialogNoticeText")
            notice_text.setWordWrap(True)
            notice_layout.addWidget(notice_icon, 0, Qt.AlignmentFlag.AlignTop)
            notice_layout.addWidget(notice_text, 1)
            content_layout.addWidget(notice_frame)

        content_scroll.setWidget(content)
        layout.addWidget(content_scroll)

        footer = QHBoxLayout()
        footer.addStretch(1)
        primary = QPushButton(button_text)
        primary.setObjectName("DialogPrimary")
        primary.setMinimumWidth(132)
        primary.setDefault(True)
        primary.setAutoDefault(True)
        primary.setCursor(Qt.CursorShape.PointingHandCursor)
        primary.clicked.connect(self.accept)
        footer.addWidget(primary)
        layout.addLayout(footer)

        localize_widget_tree(self)
        self.fit_to_content()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        self.fit_to_content()
        center_dialog(self)
