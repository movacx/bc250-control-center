from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QThread,
    QTimer,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..components.async_tools import AsyncRefresh, BackgroundExecutor
from ..components.dialogs import center_dialog, enable_adaptive_dialog, reflow_wrapped_labels
from ..components.responsive import clear_grid, configure_responsive_scroll_area, effective_viewport_width
from ..components.page_widgets import (
    ControlPageHeader,
    ConfirmDialog,
    PresetButton,
    SectionCard,
    SliderControl,
    StatusLine,
)
from ..i18n import localize_widget_tree, tr, tr_format
from ..core.state import state_cache_for
from ..theme import COLORS, application_stylesheet, scale_stylesheet
from ..components.widgets import IconBadge, InfoDialog, icon


VISIBLE_PWM_ORDER = (2, 1, 3)
CURVE_PRESETS = {
    "silent": ((50, 45), (65, 70), (75, 100)),
    "balanced": ((50, 60), (65, 85), (72, 100)),
    "cool": ((45, 70), (60, 90), (68, 100)),
}

def fans_stylesheet() -> str:
    c = COLORS
    return scale_stylesheet(f"""
QWidget#FansWorkspace QFrame[thermalRail='true'] {{
    background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 18px;
}}
QWidget#FansWorkspace QFrame[thermalMetric='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 12px;
}}
QWidget#FansWorkspace QFrame[thermalMetric='true']:hover {{
    background: {c['control_hover']}; border-color: {c['border']};
}}
QWidget#FansWorkspace QLabel[thermalMetricLabel='true'] {{ color: {c['muted']}; font-size: 10px; font-weight: 700; }}
QWidget#FansWorkspace QLabel[thermalMetricValue='true'] {{ color: {c['text']}; font-size: 18px; font-weight: 830; }}
QWidget#FansWorkspace QLabel[thermalMetricDetail='true'] {{ color: {c['subtle']}; font-size: 9px; }}
QWidget#FansWorkspace QFrame[fanDutyConsole='true'] {{
    background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 16px;
}}
QWidget#FansWorkspace QFrame[fanDutyStage='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 12px;
}}
QWidget#FansWorkspace QLabel[fanConsoleKicker='true'] {{ color: {c['blue']}; font-size: 9px; font-weight: 850; letter-spacing: 1px; }}
QWidget#FansWorkspace QLabel[fanConsoleTitle='true'] {{ color: {c['text']}; font-size: 15px; font-weight: 800; }}
QWidget#FansWorkspace QLabel[fanConsoleMeta='true'] {{ color: {c['muted']}; font-size: 10px; }}
QWidget#FansWorkspace QFrame[fanTelemetryReadout='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 13px;
}}
QWidget#FansWorkspace QLabel[fanTelemetryLabel='true'] {{ color: {c['muted']}; font-size: 10px; font-weight: 700; }}
QWidget#FansWorkspace QLabel[fanTelemetryValue='true'] {{ color: {c['text']}; font-size: 22px; font-weight: 850; }}
QWidget#FansWorkspace QLabel[fanTelemetryDetail='true'] {{ color: {c['subtle']}; font-size: 9px; }}
QWidget#FansWorkspace QFrame[curveStage='true'] {{
    background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 15px;
}}
QWidget#FansWorkspace QFrame[curveControlPanel='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 15px;
}}
QWidget#FansWorkspace QFrame[curvePointV2='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 11px;
}}
QWidget#FansWorkspace QLabel[curvePointIndex='true'] {{
    background: {c['purple_soft']}; color: {c['purple']}; border: 1px solid {c['purple_border']};
    border-radius: 8px; padding: 4px 7px; font-size: 9px; font-weight: 850;
}}
QWidget#FansWorkspace QLabel[curvePointTitle='true'] {{ color: {c['text']}; font-size: 12px; font-weight: 780; }}
QWidget#FansWorkspace QFrame[driverModeBanner='true'] {{
    background: {c['green_soft']}; border: 1px solid {c['green_border']}; border-radius: 12px;
}}
QWidget#FansWorkspace QLabel[driverModeValue='true'] {{ color: {c['text']}; font-size: 16px; font-weight: 830; }}
QWidget#FansWorkspace QLabel[driverModeDetail='true'] {{ color: {c['muted']}; font-size: 10px; }}
QWidget#FansWorkspace QFrame[fanChannelRowV2='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 12px;
}}
QWidget#FansWorkspace QFrame[fanChannelRowV2='true']:hover {{
    background: {c['control_hover']}; border-color: {c['border']};
}}
QWidget#FansWorkspace QLabel[fanChannelTitle='true'] {{ color: {c['text']}; font-size: 12px; font-weight: 790; }}
QWidget#FansWorkspace QLabel[fanChannelDetail='true'] {{ color: {c['muted']}; font-size: 9px; }}
QWidget#FansWorkspace QLabel[fanChannelValue='true'] {{ color: {c['text']}; font-size: 12px; font-weight: 790; }}
QWidget#FansWorkspace QLabel[fanColumnLabel='true'] {{ color: {c['subtle']}; font-size: 9px; font-weight: 800; letter-spacing: .5px; }}
QWidget#FansWorkspace QLabel[fanAccess='write'] {{
    background: {c['green_soft']}; color: {c['green']}; border: 1px solid {c['green_border']};
    border-radius: 8px; padding: 4px 7px; font-size: 9px; font-weight: 800;
}}
QWidget#FansWorkspace QLabel[fanAccess='admin'] {{
    background: {c['orange_soft']}; color: {c['orange']}; border: 1px solid {c['orange_border']};
    border-radius: 8px; padding: 4px 7px; font-size: 9px; font-weight: 800;
}}
QWidget#FansWorkspace QLabel[fanAccess='read'] {{
    background: {c['blue_soft']}; color: {c['blue']}; border: 1px solid {c['blue_border']};
    border-radius: 8px; padding: 4px 7px; font-size: 9px; font-weight: 800;
}}
QWidget#FansWorkspace QLabel[fanAccess='off'] {{
    background: {c['neutral_soft']}; color: {c['subtle']}; border: 1px solid {c['neutral_border']};
    border-radius: 8px; padding: 4px 7px; font-size: 9px; font-weight: 800;
}}
""")



def _dict(value) -> dict:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    try:
        return dict(value or {})
    except Exception:
        return {}


def _integer(value, default=0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _number(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _pwm_to_percent(value) -> int | None:
    if value is None:
        return None
    return max(0, min(100, round(_integer(value) * 100 / 255)))


def _percent_to_pwm(value) -> int:
    return max(0, min(255, round(_integer(value) * 255 / 100)))


class FanTask(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, operation: Callable[[], object], parent: QWidget | None = None):
        super().__init__(parent)
        self.operation = operation

    def run(self) -> None:
        try:
            self.succeeded.emit(self.operation())
        except Exception as error:  # pragma: no cover - hardware/authentication path
            self.failed.emit(str(error))


class ThermalMetricItem(QFrame):
    def __init__(self, label: str, value: str, detail: str, icon_name: str, background: str, parent=None):
        super().__init__(parent)
        self.setProperty("thermalMetric", True)
        self.setMinimumHeight(76)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        row.addWidget(IconBadge(icon_name, background, 32, radius=9), 0, Qt.AlignmentFlag.AlignTop)
        copy = QVBoxLayout()
        copy.setSpacing(0)
        label_widget = QLabel(tr(label))
        label_widget.setProperty("thermalMetricLabel", True)
        self.value = QLabel(tr(value))
        self.value.setProperty("thermalMetricValue", True)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail = QLabel(tr(detail))
        self.detail.setProperty("thermalMetricDetail", True)
        self.detail.setWordWrap(True)
        copy.addWidget(label_widget)
        copy.addWidget(self.value)
        copy.addWidget(self.detail)
        row.addLayout(copy, 1)

    def set_values(self, value: str, detail: str | None = None) -> None:
        self.value.setText(tr(value))
        if detail is not None:
            self.detail.setText(tr(detail))


class ThermalStatusRail(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("thermalRail", True)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        self.items = [
            ThermalMetricItem("Pump fan", "-- RPM", "Pump Fan / J4003", "fan_cyan", COLORS["cyan_soft"]),
            ThermalMetricItem("Selected duty", "-- %", "staged PWM channel", "fans_blue", COLORS["blue_soft"]),
            ThermalMetricItem("GPU temperature", "-- °C", "curve input", "warning_orange", COLORS["orange_soft"]),
            ThermalMetricItem("Control mode", "Checking", "NCT hwmon access", "settings_blue", COLORS["blue_soft"]),
            ThermalMetricItem("Kernel driver", "--", "active NCT module", "shield_green", COLORS["green_soft"]),
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


class DutyGauge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._display_value = 0.0
        self.setMinimumSize(190, 190)
        self.setMaximumHeight(230)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.animation = QPropertyAnimation(self, b"displayValue", self)
        self.animation.setDuration(260)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_display_value(self) -> float:
        return self._display_value

    def _set_display_value(self, value: float) -> None:
        self._display_value = max(0.0, min(100.0, float(value)))
        self.update()

    displayValue = pyqtProperty(float, _get_display_value, _set_display_value)

    def setValue(self, value: int, *, animate: bool = True) -> None:
        target = max(0.0, min(100.0, float(value)))
        if not animate:
            self.animation.stop()
            self._set_display_value(target)
            return
        self.animation.stop()
        self.animation.setStartValue(self._display_value)
        self.animation.setEndValue(target)
        self.animation.start()

    def paintEvent(self, event) -> None:  # pragma: no cover - visual rendering
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        side = min(self.width(), self.height())
        rect = QRectF((self.width() - side) / 2 + 18, (self.height() - side) / 2 + 18, side - 36, side - 36)
        pen = QPen(QColor(COLORS["progress_track"]), 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 225 * 16, -270 * 16)
        active = QColor(COLORS["cyan"] if self._display_value < 75 else COLORS["orange"])
        pen.setColor(active)
        painter.setPen(pen)
        painter.drawArc(rect, 225 * 16, int(-270 * 16 * self._display_value / 100.0))
        painter.setPen(QColor(COLORS["text"]))
        value_font = painter.font()
        value_font.setPointSize(24)
        value_font.setWeight(800)
        painter.setFont(value_font)
        painter.drawText(rect.adjusted(0, 8, 0, -12), Qt.AlignmentFlag.AlignCenter, f"{int(round(self._display_value))}%")


class TelemetryReadout(QFrame):
    def __init__(self, label: str, value: str, detail: str, icon_name: str, background: str, parent=None):
        super().__init__(parent)
        self.setProperty("fanTelemetryReadout", True)
        self.setMinimumHeight(104)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 12, 13, 12)
        layout.setSpacing(5)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(IconBadge(icon_name, background, 30, radius=8))
        title = QLabel(tr(label))
        title.setProperty("fanTelemetryLabel", True)
        top.addWidget(title)
        top.addStretch(1)
        layout.addLayout(top)
        self.value = QLabel(tr(value))
        self.value.setProperty("fanTelemetryValue", True)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail = QLabel(tr(detail))
        self.detail.setProperty("fanTelemetryDetail", True)
        self.detail.setWordWrap(True)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_values(self, value: str, detail: str | None = None) -> None:
        self.value.setText(tr(value))
        if detail is not None:
            self.detail.setText(tr(detail))


class CurvePoint(QFrame):
    changed = pyqtSignal()

    def __init__(self, title: str, temperature: int, speed: int, parent=None):
        super().__init__(parent)
        self.setProperty("curvePointV2", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QHBoxLayout(self)
        row.setContentsMargins(11, 9, 11, 9)
        row.setSpacing(9)
        index = title.split()[-1]
        marker = QLabel(index)
        marker.setProperty("curvePointIndex", True)
        marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marker.setFixedWidth(28)
        row.addWidget(marker)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        label = QLabel(tr(title))
        label.setProperty("curvePointTitle", True)
        hint = QLabel(tr("threshold / duty"))
        hint.setProperty("fieldHint", True)
        copy.addWidget(label)
        copy.addWidget(hint)
        row.addLayout(copy, 1)
        self.temperature = QSpinBox()
        self.temperature.setRange(30, 95)
        self.temperature.setSuffix(" °C")
        self.temperature.setValue(int(temperature))
        self.temperature.setMinimumWidth(88)
        self.speed = QSpinBox()
        self.speed.setRange(0, 100)
        self.speed.setSuffix(" %")
        self.speed.setValue(int(speed))
        self.speed.setMinimumWidth(82)
        row.addWidget(self.temperature)
        row.addWidget(self.speed)
        self.temperature.valueChanged.connect(lambda _value: self.changed.emit())
        self.speed.valueChanged.connect(lambda _value: self.changed.emit())

    def values(self) -> tuple[int, int]:
        return self.temperature.value(), self.speed.value()

    def set_values(self, temperature: int, speed: int) -> None:
        self.temperature.blockSignals(True)
        self.speed.blockSignals(True)
        self.temperature.setValue(int(temperature))
        self.speed.setValue(int(speed))
        self.temperature.blockSignals(False)
        self.speed.blockSignals(False)


class FanCurvePlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = [(50, 70), (65, 100), (70, 100)]
        self.live_temperature: float | None = None
        self.live_duty: int | None = None
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_curve(self, points: list[tuple[int, int]]) -> None:
        self.points = sorted(points, key=lambda item: item[0])
        self.update()

    def set_live(self, temperature: float | None, duty: int | None) -> None:
        self.live_temperature = temperature
        self.live_duty = duty
        self.update()

    def paintEvent(self, event) -> None:  # pragma: no cover - visual rendering
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        left, top, right, bottom = 42.0, 24.0, 24.0, 36.0
        plot = QRectF(left, top, max(40.0, self.width() - left - right), max(40.0, self.height() - top - bottom))
        painter.setPen(QPen(QColor(COLORS["chart_grid"]), 1))
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = plot.bottom() - plot.height() * fraction
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        painter.setPen(QColor(COLORS["subtle"]))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(QRectF(0, plot.top() - 6, 36, 18), Qt.AlignmentFlag.AlignRight, "100%")
        painter.drawText(QRectF(0, plot.center().y() - 8, 36, 18), Qt.AlignmentFlag.AlignRight, "50%")
        painter.drawText(QRectF(0, plot.bottom() - 10, 36, 18), Qt.AlignmentFlag.AlignRight, "0%")
        painter.drawText(QRectF(plot.left(), plot.bottom() + 8, 44, 18), Qt.AlignmentFlag.AlignLeft, "30 °C")
        painter.drawText(QRectF(plot.right() - 44, plot.bottom() + 8, 44, 18), Qt.AlignmentFlag.AlignRight, "95 °C")

        def x_for(temp: float) -> float:
            return plot.left() + (max(30.0, min(95.0, temp)) - 30.0) / 65.0 * plot.width()

        def y_for(duty: float) -> float:
            return plot.bottom() - max(0.0, min(100.0, duty)) / 100.0 * plot.height()

        points = sorted(self.points, key=lambda item: item[0])
        path = QPainterPath(QPointF(plot.left(), y_for(points[0][1])))
        previous_duty = points[0][1]
        for temp, duty in points:
            x = x_for(temp)
            path.lineTo(x, y_for(previous_duty))
            path.lineTo(x, y_for(duty))
            previous_duty = duty
        path.lineTo(plot.right(), y_for(previous_duty))
        painter.setPen(QPen(QColor(COLORS["purple"]), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
        for temp, duty in points:
            center = QPointF(x_for(temp), y_for(duty))
            painter.setBrush(QColor(COLORS["panel_raised"]))
            painter.setPen(QPen(QColor(COLORS["purple"]), 3))
            painter.drawEllipse(center, 5.5, 5.5)
        if self.live_temperature is not None:
            live_x = x_for(self.live_temperature)
            duty = self.live_duty if self.live_duty is not None else points[0][1]
            painter.setPen(QPen(QColor(COLORS["blue"]), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(live_x, plot.top()), QPointF(live_x, plot.bottom()))
            painter.setBrush(QColor(COLORS["blue"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(live_x, y_for(duty)), 5.0, 5.0)


class FanChannelRow(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("fanChannelRowV2", True)
        self.setMinimumHeight(66)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(11, 8, 11, 8)
        row.setSpacing(10)
        row.addWidget(IconBadge("fan_cyan", COLORS["cyan_soft"], 34, radius=9))
        copy = QVBoxLayout()
        copy.setSpacing(1)
        self.title = QLabel("PWM --")
        self.title.setProperty("fanChannelTitle", True)
        self.detail = QLabel("No channel detected")
        self.detail.setProperty("fanChannelDetail", True)
        copy.addWidget(self.title)
        copy.addWidget(self.detail)
        row.addLayout(copy, 1)
        self.rpm = QLabel("-- RPM")
        self.rpm.setProperty("fanChannelValue", True)
        self.rpm.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.rpm.setMinimumWidth(88)
        row.addWidget(self.rpm)
        self.duty = QLabel("-- %")
        self.duty.setProperty("fanChannelValue", True)
        self.duty.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.duty.setMinimumWidth(58)
        row.addWidget(self.duty)
        self.access = QLabel("Unavailable")
        self.access.setProperty("fanAccess", "off")
        self.access.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.access.setMinimumWidth(96)
        row.addWidget(self.access)

    def set_channel(self, channel: dict | None) -> None:
        if not channel:
            self.title.setText("PWM --")
            self.detail.setText("No channel detected")
            self.rpm.setText("-- RPM")
            self.duty.setText("-- %")
            self._set_access("Unavailable", "off")
            return
        index = _integer(channel.get("index"), 0)
        self.title.setText(f"PWM {index}")
        self.detail.setText(str(channel.get("label") or f"Fan {index}"))
        rpm = channel.get("rpm")
        self.rpm.setText(f"{_integer(rpm):,} RPM" if rpm is not None else "-- RPM")
        percent = _pwm_to_percent(channel.get("pwm"))
        self.duty.setText(f"{percent} %" if percent is not None else "-- %")
        mode = str(channel.get("pwm_enable") or "")
        if channel.get("pwm_user_writable"):
            self._set_access(f"Writable {mode}".strip(), "write")
        elif channel.get("pwm_root_writable"):
            self._set_access(f"Admin {mode}".strip(), "admin")
        else:
            self._set_access(f"Read only {mode}".strip(), "read")

    def _set_access(self, text: str, tone: str) -> None:
        self.access.setText(text)
        self.access.setProperty("fanAccess", tone)
        self.access.style().unpolish(self.access)
        self.access.style().polish(self.access)


class PathEntry(QFrame):
    def __init__(self, label: str, value: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("pathEntry", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        row = QHBoxLayout(self)
        row.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        row.setContentsMargins(11, 8, 11, 8)
        row.setSpacing(12)
        key = QLabel(tr(label))
        key.setProperty("pathEntryLabel", True)
        key.setWordWrap(True)
        key.setMinimumWidth(116)
        key.setMaximumWidth(180)
        key.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        row.addWidget(key, 0, Qt.AlignmentFlag.AlignTop)
        text = QLabel(tr(value))
        text.setProperty("pathEntryValue", True)
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.setWordWrap(True)
        text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        row.addWidget(text, 1, Qt.AlignmentFlag.AlignTop)


class PathsSection(QFrame):
    def __init__(self, title: str, description: str = "", entries: tuple[tuple[str, str], ...] = (), parent=None):
        super().__init__(parent)
        self.setProperty("pathsSection", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(13, 12, 13, 12)
        layout.setSpacing(8)
        heading = QLabel(tr(title))
        heading.setProperty("pathsSectionTitle", True)
        heading.setWordWrap(True)
        heading.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(heading)
        if description:
            body = QLabel(tr(description))
            body.setProperty("pathsSectionDescription", True)
            body.setTextFormat(Qt.TextFormat.PlainText)
            body.setWordWrap(True)
            body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            layout.addWidget(body)
        for label, value in entries:
            layout.addWidget(PathEntry(label, value))


class PwmPathsDialog(QDialog):
    """Responsive report for PWM routes and controller state."""

    def __init__(self, state: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("InfoDialog")
        self.setModal(True)
        self.setWindowTitle(tr("PWM paths and distribution layout"))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(application_stylesheet())
        enable_adaptive_dialog(
            self,
            preferred_width=930,
            preferred_height=650,
            minimum_width=620,
            minimum_height=440,
        )

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

        root = QVBoxLayout(card)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(13)
        header.addWidget(IconBadge("fans_blue", COLORS["blue_soft"], 44, radius=12))
        titles = QVBoxLayout()
        titles.setSpacing(2)
        eyebrow = QLabel(tr("FAN DRIVER INTEGRATION"))
        eyebrow.setObjectName("DialogEyebrow")
        eyebrow.setWordWrap(True)
        eyebrow.setStyleSheet(f"color:{COLORS['blue']};")
        title = QLabel(tr("PWM paths by distribution"))
        title.setObjectName("DialogTitle")
        title.setWordWrap(True)
        subtitle = QLabel(tr("Live hwmon routes, installed driver locations, persistence files, and useful verification commands."))
        subtitle.setObjectName("DialogBody")
        subtitle.setWordWrap(True)
        titles.addWidget(eyebrow)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        close = QPushButton()
        close.setObjectName("DialogClose")
        close.setIcon(icon("close_gray"))
        close.setFixedSize(34, 34)
        close.clicked.connect(self.accept)
        header.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        divider = QFrame()
        divider.setObjectName("CardDivider")
        divider.setFixedHeight(1)
        root.addWidget(divider)

        workspace = QHBoxLayout()
        workspace.setSpacing(14)
        navigation = QFrame()
        navigation.setProperty("pathsNavigation", True)
        navigation.setMinimumWidth(180)
        navigation.setMaximumWidth(260)
        navigation.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        nav_layout = QVBoxLayout(navigation)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(6)
        self.stack = QStackedWidget()
        self._pending_reflow_index = -1
        self._reflow_timer = QTimer(self)
        self._reflow_timer.setSingleShot(True)
        self._reflow_timer.setInterval(0)
        self._reflow_timer.timeout.connect(self._run_scheduled_page_reflow)
        self.stack.currentChanged.connect(self._schedule_page_reflow)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        pages = self._build_pages(state)
        for index, (label, page) in enumerate(pages):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("pathsNavButton", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked, i=index: self.stack.setCurrentIndex(i) if checked else None)
            self.nav_group.addButton(button)
            nav_layout.addWidget(button)
            self.stack.addWidget(page)
            if index == 0:
                button.setChecked(True)
        nav_layout.addStretch(1)
        workspace.addWidget(navigation)
        workspace.addWidget(self.stack, 1)
        root.addLayout(workspace, 1)

        footer = QHBoxLayout()
        note = QLabel(tr("Paths are informational. Driver installation and module changes remain explicit, authenticated actions."))
        note.setProperty("fieldHint", True)
        note.setWordWrap(True)
        footer.addWidget(note, 1)
        done = QPushButton(tr("Close"))
        done.setObjectName("DialogPrimary")
        done.clicked.connect(self.accept)
        footer.addWidget(done)
        root.addLayout(footer)
        localize_widget_tree(self)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        self.fit_to_content()
        self._schedule_page_reflow(self.stack.currentIndex())
        center_dialog(self)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._schedule_page_reflow(self.stack.currentIndex())

    def _page(self, sections: list[PathsSection]) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(container)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(2, 2, 8, 2)
        layout.setSpacing(10)
        for section in sections:
            layout.addWidget(section)
        layout.addStretch(1)
        scroll.setWidget(container)
        return scroll

    def _schedule_page_reflow(self, index: int) -> None:
        self._pending_reflow_index = int(index)
        if not self._reflow_timer.isActive():
            self._reflow_timer.start()

    def _run_scheduled_page_reflow(self) -> None:
        self._reflow_page(self._pending_reflow_index)

    def _reflow_page(self, index: int) -> None:
        if index < 0 or index >= self.stack.count() or index != self.stack.currentIndex():
            return
        scroll = self.stack.widget(index)
        if not isinstance(scroll, QScrollArea):
            return
        container = scroll.widget()
        if container is None:
            return
        width = max(1, scroll.viewport().contentsRect().width())
        # A hidden QStackedWidget page may have been measured at width 1.  Give
        # it the real viewport width for this pass without permanently locking
        # the dialog to that width; this keeps later UI-scale changes responsive.
        container.setMinimumWidth(0)
        container.resize(width, max(1, container.height()))
        reflow_wrapped_labels(container)
        layout = container.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        container.adjustSize()
        container.updateGeometry()
        scroll.viewport().updateGeometry()

    def _build_pages(self, state: dict) -> list[tuple[str, QWidget]]:
        sensors = _dict(state.get("sensores"))
        modules = _dict(state.get("modulos"))
        hwmon = str(sensors.get("path") or "/sys/class/hwmon/hwmonX")
        cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
        helper = str(Path(cache) / "bc250-control-center" / "bc250-fan-pwm-control-helper")
        pwm_paths = [str(item.get("path")) for item in sensors.get("pwms", []) if isinstance(item, dict) and item.get("path")]
        if not pwm_paths:
            pwm_paths = [f"{hwmon}/pwm1", f"{hwmon}/pwm2", f"{hwmon}/pwm3"]

        detected = self._page(
            [
                PathsSection(
                    "Live Linux detection",
                    "These values are read from the current NCT hwmon device and loaded kernel modules.",
                    (
                        ("Chip", str(sensors.get("chip") or tr("Not detected"))),
                        ("Hwmon root", hwmon),
                        ("Modules", f"nct6683={bool(modules.get('nct6683'))} · nct6687={bool(modules.get('nct6687'))}"),
                        ("PWM files", "\n".join(pwm_paths)),
                        ("GUI helper", helper),
                    ),
                ),
                PathsSection(
                    "Verification commands",
                    entries=(
                        ("Modules", 'lsmod | grep -E "nct6683|nct6687"'),
                        ("Driver metadata", "modinfo nct6687"),
                        ("Sensors", 'sensors | sed -n "/nct668/,+45p"'),
                    ),
                ),
            ]
        )

        arch = self._page(
            [
                PathsSection(
                    "Arch · CachyOS · Manjaro",
                    "The application uses the Arch repository strategy and an AUR helper when nct6687d-dkms-git is available.",
                    (
                        ("Configuration", "/etc/modprobe.d/nct6683.conf\n/etc/modprobe.d/nct6687.conf\n/etc/modules-load.d/nct6687.conf"),
                        ("Persistence", "/etc/systemd/system/nct6687-load.service\n/usr/local/sbin/bc250-load-nct6687"),
                        ("DKMS / kernel", "/var/lib/dkms/\n/usr/lib/modules/$(uname -r)/"),
                        ("Build cache", "~/.cache/yay/nct6687d-dkms-git/\n~/.cache/paru/clone/nct6687d-dkms-git/"),
                    ),
                ),
                PathsSection(
                    "Verification commands",
                    entries=(
                        ("Package files", "pacman -Ql nct6687d-dkms-git"),
                        ("DKMS", "dkms status"),
                        ("Sensors", 'sensors | sed -n "/nct668/,+45p"'),
                    ),
                ),
            ]
        )

        fedora = self._page(
            [
                PathsSection(
                    "Fedora · Nobara",
                    "Mutable Fedora systems compile the module for the active kernel and install it in the normal module tree.",
                    (
                        ("Configuration", "/etc/modprobe.d/nct6683.conf\n/etc/modprobe.d/nct6687.conf\n/etc/modules-load.d/nct6687.conf"),
                        ("Persistence", "/etc/systemd/system/nct6687-load.service\n/usr/local/sbin/bc250-load-nct6687"),
                        ("Kernel module", "/lib/modules/$(uname -r)/kernel/drivers/hwmon/nct6687.ko"),
                        ("Source cache", "ResourceTools/nct6687d/"),
                    ),
                ),
                PathsSection(
                    "Bazzite · Fedora Atomic",
                    "The immutable strategy stores a kernel-specific module under /var and loads the exact file through systemd.",
                    (
                        ("Persistent state", "/var/lib/bc250-control-center/kernel-modules/$(uname -r)/"),
                        ("Compatibility path", "/var/lib/nct6687/nct6687.ko"),
                        ("SELinux type", "system_u:object_r:modules_object_t:s0"),
                        ("Service", "/etc/systemd/system/nct6687-load.service"),
                    ),
                ),
                PathsSection(
                    "Verification commands",
                    entries=(
                        ("Atomic status", "rpm-ostree status"),
                        ("Service", "systemctl status nct6687-load.service --no-pager"),
                        ("Journal", "journalctl -b -u nct6687-load.service --no-pager"),
                        ("Module labels", "ls -lZ /var/lib/bc250-control-center/kernel-modules/$(uname -r)/"),
                    ),
                ),
            ]
        )

        debian = self._page(
            [
                PathsSection(
                    "Debian · Ubuntu",
                    "The Debian strategy installs matching kernel headers, builds nct6687d, runs depmod, and updates initramfs when available.",
                    (
                        ("Configuration", "/etc/modprobe.d/nct6683.conf\n/etc/modprobe.d/nct6687.conf\n/etc/modules-load.d/nct6687.conf"),
                        ("Persistence", "/etc/systemd/system/nct6687-load.service\n/usr/local/sbin/bc250-load-nct6687"),
                        ("Kernel module", "/lib/modules/$(uname -r)/kernel/drivers/hwmon/nct6687.ko"),
                        ("Kernel headers", "/lib/modules/$(uname -r)/build"),
                        ("Source cache", "ResourceTools/nct6687d/"),
                    ),
                ),
                PathsSection(
                    "Verification commands",
                    entries=(
                        ("Packages", 'dpkg -l | grep -E "lm-sensors|linux-headers"'),
                        ("Driver metadata", "modinfo nct6687"),
                        ("Sensors", 'sensors | sed -n "/nct668/,+45p"'),
                    ),
                ),
            ]
        )

        steamos = self._page(
            [
                PathsSection(
                    "SteamOS",
                    "SteamOS uses its own strategy because read-only root handling, pacman keyring setup, and Neptune kernel headers are not standard Arch behavior.",
                    (
                        ("Application sources", "~/.local/share/bc250-control-center/ResourceTools/nct6687d/"),
                        ("Configuration", "/etc/modprobe.d/nct6687.conf\n/etc/modules-load.d/nct6687.conf"),
                        ("Persistence", "/etc/systemd/system/nct6687-load.service\n/usr/local/sbin/bc250-load-nct6687"),
                        ("Kernel tree", "/usr/lib/modules/$(uname -r)/"),
                    ),
                ),
                PathsSection(
                    "Verification commands",
                    entries=(
                        ("Kernel", "uname -r"),
                        ("Packages", 'pacman -Q | grep -E "linux-neptune|lm_sensors"'),
                        ("Driver", "modinfo nct6687"),
                        ("Sensors", 'sensors | sed -n "/nct668/,+45p"'),
                    ),
                ),
            ]
        )
        return [
            ("Detected", detected),
            ("Arch family", arch),
            ("Fedora / Bazzite", fedora),
            ("Debian / Ubuntu", debian),
            ("SteamOS", steamos),
        ]


class FansPage(QWidget):
    def apply_appearance(self) -> None:
        if hasattr(self, "content"):
            self.content.setStyleSheet(fans_stylesheet())
            self.content.update()

    """Thermal workstation backed by the existing validated R64 fan repository."""

    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.current_state: dict = {}
        self._updates_active = False
        self._state_cache = state_cache_for(controller)
        self._background = BackgroundExecutor(self)
        self._event_sequence = 0
        self._curve_config_busy = False
        self._curve_config_loaded = False
        self.performance_state: dict = {}
        self.gpu_state: dict = {}
        self._worker: FanTask | None = None
        self._busy = False
        self._summary_columns = 5
        self._workspace_columns = 0
        self._bottom_columns = 0
        self._metric_columns = 0
        self._curve_columns = 0
        self._curve_workspace_columns = 0
        self._driver_action_columns = 0
        self._curve_loading = False
        self._curve_dirty = False
        self._curve_preset = "custom"
        self._last_curve_apply = 0.0
        self._last_curve_percent: int | None = None
        self._last_pwm_text = "--"
        self._preferred_pwm = 2

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        self.scroll = scroll
        self.content = QWidget()
        self.content.setObjectName("FansWorkspace")
        self.content.setStyleSheet(fans_stylesheet())
        configure_responsive_scroll_area(scroll, self.content)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(18, 8, 18, 24)
        layout.setSpacing(14)
        scroll.setWidget(self.content)
        outer.addWidget(scroll)

        self.header = ControlPageHeader(
            "THERMAL WORKSTATION",
            "Fans and PWM",
            "A single workspace for live cooling telemetry, explicit PWM writes, automatic response curves, and Linux driver integration.",
            mode_text="● LIVE SESSION",
            action_text="Prepare PWM control",
            action_icon="download_blue",
        )
        self.header.refresh_requested.connect(self._manual_refresh)
        self.header.action_requested.connect(self.prepare_pwm_driver)
        layout.addWidget(self.header)
        # Retain the connected controls internally, but remove the visible top
        # banner so the fan workspace begins immediately at the page margin.
        self.header.hide()

        # Live values continue to feed the detailed thermal telemetry below;
        # the redundant full-width status rail is no longer rendered.
        self.summary_strip = ThermalStatusRail(self.content)
        self.summary_strip.hide()

        self.workspace = QGridLayout()
        self.workspace.setContentsMargins(0, 0, 0, 0)
        self.workspace.setHorizontalSpacing(14)
        self.workspace.setVerticalSpacing(14)
        layout.addLayout(self.workspace)
        self.manual_card = self._build_manual_card()
        self.telemetry_card = self._build_telemetry_card()
        self.manual_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.telemetry_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.manual_card.setMinimumHeight(430)
        self.telemetry_card.setMinimumHeight(430)

        self.curve_card = self._build_curve_card()
        layout.addWidget(self.curve_card)

        self.bottom_grid = QGridLayout()
        self.bottom_grid.setContentsMargins(0, 0, 0, 0)
        self.bottom_grid.setHorizontalSpacing(14)
        self.bottom_grid.setVerticalSpacing(14)
        self.driver_card = self._build_driver_card()
        self.channels_card = self._build_channels_card()
        self.channels_card.hide()
        self.driver_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.channels_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.driver_card.setMinimumHeight(400)
        self.channels_card.setMinimumHeight(400)
        layout.addLayout(self.bottom_grid)
        layout.addStretch(1)

        self._apply_curve_config({})
        self._reflow(1400)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.refresh)
        self._refresher = AsyncRefresh(
            self,
            "fans-refresh",
            self._fetch_refresh_payload,
            self._apply_refresh_payload,
            self._refresh_failed,
        )

    def _build_manual_card(self) -> SectionCard:
        card = SectionCard(
            "Fan command",
            "Pump Fan / J4003 is the only writable service channel. Stage one duty target, review it, then authorize one deliberate write.",
            icon_name="fan_cyan",
            icon_background=COLORS["cyan_soft"],
            status=("Explicit write", "orange"),
        )
        self.channel_combo = QComboBox()
        self.channel_combo.hide()
        self.channel_combo.currentIndexChanged.connect(self._selected_channel_changed)

        console = QFrame()
        console.setProperty("fanDutyConsole", True)
        console_layout = QHBoxLayout(console)
        console_layout.setContentsMargins(14, 12, 14, 12)
        console_layout.setSpacing(18)
        self.duty_gauge = DutyGauge()
        console_layout.addWidget(self.duty_gauge, 0)
        controls = QVBoxLayout()
        controls.setSpacing(10)
        channel_copy = QVBoxLayout()
        channel_copy.setSpacing(1)
        title = QLabel("CONTROLLED CHANNEL")
        title.setProperty("fanConsoleKicker", True)
        self.selected_channel_title = QLabel("PWM 2 · Pump Fan / J4003 Fan 1")
        self.selected_channel_title.setProperty("fanConsoleTitle", True)
        self.selected_channel_meta = QLabel("Fixed service channel for BC250 cooling control.")
        self.selected_channel_meta.setProperty("fanConsoleMeta", True)
        self.selected_channel_meta.setWordWrap(True)
        channel_copy.addWidget(title)
        channel_copy.addWidget(self.selected_channel_title)
        channel_copy.addWidget(self.selected_channel_meta)
        controls.addLayout(channel_copy)
        live_row = QHBoxLayout()
        live_row.setSpacing(16)
        self.selected_live_rpm = QLabel("-- RPM")
        self.selected_live_rpm.setProperty("fanConsoleTitle", True)
        self.selected_access = QLabel("Access unavailable")
        self.selected_access.setProperty("fanConsoleMeta", True)
        live_row.addWidget(self.selected_live_rpm)
        live_row.addWidget(self.selected_access)
        live_row.addStretch(1)
        controls.addLayout(live_row)
        self.speed_control = SliderControl(
            "Requested fan speed",
            0,
            100,
            70,
            suffix=" %",
            step=1,
            hint="The dial shows the staged value. Hardware is not touched until Review and apply PWM is confirmed.",
        )
        self.speed_control.value_changed.connect(self._manual_value_changed)
        controls.addWidget(self.speed_control)
        self.manual_presets_grid = QGridLayout()
        self.manual_presets_grid.setContentsMargins(0, 0, 0, 0)
        self.manual_presets_grid.setHorizontalSpacing(8)
        self.manual_presets_grid.setVerticalSpacing(8)
        self.manual_preset_group = QButtonGroup(self)
        self.manual_preset_group.setExclusive(True)
        self.manual_preset_buttons: list[PresetButton] = []
        for preset_title, summary, value in (
            ("Quiet", "45% duty", 45),
            ("Balanced", "60% duty", 60),
            ("Cooling", "70% duty", 70),
            ("Maximum", "100% duty", 100),
        ):
            button = PresetButton(preset_title, summary, value)
            button.clicked.connect(lambda checked, b=button: self._select_manual_preset(b) if checked else None)
            self.manual_preset_group.addButton(button)
            self.manual_preset_buttons.append(button)
        controls.addLayout(self.manual_presets_grid)
        console_layout.addLayout(controls, 1)
        card.body.addWidget(console, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.manual_note = QLabel("Pump Fan / J4003 will be used for every staged write.")
        self.manual_note.setProperty("sectionSubtitle", True)
        self.manual_note.setWordWrap(True)
        footer.addWidget(self.manual_note, 1)
        self.use_live_button = QPushButton("Use live duty")
        self.use_live_button.setProperty("compactAction", True)
        self.use_live_button.clicked.connect(self._use_live_duty)
        footer.addWidget(self.use_live_button)
        self.apply_pwm_button = QPushButton("Review and apply PWM")
        self.apply_pwm_button.setObjectName("PrimaryAction")
        self.apply_pwm_button.clicked.connect(self.apply_manual_pwm)
        footer.addWidget(self.apply_pwm_button)
        card.body.addLayout(footer)
        return card

    def _build_telemetry_card(self) -> SectionCard:
        card = SectionCard(
            "Thermal telemetry",
            "Live read-only cooling signals kept visible while PWM changes are staged and applied.",
            icon_name="activity_purple",
            icon_background=COLORS["purple_soft"],
            status=("Passive", "green"),
        )
        self.metrics_grid = QGridLayout()
        self.metrics_grid.setContentsMargins(0, 0, 0, 0)
        self.metrics_grid.setHorizontalSpacing(10)
        self.metrics_grid.setVerticalSpacing(10)
        self.rpm_metric = TelemetryReadout("Main fan", "-- RPM", "Highest reporting visible channel", "fan_cyan", COLORS["cyan_soft"])
        self.duty_metric = TelemetryReadout("Selected duty", "-- %", "Current PWM value", "fans_blue", COLORS["blue_soft"])
        self.gpu_temp_metric = TelemetryReadout("GPU temperature", "-- °C", "Automatic curve input", "warning_orange", COLORS["orange_soft"])
        self.cpu_temp_metric = TelemetryReadout("CPU temperature", "-- °C", "Package sensor", "cpu_blue", COLORS["blue_soft"])
        self.metric_tiles = [self.rpm_metric, self.duty_metric, self.gpu_temp_metric, self.cpu_temp_metric]
        card.body.addLayout(self.metrics_grid)
        source_panel = QFrame()
        source_panel.setProperty("fanDutyStage", True)
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(10, 9, 10, 9)
        source_layout.setSpacing(7)
        self.telemetry_source = StatusLine("Sensor source", "Not detected", "Waiting for an NCT hwmon device")
        self.telemetry_refresh = StatusLine("Last refresh", "--:--:--", "Passive read")
        source_layout.addWidget(self.telemetry_source)
        source_layout.addWidget(self.telemetry_refresh)
        card.body.addWidget(source_panel)
        return card

    def _build_curve_card(self) -> SectionCard:
        card = SectionCard(
            "Temperature response",
            "A visual three-threshold GPU curve. The saved profile is shared with the optional user daemon.",
            icon_name="activity_purple",
            icon_background=COLORS["purple_soft"],
            status=("Disabled", "gray"),
        )
        self.curve_workspace = QGridLayout()
        self.curve_workspace.setContentsMargins(0, 0, 0, 0)
        self.curve_workspace.setHorizontalSpacing(12)
        self.curve_workspace.setVerticalSpacing(12)

        self.curve_plot_panel = QFrame()
        self.curve_plot_panel.setProperty("curveStage", True)
        plot_layout = QVBoxLayout(self.curve_plot_panel)
        plot_layout.setContentsMargins(14, 12, 14, 12)
        plot_layout.setSpacing(6)
        plot_head = QHBoxLayout()
        plot_copy = QVBoxLayout()
        plot_copy.setSpacing(1)
        plot_title = QLabel("LIVE RESPONSE MAP")
        plot_title.setProperty("fanConsoleKicker", True)
        self.curve_live_value = QLabel("Waiting for GPU temperature")
        self.curve_live_value.setProperty("fanConsoleTitle", True)
        plot_copy.addWidget(plot_title)
        plot_copy.addWidget(self.curve_live_value)
        plot_head.addLayout(plot_copy, 1)
        self.curve_live_target = QLabel("Target -- %")
        self.curve_live_target.setProperty("fanConsoleMeta", True)
        plot_head.addWidget(self.curve_live_target, 0, Qt.AlignmentFlag.AlignTop)
        plot_layout.addLayout(plot_head)
        self.curve_plot = FanCurvePlot()
        plot_layout.addWidget(self.curve_plot, 1)

        self.curve_controls_panel = QFrame()
        self.curve_controls_panel.setProperty("curveControlPanel", True)
        controls_layout = QVBoxLayout(self.curve_controls_panel)
        controls_layout.setContentsMargins(13, 12, 13, 12)
        controls_layout.setSpacing(10)
        mode_row = QHBoxLayout()
        self.curve_enabled = QCheckBox("Enable automatic curve")
        self.curve_enabled.toggled.connect(self._curve_toggle_changed)
        mode_row.addWidget(self.curve_enabled)
        mode_row.addStretch(1)
        controls_layout.addLayout(mode_row)
        presets = QHBoxLayout()
        presets.setSpacing(7)
        self.curve_preset_group = QButtonGroup(self)
        self.curve_preset_group.setExclusive(True)
        self.curve_preset_buttons: list[QPushButton] = []
        for title, key in (("Silent", "silent"), ("Balanced", "balanced"), ("Cool", "cool")):
            button = QPushButton(title)
            button.setCheckable(True)
            button.setProperty("compactAction", True)
            button.setProperty("curvePreset", key)
            button.clicked.connect(lambda checked, k=key: self._apply_curve_preset(k) if checked else None)
            self.curve_preset_group.addButton(button)
            self.curve_preset_buttons.append(button)
            presets.addWidget(button)
        controls_layout.addLayout(presets)
        self.curve_points_grid = QGridLayout()
        self.curve_points_grid.setContentsMargins(0, 0, 0, 0)
        self.curve_points_grid.setHorizontalSpacing(8)
        self.curve_points_grid.setVerticalSpacing(8)
        self.curve_points = [
            CurvePoint("Point 1", 50, 70),
            CurvePoint("Point 2", 65, 100),
            CurvePoint("Point 3", 70, 100),
        ]
        for point in self.curve_points:
            point.changed.connect(self._curve_values_changed)
        controls_layout.addLayout(self.curve_points_grid)
        self.curve_summary = QLabel("Curve not loaded")
        self.curve_summary.setProperty("fieldLabel", True)
        self.curve_summary.setWordWrap(True)
        self.curve_detail = QLabel("The optional daemon can continue applying the saved curve after the GUI closes.")
        self.curve_detail.setProperty("fieldHint", True)
        self.curve_detail.setWordWrap(True)
        controls_layout.addWidget(self.curve_summary)
        controls_layout.addWidget(self.curve_detail)
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.save_curve_button = QPushButton("Save curve")
        self.save_curve_button.setProperty("compactAction", True)
        self.save_curve_button.clicked.connect(self.save_curve)
        action_row.addWidget(self.save_curve_button)
        self.apply_curve_button = QPushButton("Apply curve now")
        self.apply_curve_button.setObjectName("PrimaryAction")
        self.apply_curve_button.clicked.connect(self.apply_curve_now)
        action_row.addWidget(self.apply_curve_button)
        controls_layout.addLayout(action_row)

        card.body.addLayout(self.curve_workspace)
        return card

    def _build_driver_card(self) -> SectionCard:
        card = SectionCard(
            "Controller stack",
            "NCT discovery, kernel module state, authenticated PWM access, and distribution-aware setup routes.",
            icon_name="settings_blue",
            icon_background=COLORS["blue_soft"],
            status=("Checking", "gray"),
        )
        banner = QFrame()
        banner.setProperty("driverModeBanner", True)
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(12, 10, 12, 10)
        banner_layout.setSpacing(10)
        banner_layout.addWidget(IconBadge("shield_green", COLORS["green_soft"], 34, radius=9))
        copy = QVBoxLayout()
        copy.setSpacing(1)
        self.driver_mode_value = QLabel("Detecting controller")
        self.driver_mode_value.setProperty("driverModeValue", True)
        self.driver_mode_detail = QLabel("No NCT hwmon route has been authorized yet.")
        self.driver_mode_detail.setProperty("driverModeDetail", True)
        self.driver_mode_detail.setWordWrap(True)
        copy.addWidget(self.driver_mode_value)
        copy.addWidget(self.driver_mode_detail)
        banner_layout.addLayout(copy, 1)
        card.body.addWidget(banner)
        self.chip_status = StatusLine("NCT chip", "Not detected", "hwmon discovery")
        self.module_status = StatusLine("Kernel module", "--", "nct6683 read-only · nct6687 PWM")
        self.control_status = StatusLine("PWM access", "Unavailable", "Polkit helper and hwmon permissions")
        self.path_status = StatusLine("Hwmon path", "--", "Live Linux route")
        for line in (self.chip_status, self.module_status, self.control_status, self.path_status):
            card.body.addWidget(line)
        self.driver_actions_grid = QGridLayout()
        self.driver_actions_grid.setContentsMargins(0, 0, 0, 0)
        self.driver_actions_grid.setHorizontalSpacing(8)
        self.driver_actions_grid.setVerticalSpacing(8)
        self.prepare_button = QPushButton("Prepare PWM driver")
        self.prepare_button.setObjectName("PrimaryAction")
        self.prepare_button.setIcon(icon("download_blue"))
        self.prepare_button.clicked.connect(self.prepare_pwm_driver)
        self.read_only_button = QPushButton("Use read-only monitoring")
        self.read_only_button.setProperty("compactAction", True)
        self.read_only_button.clicked.connect(self.enable_read_only)
        self.disable_button = QPushButton("Disable PWM setup")
        self.disable_button.setProperty("dangerAction", True)
        self.disable_button.clicked.connect(self.disable_pwm_setup)
        self.paths_button = QPushButton("PWM paths by OS")
        self.paths_button.setProperty("compactAction", True)
        self.paths_button.setIcon(icon("info_blue"))
        self.paths_button.clicked.connect(self.show_pwm_paths)
        self.raw_status_button = QPushButton("Raw chip status")
        self.raw_status_button.setProperty("compactAction", True)
        self.raw_status_button.clicked.connect(self.show_raw_status)
        self.driver_action_buttons = [self.prepare_button, self.read_only_button, self.disable_button, self.paths_button, self.raw_status_button]
        card.body.addLayout(self.driver_actions_grid)
        return card

    def _build_channels_card(self) -> SectionCard:
        card = SectionCard(
            "Cooling channels",
            "Legacy multi-channel diagnostics preserved for compatibility; the redesigned workspace targets PWM 2 only.",
            icon_name="fans_blue",
            icon_background=COLORS["blue_soft"],
            status=("Hidden", "gray"),
        )
        header = QHBoxLayout()
        header.setContentsMargins(45, 0, 11, 0)
        for title, stretch, minimum in (("CHANNEL", 1, 0), ("RPM", 0, 88), ("DUTY", 0, 58), ("ACCESS", 0, 96)):
            label = QLabel(tr(title))
            label.setProperty("fanColumnLabel", True)
            if minimum:
                label.setMinimumWidth(minimum)
                label.setAlignment(Qt.AlignmentFlag.AlignRight if title != "ACCESS" else Qt.AlignmentFlag.AlignCenter)
            header.addWidget(label, stretch)
        card.body.addLayout(header)
        self.channel_rows = [FanChannelRow(), FanChannelRow(), FanChannelRow()]
        for row in self.channel_rows:
            card.body.addWidget(row)
        self.channels_note = QLabel("PWM splitters and hubs normally share one control signal and expose only one tach/RPM signal.")
        self.channels_note.setProperty("fieldHint", True)
        self.channels_note.setWordWrap(True)
        card.body.addWidget(self.channels_note)
        card.body.addStretch(1)
        return card

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow(effective_viewport_width(self, self.scroll))

    def _reflow(self, width: int) -> None:
        workspace_columns = 2 if width >= 1040 else 1
        if workspace_columns != self._workspace_columns:
            self._workspace_columns = workspace_columns
            self._clear_grid(self.workspace)
            if workspace_columns == 2:
                self.workspace.addWidget(self.manual_card, 0, 0)
                self.workspace.addWidget(self.telemetry_card, 0, 1)
                self.workspace.setColumnStretch(0, 3)
                self.workspace.setColumnStretch(1, 2)
            else:
                self.workspace.addWidget(self.manual_card, 0, 0)
                self.workspace.addWidget(self.telemetry_card, 1, 0)
                self.workspace.setColumnStretch(0, 1)

        bottom_columns = 2 if width >= 1040 else 1
        if bottom_columns != self._bottom_columns:
            self._bottom_columns = bottom_columns
            self._clear_grid(self.bottom_grid)
            # legacy layout reference kept for contract compatibility:
            # self.bottom_grid.addWidget(self.channels_card, 0, 1)
            if bottom_columns == 2:
                self.bottom_grid.addWidget(self.driver_card, 0, 0, 1, 2)
                self.bottom_grid.setColumnStretch(0, 1)
                self.bottom_grid.setColumnStretch(1, 1)
            else:
                self.bottom_grid.addWidget(self.driver_card, 0, 0)
                self.bottom_grid.setColumnStretch(0, 1)

        curve_workspace_columns = 2 if width >= 1000 else 1
        if curve_workspace_columns != self._curve_workspace_columns:
            self._curve_workspace_columns = curve_workspace_columns
            self._clear_grid(self.curve_workspace)
            if curve_workspace_columns == 2:
                self.curve_workspace.addWidget(self.curve_plot_panel, 0, 0)
                self.curve_workspace.addWidget(self.curve_controls_panel, 0, 1)
                self.curve_workspace.setColumnStretch(0, 3)
                self.curve_workspace.setColumnStretch(1, 2)
            else:
                self.curve_workspace.addWidget(self.curve_plot_panel, 0, 0)
                self.curve_workspace.addWidget(self.curve_controls_panel, 1, 0)
                self.curve_workspace.setColumnStretch(0, 1)

        self._reflow_metric_tiles(width)
        self._reflow_curve_points(width)
        self._reflow_driver_actions(width)
        self._reflow_manual_presets(width)

    def _reflow_metric_tiles(self, width: int) -> None:
        columns = 2 if width >= 700 else 1
        if columns == self._metric_columns:
            return
        self._metric_columns = columns
        self._clear_grid(self.metrics_grid)
        for index, tile in enumerate(self.metric_tiles):
            self.metrics_grid.addWidget(tile, index // columns, index % columns)
        for column in range(columns):
            self.metrics_grid.setColumnStretch(column, 1)

    def _reflow_curve_points(self, width: int) -> None:
        columns = 1 if width >= 1080 else 3 if width >= 900 else 1
        if columns == self._curve_columns:
            return
        self._curve_columns = columns
        self._clear_grid(self.curve_points_grid)
        for index, point in enumerate(self.curve_points):
            self.curve_points_grid.addWidget(point, index // columns, index % columns)
        for column in range(columns):
            self.curve_points_grid.setColumnStretch(column, 1)

    def _reflow_driver_actions(self, width: int) -> None:
        columns = 3 if width >= 1180 else 2 if width >= 700 else 1
        if columns == self._driver_action_columns:
            return
        self._driver_action_columns = columns
        self._clear_grid(self.driver_actions_grid)
        for index, button in enumerate(self.driver_action_buttons):
            self.driver_actions_grid.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self.driver_actions_grid.setColumnStretch(column, 1)

    def _reflow_manual_presets(self, width: int) -> None:
        columns = 4 if width >= 980 else 2 if width >= 480 else 1
        current = self.manual_presets_grid.property("columns")
        if current == columns:
            return
        self.manual_presets_grid.setProperty("columns", columns)
        self._clear_grid(self.manual_presets_grid)
        for index, button in enumerate(self.manual_preset_buttons):
            self.manual_presets_grid.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self.manual_presets_grid.setColumnStretch(column, 1)

    @staticmethod
    def _clear_grid(layout: QGridLayout) -> None:
        clear_grid(layout)

    def _load_curve_config(self) -> None:
        # The shared cache delegates to controller.leer_config_local() off the
        # UI thread and coalesces duplicate reads from other interface pages.
        if self._curve_config_loaded or self._curve_config_busy:
            return
        self._curve_config_busy = True

        def success(payload: object) -> None:
            self._curve_config_busy = False
            self._curve_config_loaded = True
            config = _dict(payload).get("fan_curve") or {}
            self._apply_curve_config(_dict(config))

        def failure(_message: str) -> None:
            self._curve_config_busy = False
            self._curve_config_loaded = True

        self._background.start("fan-config-load", self._state_cache.config, success, failure)

    def _apply_curve_config(self, config: dict) -> None:
        self._curve_loading = True
        self._preferred_pwm = _integer(config.get("pwm"), 2) or 2
        self._curve_preset = str(config.get("preset") or "custom")
        self._last_pwm_text = str(config.get("last_pwm_text") or "--")
        values = (
            (_integer(config.get("t1"), 50), _integer(config.get("s1"), 70)),
            (_integer(config.get("t2"), 65), _integer(config.get("s2"), 100)),
            (_integer(config.get("t3"), 70), _integer(config.get("s3"), 100)),
        )
        for point, (temperature, speed) in zip(self.curve_points, values):
            point.set_values(temperature, speed)
        self.curve_enabled.setChecked(bool(config.get("enabled", False)))
        for button in self.curve_preset_buttons:
            button.setChecked(button.property("curvePreset") == self._curve_preset)
        self._curve_loading = False
        self._curve_dirty = False
        self._update_curve_summary()

    def _curve_points_values(self) -> list[tuple[int, int]]:
        return sorted((point.values() for point in self.curve_points), key=lambda item: item[0])

    def _normalize_curve_points(self) -> None:
        values = self._curve_points_values()
        for point, (temperature, speed) in zip(self.curve_points, values):
            point.set_values(temperature, speed)

    def _curve_config(self) -> dict:
        self._normalize_curve_points()
        points = [point.values() for point in self.curve_points]
        pwm = self.channel_combo.currentData()
        if pwm is None:
            pwm = self._preferred_pwm
        return {
            "enabled": bool(self.curve_enabled.isChecked()),
            "edit_enabled": bool(self.curve_enabled.isChecked()),
            "pwm": int(pwm or 2),
            "t1": points[0][0],
            "s1": points[0][1],
            "t2": points[1][0],
            "s2": points[1][1],
            "t3": points[2][0],
            "s3": points[2][1],
            "preset": self._curve_preset,
            "last_pwm_text": self._last_pwm_text,
        }

    def _persist_curve(self, *, show_error: bool = True, on_success=None) -> bool:
        config = self._curve_config()

        def operation() -> object:
            self.controller.guardar_config_local({"fan_curve": config})
            return True

        def success(_result: object) -> None:
            self._state_cache.invalidate("config")
            self._curve_dirty = False
            self._update_curve_summary()
            if callable(on_success):
                on_success()

        def failure(message: str) -> None:
            if show_error:
                self._show_error("Could not save fan curve", message)

        return self._background.start("fan-config-save", operation, success, failure)

    def save_curve(self) -> None:
        def saved() -> None:
            self._record_event("info", "Fan curve saved", self.curve_summary.text())
            self._show_info(
                "Fan curve saved",
                "The curve was written to the shared BC250 Control Center configuration. The optional user daemon can use the same values after the GUI closes.",
                tone="blue",
            )

        self._persist_curve(on_success=saved)

    def _curve_values_changed(self) -> None:
        if self._curve_loading:
            return
        self._curve_preset = "custom"
        self.curve_preset_group.setExclusive(False)
        for button in self.curve_preset_buttons:
            button.setChecked(False)
        self.curve_preset_group.setExclusive(True)
        self._curve_dirty = True
        self._update_curve_summary()

    def _curve_toggle_changed(self, enabled: bool) -> None:
        if self._curve_loading:
            return
        if enabled and not self._fan_control_available():
            self.curve_enabled.blockSignals(True)
            self.curve_enabled.setChecked(False)
            self.curve_enabled.blockSignals(False)
            self._show_info(
                "PWM control is not ready",
                "Prepare the nct6687 PWM driver first. Read-only nct6683 monitoring cannot apply an automatic curve.",
                tone="orange",
            )
            return
        self._curve_dirty = True
        self._persist_curve(show_error=False)
        self._update_curve_summary()

    def _apply_curve_preset(self, key: str) -> None:
        values = CURVE_PRESETS.get(key)
        if not values:
            return
        self._curve_loading = True
        for point, (temperature, speed) in zip(self.curve_points, values):
            point.set_values(temperature, speed)
        self._curve_loading = False
        self._curve_preset = key
        self._curve_dirty = True
        self._persist_curve(show_error=False)
        self._update_curve_summary()

    def _curve_percent_for_temp(self, temperature: float) -> int:
        points = self._curve_points_values()
        target = points[0][1]
        for limit, speed in points:
            if temperature >= limit:
                target = speed
        return max(0, min(100, int(target)))

    def _update_curve_summary(self) -> None:
        points = self._curve_points_values()
        profile_names = {"silent": tr("Silent"), "balanced": tr("Balanced"), "cool": tr("Cool"), "custom": tr("Custom")}
        point_text = " · ".join(f"{temp} °C / {speed}%" for temp, speed in points)
        dirty = tr(" · unsaved edits") if self._curve_dirty else ""
        self.curve_summary.setText(f"{profile_names.get(self._curve_preset, tr('Custom'))} · {point_text}{dirty}")
        status = tr("Enabled" if self.curve_enabled.isChecked() else "Disabled")
        if self.curve_card.status is not None:
            self.curve_card.status.setText(status)
            self.curve_card.status.set_tone("green" if self.curve_enabled.isChecked() else "gray")
        self.curve_detail.setText(tr_format(
            "Last PWM: {value}. The optional daemon reads this same saved curve from config.json.",
            value=self._last_pwm_text,
        ))
        self.curve_plot.set_curve(points)
        temperature = self._gpu_temperature()
        duty = self._curve_percent_for_temp(temperature) if temperature is not None else None
        self.curve_plot.set_live(temperature, duty)
        self.curve_live_value.setText(f"GPU {temperature:.1f} °C" if temperature is not None else tr("Waiting for GPU temperature"))
        self.curve_live_target.setText(tr_format("Target {value}%", value=duty) if duty is not None else tr("Target -- %"))

    def _select_manual_preset(self, button: PresetButton) -> None:
        self.speed_control.setValue(_integer(button.payload, 70))

    def _manual_value_changed(self, value: int) -> None:
        matched = False
        for button in self.manual_preset_buttons:
            checked = _integer(button.payload) == int(value)
            button.setChecked(checked)
            matched = matched or checked
        if not matched:
            self.manual_preset_group.setExclusive(False)
            for button in self.manual_preset_buttons:
                button.setChecked(False)
            self.manual_preset_group.setExclusive(True)
        raw = _percent_to_pwm(value)
        self.duty_gauge.setValue(value)
        self.manual_note.setText(tr_format("Staged duty: {value}% · raw PWM {raw}/255. No write occurs until confirmed.", value=value, raw=raw))

    def _visible_fans(self) -> list[dict]:
        sensors = _dict(self.current_state.get("sensores"))
        fans = [item for item in sensors.get("fans", []) if isinstance(item, dict)]
        pump = next((fan for fan in fans if _integer(fan.get("index")) == 2), None)
        if pump is not None:
            return [pump]
        order = {index: position for position, index in enumerate(VISIBLE_PWM_ORDER)}
        visible = sorted((fan for fan in fans if _integer(fan.get("index")) in order), key=lambda fan: order[_integer(fan.get("index"))])
        return visible[:1]

    def _main_fan(self) -> dict:
        fans = self._visible_fans()
        active = [fan for fan in fans if _integer(fan.get("rpm"), 0) > 0]
        if active:
            return max(active, key=lambda fan: _integer(fan.get("rpm"), 0))
        return next((fan for fan in fans if _integer(fan.get("index")) == 2), fans[0] if fans else {})

    def _selected_fan(self) -> dict:
        selected = self.channel_combo.currentData()
        visible = self._visible_fans()
        return next((fan for fan in visible if _integer(fan.get("index")) == _integer(selected, -1)), visible[0] if visible else {})

    def _selected_channel_changed(self) -> None:
        selected = self.channel_combo.currentData()
        if selected is not None:
            self._preferred_pwm = _integer(selected, 2)
        fan = self._selected_fan()
        percent = _pwm_to_percent(fan.get("pwm")) if fan else None
        if percent is not None and not self.speed_control.slider.isSliderDown() and not self.speed_control.spin.hasFocus():
            self.speed_control.setValue(percent)
        if not self._curve_loading:
            self._persist_curve(show_error=False)
        self._update_selected_metrics()

    def _use_live_duty(self) -> None:
        fan = self._selected_fan()
        percent = _pwm_to_percent(fan.get("pwm")) if fan else None
        if percent is None:
            self._show_info("No live duty", "The selected channel does not expose a readable PWM value.", tone="orange")
            return
        self.speed_control.setValue(percent)

    def _fan_control_available(self) -> bool:
        return bool(self.current_state.get("driver_control"))

    def apply_manual_pwm(self) -> None:
        if not self._fan_control_available():
            self._show_info(
                "PWM control is not ready",
                "Prepare the nct6687 driver first. The current NCT device is available for monitoring only.",
                tone="orange",
            )
            return
        pwm = self.channel_combo.currentData()
        if pwm is None:
            self._show_info("No PWM channel", "Refresh the page after the NCT hwmon device is detected.", tone="orange")
            return
        percent = self.speed_control.value()
        raw = _percent_to_pwm(percent)
        fan = self._selected_fan()
        dialog = ConfirmDialog(
            "Apply manual fan speed",
            "The selected NCT PWM file will be written through the existing narrow Polkit helper. Monitor temperature and RPM after the change.",
            summary=(
                ("Channel", f"PWM {pwm} · {fan.get('label') or 'fan channel'}"),
                ("Requested duty", f"{percent}%"),
                ("Raw hwmon value", f"{raw} / 255"),
                ("Persistence", "Live value; curve settings are separate"),
            ),
            confirm_text="Apply PWM value",
            tone="orange" if percent < 40 else "blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_pwm_write(pwm, percent, source="manual")

    def apply_curve_now(self) -> None:
        if not self._fan_control_available():
            self._show_info("PWM control is not ready", "Prepare nct6687 before applying the curve.", tone="orange")
            return
        temperature = self._gpu_temperature()
        if temperature is None:
            self._show_info("GPU temperature unavailable", "The curve cannot be evaluated until the GPU temperature sensor reports a value.", tone="orange")
            return
        pwm = self.channel_combo.currentData() or self._preferred_pwm
        percent = self._curve_percent_for_temp(temperature)
        raw = _percent_to_pwm(percent)
        dialog = ConfirmDialog(
            "Apply GPU temperature curve now",
            "The current GPU temperature will be evaluated against the three saved points and one PWM value will be written immediately.",
            summary=(
                ("GPU temperature", f"{temperature:.1f} °C"),
                ("Target channel", f"PWM {pwm}"),
                ("Calculated duty", f"{percent}% · {raw}/255"),
                ("Automatic mode", "Enabled" if self.curve_enabled.isChecked() else "One-time apply"),
            ),
            confirm_text="Apply calculated duty",
            tone="blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._persist_curve(show_error=False)
        self._run_pwm_write(pwm, percent, source="curve")

    def _run_pwm_write(self, pwm, percent: int, *, source: str, automatic: bool = False) -> None:
        if self._busy:
            return
        pwm = _integer(pwm, 2)
        percent = max(0, min(100, _integer(percent)))
        raw = _percent_to_pwm(percent)
        self._set_busy(True, "Applying PWM…")
        worker = FanTask(lambda: self.controller.aplicar_pwm_fan(pwm, raw), self)
        self._worker = worker

        def complete(result) -> None:
            self._last_pwm_text = f"PWM {pwm} · {percent}%"
            self._last_curve_apply = time.monotonic()
            self._last_curve_percent = percent if source == "curve" else self._last_curve_percent
            self._persist_curve(show_error=False)
            self._record_event(
                "info" if automatic else "warning",
                "Fan curve applied" if source == "curve" else "Manual fan speed applied",
                f"PWM {pwm} set to {percent}% ({raw}/255).",
            )
            self._set_busy(False, "")
            self._state_cache.invalidate("fans", "performance", "gpu")
            self.refresh()
            if not automatic:
                self._show_info(
                    "Fan speed applied",
                    tr_format("PWM {pwm} is now staged at {percent}% ({raw}/255). Sensor values were refreshed.", pwm=pwm, percent=percent, raw=raw),
                    tone="blue",
                )

        def failed(message: str) -> None:
            self._set_busy(False, "")
            if automatic:
                self.curve_enabled.blockSignals(True)
                self.curve_enabled.setChecked(False)
                self.curve_enabled.blockSignals(False)
                self._persist_curve(show_error=False)
            self._record_event("error", "Fan PWM operation failed", message)
            self._show_error("Fan PWM operation failed", message)

        worker.succeeded.connect(complete)
        worker.failed.connect(failed)
        worker.finished.connect(self._worker_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _worker_finished(self) -> None:
        self._worker = None

    def _set_busy(self, busy: bool, label: str) -> None:
        self._busy = bool(busy)
        self.apply_pwm_button.setEnabled(not busy and self._fan_control_available())
        self.apply_curve_button.setEnabled(not busy and self._fan_control_available())
        for button in (self.prepare_button, self.read_only_button, self.disable_button):
            button.setEnabled(not busy)
        if self.header.action_button is not None:
            self.header.action_button.setEnabled(not busy)
            self.header.action_button.setText(tr(label) if busy else tr("Prepare PWM driver"))

    def _run_driver_action(self, operation, on_success, error_title: str) -> None:
        self._set_busy(True, "Working…")

        def success(result: object) -> None:
            on_success(result)
            self._state_cache.invalidate("fans", "tools", "config")
            self.refresh()

        def failure(message: str) -> None:
            self._show_error(error_title, message)

        def finished() -> None:
            self._set_busy(False, "")

        if not self._background.start("fan-driver-action", operation, success, failure, finished):
            self._set_busy(False, "")

    def prepare_pwm_driver(self) -> None:
        dialog = ConfirmDialog(
            "Prepare nct6687 PWM control",
            "The distribution-specific workflow checks that the installed kernel headers match the active kernel before compiling nct6687. It may try to install the exact headers package, but it will stop safely if only headers for another kernel are available. A reboot may be required after a system or kernel update.",
            summary=(
                ("Purpose", "Writable NCT PWM channels"),
                ("Kernel/header safety", "Exact match with uname -r required"),
                ("Authentication", "Visible terminal and sudo"),
                ("Monitoring fallback", "nct6683 remains available as read-only mode"),
            ),
            confirm_text="Open preparation workflow",
            tone="orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        def success(_result: object) -> None:
            self._record_event("warning", "Fan PWM setup opened", "Distribution-specific nct6687 preparation workflow started.")
            self._show_info(
                "PWM preparation opened",
                "Complete the visible terminal workflow. Reboot if requested, then return here and refresh the fan page.",
                tone="orange",
            )

        self._run_driver_action(self.controller.preparar_nct6687_control_pwm, success, "PWM preparation failed")

    def enable_read_only(self) -> None:
        dialog = ConfirmDialog(
            "Enable read-only NCT monitoring",
            "The application will configure nct6683 for temperatures and RPM monitoring only. Writable PWM control will not be available in this mode.",
            summary=(
                ("Module", "nct6683 force=true"),
                ("Capability", "Sensors and fan RPM"),
                ("PWM writes", "Disabled"),
            ),
            confirm_text="Open read-only setup",
            tone="blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        def success(_result: object) -> None:
            self._record_event("info", "Fan read-only setup opened", "nct6683 monitoring workflow started.")

        self._run_driver_action(self.controller.cargar_nct6683_solo_lectura, success, "Read-only setup failed")

    def disable_pwm_setup(self) -> None:
        dialog = ConfirmDialog(
            "Disable nct6687 PWM setup",
            "Boot preference files and the nct6687 load service will be removed, then the system will return to nct6683 read-only monitoring. The installed package is not uninstalled.",
            summary=(
                ("PWM control", "Disabled"),
                ("Read-only monitoring", "Restored"),
                ("Package files", "Retained"),
                ("Reboot", "May be required"),
            ),
            confirm_text="Disable PWM setup",
            tone="red",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        def success(_result: object) -> None:
            self._record_event("warning", "Fan PWM setup disabled", "nct6687 boot preference removal workflow started.")

        self._run_driver_action(self.controller.desactivar_nct6687_control_pwm, success, "Could not disable PWM setup")

    def show_pwm_paths(self) -> None:
        PwmPathsDialog(self.current_state, self).exec()

    def show_raw_status(self) -> None:
        sensors = _dict(self.current_state.get("sensores"))
        modules = _dict(self.current_state.get("modulos"))
        fans = self._visible_fans()
        channel_lines = "\n".join(
            f"PWM {fan.get('index')}: {fan.get('label')} · {fan.get('rpm') or '--'} RPM · {fan.get('pwm_path') or '--'}"
            for fan in fans
        ) or "No visible channels detected."
        text = (
            f"Chip: {sensors.get('chip') or '--'}\n"
            f"Hwmon: {sensors.get('path') or '--'}\n"
            f"Modules: nct6683={bool(modules.get('nct6683'))} · nct6687={bool(modules.get('nct6687'))}\n"
            f"PWM control: {'available' if self._fan_control_available() else 'read only / unavailable'}\n\n"
            f"{channel_lines}\n\n"
            f"{self.current_state.get('resumen') or 'No repository summary available.'}"
        )
        self._show_info("NCT fan controller status", text, tone="blue")

    def _manual_refresh(self) -> None:
        self._state_cache.invalidate("fans", "performance", "gpu")
        self.refresh()

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if self._updates_active:
            self._load_curve_config()
            if not self.timer.isActive():
                self.timer.start()
            self._refresher.activate(fresh_for=1.5)
        else:
            self._refresher.set_active(False)
            self.timer.stop()

    def _fetch_refresh_payload(self) -> dict[str, dict]:
        # state_cache.fans() delegates to controller.estado_fans_bc250() in the
        # worker pool; refresh() itself remains a non-blocking UI slot.
        return {
            "fans": self._state_cache.fans(),
            "performance": self._state_cache.performance(),
            "gpu": self._state_cache.gpu(),
        }

    def refresh(self) -> None:
        if self._busy:
            return
        self._refresher.request()

    def _refresh_failed(self, message: str) -> None:
        self.current_state = {"error": message, "sensores": {}, "modulos": {}, "driver_control": False}
        self._apply_state()

    def _apply_refresh_payload(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        self.current_state = _dict(data.get("fans"))
        self.performance_state = _dict(data.get("performance"))
        self.gpu_state = _dict(data.get("gpu"))
        self._apply_state()
        if self._updates_active:
            self._maybe_apply_curve()

    def _apply_state(self) -> None:
        sensors = _dict(self.current_state.get("sensores"))
        modules = _dict(self.current_state.get("modulos"))
        fans = self._visible_fans()
        main_fan = self._main_fan()
        selected_before = self.channel_combo.currentData()

        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        for fan in fans:
            index = _integer(fan.get("index"), 0)
            self.channel_combo.addItem(f"PWM {index} · {fan.get('label') or f'Fan {index}'}", index)
        target = selected_before if selected_before is not None else self._preferred_pwm
        selected_index = self.channel_combo.findData(target)
        if selected_index < 0 and self.channel_combo.count() > 0:
            selected_index = 0
        if selected_index >= 0:
            self.channel_combo.setCurrentIndex(selected_index)
        self.channel_combo.blockSignals(False)

        for row, channel in zip(self.channel_rows, fans + [None] * (len(self.channel_rows) - len(fans))):
            row.set_channel(channel)

        main_rpm = main_fan.get("rpm")
        selected_fan = self._selected_fan()
        selected_percent = _pwm_to_percent(selected_fan.get("pwm")) if selected_fan else None
        gpu_temp = self._gpu_temperature()
        cpu_temp = self._cpu_temperature()
        driver = "nct6687" if modules.get("nct6687") else "nct6683" if modules.get("nct6683") else tr("Not loaded")
        control = self._fan_control_available()

        self.summary_strip.items[0].set_values(f"{_integer(main_rpm):,} RPM" if main_rpm is not None else "-- RPM", str(main_fan.get("label") or "Pump Fan / J4003"))
        self.summary_strip.items[1].set_values(f"{selected_percent} %" if selected_percent is not None else "-- %", "PWM 2")
        self.summary_strip.items[2].set_values(f"{gpu_temp:.1f} °C" if gpu_temp is not None else "-- °C", tr("curve input sensor"))
        self.summary_strip.items[3].set_values(tr("Writable" if control else "Read only"), "nct6687 / hwmon")
        self.summary_strip.items[4].set_values(driver, str(sensors.get("chip") or tr("NCT not detected")))

        self.driver_mode_value.setText(tr("Writable PWM control" if control else "Read-only monitoring" if sensors.get("chip") else "Controller not detected"))
        self.driver_mode_detail.setText(str(self.current_state.get("resumen") or sensors.get("path") or tr("No NCT hwmon route available.")))

        self.rpm_metric.set_values(f"{_integer(main_rpm):,} RPM" if main_rpm is not None else "-- RPM", str(main_fan.get("label") or tr("No reporting fan")))
        self.duty_metric.set_values(f"{selected_percent} %" if selected_percent is not None else "-- %", "PWM 2")
        self.gpu_temp_metric.set_values(f"{gpu_temp:.1f} °C" if gpu_temp is not None else "-- °C", tr("Automatic curve input"))
        self.cpu_temp_metric.set_values(f"{cpu_temp:.1f} °C" if cpu_temp is not None else "-- °C", tr("CPU package sensor"))
        self.telemetry_source.set_values(str(sensors.get("chip") or tr("Not detected")), str(sensors.get("path") or tr("No NCT hwmon route")))
        self.telemetry_refresh.set_values(datetime.now().strftime("%H:%M:%S"), tr("Passive refresh"))
        self.curve_plot.set_live(gpu_temp, self._curve_percent_for_temp(gpu_temp) if gpu_temp is not None else None)
        self.curve_live_value.setText(f"GPU {gpu_temp:.1f} °C" if gpu_temp is not None else tr("Waiting for GPU temperature"))
        live_target = self._curve_percent_for_temp(gpu_temp) if gpu_temp is not None else None
        self.curve_live_target.setText(tr_format("Target {value}%", value=live_target) if live_target is not None else tr("Target -- %"))

        self.chip_status.set_values(str(sensors.get("chip") or tr("Not detected")), "NCT hardware monitor")
        self.module_status.set_values(driver, str(modules.get("raw") or tr("No NCT module line in /proc/modules")))
        self.control_status.set_values(tr("Available" if control else "Read only"), str(self.current_state.get("resumen") or tr("PWM status unavailable")))
        self.path_status.set_values(str(sensors.get("path") or "--"), tr("Detected /sys/class/hwmon route"))
        if self.driver_card.status is not None:
            self.driver_card.status.setText(tr("PWM ready" if control else "Read only" if sensors.get("chip") else "Not detected"))
            self.driver_card.status.set_tone("green" if control else "blue" if sensors.get("chip") else "gray")

        if selected_percent is not None and not self.speed_control.slider.isSliderDown() and not self.speed_control.spin.hasFocus():
            self.speed_control.setValue(selected_percent)
        self._update_selected_metrics()
        self._update_action_availability()
        self._update_curve_summary()

    def _update_selected_metrics(self) -> None:
        selected_fan = self._selected_fan()
        percent = _pwm_to_percent(selected_fan.get("pwm")) if selected_fan else None
        pwm = self.channel_combo.currentData()
        self.duty_metric.set_values(f"{percent} %" if percent is not None else "-- %", "PWM 2")
        self.summary_strip.items[1].set_values(f"{percent} %" if percent is not None else "-- %", "PWM 2")
        self.selected_channel_title.setText(f"PWM 2 · {selected_fan.get('label') or 'Pump Fan / J4003 Fan 1'}" if selected_fan else tr("Waiting for NCT telemetry"))
        self.selected_channel_meta.setText(str(selected_fan.get("pwm_path") or tr("Fixed service channel for BC250 cooling control.")))
        rpm = selected_fan.get("rpm") if selected_fan else None
        self.selected_live_rpm.setText(f"{_integer(rpm):,} RPM" if rpm is not None else "-- RPM")
        if selected_fan.get("pwm_user_writable"):
            access = tr("User-writable channel")
        elif selected_fan.get("pwm_root_writable"):
            access = tr("Authenticated write required")
        else:
            access = tr("Read-only channel")
        self.selected_access.setText(access)

    def _update_action_availability(self) -> None:
        control = self._fan_control_available()
        has_channels = self.channel_combo.count() > 0
        self.channel_combo.setEnabled(has_channels and not self._busy)
        self.use_live_button.setEnabled(has_channels and not self._busy)
        self.apply_pwm_button.setEnabled(control and has_channels and not self._busy)
        self.apply_curve_button.setEnabled(control and has_channels and not self._busy)
        self.save_curve_button.setEnabled(not self._busy)
        for point in self.curve_points:
            point.setEnabled(not self._busy)
        for button in self.curve_preset_buttons:
            button.setEnabled(not self._busy)
        self.curve_enabled.setEnabled(not self._busy)
        self.prepare_button.setEnabled(not self._busy)
        self.read_only_button.setEnabled(not self._busy)
        self.disable_button.setEnabled(not self._busy)
        if self.header.action_button is not None:
            self.header.action_button.setEnabled(not self._busy)

    def _gpu_temperature(self) -> float | None:
        for source, key in ((self.performance_state, "gpu_temp"), (self.gpu_state, "gpu_temp"), (self.gpu_state, "temperature")):
            value = source.get(key)
            if value is not None:
                return _number(value)
        return None

    def _cpu_temperature(self) -> float | None:
        value = self.performance_state.get("cpu_temp")
        return _number(value) if value is not None else None

    def _maybe_apply_curve(self) -> None:
        if self._busy or not self.curve_enabled.isChecked() or not self._fan_control_available():
            return
        temperature = self._gpu_temperature()
        if temperature is None:
            return
        now = time.monotonic()
        if now - self._last_curve_apply < 5:
            return
        percent = self._curve_percent_for_temp(temperature)
        if self._last_curve_percent == percent:
            self._last_curve_apply = now
            return
        pwm = self.channel_combo.currentData() or self._preferred_pwm
        self._run_pwm_write(pwm, percent, source="curve", automatic=True)

    def _record_event(self, level: str, title: str, detail: str) -> None:
        self._event_sequence += 1

        def operation() -> object:
            self.controller.registrar_evento("fan", level, title, detail, {})
            return True

        self._background.start(
            f"fan-event:{self._event_sequence}",
            operation,
        )

    def _show_info(self, title: str, message: str, *, tone: str = "blue") -> None:
        icon_name = "warning_orange" if tone in {"orange", "red"} else "info_blue"
        InfoDialog(
            title,
            message,
            icon_name=icon_name,
            parent=self,
            eyebrow="THERMAL CONTROL",
            button_text="Close",
            notice="No additional hardware command will run automatically.",
            tone=tone,
        ).exec()

    def _show_error(self, title: str, message: str) -> None:
        self._show_info(title, message, tone="red")
