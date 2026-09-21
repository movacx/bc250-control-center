from __future__ import annotations

import math
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
    Qt,
    QThread,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen
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
    QListView,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from bc250cc.domain.fan.persistence import (
    normalize_fan_curve,
    select_fan_control_temperature,
    validate_fan_curve_points,
)
from bc250cc.platform.init.services import detect_init_manager

from ..components.async_tools import AsyncRefresh, BackgroundExecutor
from ..components.buttons import WrappingButton as QPushButton
from ..components.dialogs import (
    center_dialog,
    enable_adaptive_dialog,
    reflow_wrapped_labels,
)
from ..components.page_widgets import (
    ConfirmDialog,
    ControlPageHeader,
    PresetButton,
    SliderControl,
    StatusLine,
)
from ..components.responsive import (
    clear_grid,
    configure_responsive_scroll_area,
    effective_viewport_width,
)
from ..components.widgets import IconBadge, InfoDialog, icon
from ..core.fan_action_policy import plan_automatic_curve, plan_fan_action_availability
from ..core.fan_state_presenter import (
    FanStatePresentation,
    present_fan_state,
    visible_fans,
)
from ..core.state import state_cache_for
from ..i18n import localize_widget_tree, tr, tr_format
from ..theme import COLORS, application_stylesheet, scale_stylesheet

VISIBLE_PWM_ORDER = (2, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
CURVE_PRESETS = {
    "silent": ((50, 45), (65, 70), (75, 100)),
    "balanced": ((50, 60), (65, 85), (72, 100)),
    "aggressive": ((45, 70), (60, 90), (68, 100)),
}

def fans_stylesheet() -> str:
    c = COLORS
    return scale_stylesheet(f"""
QWidget#FansWorkspace QFrame[coolingHero='true'] {{
    background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 16px;
}}
QWidget#FansWorkspace QFrame[coolingSurface='true'] {{
    background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 16px;
}}
QWidget#FansWorkspace QFrame[coolingMetric='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 10px;
}}
QWidget#FansWorkspace QLabel[coolingEyebrow='true'] {{
    color: {c['blue']}; font-size: 9px; font-weight: 820; letter-spacing: .7px;
}}
QWidget#FansWorkspace QLabel[coolingHeading='true'] {{
    color: {c['text']}; font-size: 17px; font-weight: 820;
}}
QWidget#FansWorkspace QLabel[coolingDetail='true'] {{
    color: {c['muted']}; font-size: 10px;
}}
QWidget#FansWorkspace QLabel[coolingMetricLabel='true'] {{
    color: {c['muted']}; font-size: 9px; font-weight: 760; letter-spacing: .35px;
}}
QWidget#FansWorkspace QLabel[coolingMetricValue='true'] {{
    color: {c['text']}; font-size: 18px; font-weight: 830;
}}
QWidget#FansWorkspace QLabel[coolingMetricDetail='true'] {{
    color: {c['subtle']}; font-size: 9px;
}}
QWidget#FansWorkspace QFrame[fanModeSwitch='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 11px;
}}
QWidget#FansWorkspace QPushButton[fanModeButton='true'] {{
    background: transparent; color: {c['muted']}; border: 1px solid transparent;
    border-radius: 8px; min-height: 30px; padding: 5px 11px; font-size: 11px; font-weight: 760;
}}
QWidget#FansWorkspace QPushButton[fanModeButton='true']:hover {{
    background: {c['control_hover']}; color: {c['text']};
}}
QWidget#FansWorkspace QPushButton[fanModeButton='true']:checked {{
    background: {c['control']}; color: {c['text']}; border-color: {c['border']};
}}
QWidget#FansWorkspace QFrame[fanModePage='true'] {{
    background: transparent; border: 0;
}}
QWidget#FansWorkspace QFrame[fanChannelStrip='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 10px;
}}
QWidget#FansWorkspace QLabel[fanSelectedValue='true'] {{
    color: {c['text']}; font-size: 16px; font-weight: 820;
}}
QWidget#FansWorkspace QLabel[fanSelectedMeta='true'] {{
    color: {c['muted']}; font-size: 10px;
}}
QWidget#FansWorkspace QLabel[fanInlineReading='true'] {{
    color: {c['text']}; font-size: 11px; font-weight: 780;
}}
QWidget#FansWorkspace QPushButton[fanPresetButton='true'] {{
    background: {c['panel_alt']}; color: {c['text']}; border: 1px solid {c['border_soft']};
    border-radius: 9px; min-height: 31px; padding: 5px 9px; font-size: 10px; font-weight: 760;
}}
QWidget#FansWorkspace QPushButton[fanPresetButton='true']:hover {{
    background: {c['control_hover']}; border-color: {c['border']};
}}
QWidget#FansWorkspace QPushButton[fanPresetButton='true']:checked {{
    background: {c['blue_soft']}; color: {c['blue']}; border-color: {c['blue_border']};
}}
QWidget#FansWorkspace QLabel[fanStageNote='true'] {{ color: {c['subtle']}; font-size: 9px; }}
QWidget#FansWorkspace QFrame[curveQuickState='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 10px;
}}
QWidget#FansWorkspace QFrame[curveStage='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 12px;
}}
QWidget#FansWorkspace QLabel[fanResponseEyebrow='true'] {{
    color: {c['subtle']}; font-size: 9px; font-weight: 800; letter-spacing: .45px;
}}
QWidget#FansWorkspace QLabel[fanResponseLive='true'] {{
    color: {c['text']}; font-size: 16px; font-weight: 830;
}}
QWidget#FansWorkspace QLabel[fanResponseArrow='true'] {{
    color: {c['blue']}; font-size: 16px; font-weight: 850;
}}
QWidget#FansWorkspace QFrame[fanResponseStep='true'] {{
    background: {c['control']}; border: 1px solid {c['border_soft']}; border-radius: 9px;
}}
QWidget#FansWorkspace QFrame[fanResponseStepState='active'] {{
    background: {c['cyan_soft']}; border-color: {c['cyan_border']};
}}
QWidget#FansWorkspace QFrame[fanResponseStepState='passed'] {{
    background: {c['panel_alt']}; border-color: {c['border_soft']};
}}
QWidget#FansWorkspace QLabel[fanResponseRange='true'] {{
    color: {c['muted']}; font-size: 9px; font-weight: 720;
}}
QWidget#FansWorkspace QFrame[fanResponseStepState='active'] QLabel[fanResponseRange='true'] {{
    color: {c['cyan']};
}}
QWidget#FansWorkspace QLabel[fanResponseDuty='true'] {{
    color: {c['text']}; font-size: 14px; font-weight: 840;
}}
QWidget#FansWorkspace QFrame[curveControlPanel='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 12px;
}}
QWidget#FansWorkspace QFrame[curvePointV2='true'] {{
    background: {c['control']}; border: 1px solid {c['border_soft']}; border-radius: 10px;
}}
QWidget#FansWorkspace QLabel[curvePointIndex='true'] {{
    background: {c['purple_soft']}; color: {c['purple']}; border: 1px solid {c['purple_border']};
    border-radius: 8px; padding: 4px 7px; font-size: 9px; font-weight: 850;
}}
QWidget#FansWorkspace QLabel[curvePointTitle='true'] {{ color: {c['text']}; font-size: 12px; font-weight: 780; }}
QWidget#FansWorkspace QFrame[fanDriverStrip='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 13px;
}}
QWidget#FansWorkspace QFrame[fanDriverDetails='true'] {{
    background: {c['control']}; border: 1px solid {c['border_soft']}; border-radius: 11px;
}}
QWidget#FansWorkspace QLabel[driverModeValue='true'] {{ color: {c['text']}; font-size: 13px; font-weight: 800; }}
QWidget#FansWorkspace QLabel[driverModeDetail='true'] {{ color: {c['muted']}; font-size: 9px; }}
QWidget#FansWorkspace QLabel[fanStatusChip='true'] {{
    background: {c['neutral_soft']}; color: {c['muted']}; border: 1px solid {c['neutral_border']};
    border-radius: 8px; padding: 4px 7px; font-size: 9px; font-weight: 800;
}}
QWidget#FansWorkspace QLabel[fanStatusChipTone='green'] {{
    background: {c['green_soft']}; color: {c['green']}; border-color: {c['green_border']};
}}
QWidget#FansWorkspace QLabel[fanStatusChipTone='blue'] {{
    background: {c['blue_soft']}; color: {c['blue']}; border-color: {c['blue_border']};
}}
QWidget#FansWorkspace QLabel[fanStatusChipTone='orange'] {{
    background: {c['orange_soft']}; color: {c['orange']}; border-color: {c['orange_border']};
}}
QWidget#FansWorkspace QLabel[fanStatusChipTone='gray'] {{
    background: {c['neutral_soft']}; color: {c['subtle']}; border-color: {c['neutral_border']};
}}
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

/* Fan command deck — shares the topology language of Compute Units. */
QWidget#FansWorkspace QFrame[fanCommandDeck='true'] {{
    background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 18px;
}}
QWidget#FansWorkspace QFrame[fanTelemetryBand='true'],
QWidget#FansWorkspace QFrame[fanControlBoard='true'],
QWidget#FansWorkspace QFrame[fanSystemRail='true'] {{
    background: transparent; border: none;
}}
QWidget#FansWorkspace QFrame[fanDeckDivider='true'] {{
    background: {c['border_soft']}; border: none; min-height: 1px; max-height: 1px;
}}
QWidget#FansWorkspace QLabel[fanDeckTitle='true'] {{
    color: {c['text']}; font-size: 14px; font-weight: 830;
}}
QWidget#FansWorkspace QFrame[fanSignalTile='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 12px;
}}
QWidget#FansWorkspace QFrame[fanSignalTile='true']:hover {{
    background: {c['panel_raised']}; border-color: {c['border_strong']};
}}
QWidget#FansWorkspace QLabel[fanSignalMarker='true'] {{
    border: none; border-radius: 4px; background: {c['blue']};
}}
QWidget#FansWorkspace QLabel[fanSignalMarker='true'][fanSignalTone='green'] {{ background: {c['green']}; }}
QWidget#FansWorkspace QLabel[fanSignalMarker='true'][fanSignalTone='cyan'] {{ background: {c['cyan']}; }}
QWidget#FansWorkspace QLabel[fanSignalMarker='true'][fanSignalTone='orange'] {{ background: {c['orange']}; }}
QWidget#FansWorkspace QLabel[fanSignalMarker='true'][fanSignalTone='purple'] {{ background: {c['purple']}; }}
QWidget#FansWorkspace QLabel[fanSignalLabel='true'] {{
    color: {c['muted']}; font-size: 8px; font-weight: 760;
}}
QWidget#FansWorkspace QLabel[fanSignalValue='true'] {{
    color: {c['text']}; font-size: 16px; font-weight: 840;
}}
QWidget#FansWorkspace QLabel[fanSignalDetail='true'] {{
    color: {c['subtle']}; font-size: 8px;
}}
QWidget#FansWorkspace QFrame[fanModeRail='true'] {{
    background: {c['neutral_soft']}; border: 1px solid {c['border_soft']}; border-radius: 12px;
}}
QWidget#FansWorkspace QPushButton[fanModeButton='true'] {{
    background: transparent; color: {c['muted']}; border: 1px solid transparent;
    border-radius: 9px; min-height: 34px; padding: 5px 12px; font-size: 10px; font-weight: 820;
}}
QWidget#FansWorkspace QPushButton[fanModeButton='true']:hover {{
    background: {c['panel_raised']}; color: {c['text']};
}}
QWidget#FansWorkspace QPushButton[fanModeButton='true'][fanModeKind='manual']:checked {{
    background: {c['blue_soft']}; color: {c['blue']}; border-color: {c['blue_border']};
}}
QWidget#FansWorkspace QPushButton[fanModeButton='true'][fanModeKind='curve']:checked {{
    background: {c['cyan_soft']}; color: {c['cyan']}; border-color: {c['cyan_border']};
}}
QWidget#FansWorkspace QFrame[fanChannelBay='true'],
QWidget#FansWorkspace QFrame[fanCurveHeader='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 12px;
}}
QWidget#FansWorkspace QFrame[fanOutputControl='true'] {{
    background: {c['neutral_soft']}; border: 1px solid {c['border_soft']}; border-radius: 12px;
}}
QWidget#FansWorkspace QFrame[fanOutputControl='true'] QSlider::sub-page:horizontal {{
    background: {c['blue']}; border-radius: 3px;
}}
QWidget#FansWorkspace QFrame[fanOutputControl='true'] QSlider::handle:horizontal {{
    background: {c['panel']}; border: 2px solid {c['blue']};
    width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
}}
QWidget#FansWorkspace QFrame[fanOutputControl='true'] QSpinBox {{
    background: {c['panel_raised']}; color: {c['blue']};
    border: 1px solid {c['blue_border']}; border-radius: 8px; font-weight: 820;
}}
QWidget#FansWorkspace QFrame[fanDutyDial='true'] {{
    background: {c['neutral_soft']}; border: 1px solid {c['border_soft']}; border-radius: 14px;
}}
QWidget#FansWorkspace QLabel[fanDutyEyebrow='true'] {{
    color: {c['blue']}; font-size: 9px; font-weight: 840; letter-spacing: .65px;
}}
QWidget#FansWorkspace QLabel[fanDutyChannel='true'] {{
    color: {c['text']}; font-size: 14px; font-weight: 830;
}}
QWidget#FansWorkspace QLabel[fanDutyRaw='true'] {{
    color: {c['subtle']}; font-size: 9px;
}}
QWidget#FansWorkspace QFrame[fanManualPanel='true'] {{
    background: transparent; border: none;
}}
QWidget#FansWorkspace QPushButton[fanPresetButton='true'] {{
    background: {c['panel_alt']}; color: {c['muted']}; border: 1px solid {c['border_soft']};
    border-radius: 10px; min-height: 34px; padding: 5px 9px; font-size: 9px; font-weight: 820;
}}
QWidget#FansWorkspace QPushButton[fanPresetButton='true']:hover {{
    background: {c['panel_raised']}; color: {c['text']}; border-color: {c['border_strong']};
}}
QWidget#FansWorkspace QPushButton[fanPresetButton='true'][fanPresetTone='green']:checked {{
    background: {c['green_soft']}; color: {c['green']}; border-color: {c['green_border']};
}}
QWidget#FansWorkspace QPushButton[fanPresetButton='true'][fanPresetTone='cyan']:checked {{
    background: {c['cyan_soft']}; color: {c['cyan']}; border-color: {c['cyan_border']};
}}
QWidget#FansWorkspace QPushButton[fanPresetButton='true'][fanPresetTone='blue']:checked {{
    background: {c['blue_soft']}; color: {c['blue']}; border-color: {c['blue_border']};
}}
QWidget#FansWorkspace QPushButton[fanPresetButton='true'][fanPresetTone='orange']:checked {{
    background: {c['blue_soft']}; color: {c['blue']}; border-color: {c['blue_border']};
}}
QWidget#FansWorkspace QFrame[curveStage='true'] {{
    background: {c['neutral_soft']}; border: 1px solid {c['border_soft']}; border-radius: 12px;
}}
QWidget#FansWorkspace QFrame[fanSystemRail='true'] QLabel[driverModeValue='true'] {{
    color: {c['text']}; font-size: 11px; font-weight: 820;
}}
QWidget#FansWorkspace QFrame[fanSystemRail='true'] QLabel[driverModeDetail='true'] {{
    color: {c['subtle']}; font-size: 8px;
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
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _finite_number(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _pwm_to_percent(value) -> int | None:
    if value is None:
        return None
    return max(0, min(100, round(_integer(value) * 100 / 255)))


def _percent_to_pwm(value) -> int:
    return max(0, min(255, round(_integer(value) * 255 / 100)))


def _rpm_text(value: object) -> str:
    number = _finite_number(value)
    return f"{int(number):,} RPM" if number is not None else "-- RPM"


def _percent_text(value: object) -> str:
    return f"{_integer(value)} %" if value is not None else "-- %"


def _temperature_text(value: float | None) -> str:
    return f"{value:.1f} °C" if value is not None else "-- °C"


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
        painter.drawText(rect.adjusted(0, 8, 0, -12), Qt.AlignmentFlag.AlignCenter, f"{round(self._display_value)}%")


class CoolingStat(QFrame):
    """One signal cell in the fan command deck."""

    def __init__(self, label: str, value: str, detail: str, parent=None):
        super().__init__(parent)
        signal = {
            "RPM observed": "green",
            "Current duty": "cyan",
            "GPU temperature": "orange",
            "CPU temperature": "purple",
        }.get(label, "blue")
        self.setProperty("fanSignalTile", True)
        self.setProperty("fanSignalTone", signal)
        self.setMinimumHeight(76)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 9, 11, 9)
        layout.setSpacing(2)
        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(6)
        marker = QLabel("")
        marker.setProperty("fanSignalMarker", True)
        marker.setProperty("fanSignalTone", signal)
        marker.setFixedSize(8, 8)
        heading.addWidget(marker, 0, Qt.AlignmentFlag.AlignVCenter)
        self.label = QLabel(tr(label))
        self.label.setProperty("fanSignalLabel", True)
        self.label.setWordWrap(True)
        heading.addWidget(self.label, 1)
        layout.addLayout(heading)
        self.value = QLabel(tr(value))
        self.value.setProperty("fanSignalValue", True)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail = QLabel(tr(detail))
        self.detail.setProperty("fanSignalDetail", True)
        self.detail.setWordWrap(True)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_values(self, value: str, detail: str | None = None) -> None:
        self.value.setText(tr(value))
        if detail is not None:
            self.detail.setText(tr(detail))


class FanStatusChip(QLabel):
    """A muted status token that can change semantic tone without restyling callers."""

    def __init__(self, text: str = "Checking", tone: str = "gray", parent=None):
        super().__init__(tr(text), parent)
        self.setProperty("fanStatusChip", True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        normalized = tone if tone in {"green", "blue", "orange", "gray"} else "gray"
        self.setProperty("fanStatusChipTone", normalized)
        self.style().unpolish(self)
        self.style().polish(self)


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
        self.marker = QLabel(index)
        self.marker.setProperty("curvePointIndex", True)
        self.marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.marker.setFixedWidth(28)
        row.addWidget(self.marker)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        self.title_label = QLabel(tr(title))
        self.title_label.setProperty("curvePointTitle", True)
        hint = QLabel(tr("threshold / duty"))
        hint.setProperty("fieldHint", True)
        hint.setWordWrap(True)
        copy.addWidget(self.title_label)
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

    def set_index(self, index: int) -> None:
        self.marker.setText(str(int(index)))
        self.title_label.setText(tr_format("Point {index}", index=int(index)))


class FanCurveScale(QWidget):
    """Paint the daemon's discrete response against explicit thermal axes."""

    MIN_TEMPERATURE = 30.0
    MAX_TEMPERATURE = 95.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points: list[tuple[int, int]] = [(50, 70), (65, 100), (70, 100)]
        self.live_temperature: float | None = None
        self.live_duty: int | None = None
        self.enabled = False
        self.compact = False
        self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_state(
        self,
        points: list[tuple[int, int]],
        temperature: float | None,
        duty: int | None,
        enabled: bool,
    ) -> None:
        self.points = sorted(points, key=lambda item: item[0]) or [(50, 70)]
        self.live_temperature = temperature
        self.live_duty = duty
        self.enabled = bool(enabled)
        self.update()

    def set_compact(self, compact: bool) -> None:
        self.compact = bool(compact)
        self.setMinimumHeight(176 if self.compact else 210)
        self.updateGeometry()
        self.update()

    @classmethod
    def _bounded_temperature(cls, temperature: float) -> float:
        return max(cls.MIN_TEMPERATURE, min(cls.MAX_TEMPERATURE, float(temperature)))

    @staticmethod
    def _bounded_duty(duty: float) -> float:
        return max(0.0, min(100.0, float(duty)))

    def paintEvent(self, event) -> None:  # pragma: no cover - visual rendering
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        left = 38.0 if self.compact else 46.0
        top = 16.0
        right = 13.0
        bottom = 31.0
        plot = QRectF(
            left,
            top,
            max(40.0, self.width() - left - right),
            max(50.0, self.height() - top - bottom),
        )

        def x_for(temperature: float) -> float:
            bounded = self._bounded_temperature(temperature)
            return plot.left() + (bounded - self.MIN_TEMPERATURE) / (
                self.MAX_TEMPERATURE - self.MIN_TEMPERATURE
            ) * plot.width()

        def y_for(duty: float) -> float:
            return plot.bottom() - self._bounded_duty(duty) / 100.0 * plot.height()

        grid_pen = QPen(QColor(COLORS["chart_grid"]), 1)
        painter.setPen(grid_pen)
        for duty in (0, 25, 50, 75, 100):
            y = y_for(duty)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        for temperature in (30, 45, 60, 75, 90):
            x = x_for(temperature)
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

        axis_color = QColor(COLORS["subtle"])
        painter.setPen(axis_color)
        font = painter.font()
        font.setPointSize(7 if self.compact else 8)
        painter.setFont(font)
        for duty in (0, 25, 50, 75, 100):
            painter.drawText(
                QRectF(0, y_for(duty) - 8, left - 7, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{duty}%",
            )
        for temperature in (30, 45, 60, 75, 90):
            painter.drawText(
                QRectF(x_for(temperature) - 20, plot.bottom() + 7, 40, 17),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                f"{temperature}°",
            )

        points = self.points or [(50, 70)]
        line_color = QColor(COLORS["cyan"] if self.enabled else COLORS["purple"])
        line_pen = QPen(
            line_color,
            3,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(line_pen)
        previous_duty = points[0][1]
        cursor = QPointF(plot.left(), y_for(previous_duty))
        for threshold, duty in points[1:]:
            x = x_for(threshold)
            painter.drawLine(cursor, QPointF(x, y_for(previous_duty)))
            painter.drawLine(QPointF(x, y_for(previous_duty)), QPointF(x, y_for(duty)))
            cursor = QPointF(x, y_for(duty))
            previous_duty = duty
        painter.drawLine(cursor, QPointF(plot.right(), y_for(previous_duty)))

        painter.setBrush(QColor(COLORS["panel_raised"]))
        painter.setPen(QPen(line_color, 2))
        for threshold, duty in points:
            painter.drawEllipse(QPointF(x_for(threshold), y_for(duty)), 4.5, 4.5)

        if self.live_temperature is not None:
            live_x = x_for(self.live_temperature)
            live_duty = self.live_duty if self.live_duty is not None else points[0][1]
            painter.setPen(QPen(QColor(COLORS["orange"]), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(live_x, plot.top()), QPointF(live_x, plot.bottom()))
            painter.setPen(QPen(QColor(COLORS["panel"]), 2))
            painter.setBrush(QColor(COLORS["orange"]))
            painter.drawEllipse(QPointF(live_x, y_for(live_duty)), 5.5, 5.5)


class FanCurvePlot(QWidget):
    """Scaled thermal reference for the exact step response of the daemon."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = [(50, 70), (65, 100), (70, 100)]
        self.live_temperature: float | None = None
        self.live_duty: int | None = None
        self.enabled = False
        self.compact = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        live_row = QHBoxLayout()
        live_row.setContentsMargins(1, 0, 1, 0)
        live_row.setSpacing(8)
        self.live_title = QLabel(tr("Response preview"))
        self.live_title.setProperty("fanResponseEyebrow", True)
        live_row.addWidget(self.live_title)
        live_row.addStretch(1)
        self.live_temperature_label = QLabel("GPU -- °C")
        self.live_temperature_label.setProperty("fanResponseLive", True)
        live_row.addWidget(self.live_temperature_label)
        arrow = QLabel("→")
        arrow.setProperty("fanResponseArrow", True)
        live_row.addWidget(arrow)
        self.live_duty_label = QLabel("PWM -- %")
        self.live_duty_label.setProperty("fanResponseLive", True)
        live_row.addWidget(self.live_duty_label)
        root.addLayout(live_row)

        self.ranges_title = QLabel(tr("Thermal response scale"))
        self.ranges_title.setProperty("fanResponseEyebrow", True)
        root.addWidget(self.ranges_title)
        self.scale = FanCurveScale(self)
        root.addWidget(self.scale)
        self.scale_caption = QLabel(tr("GPU temperature → · PWM duty ↑ · exact step response"))
        self.scale_caption.setProperty("fanStageNote", True)
        self.scale_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scale_caption.setWordWrap(True)
        root.addWidget(self.scale_caption)
        self._render()

    def set_curve(self, points: list[tuple[int, int]]) -> None:
        self.points = sorted(points, key=lambda item: item[0]) or [(50, 70)]
        self._render()

    def set_live(self, temperature: float | None, duty: int | None) -> None:
        self.live_temperature = temperature
        self.live_duty = duty
        self._render()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self._render()

    def set_compact(self, compact: bool) -> None:
        self.compact = bool(compact)
        self.live_title.setVisible(not self.compact)
        self.scale.set_compact(self.compact)
        self.updateGeometry()

    def retranslate(self) -> None:
        self.live_title.setText(tr("Live response" if self.enabled else "Response preview"))
        self.ranges_title.setText(tr("Thermal response scale"))
        self.scale_caption.setText(tr("GPU temperature → · PWM duty ↑ · exact step response"))
        self._render()

    def _render(self) -> None:
        self.live_title.setText(tr("Live response" if self.enabled else "Response preview"))
        if self.live_temperature is None:
            self.live_temperature_label.setText("GPU -- °C")
        else:
            self.live_temperature_label.setText(f"GPU {self.live_temperature:.1f} °C")
        if self.live_duty is None:
            self.live_duty_label.setText("PWM -- %")
        else:
            self.live_duty_label.setText(f"PWM {int(self.live_duty)} %")
        self.scale.set_state(
            self.points,
            self.live_temperature,
            self.live_duty,
            self.enabled,
        )


class FanModeStack(QStackedWidget):
    """A mode stack whose height follows only the page currently in use."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Fixed means “use the current page's natural hint”, not a manually
        # cached pixel height.  It keeps a maximized window from donating all
        # of its spare vertical room to the slider.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.currentChanged.connect(lambda _index: self.updateGeometry())

    def sizeHint(self):  # noqa: N802 - Qt API name
        current = self.currentWidget()
        return current.sizeHint() if current is not None else super().sizeHint()

    def minimumSizeHint(self):  # noqa: N802 - Qt API name
        current = self.currentWidget()
        return current.minimumSizeHint() if current is not None else super().minimumSizeHint()


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

    @staticmethod
    def _reported_paths(sensors: dict, field: str) -> tuple[str, ...]:
        """Return only non-empty paths published by the last sensor scan.

        This dialog is informational, so it must not turn an absent hwmon
        route into an attractive but fictitious ``hwmonX`` path.  Entries are
        deliberately read from the repository snapshot rather than guessed
        from a channel number.
        """
        values: list[str] = []
        for entry in sensors.get(field, []):
            if not isinstance(entry, dict):
                continue
            value = str(entry.get("path", entry.get("pwm_path", "")) or "").strip()
            if value and value not in values:
                values.append(value)
        return tuple(values)

    @staticmethod
    def _existing_paths(candidates: tuple[Path, ...]) -> tuple[str, ...]:
        """List real local artifacts without claiming a standard path exists."""
        found: list[str] = []
        for candidate in candidates:
            try:
                if candidate.exists():
                    found.append(str(candidate))
            except OSError:
                continue
        return tuple(found)

    @staticmethod
    def _line_or_unavailable(values: tuple[str, ...], unavailable: str) -> str:
        return "\n".join(values) if values else tr(unavailable)

    def _build_pages(self, state: dict) -> list[tuple[str, QWidget]]:
        """Build a host-specific, read-only diagnostic report.

        Older revisions displayed every distribution's *possible* paths and
        always included systemd units.  That was misleading on OpenRC and
        made an undiscovered NCT device look configured.  The report now
        distinguishes scan evidence from guidance and never performs an
        installation, module load, service action, or file mutation.
        """
        state = _dict(state)
        sensors = _dict(state.get("sensores"))
        modules = _dict(state.get("modulos"))
        reported_hwmon = str(sensors.get("path") or "").strip()
        pwm_paths = self._reported_paths(sensors, "pwms")
        fan_pwm_paths = self._reported_paths(sensors, "fans")
        all_pwm_paths = tuple(dict.fromkeys((*pwm_paths, *fan_pwm_paths)))

        helper_candidates: list[Path] = [
            Path("/usr/libexec/bc250-control-center/bc250-fan-pwm-helper"),
            Path("/usr/local/libexec/bc250-control-center/bc250-fan-pwm-helper"),
        ]
        configured_helper = os.environ.get("BC250_FAN_PWM_HELPER", "").strip()
        if configured_helper:
            try:
                helper_candidates.insert(0, Path(configured_helper))
            except (OSError, ValueError):
                pass
        installed_helpers = self._existing_paths(tuple(helper_candidates))
        configuration_files = self._existing_paths((
            Path("/etc/modprobe.d/nct6683.conf"),
            Path("/etc/modprobe.d/nct6687.conf"),
            Path("/etc/modprobe.d/sensors.conf"),
            Path("/etc/modules-load.d/nct6683.conf"),
            Path("/etc/modules-load.d/nct6687.conf"),
            Path("/etc/modules-load.d/99-sensors.conf"),
        ))

        init = detect_init_manager()
        if init.kind == "openrc" and init.available:
            service_files = self._existing_paths((
                Path("/etc/init.d/nct6687-load"),
                Path("/etc/conf.d/nct6687-load"),
                Path("/usr/local/sbin/bc250-load-nct6687"),
            ))
            persistence_sections = [
                PathsSection(
                    "OpenRC persistence",
                    "OpenRC is active. These commands are read-only checks; this window will not run them.",
                    (
                        ("Active manager", "OpenRC · default runlevel"),
                        ("Detected service files", self._line_or_unavailable(
                            service_files,
                            "No BC250 NCT6687 OpenRC service file is currently detected.",
                        )),
                        ("Status command", "rc-service nct6687-load status"),
                        ("Runlevel command", "rc-update show default"),
                    ),
                ),
            ]
        elif init.kind == "systemd" and init.available:
            service_files = self._existing_paths((
                Path("/etc/systemd/system/nct6687-load.service"),
                Path("/usr/local/sbin/bc250-load-nct6687"),
            ))
            persistence_sections = [
                PathsSection(
                    "systemd persistence",
                    "systemd is active. These commands are read-only checks; this window will not run them.",
                    (
                        ("Active manager", "systemd"),
                        ("Detected unit files", self._line_or_unavailable(
                            service_files,
                            "No BC250 NCT6687 systemd unit file is currently detected.",
                        )),
                        ("Status command", "systemctl status nct6687-load.service --no-pager"),
                        ("Journal command", "journalctl -b -u nct6687-load.service --no-pager"),
                    ),
                ),
            ]
        else:
            persistence_sections = [
                PathsSection(
                    "Persistence unavailable",
                    "No supported active init manager was detected. This window will not suggest a service command.",
                    (
                        ("Detection", str(init.detail or tr("No supported active init manager was detected."))),
                        ("Current capability", "Live sensor inspection remains read-only."),
                    ),
                ),
            ]

        detected = self._page(
            [
                PathsSection(
                    "Live Linux detection",
                    "Values below are evidence from the latest NCT scan. Missing data is shown as missing; no path is guessed.",
                    (
                        ("Chip", str(sensors.get("chip") or tr("Not detected"))),
                        ("Hwmon route", reported_hwmon or tr("No NCT hwmon route was reported by the latest scan.")),
                        ("Loaded modules", f"nct6683={bool(modules.get('nct6683'))} · nct6687={bool(modules.get('nct6687'))}"),
                        ("Reported PWM files", self._line_or_unavailable(
                            all_pwm_paths,
                            "No PWM file was reported by the latest scan.",
                        )),
                        ("Installed PWM helpers", self._line_or_unavailable(
                            installed_helpers,
                            "No installed root PWM helper was detected.",
                        )),
                        ("Detected fan configuration", self._line_or_unavailable(
                            configuration_files,
                            "No BC250 fan configuration file is currently detected.",
                        )),
                    ),
                ),
            ]
        )
        verification = self._page(
            [
                PathsSection(
                    "Read-only verification",
                    "Copy a command only when you need more diagnostics. None of these commands changes fan mode, duty, modules, or services.",
                    (
                        ("Modules", 'lsmod | grep -E "nct6683|nct6687"'),
                        ("Driver metadata", "modinfo nct6687"),
                        ("Sensors", 'sensors | sed -n "/nct668/,+45p"'),
                        ("Hwmon files", "find /sys/class/hwmon -maxdepth 2 -name 'pwm*_enable' -o -name 'fan*_input'"),
                    ),
                ),
            ]
        )
        persistence = self._page(persistence_sections)
        return [
            (tr("Detected"), detected),
            (tr("Persistence"), persistence),
            (tr("Verification"), verification),
        ]


class FansPage(QWidget):
    # Emitted when the user wants to change the optional user-daemon settings.
    # The application shell owns SettingsDialog, so the fan page never creates
    # a second settings window or bypasses the normal navigation lifecycle.
    settings_requested = pyqtSignal(str)

    def apply_appearance(self) -> None:
        if hasattr(self, "content"):
            self.content.setStyleSheet(fans_stylesheet())
            self.content.update()

    """Thermal workstation backed by the existing validated R64 fan repository."""

    def __init__(self, controller, parent: QWidget | None = None, *, activity_service=None, settings_service=None):
        super().__init__(parent)
        self.controller = controller
        self.activity_service = activity_service
        self.settings_service = settings_service
        self.current_state: dict = {}
        self._updates_active = False
        self._state_cache = state_cache_for(controller)
        self._background = BackgroundExecutor(self)
        self._event_sequence = 0
        self._curve_config_busy = False
        self._curve_config_loaded = False
        self._fan_preset_config: dict = {}
        self.performance_state: dict = {}
        self.gpu_state: dict = {}
        self._worker: FanTask | None = None
        self._busy = False
        self._summary_columns = 5
        self._metric_columns = 0
        self._curve_columns = 0
        self._driver_action_columns = 0
        self._manual_workspace_columns = 0
        self._curve_loading = False
        self._curve_dirty = False
        self._curve_preset = "custom"
        self._last_curve_apply = 0.0
        self._last_curve_percent: int | None = None
        self._last_pwm_text = "--"
        self._refresh_error = ""
        self._preferred_pwm = 2
        self._curve_target_pwm = 2
        self._staged_pwm_percent = 70
        self._control_mode = "manual"
        self._curve_editor_open = False
        self._driver_details_open = False
        self._deck_sync_queued = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.content = QWidget()
        self.content.setObjectName("FansWorkspace")
        self.content.setStyleSheet(fans_stylesheet())
        configure_responsive_scroll_area(self.scroll, self.content)
        self.content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(18, 14, 18, 24)
        layout.setSpacing(12)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll)

        # This invisible compatibility header keeps the established refresh and
        # preparation signals available without consuming vertical space.  The
        # new cooling overview owns their visible counterparts.
        self.header = ControlPageHeader(
            "THERMAL WORKSTATION",
            "Fans and PWM",
            "A single workspace for live cooling telemetry, explicit PWM writes, automatic response curves, and Linux driver integration.",
            mode_text="● LIVE SESSION",
            action_text="Prepare PWM control",
            action_icon="download_blue",
            parent=self.content,
        )
        self.header.refresh_requested.connect(self._manual_refresh)
        self.header.action_requested.connect(self.prepare_pwm_driver)
        self.header.hide()

        # Retain these non-rendered compatibility objects for integrations that
        # already feed them.  The redesigned overview below is the only live
        # telemetry surface presented to the user.
        self.summary_strip = ThermalStatusRail(self.content)
        self.summary_strip.hide()

        # A single command deck replaces the former stack of unrelated cards.
        # Telemetry, control and driver state now read as one topology surface,
        # matching the visual hierarchy of the Compute Units editor.
        self.fan_workspace = QFrame()
        self.fan_workspace.setObjectName("fan-command-deck")
        self.fan_workspace.setProperty("fanCommandDeck", True)
        self.fan_workspace.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        deck = QVBoxLayout(self.fan_workspace)
        deck.setContentsMargins(10, 10, 10, 10)
        deck.setSpacing(9)
        deck.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.overview_card = self._build_overview_card()
        self.telemetry_card = self.overview_card
        deck.addWidget(self.overview_card)

        upper_divider = QFrame()
        upper_divider.setProperty("fanDeckDivider", True)
        deck.addWidget(upper_divider)

        self.control_surface = self._build_control_surface()
        deck.addWidget(self.control_surface)

        lower_divider = QFrame()
        lower_divider.setProperty("fanDeckDivider", True)
        deck.addWidget(lower_divider)

        self.driver_card = self._build_compact_driver_card()
        deck.addWidget(self.driver_card)
        layout.addWidget(self.fan_workspace)

        # Multi-channel diagnostic row widgets remain as a data-only
        # compatibility seam; the primary UI now selects the same channel in
        # one place rather than rendering a second competing channel table.
        self.channels_card = QWidget(self.content)
        self.channels_card.hide()
        self.channel_rows: list[FanChannelRow] = []
        layout.addStretch(1)

        self._apply_curve_config({})
        self._reflow(1400)
        self._sync_command_deck_height()
        QTimer.singleShot(0, self._sync_command_deck_height)
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

    def _build_overview_card(self) -> QFrame:
        """Build the signal band at the top of the unified fan deck."""
        card = QFrame()
        card.setObjectName("fan-live-overview")
        card.setProperty("fanTelemetryBand", True)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root = QVBoxLayout(card)
        root.setContentsMargins(3, 2, 3, 3)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(IconBadge("fan_cyan", COLORS["cyan_soft"], 30, radius=9))
        self.overview_title = QLabel(tr("Live cooling"))
        self.overview_title.setProperty("fanDeckTitle", True)
        self.overview_title.setWordWrap(True)
        header.addWidget(self.overview_title, 1)
        self.overview_status = FanStatusChip("Checking", "gray")
        header.addWidget(self.overview_status, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)

        # Kept as non-rendered compatibility data for diagnostics and tests.
        self.overview_detail = QLabel(tr("Waiting for NCT telemetry"))
        self.overview_detail.hide()
        self.overview_balance_spacer = QWidget()
        self.overview_balance_spacer.hide()

        self.metrics_grid = QGridLayout()
        self.metrics_grid.setContentsMargins(0, 0, 0, 0)
        self.metrics_grid.setHorizontalSpacing(8)
        self.metrics_grid.setVerticalSpacing(8)
        self.rpm_metric = CoolingStat("RPM observed", "-- RPM", "No reporting channel")
        self.duty_metric = CoolingStat("Current duty", "-- %", "No PWM channel")
        self.gpu_temp_metric = CoolingStat("GPU temperature", "-- °C", "Curve input")
        self.cpu_temp_metric = CoolingStat("CPU temperature", "-- °C", "Package sensor")
        self.metric_tiles = [
            self.rpm_metric,
            self.duty_metric,
            self.gpu_temp_metric,
            self.cpu_temp_metric,
        ]
        root.addLayout(self.metrics_grid)
        return card

    def _build_control_surface(self) -> QFrame:
        """Build the mode router and its two hardware-control surfaces."""
        card = QFrame()
        card.setObjectName("fan-control-surface")
        card.setProperty("fanControlBoard", True)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root = QVBoxLayout(card)
        root.setContentsMargins(3, 1, 3, 2)
        root.setSpacing(9)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        # The workspace title and staging instruction repeated information
        # already present in the selected mode/action buttons.  Keep the
        # mutable status value for diagnostics but reclaim that vertical space.
        self.control_status_chip = FanStatusChip("Checking", "gray")
        self.control_status_chip.hide()

        mode_switch = QFrame()
        mode_switch.setProperty("fanModeRail", True)
        self.mode_switch = mode_switch
        switch_layout = QHBoxLayout(mode_switch)
        switch_layout.setContentsMargins(4, 4, 4, 4)
        switch_layout.setSpacing(4)
        self.manual_mode_button = QPushButton(tr("Manual"))
        self.manual_mode_button.setObjectName("fan-mode-manual")
        self.manual_mode_button.setProperty("fanModeButton", True)
        self.manual_mode_button.setProperty("fanModeKind", "manual")
        self.manual_mode_button.setCheckable(True)
        self.curve_mode_button = QPushButton(tr("Automatic curve"))
        self.curve_mode_button.setObjectName("fan-mode-curve")
        self.curve_mode_button.setProperty("fanModeButton", True)
        self.curve_mode_button.setProperty("fanModeKind", "curve")
        self.curve_mode_button.setCheckable(True)
        self.fan_mode_group = QButtonGroup(self)
        self.fan_mode_group.setExclusive(True)
        self.fan_mode_group.addButton(self.manual_mode_button)
        self.fan_mode_group.addButton(self.curve_mode_button)
        self.manual_mode_button.clicked.connect(
            lambda checked: self._set_control_mode("manual") if checked else None
        )
        self.curve_mode_button.clicked.connect(
            lambda checked: self._set_control_mode("curve") if checked else None
        )
        switch_layout.addWidget(self.manual_mode_button, 1)
        switch_layout.addWidget(self.curve_mode_button, 1)
        root.addWidget(mode_switch)

        self.control_stack = FanModeStack()
        self.manual_card = self._build_cooling_manual_page()
        self.curve_card = self._build_cooling_curve_page()
        self.control_stack.addWidget(self.manual_card)
        self.control_stack.addWidget(self.curve_card)
        root.addWidget(self.control_stack)
        # Do not trigger a reflow here: the driver strip is constructed by the
        # caller immediately afterwards.  The full initial reflow happens once
        # the complete page tree exists.
        self.manual_mode_button.setChecked(True)
        self.control_stack.setCurrentWidget(self.manual_card)
        return card

    def _make_channel_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("fan-channel-selector")
        combo.setToolTip(tr("Selecting a channel only stages the target; it does not write hardware."))
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setMaxVisibleItems(8)
        popup = QListView(combo)
        popup.setUniformItemSizes(True)
        popup.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        popup.setAutoFillBackground(True)
        popup.viewport().setAutoFillBackground(True)
        palette = popup.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(COLORS["panel"]))
        palette.setColor(QPalette.ColorRole.Window, QColor(COLORS["panel"]))
        palette.setColor(QPalette.ColorRole.Text, QColor(COLORS["text"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["selection"]))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(COLORS["text"]))
        popup.setPalette(palette)
        popup.viewport().setPalette(palette)
        combo.setPalette(palette)
        combo.setStyleSheet(scale_stylesheet(f"""
            QComboBox {{
                background: {COLORS['control']}; color: {COLORS['text']};
                border: 1px solid {COLORS['border']}; border-radius: 8px;
                padding: 5px 9px; min-height: 27px;
            }}
            QComboBox:focus {{ border-color: {COLORS['focus']}; }}
            QComboBox QAbstractItemView, QListView {{
                background: {COLORS['panel']}; color: {COLORS['text']};
                border: 1px solid {COLORS['border']}; border-radius: 9px;
                padding: 4px; outline: none;
            }}
            QComboBox QAbstractItemView::item, QListView::item {{
                background: {COLORS['panel']}; color: {COLORS['text']};
                min-height: 30px; padding: 5px 9px; border-radius: 6px;
            }}
            QComboBox QAbstractItemView::item:selected, QListView::item:selected {{
                background: {COLORS['selection']}; color: {COLORS['text']};
            }}
            QComboBox QAbstractItemView::item:hover, QListView::item:hover {{
                background: {COLORS['control_hover']}; color: {COLORS['text']};
            }}
        """))
        combo.setView(popup)
        combo.currentIndexChanged.connect(self._selected_channel_changed)
        return combo

    def _build_cooling_manual_page(self) -> QFrame:
        page = QFrame()
        page.setProperty("fanModePage", True)
        page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.manual_workspace = QGridLayout()
        self.manual_workspace.setContentsMargins(0, 0, 0, 0)
        self.manual_workspace.setHorizontalSpacing(10)
        self.manual_workspace.setVerticalSpacing(10)

        self.duty_panel = QFrame()
        self.duty_panel.setProperty("fanDutyDial", True)
        self.duty_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        duty_layout = QVBoxLayout(self.duty_panel)
        duty_layout.setContentsMargins(12, 10, 12, 10)
        duty_layout.setSpacing(1)
        duty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.duty_eyebrow = QLabel(tr("Staged output"))
        self.duty_eyebrow.setProperty("fanDutyEyebrow", True)
        self.duty_eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        duty_layout.addWidget(self.duty_eyebrow)
        self.duty_gauge = DutyGauge(self.duty_panel)
        self.duty_gauge.setMinimumSize(168, 168)
        self.duty_gauge.setMaximumHeight(190)
        duty_layout.addWidget(self.duty_gauge, 1, Qt.AlignmentFlag.AlignCenter)
        self.duty_channel_label = QLabel("PWM 2")
        self.duty_channel_label.setProperty("fanDutyChannel", True)
        self.duty_channel_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        duty_layout.addWidget(self.duty_channel_label)
        self.duty_raw_label = QLabel("178 / 255")
        self.duty_raw_label.setProperty("fanDutyRaw", True)
        self.duty_raw_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        duty_layout.addWidget(self.duty_raw_label)

        self.manual_controls_panel = QFrame()
        self.manual_controls_panel.setProperty("fanManualPanel", True)
        controls = QVBoxLayout(self.manual_controls_panel)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(9)

        self.channel_combo = self._make_channel_combo()
        self.channel_selector_host = QFrame()
        self.channel_selector_host.setProperty("fanChannelBay", True)
        self.channel_selector_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        selector = QHBoxLayout(self.channel_selector_host)
        selector.setContentsMargins(9, 8, 9, 8)
        selector.setSpacing(9)
        selector.addWidget(IconBadge("fan_cyan", COLORS["cyan_soft"], 28, radius=8))
        selector.addWidget(self.channel_combo, 1)
        self.selected_live_rpm = QLabel("-- RPM")
        self.selected_live_rpm.setProperty("fanInlineReading", True)
        self.selected_live_rpm.setToolTip(tr("RPM observed"))
        selector.addWidget(self.selected_live_rpm, 0, Qt.AlignmentFlag.AlignVCenter)
        self.selected_mode = FanStatusChip("Unknown mode", "gray")
        self.selected_mode.setWordWrap(False)
        selector.addWidget(self.selected_mode, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        controls.addWidget(self.channel_selector_host)

        # Retain the values as hidden compatibility widgets for existing
        # diagnostics/tests, but do not render a second “selected channel”
        # slab below the selector.  RPM and mode above are the live summary.
        self.selected_channel_readout = QLabel("PWM --")
        self.selected_access = QLabel(tr("Access unavailable"))
        self.selected_channel_readout.hide()
        self.selected_access.hide()

        # This hidden text keeps the selected physical route available as a
        # tooltip without filling the primary control surface with paths.
        self.selected_channel_meta = QLabel(tr("Select a detected PWM channel for BC250 cooling control."))
        self.selected_channel_meta.hide()
        self.speed_control = SliderControl(
            "Requested fan speed",
            0,
            100,
            70,
            suffix=" %",
            step=1,
            hint="This value is staged only. Hardware changes only after confirmation.",
        )
        self.speed_control.setObjectName("fan-duty-slider")
        self.speed_control.setProperty("fanOutputControl", True)
        self.speed_control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.speed_control.value_changed.connect(self._manual_value_changed)
        controls.addWidget(self.speed_control)

        self.manual_presets_grid = QGridLayout()
        self.manual_presets_grid.setContentsMargins(0, 0, 0, 0)
        self.manual_presets_grid.setHorizontalSpacing(7)
        self.manual_presets_grid.setVerticalSpacing(7)
        self.manual_preset_group = QButtonGroup(self)
        self.manual_preset_group.setExclusive(True)
        self.manual_preset_buttons: list[QPushButton] = []
        for preset_key, title, value, tone in (
            ("quiet", "Quiet", 45, "green"),
            ("balanced", "Balanced", 60, "cyan"),
            ("cooling", "Cooling", 70, "blue"),
            ("maximum", "Maximum", 100, "blue"),
        ):
            button = QPushButton(tr_format("{name} · {value}%", name=tr(title), value=value))
            button.setProperty("fanPresetButton", True)
            button.setProperty("fanPreset", preset_key)
            button.setProperty("fanPresetTone", tone)
            button.setCheckable(True)
            button.payload = value
            button.clicked.connect(
                lambda checked, b=button: self._select_manual_preset(b) if checked else None
            )
            self.manual_preset_group.addButton(button)
            self.manual_preset_buttons.append(button)
        controls.addLayout(self.manual_presets_grid)
        self.manual_workspace.addWidget(self.duty_panel, 0, 0)
        self.manual_workspace.addWidget(self.manual_controls_panel, 0, 1)
        self.manual_workspace.setColumnStretch(0, 2)
        self.manual_workspace.setColumnStretch(1, 5)
        root.addLayout(self.manual_workspace)

        self.manual_note = QLabel()
        self.manual_note.setProperty("fanStageNote", True)
        self.manual_note.setWordWrap(True)
        # The slider already says the value is staged.  Keep this translated
        # detail for accessibility/tooltips but remove the large visual gap.
        self.manual_note.hide()

        self.manual_footer_grid = QGridLayout()
        self.manual_footer_grid.setContentsMargins(0, 0, 0, 0)
        self.manual_footer_grid.setHorizontalSpacing(7)
        self.manual_footer_grid.setVerticalSpacing(7)
        self.use_live_button = QPushButton(tr("Use current duty"))
        self.use_live_button.setProperty("compactAction", True)
        self.use_live_button.setIcon(icon("activity_purple"))
        self.use_live_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.use_live_button.clicked.connect(self._use_live_duty)
        self.restore_auto_button = QPushButton(tr("Automatic"))
        self.restore_auto_button.setObjectName("fan-automatic")
        self.restore_auto_button.setProperty("compactAction", True)
        self.restore_auto_button.setIcon(icon("refresh_gray"))
        self.restore_auto_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.restore_auto_button.clicked.connect(self.restore_automatic_pwm)
        self.apply_pwm_button = QPushButton(tr("Apply PWM"))
        self.apply_pwm_button.setObjectName("fan-apply")
        self.apply_pwm_button.setProperty("primaryAction", True)
        self.apply_pwm_button.setIcon(icon("fan_cyan"))
        self.apply_pwm_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.apply_pwm_button.clicked.connect(self.apply_manual_pwm)
        root.addLayout(self.manual_footer_grid)
        self._manual_value_changed(self._staged_pwm_percent)
        return page

    def _build_cooling_curve_page(self) -> QFrame:
        page = QFrame()
        page.setProperty("fanModePage", True)
        page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        summary = QFrame()
        summary.setProperty("fanCurveHeader", True)
        summary_layout = QGridLayout(summary)
        summary_layout.setContentsMargins(10, 9, 10, 9)
        summary_layout.setHorizontalSpacing(10)
        summary_layout.setVerticalSpacing(4)
        self.curve_enabled = QCheckBox(tr("Enable automatic curve"))
        self.curve_enabled.toggled.connect(self._curve_toggle_changed)
        summary_layout.addWidget(self.curve_enabled, 0, 0, 1, 2)
        self.curve_status_chip = FanStatusChip("Disabled", "gray")
        summary_layout.addWidget(self.curve_status_chip, 0, 2, Qt.AlignmentFlag.AlignRight)
        # Keep these state labels as non-rendered values for the telemetry
        # renderer.  The response strip below communicates the active target
        # without repeating a GPU-temperature sentence under the checkbox.
        self.curve_live_value = QLabel(tr("Waiting for GPU temperature"))
        self.curve_live_target = QLabel(tr("Target -- %"))
        self.curve_live_value.hide()
        self.curve_live_target.hide()
        target_label = QLabel(tr("Curve target"))
        target_label.setWordWrap(True)
        target_label.setProperty("fanSignalLabel", True)
        self.curve_target_label = QLabel("PWM 2")
        self.curve_target_label.setProperty("fanSelectedValue", True)
        summary_layout.addWidget(target_label, 1, 0)
        summary_layout.addWidget(self.curve_target_label, 1, 1)
        self.curve_use_channel_button = QPushButton(tr("Use selected channel"))
        self.curve_use_channel_button.setProperty("compactAction", True)
        self.curve_use_channel_button.setProperty("i18nSourceText", "Use selected channel")
        self.curve_use_channel_button.setProperty("i18nSourceToolTip", "Use selected channel")
        self.curve_use_channel_button.setIcon(icon("fan_cyan"))
        self.curve_use_channel_button.clicked.connect(self._use_selected_channel_for_curve)
        self.curve_daemon_settings_button = QPushButton(tr("Configure BC250 daemon"))
        self.curve_daemon_settings_button.setProperty("compactAction", True)
        self.curve_daemon_settings_button.setProperty("i18nSourceText", "Configure BC250 daemon")
        self.curve_daemon_settings_button.setProperty("i18nSourceToolTip", "Configure BC250 daemon")
        self.curve_daemon_settings_button.setIcon(icon("settings_blue"))
        self.curve_daemon_settings_button.clicked.connect(self._open_daemon_settings)
        curve_actions = QHBoxLayout()
        curve_actions.setContentsMargins(0, 0, 0, 0)
        curve_actions.setSpacing(6)
        curve_actions.addWidget(self.curve_use_channel_button, 1)
        curve_actions.addWidget(self.curve_daemon_settings_button, 1)
        self.curve_actions_layout = curve_actions
        summary_layout.addLayout(curve_actions, 1, 2, Qt.AlignmentFlag.AlignRight)
        summary_layout.setColumnStretch(1, 1)
        root.addWidget(summary)

        self.curve_presets_grid = QGridLayout()
        self.curve_presets_grid.setContentsMargins(0, 0, 0, 0)
        self.curve_presets_grid.setHorizontalSpacing(7)
        self.curve_presets_grid.setVerticalSpacing(7)
        self._curve_preset_columns = 0
        self.curve_preset_group = QButtonGroup(self)
        self.curve_preset_group.setExclusive(True)
        self.curve_preset_buttons: list[QPushButton] = []
        for title, key, tone in (
            ("Silent", "silent", "green"),
            ("Balanced", "balanced", "cyan"),
            ("Aggressive", "aggressive", "orange"),
        ):
            button = QPushButton(tr(title))
            button.setCheckable(True)
            button.setProperty("fanPresetButton", True)
            button.setProperty("curvePreset", key)
            button.setProperty("fanPresetTone", tone)
            button.clicked.connect(
                lambda checked, preset=key: self._apply_curve_preset(preset) if checked else None
            )
            self.curve_preset_group.addButton(button)
            self.curve_preset_buttons.append(button)
        root.addLayout(self.curve_presets_grid)

        # The response map states the ranges the controller actually applies;
        # it deliberately avoids the misleading interpolation of a graph.
        self.curve_plot_panel = QFrame()
        self.curve_plot_panel.setProperty("curveStage", True)
        plot_layout = QVBoxLayout(self.curve_plot_panel)
        plot_layout.setContentsMargins(10, 9, 10, 9)
        plot_layout.setSpacing(0)
        self.curve_plot = FanCurvePlot()
        plot_layout.addWidget(self.curve_plot)
        root.addWidget(self.curve_plot_panel)

        # Long textual copies are still kept for screen readers, diagnostics,
        # and the event log, but no longer consume a whole visual row.
        self.curve_summary = QLabel(tr("Curve not loaded"))
        self.curve_summary.setProperty("fanSelectedMeta", True)
        self.curve_summary.setWordWrap(True)
        self.curve_summary.hide()

        self.curve_editor_toggle = QPushButton(tr("Show curve editor"))
        self.curve_editor_toggle.setObjectName("fan-curve-editor-toggle")
        self.curve_editor_toggle.setProperty("compactAction", True)
        self.curve_editor_toggle.setIcon(icon("settings_blue"))
        self.curve_editor_toggle.setCheckable(True)
        self.curve_editor_toggle.toggled.connect(self._set_curve_editor_visible)
        root.addWidget(self.curve_editor_toggle)

        self.curve_editor_details = QFrame()
        self.curve_editor_details.setProperty("curveQuickState", True)
        editor_layout = QVBoxLayout(self.curve_editor_details)
        editor_layout.setContentsMargins(10, 10, 10, 10)
        editor_layout.setSpacing(10)
        self.curve_controls_panel = QFrame()
        self.curve_controls_panel.setProperty("curveControlPanel", True)
        controls = QVBoxLayout(self.curve_controls_panel)
        controls.setContentsMargins(10, 9, 10, 9)
        controls.setSpacing(8)
        point_actions = QHBoxLayout()
        point_actions.setSpacing(7)
        self.add_curve_point_button = QPushButton(tr("Add point"))
        self.add_curve_point_button.setProperty("compactAction", True)
        self.add_curve_point_button.clicked.connect(self._add_curve_point)
        self.remove_curve_point_button = QPushButton(tr("Remove point"))
        self.remove_curve_point_button.setProperty("compactAction", True)
        self.remove_curve_point_button.setToolTip(tr("Removes the highest-temperature custom point."))
        self.remove_curve_point_button.clicked.connect(self._remove_curve_point)
        point_actions.addWidget(self.add_curve_point_button)
        point_actions.addWidget(self.remove_curve_point_button)
        point_actions.addStretch(1)
        controls.addLayout(point_actions)
        self.curve_points_grid = QGridLayout()
        self.curve_points_grid.setContentsMargins(0, 0, 0, 0)
        self.curve_points_grid.setHorizontalSpacing(7)
        self.curve_points_grid.setVerticalSpacing(7)
        self.curve_points = [
            CurvePoint("Point 1", 50, 70),
            CurvePoint("Point 2", 65, 100),
            CurvePoint("Point 3", 70, 100),
        ]
        for point in self.curve_points:
            point.changed.connect(self._curve_values_changed)
        controls.addLayout(self.curve_points_grid)
        self.curve_detail = QLabel()
        self.curve_detail.setProperty("fanStageNote", True)
        self.curve_detail.setWordWrap(True)
        # The full persistence explanation belongs in a tooltip/details view,
        # not between editable points and the action buttons.
        self.curve_detail.hide()
        editor_layout.addWidget(self.curve_controls_panel)
        root.addWidget(self.curve_editor_details)
        self.curve_editor_details.hide()

        actions = QGridLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setHorizontalSpacing(7)
        self.curve_action_grid = actions
        self.save_curve_button = QPushButton(tr("Save curve"))
        self.save_curve_button.setProperty("compactAction", True)
        self.save_curve_button.setIcon(icon("app_blue"))
        self.save_curve_button.clicked.connect(self.save_curve)
        self.apply_curve_button = QPushButton(tr("Apply curve now"))
        self.apply_curve_button.setObjectName("fan-curve-apply")
        self.apply_curve_button.setProperty("primaryAction", True)
        self.apply_curve_button.setIcon(icon("fan_cyan"))
        self.apply_curve_button.clicked.connect(self.apply_curve_now)
        root.addLayout(actions)
        return page

    def _build_compact_driver_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("fan-driver-summary")
        card.setProperty("fanSystemRail", True)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root = QVBoxLayout(card)
        root.setContentsMargins(3, 2, 3, 2)
        root.setSpacing(7)

        header = QGridLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setHorizontalSpacing(9)
        header.setVerticalSpacing(5)
        header.addWidget(IconBadge("settings_blue", COLORS["blue_soft"], 28, radius=8), 0, 0, 2, 1)
        self.driver_mode_value = QLabel(tr("Detecting controller"))
        self.driver_mode_value.setProperty("driverModeValue", True)
        self.driver_mode_value.setWordWrap(True)
        self.driver_mode_detail = QLabel(tr("No NCT hwmon route has been authorized yet."))
        self.driver_mode_detail.setProperty("driverModeDetail", True)
        self.driver_mode_detail.setWordWrap(True)
        header.addWidget(self.driver_mode_value, 0, 1)
        header.addWidget(self.driver_mode_detail, 1, 1)
        self.driver_status_chip = FanStatusChip("Checking", "gray")
        header.addWidget(self.driver_status_chip, 0, 2, Qt.AlignmentFlag.AlignRight)
        self.paths_button = QPushButton(tr("PWM paths by OS"))
        self.paths_button.setObjectName("fan-paths")
        self.paths_button.setProperty("compactAction", True)
        self.paths_button.setIcon(icon("info_blue"))
        self.paths_button.clicked.connect(self.show_pwm_paths)
        header.addWidget(self.paths_button, 1, 2, Qt.AlignmentFlag.AlignRight)
        header.setColumnStretch(1, 1)
        root.addLayout(header)

        self.driver_tools_button = QPushButton(tr("Show controller tools"))
        self.driver_tools_button.setObjectName("fan-driver-tools-toggle")
        self.driver_tools_button.setProperty("compactAction", True)
        self.driver_tools_button.setCheckable(True)
        self.driver_tools_button.toggled.connect(self._set_driver_details_visible)
        root.addWidget(self.driver_tools_button)

        self.driver_details = QFrame()
        self.driver_details.setProperty("fanDriverDetails", True)
        details = QVBoxLayout(self.driver_details)
        details.setContentsMargins(10, 10, 10, 10)
        details.setSpacing(7)
        self.chip_status = StatusLine("NCT chip", "Not detected", "hwmon discovery")
        self.module_status = StatusLine("Kernel module", "--", "nct6683 read-only · nct6687 PWM")
        self.control_status = StatusLine("PWM access", "Unavailable", "Polkit helper and hwmon permissions")
        self.path_status = StatusLine("Hwmon path", "--", "Live Linux route")
        self.telemetry_source = StatusLine("Sensor source", "Not detected", "Waiting for an NCT hwmon device")
        self.telemetry_refresh = StatusLine("Last refresh", "--:--:--", "Passive read")
        for line in (
            self.chip_status,
            self.module_status,
            self.control_status,
            self.path_status,
            self.telemetry_source,
            self.telemetry_refresh,
        ):
            details.addWidget(line)
        self.driver_actions_grid = QGridLayout()
        self.driver_actions_grid.setContentsMargins(0, 3, 0, 0)
        self.driver_actions_grid.setHorizontalSpacing(7)
        self.driver_actions_grid.setVerticalSpacing(7)
        self.prepare_button = QPushButton(tr("Prepare PWM driver"))
        self.prepare_button.setProperty("primaryAction", True)
        self.prepare_button.setIcon(icon("download_blue"))
        self.prepare_button.clicked.connect(self.prepare_pwm_driver)
        self.read_only_button = QPushButton(tr("Use read-only monitoring"))
        self.read_only_button.setProperty("compactAction", True)
        self.read_only_button.clicked.connect(self.enable_read_only)
        self.disable_button = QPushButton(tr("Disable PWM setup"))
        self.disable_button.setProperty("dangerAction", True)
        self.disable_button.clicked.connect(self.disable_pwm_setup)
        self.raw_status_button = QPushButton(tr("Raw chip status"))
        self.raw_status_button.setProperty("compactAction", True)
        self.raw_status_button.clicked.connect(self.show_raw_status)
        self.driver_action_buttons = [
            self.prepare_button,
            self.read_only_button,
            self.disable_button,
            self.raw_status_button,
        ]
        details.addLayout(self.driver_actions_grid)
        root.addWidget(self.driver_details)
        self.driver_details.hide()
        return card

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow(effective_viewport_width(self, self.scroll))
        self._queue_command_deck_sync()

    def _reflow_curve_points(self, width: int) -> None:
        # Three cards fit only while the curve editor owns the full page width.
        # Once the plot/editor split activates at 1000 px, the controls column
        # becomes narrower and must return to a vertical point list.
        columns = 3 if 820 <= width < 1000 else 1
        if columns == self._curve_columns:
            return
        self._curve_columns = columns
        self._clear_grid(self.curve_points_grid)
        for index, point in enumerate(self.curve_points):
            self.curve_points_grid.addWidget(point, index // columns, index % columns)
        for column in range(columns):
            self.curve_points_grid.setColumnStretch(column, 1)

    @staticmethod
    def _clear_grid(layout: QGridLayout) -> None:
        clear_grid(layout)

    def retranslate_dynamic_copy(self) -> None:
        """Rebuild dynamic cooling labels after a live language change.

        Generic widget-tree localization handles ordinary labels, but the fan
        workspace also contains formatted preset and telemetry text.  Their
        English source is not a literal widget label once a percentage or a
        live PWM value is inserted, so render that small dynamic surface again
        using the newly selected language.  This is display-only: it does not
        write PWM, persist a profile, or refresh hardware.
        """
        preset_titles = {
            "quiet": "Quiet",
            "balanced": "Balanced",
            "cooling": "Cooling",
            "maximum": "Maximum",
        }
        for button in self.manual_preset_buttons:
            key = str(button.property("fanPreset") or "")
            title = preset_titles.get(key, "Custom")
            value = _integer(getattr(button, "payload", 0))
            source = f"{title} · {value}%"
            button.setText(tr_format("{name} · {value}%", name=tr(title), value=value))
            # Keep a stable English source for future generic tree passes.
            button.setProperty("i18nSourceText", source)
        self.curve_editor_toggle.setText(
            tr("Hide curve editor" if self._curve_editor_open else "Show curve editor")
        )
        self.driver_tools_button.setText(
            tr("Hide controller tools" if self._driver_details_open else "Show controller tools")
        )
        self.curve_use_channel_button.setText(tr("Use selected channel"))
        self.curve_daemon_settings_button.setText(tr("Configure BC250 daemon"))
        self.curve_plot.retranslate()
        self._manual_value_changed(self._staged_pwm_percent)
        self._update_curve_summary()
        if self.current_state:
            self._apply_state()

    def _set_control_mode(self, mode: str) -> None:
        mode = "curve" if mode == "curve" else "manual"
        self._control_mode = mode
        if hasattr(self, "control_stack"):
            self.control_stack.setCurrentWidget(
                self.curve_card if mode == "curve" else self.manual_card
            )
        if hasattr(self, "manual_mode_button"):
            self.manual_mode_button.blockSignals(True)
            self.curve_mode_button.blockSignals(True)
            self.manual_mode_button.setChecked(mode == "manual")
            self.curve_mode_button.setChecked(mode == "curve")
            self.manual_mode_button.blockSignals(False)
            self.curve_mode_button.blockSignals(False)
        self.control_surface.updateGeometry()
        self.fan_workspace.updateGeometry()
        self._sync_command_deck_height()
        QTimer.singleShot(0, self._sync_command_deck_height)
        self._reflow(effective_viewport_width(self, self.scroll))

    def _set_curve_editor_visible(self, visible: bool) -> None:
        self._curve_editor_open = bool(visible)
        self.curve_editor_details.setVisible(self._curve_editor_open)
        self.curve_editor_toggle.setText(
            tr("Hide curve editor" if self._curve_editor_open else "Show curve editor")
        )
        self.curve_card.updateGeometry()
        self.control_stack.updateGeometry()
        self.control_surface.updateGeometry()
        self.fan_workspace.updateGeometry()
        self._sync_command_deck_height()
        QTimer.singleShot(0, self._sync_command_deck_height)
        self._reflow(effective_viewport_width(self, self.scroll))

    def _set_driver_details_visible(self, visible: bool) -> None:
        self._driver_details_open = bool(visible)
        self.driver_details.setVisible(self._driver_details_open)
        self.driver_tools_button.setText(
            tr("Hide controller tools" if self._driver_details_open else "Show controller tools")
        )
        self.driver_card.updateGeometry()
        self.fan_workspace.updateGeometry()
        self._sync_command_deck_height()
        QTimer.singleShot(0, self._sync_command_deck_height)
        self._reflow(effective_viewport_width(self, self.scroll))

    def _use_selected_channel_for_curve(self) -> None:
        selected = self.channel_combo.currentData()
        if selected is None:
            self._show_info(
                "No PWM channel",
                "Select a detected PWM channel before assigning the automatic curve.",
                tone="orange",
            )
            return
        self._curve_target_pwm = _integer(selected, self._preferred_pwm)
        self._persist_curve(show_error=False)
        self._update_curve_summary()

    def _open_daemon_settings(self) -> None:
        """Open the shared Settings dialog directly on Telemetry.

        Settings ownership stays in :class:`ControlCenterWindow`; emitting a
        route keeps this page free of modal-dialog lifecycle and localization
        concerns while preserving the normal settings navigation path.
        """
        self.settings_requested.emit("telemetry")

    @staticmethod
    def _place_grid_items(layout: QGridLayout, widgets: list[QWidget], columns: int) -> None:
        columns = max(1, int(columns))
        clear_grid(layout)
        for index, widget in enumerate(widgets):
            layout.addWidget(widget, index // columns, index % columns)
        for column in range(columns):
            layout.setColumnStretch(column, 1)

    def _place_manual_actions(self, columns: int) -> None:
        """Keep the primary write action visually dominant at every width."""
        columns = max(1, min(3, int(columns)))
        clear_grid(self.manual_footer_grid)
        if columns == 3:
            self.manual_footer_grid.addWidget(self.use_live_button, 0, 0)
            self.manual_footer_grid.addWidget(self.restore_auto_button, 0, 1)
            self.manual_footer_grid.addWidget(self.apply_pwm_button, 0, 2)
        elif columns == 2:
            self.manual_footer_grid.addWidget(self.use_live_button, 0, 0)
            self.manual_footer_grid.addWidget(self.restore_auto_button, 0, 1)
            self.manual_footer_grid.addWidget(self.apply_pwm_button, 1, 0, 1, 2)
        else:
            self.manual_footer_grid.addWidget(self.use_live_button, 0, 0)
            self.manual_footer_grid.addWidget(self.restore_auto_button, 1, 0)
            self.manual_footer_grid.addWidget(self.apply_pwm_button, 2, 0)
        for column in range(columns):
            self.manual_footer_grid.setColumnStretch(column, 1)

    def _queue_command_deck_sync(self) -> None:
        """Measure after Qt has assigned the real viewport width once."""
        if self._deck_sync_queued:
            return
        self._deck_sync_queued = True

        def settle() -> None:
            self._deck_sync_queued = False
            self._sync_command_deck_height()

        QTimer.singleShot(0, settle)

    def _sync_command_deck_height(self) -> None:
        """Fit the deck to the visible mode after its layout has settled.

        The deck must have a natural fixed height on wide windows, otherwise
        Qt donates all spare vertical space to the slider.  Measuring after a
        queued resize avoids the early construction-time measurement that used
        to clip compact layouts.
        """
        if not hasattr(self, "control_stack"):
            return
        current = self.control_stack.currentWidget()
        if current is None:
            return
        page_layout = current.layout()
        if page_layout is not None:
            page_layout.invalidate()
            page_layout.activate()
        page_height = max(current.minimumSizeHint().height(), current.sizeHint().height())
        self.control_stack.setFixedHeight(page_height)
        if hasattr(self, "control_surface"):
            control_layout = self.control_surface.layout()
            control_layout.invalidate()
            control_layout.activate()
            margins = control_layout.contentsMargins()
            control_height = (
                margins.top()
                + margins.bottom()
                + self.mode_switch.sizeHint().height()
                + control_layout.spacing()
                + page_height
            )
            self.control_surface.setFixedHeight(control_height)
            self.control_surface.updateGeometry()
        if hasattr(self, "fan_workspace"):
            workspace_layout = self.fan_workspace.layout()
            workspace_layout.invalidate()
            workspace_layout.activate()
            self.fan_workspace.setFixedHeight(workspace_layout.sizeHint().height())
            self.fan_workspace.updateGeometry()
        if hasattr(self, "content"):
            self.content.layout().invalidate()
            self.content.updateGeometry()

    def _reflow(self, width: int) -> None:
        """Reflow against each real surface, not a theoretical full page width."""
        width = max(1, int(width))
        self._update_overview_actions(width)
        overview_columns = 4 if width >= 1080 else 2 if width >= 420 else 1
        if overview_columns != self._metric_columns:
            self._metric_columns = overview_columns
            self._place_grid_items(self.metrics_grid, self.metric_tiles, overview_columns)

        # During the first resize Qt may still report the construction width
        # of a stacked page.  Never let that stale value select a wider grid
        # than the real viewport can hold.
        manual_width = max(1, width - 50)
        manual_workspace_columns = 2 if manual_width >= 760 else 1
        if manual_workspace_columns != self._manual_workspace_columns:
            self._manual_workspace_columns = manual_workspace_columns
            clear_grid(self.manual_workspace)
            if manual_workspace_columns == 2:
                self.duty_panel.setMaximumHeight(16_777_215)
                self.duty_gauge.setMinimumSize(168, 168)
                self.duty_gauge.setMaximumHeight(190)
                self.manual_workspace.addWidget(self.duty_panel, 0, 0)
                self.manual_workspace.addWidget(self.manual_controls_panel, 0, 1)
                self.manual_workspace.setColumnStretch(0, 2)
                self.manual_workspace.setColumnStretch(1, 5)
            else:
                self.duty_panel.setMaximumHeight(202)
                self.duty_gauge.setMinimumSize(128, 128)
                self.duty_gauge.setMaximumHeight(140)
                self.manual_workspace.addWidget(self.duty_panel, 0, 0)
                self.manual_workspace.addWidget(self.manual_controls_panel, 1, 0)
                self.manual_workspace.setColumnStretch(0, 1)
        manual_preset_columns = 4 if manual_width >= 760 else 2
        current_preset_columns = self.manual_presets_grid.property("columns")
        if current_preset_columns != manual_preset_columns:
            self.manual_presets_grid.setProperty("columns", manual_preset_columns)
            self._place_grid_items(
                self.manual_presets_grid,
                list(self.manual_preset_buttons),
                manual_preset_columns,
            )

        # A primary action spanning a full second row made "Apply PWM" look
        # heavier than "Use current duty" and "Automatic".  Keep the three
        # commands equal: three columns once they fit, otherwise one column.
        manual_action_columns = 3 if manual_width >= 500 else 1
        current_action_columns = self.manual_footer_grid.property("columns")
        if current_action_columns != manual_action_columns:
            self.manual_footer_grid.setProperty("columns", manual_action_columns)
            self._place_manual_actions(manual_action_columns)

        self._queue_command_deck_sync()

        curve_width = max(1, width - 50)
        compact_curve_header = curve_width < 520
        self.curve_plot.set_compact(compact_curve_header)
        if compact_curve_header:
            self.curve_use_channel_button.setText("")
            self.curve_use_channel_button.setToolTip(tr("Use selected channel"))
            self.curve_use_channel_button.setFixedSize(34, 34)
            self.curve_daemon_settings_button.setText("")
            self.curve_daemon_settings_button.setToolTip(tr("Configure BC250 daemon"))
            self.curve_daemon_settings_button.setFixedSize(34, 34)
        else:
            self.curve_use_channel_button.setMinimumSize(0, 0)
            self.curve_use_channel_button.setMaximumSize(16_777_215, 16_777_215)
            self.curve_use_channel_button.setText(tr("Use selected channel"))
            self.curve_use_channel_button.setToolTip("")
            self.curve_daemon_settings_button.setMinimumSize(0, 0)
            self.curve_daemon_settings_button.setMaximumSize(16_777_215, 16_777_215)
            self.curve_daemon_settings_button.setText(tr("Configure BC250 daemon"))
            self.curve_daemon_settings_button.setToolTip("")
        curve_preset_columns = 3 if curve_width >= 480 else 1
        if curve_preset_columns != self._curve_preset_columns:
            self._curve_preset_columns = curve_preset_columns
            self._place_grid_items(
                self.curve_presets_grid,
                list(self.curve_preset_buttons),
                curve_preset_columns,
            )
        curve_action_columns = 2 if curve_width >= 430 else 1
        if self.curve_action_grid.property("columns") != curve_action_columns:
            self.curve_action_grid.setProperty("columns", curve_action_columns)
            self._place_grid_items(
                self.curve_action_grid,
                [self.save_curve_button, self.apply_curve_button],
                curve_action_columns,
            )

        # The response strip is now always visible above the optional editor.
        # Only the editable point cards need to reflow when the editor opens.
        editor_width = curve_width
        point_columns = 2 if editor_width >= 760 else 1
        if point_columns != self._curve_columns:
            self._curve_columns = point_columns
            self._place_grid_items(self.curve_points_grid, list(self.curve_points), point_columns)

        driver_width = max(1, width - 50)
        driver_columns = 2 if driver_width >= 580 else 1
        if driver_columns != self._driver_action_columns:
            self._driver_action_columns = driver_columns
            self._place_grid_items(
                self.driver_actions_grid,
                list(self.driver_action_buttons),
                driver_columns,
            )

    def _update_overview_actions(self, width: int) -> None:
        """Keep the retained diagnostics compact without adding a refresh action."""
        paths_icon_only = width < 620
        self.overview_status.setVisible(width >= 420)
        self.overview_balance_spacer.setMinimumWidth(74 if width >= 420 else 0)
        # This status is deliberately retained only as a data seam; the
        # selected channel's inline mode and the live overview already state
        # the actionable condition without recreating a control header.
        self.control_status_chip.hide()
        self.selected_mode.setVisible(width >= 420)
        for button, icon_only, full_text in (
            (self.paths_button, paths_icon_only, tr("PWM paths by OS")),
        ):
            if icon_only:
                button.setText("")
                button.setToolTip(full_text)
                button.setFixedSize(34, 34)
            else:
                button.setText(full_text)
                button.setToolTip(full_text)
                button.setMinimumSize(0, 0)
                button.setMaximumSize(16777215, 16777215)
                button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _load_curve_config(self) -> None:
        # The shared cache delegates to SettingsService off the
        # UI thread and coalesces duplicate reads from other interface pages.
        if self._curve_config_loaded or self._curve_config_busy:
            return
        self._curve_config_busy = True

        def success(payload: object) -> None:
            self._curve_config_busy = False
            self._curve_config_loaded = True
            root_config = _dict(payload)
            config = root_config.get("fan_curve") or {}
            self._fan_preset_config = _dict(root_config.get("fan_preset"))
            self._apply_curve_config(_dict(config))

        def failure(_message: str) -> None:
            self._curve_config_busy = False
            self._curve_config_loaded = True

        self._background.start("fan-config-load", self._state_cache.config, success, failure)

    def _apply_curve_config(self, config: dict) -> None:
        normalized = normalize_fan_curve(config)
        self._curve_loading = True
        configured_pwm = _integer(normalized.get("pwm"), 2) or 2
        self._preferred_pwm = configured_pwm
        self._curve_target_pwm = configured_pwm
        self._curve_preset = str(normalized.get("preset") or "custom")
        self._last_pwm_text = str(normalized.get("last_pwm_text") or "--")
        values = [
            (_integer(point.get("temperature"), 50), _integer(point.get("speed"), 70))
            for point in normalized.get("points", [])
            if isinstance(point, dict)
        ]
        self._replace_curve_points(values)
        self.curve_enabled.setChecked(bool(normalized.get("enabled", False)))
        for button in self.curve_preset_buttons:
            button.setChecked(button.property("curvePreset") == self._curve_preset)
        self._curve_loading = False
        self._curve_dirty = False
        self._update_curve_summary()
        self._update_action_availability()

    def _curve_points_values(self) -> list[tuple[int, int]]:
        return sorted((point.values() for point in self.curve_points), key=lambda item: item[0])

    def _normalize_curve_points(self) -> None:
        values = self._curve_points_values()
        for point, (temperature, speed) in zip(self.curve_points, values):
            point.set_values(temperature, speed)
        for index, point in enumerate(self.curve_points, start=1):
            point.set_index(index)

    def _replace_curve_points(self, values: list[tuple[int, int]]) -> None:
        while self.curve_points_grid.count():
            self.curve_points_grid.takeAt(0)
        for point in getattr(self, "curve_points", []):
            point.setParent(None)
            point.deleteLater()
        self.curve_points = []
        for index, (temperature, speed) in enumerate(values[:8], start=1):
            point = CurvePoint(tr_format("Point {index}", index=index), temperature, speed)
            point.changed.connect(self._curve_values_changed)
            self.curve_points.append(point)
        self._curve_columns = 0
        width = effective_viewport_width(self.scroll, self.content)
        self._reflow_curve_points(width)
        if hasattr(self, "control_stack"):
            self._sync_command_deck_height()
            QTimer.singleShot(0, self._sync_command_deck_height)

    def _add_curve_point(self) -> None:
        if len(self.curve_points) >= 8:
            self._show_info("Maximum curve size", "A custom fan curve supports up to 8 points.", tone="orange")
            return
        values = self._curve_points_values()
        temperature = values[-1][0] + 5
        if temperature > 95:
            candidates = []
            bounds = [(30, values[0][0]), *zip([item[0] for item in values], [item[0] for item in values][1:]), (values[-1][0], 95)]
            for lower, upper in bounds:
                if upper - lower > 1:
                    candidates.append((upper - lower, lower + ((upper - lower) // 2)))
            temperature = max(candidates)[1] if candidates else 95
        previous_speed = max((speed for temp, speed in values if temp <= temperature), default=values[-1][1])
        values.append((temperature, previous_speed))
        values.sort(key=lambda item: item[0])
        self._replace_curve_points(values)
        self._curve_values_changed()

    def _remove_curve_point(self) -> None:
        if len(self.curve_points) <= 3:
            self._show_info("Minimum curve size", "A fan curve requires at least 3 points.", tone="orange")
            return
        values = self._curve_points_values()[:-1]
        self._replace_curve_points(values)
        self._curve_values_changed()

    def _curve_validation_error(self) -> str:
        valid, message = validate_fan_curve_points(self._curve_points_values())
        return "" if valid else message

    def _curve_config(self) -> dict:
        self._normalize_curve_points()
        points = [point.values() for point in self.curve_points]
        valid, message = validate_fan_curve_points(points)
        if not valid:
            raise ValueError(message)
        pwm = self._curve_target_pwm or self._preferred_pwm
        config = {
            "enabled": bool(self.curve_enabled.isChecked()),
            "edit_enabled": bool(self.curve_enabled.isChecked()),
            "pwm": int(pwm or 2),
            "point_count": len(points),
            "points": [
                {"temperature": temperature, "speed": speed}
                for temperature, speed in points
            ],
            "preset": self._curve_preset,
            "last_pwm_text": self._last_pwm_text,
        }
        # Legacy daemon compatibility: the original three keys remain present.
        for index, (temperature, speed) in enumerate(points[:3], start=1):
            config[f"t{index}"] = temperature
            config[f"s{index}"] = speed
        return config

    def _persist_curve(self, *, show_error: bool = True, on_success=None) -> bool:
        try:
            config = self._curve_config()
        except ValueError as exc:
            if show_error:
                self._show_info("Invalid fan curve", str(exc), tone="orange")
            return False

        def operation() -> object:
            payload = {"fan_curve": config}
            if config.get("enabled"):
                payload["fan_preset"] = {
                    "enabled": False,
                    "preset": "",
                    "percent": 0,
                    "pwm": int(config.get("pwm") or 2),
                }
            elif bool(self._fan_preset_config.get("enabled")):
                preset_config = dict(self._fan_preset_config)
                preset_config["pwm"] = int(config.get("pwm") or 2)
                payload["fan_preset"] = preset_config
            if self.settings_service is None:
                raise RuntimeError("FansPage requires a settings service to save preferences")
            self.settings_service.save_local_config(payload)
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
        self._normalize_curve_points()
        self._curve_dirty = True
        self._update_curve_summary()

    def _curve_toggle_changed(self, enabled: bool) -> None:
        if self._curve_loading:
            return
        validation_error = self._curve_validation_error()
        if enabled and validation_error:
            self.curve_enabled.blockSignals(True)
            self.curve_enabled.setChecked(False)
            self.curve_enabled.blockSignals(False)
            self._show_info("Invalid fan curve", validation_error, tone="orange")
            self._update_action_availability()
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
            self._update_action_availability()
            return
        if enabled:
            self._set_control_mode("curve")
        elif self.curve_editor_toggle.isChecked():
            self.curve_editor_toggle.setChecked(False)
        self._curve_dirty = True
        self._persist_curve(show_error=False)
        self._update_curve_summary()
        self._update_action_availability()

    def _apply_curve_preset(self, key: str) -> None:
        # A named response is part of the automatic-control workflow; do not
        # mutate or persist it through a programmatic call while that workflow
        # is explicitly disabled in the UI.
        if not self.curve_enabled.isChecked() or self._busy or not self._fan_control_available():
            return
        values = CURVE_PRESETS.get(key)
        if not values:
            return
        self._curve_loading = True
        self._replace_curve_points(list(values))
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
        profile_names = {
            "silent": tr("Silent"),
            "balanced": tr("Balanced"),
            "aggressive": tr("Aggressive"),
            "custom": tr("Custom"),
        }
        point_text = " · ".join(f"{temp} °C / {speed}%" for temp, speed in points)
        dirty = tr(" · unsaved edits") if self._curve_dirty else ""
        validation_error = self._curve_validation_error()
        invalid = tr_format(" · invalid: {message}", message=validation_error) if validation_error else ""
        target_pwm = _integer(self._curve_target_pwm, self._preferred_pwm) or 2
        self.curve_summary.setText(
            f"{profile_names.get(self._curve_preset, tr('Custom'))} · PWM {target_pwm} · {point_text}{dirty}{invalid}"
        )
        status = tr("Enabled" if self.curve_enabled.isChecked() else "Disabled")
        self.curve_status_chip.setText(status)
        self.curve_status_chip.set_tone("green" if self.curve_enabled.isChecked() else "gray")
        self.curve_target_label.setText(f"PWM {target_pwm}")
        self.curve_detail.setText(tr_format(
            "Last PWM: {value}. The manual slider is temporary. A named preset or enabled automatic curve is restored after login only when the optional daemon is enabled in Settings.",
            value=self._last_pwm_text,
        ))
        self.curve_plot.set_curve(points)
        self.curve_plot.set_enabled(self.curve_enabled.isChecked())
        temperature, sensor = self._curve_temperature()
        duty = self._curve_percent_for_temp(temperature) if temperature is not None else None
        self.curve_plot.set_live(temperature, duty)
        self.curve_live_value.setText(
            f"{str(sensor).upper()} {temperature:.1f} °C"
            if temperature is not None
            else f"{tr('CPU temperature')} / {tr('GPU temperature')}: --"
        )
        self.curve_live_target.setText(tr_format("Target {value}%", value=duty) if duty is not None else tr("Target -- %"))

    def _select_manual_preset(self, button: PresetButton) -> None:
        self._set_staged_pwm_percent(_integer(button.payload, 70))

    def _set_staged_pwm_percent(self, value: int) -> None:
        percent = max(0, min(100, _integer(value, 70)))
        self._staged_pwm_percent = percent
        if self.speed_control.value() != percent:
            self.speed_control.setValue(percent)
        else:
            self._manual_value_changed(percent)

    def _manual_value_changed(self, value: int) -> None:
        self._staged_pwm_percent = max(0, min(100, int(value)))
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
        value = self._staged_pwm_percent
        raw = _percent_to_pwm(value)
        self.duty_gauge.setValue(value, animate=self.isVisible())
        if hasattr(self, "duty_raw_label"):
            self.duty_raw_label.setText(tr_format("Raw PWM {raw} / 255", raw=raw))
        if hasattr(self, "duty_channel_label"):
            pwm = self.channel_combo.currentData() if hasattr(self, "channel_combo") else None
            self.duty_channel_label.setText(f"PWM {_integer(pwm, self._preferred_pwm)}")
        preset = next(
            (
                str(button.property("fanPreset") or "")
                for button in self.manual_preset_buttons
                if button.isChecked()
            ),
            "",
        )
        persistence = (
            "This named preset can be restored after login by the optional daemon."
            if preset
            else
            "This custom slider value is temporary and will not be restored after reboot."
        )
        self.manual_note.setText(
            tr_format(
                "Staged duty: {value}% · raw PWM {raw}/255. No write occurs until confirmed. {persistence}",
                value=value,
                raw=raw,
                persistence=tr(persistence),
            )
        )

    def _visible_fans(self) -> list[dict]:
        return list(visible_fans(self.current_state, visible_order=VISIBLE_PWM_ORDER))

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
        if hasattr(self, "duty_channel_label"):
            self.duty_channel_label.setText(f"PWM {self._preferred_pwm}")
        # Switching the manual channel must never silently re-target an
        # enabled automatic curve.  That target has its own explicit action
        # in the curve view.  Preserve legacy convenience while no curve is
        # enabled, including saved manual presets.
        if not self._curve_loading and not self.curve_enabled.isChecked():
            self._curve_target_pwm = self._preferred_pwm
            self._persist_curve(show_error=False)
        self._update_selected_metrics()
        self._update_curve_summary()

    def _use_live_duty(self) -> None:
        fan = self._selected_fan()
        percent = _pwm_to_percent(fan.get("pwm")) if fan else None
        if percent is None:
            self._show_info("No live duty", "The selected channel does not expose a readable PWM value.", tone="orange")
            return
        self._set_staged_pwm_percent(percent)

    def _fan_control_available(self) -> bool:
        # A stale state can remain visible for diagnosis, but it must never
        # authorize a write based on old hwmon evidence.
        return bool(self.current_state.get("driver_control")) and not self._refresh_error

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
        if not self._selected_channel_writable():
            self._show_info(
                "Selected channel is read-only",
                "Choose a detected writable PWM channel or prepare nct6687 before applying a fan speed.",
                tone="orange",
            )
            return
        percent = self._staged_pwm_percent
        raw = _percent_to_pwm(percent)
        fan = self._selected_fan()
        dialog = ConfirmDialog(
            "Apply manual fan speed",
            "The selected NCT PWM file will be written through the existing narrow Polkit helper. Monitor temperature and RPM after the change.",
            summary=(
                ("Channel", f"PWM {pwm} · {fan.get('label') or 'fan channel'}"),
                ("Requested duty", f"{percent}%"),
                ("Raw hwmon value", f"{raw} / 255"),
                (
                    "Persistence",
                    "Named preset restored by optional daemon"
                    if any(button.isChecked() for button in self.manual_preset_buttons)
                    else "Temporary slider value; not restored after reboot",
                ),
            ),
            confirm_text="Apply PWM value",
            tone="orange" if percent < 40 else "blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_pwm_write(pwm, percent, source="manual")

    def restore_automatic_pwm(self) -> None:
        if not self._fan_control_available():
            self._show_info(
                "PWM control is not ready",
                "Prepare the nct6687 driver before restoring firmware automatic mode.",
                tone="orange",
            )
            return
        pwm = self.channel_combo.currentData()
        if pwm is None:
            self._show_info("No PWM channel", "Select a detected PWM channel first.", tone="orange")
            return
        if not self._selected_channel_writable():
            self._show_info(
                "Selected channel is read-only",
                "Choose a detected writable PWM channel or prepare nct6687 before restoring automatic mode.",
                tone="orange",
            )
            return
        dialog = ConfirmDialog(
            "Restore firmware automatic fan control",
            "This returns the selected channel to the NCT controller's automatic mode and verifies the mode readback. Saved application curves and presets for this channel will be disabled.",
            summary=(("Channel", f"PWM {pwm}"), ("Target mode", "Firmware automatic (hwmon mode 2)")),
            confirm_text="Restore automatic mode",
            tone="blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._set_busy(True, "Restoring automatic mode…")
        worker = FanTask(lambda: self.controller.restaurar_pwm_automatico(pwm), self)
        self._worker = worker

        def complete(result) -> None:
            verification_error = self._pwm_result_verification_error(
                result,
                pwm=int(pwm),
                automatic=True,
            )
            if verification_error:
                failed(verification_error)
                return
            self.curve_enabled.blockSignals(True)
            self.curve_enabled.setChecked(False)
            self.curve_enabled.blockSignals(False)
            curve_config = self._curve_config()
            curve_config["enabled"] = False
            preset_config = {"enabled": False, "preset": "", "percent": 0, "pwm": int(pwm)}
            if self.settings_service is None:
                raise RuntimeError("FansPage requires a settings service to save preferences")
            self.settings_service.save_local_config({"fan_curve": curve_config, "fan_preset": preset_config})
            self._fan_preset_config = dict(preset_config)
            self._record_event("info", "Automatic fan control restored", f"PWM {pwm} returned to hwmon automatic mode 2.")
            self._set_busy(False, "")
            self._state_cache.invalidate("fans", "config")
            self.refresh()
            self._show_info("Automatic fan control restored", f"PWM {pwm} is back in firmware automatic mode.", tone="blue")

        def failed(message: str) -> None:
            self._set_busy(False, "")
            self._record_event("error", "Automatic fan restore failed", message)
            self._show_error("Automatic fan restore failed", message)

        worker.succeeded.connect(complete)
        worker.failed.connect(failed)
        worker.finished.connect(self._worker_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def apply_curve_now(self) -> None:
        if not self.curve_enabled.isChecked():
            self._show_info(
                tr("Automatic curve is disabled"),
                tr("Enable the automatic curve before applying its calculated PWM value."),
                tone="orange",
            )
            return
        validation_error = self._curve_validation_error()
        if validation_error:
            self._show_info("Invalid fan curve", validation_error, tone="orange")
            return
        if not self._fan_control_available():
            self._show_info("PWM control is not ready", "Prepare nct6687 before applying the curve.", tone="orange")
            return
        temperature, sensor = self._curve_temperature()
        if temperature is None:
            self._show_info(
                "Fan curve",
                f"{tr('CPU temperature')} / {tr('GPU temperature')}: --",
                tone="orange",
            )
            return
        pwm = _integer(self._curve_target_pwm, self._preferred_pwm)
        if not any(_integer(fan.get("index"), -1) == pwm for fan in self._visible_fans()):
            self._show_info(
                "Curve target unavailable",
                "Choose a detected PWM channel for the curve before applying it.",
                tone="orange",
            )
            return
        if not self._fan_writable_for_pwm(pwm):
            self._show_info(
                "Curve target is read-only",
                "Choose a writable detected PWM channel for the curve before applying it.",
                tone="orange",
            )
            return
        percent = self._curve_percent_for_temp(temperature)
        raw = _percent_to_pwm(percent)
        dialog = ConfirmDialog(
            "Fan curve",
            "The hottest available CPU/GPU temperature will be evaluated against the saved curve and one PWM value will be written immediately.",
            summary=(
                (f"{str(sensor).upper()} temperature", f"{temperature:.1f} °C"),
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
            verification_error = self._pwm_result_verification_error(
                result,
                pwm=pwm,
                raw=raw,
            )
            if verification_error:
                failed(verification_error)
                return
            self._last_pwm_text = f"PWM {pwm} · {percent}%"
            self._last_curve_apply = time.monotonic()
            self._last_curve_percent = percent if source == "curve" else self._last_curve_percent
            if source == "manual":
                selected_preset = next(
                    (
                        str(button.property("fanPreset") or "")
                        for button in self.manual_preset_buttons
                        if button.isChecked()
                    ),
                    "",
                )
                if selected_preset:
                    self.curve_enabled.blockSignals(True)
                    self.curve_enabled.setChecked(False)
                    self.curve_enabled.blockSignals(False)
                    curve_config = self._curve_config()
                    curve_config["enabled"] = False
                    preset_config = {
                        "enabled": True,
                        "preset": selected_preset,
                        "percent": percent,
                        "pwm": pwm,
                    }
                else:
                    curve_config = self._curve_config()
                    preset_config = {
                        "enabled": False,
                        "preset": "",
                        "percent": 0,
                        "pwm": pwm,
                    }
                self._fan_preset_config = dict(preset_config)

                def persist_manual_mode() -> object:
                    if self.settings_service is None:
                        raise RuntimeError("FansPage requires a settings service to save preferences")
                    self.settings_service.save_local_config({
                        "fan_curve": curve_config,
                        "fan_preset": preset_config,
                    })
                    return True

                self._background.start(
                    "fan-manual-mode-save",
                    persist_manual_mode,
                    lambda _result: self._state_cache.invalidate("config"),
                )
            else:
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

    @staticmethod
    def _pwm_result_verification_error(
        result: object,
        *,
        pwm: int,
        raw: int | None = None,
        automatic: bool = False,
    ) -> str:
        """Reject a helper acknowledgement that lacks the promised read-back.

        A process exit or an ``OK`` line is not proof that an NCT6687 applied
        the write; the controller can still expose the preceding duty during
        the automatic-to-manual transition.  This guard protects the UI and
        persistent profile state even when a transport returns a partial
        result instead of raising an exception.
        """
        if not isinstance(result, dict):
            return tr("The PWM helper returned no verification result.")
        verified = _dict(result.get("verified"))
        if not verified:
            detail = str(result.get("verification_error") or "").strip()
            return detail or tr("The PWM change could not be verified from hwmon.")
        if _integer(verified.get("pwm"), -1) != int(pwm):
            return tr_format(
                "PWM verification reported channel {actual}, expected PWM {expected}.",
                actual=verified.get("pwm", "--"),
                expected=int(pwm),
            )
        if automatic:
            if _integer(verified.get("enable"), -1) != 2:
                return tr_format(
                    "PWM {pwm} did not verify firmware automatic mode (read-back: {value}).",
                    pwm=int(pwm),
                    value=verified.get("enable", "--"),
                )
            return ""
        if raw is None:
            return tr("The requested PWM duty was missing before verification.")
        if _integer(verified.get("value"), -1) != int(raw):
            return tr_format(
                "PWM {pwm} read-back was {actual}, expected {expected}.",
                pwm=int(pwm),
                actual=verified.get("value", "--"),
                expected=int(raw),
            )
        enable = verified.get("enable")
        if enable is not None and _integer(enable, -1) != 1:
            return tr_format(
                "PWM {pwm} duty was read, but manual mode read-back was {value} instead of 1.",
                pwm=int(pwm),
                value=enable,
            )
        return ""

    def _worker_finished(self) -> None:
        self._worker = None

    def _set_busy(self, busy: bool, label: str) -> None:
        self._busy = bool(busy)
        self._update_action_availability()
        if self.header.action_button is not None:
            self.header.action_button.setEnabled(not busy)
            self.header.action_button.setText(tr(label) if busy else tr("Prepare PWM driver"))

    def _run_driver_action(
        self,
        operation,
        on_success,
        error_title: str,
        *,
        error_parent: QWidget | None = None,
    ) -> None:
        self._set_busy(True, "Working…")

        def success(result: object) -> None:
            on_success(result)
            self._state_cache.invalidate("fans", "tools", "config")
            self.refresh()

        def failure(message: str) -> None:
            self._show_error(error_title, message, parent=error_parent)

        def finished() -> None:
            self._set_busy(False, "")

        if not self._background.start("fan-driver-action", operation, success, failure, finished):
            self._set_busy(False, "")

    def prepare_pwm_driver(self, *, dialog_parent: QWidget | None = None) -> None:
        dialog = ConfirmDialog(
            "Prepare nct6687 PWM control",
            "The distribution-specific workflow checks that the installed kernel headers match the active kernel before compiling nct6687. It may try to install the exact headers package, but it will stop safely if only headers for another kernel are available. A reboot may be required after a system or kernel update.",
            summary=(
                ("Purpose", "Writable NCT PWM channels"),
                ("Kernel/header safety", "Exact match with uname -r required"),
                ("Authentication", "Visible terminal and sudo, once"),
                ("Monitoring fallback", "nct6683 remains available as read-only mode"),
                ("Boot behavior", "The last PWM duty is restored automatically, no password"),
            ),
            confirm_text="Open preparation workflow",
            tone="orange",
            parent=dialog_parent or self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        def success(_result: object) -> None:
            self._record_event("warning", "Fan PWM setup opened", "Distribution-specific nct6687 preparation workflow started.")
            self._show_info(
                "PWM preparation opened",
                "Complete the visible terminal workflow. Reboot if requested, then return here and refresh the fan page.",
                tone="orange",
                parent=dialog_parent,
            )

        self._run_driver_action(
            self.controller.preparar_nct6687_control_pwm,
            success,
            "PWM preparation failed",
            error_parent=dialog_parent,
        )

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
        self._refresh_error = str(message or tr("Read error"))
        # Do not erase useful last-known telemetry after a transient worker
        # failure. Keeping it on screen helps diagnosis, while
        # ``_fan_control_available`` disables every write until a fresh read
        # succeeds. With no previous sample, retain the empty-safe fallback.
        if not self.current_state:
            self.current_state = {
                "error": self._refresh_error,
                "sensores": {},
                "modulos": {},
                "driver_control": False,
            }
        self._apply_state()

    def _apply_refresh_payload(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        self.current_state = _dict(data.get("fans"))
        self.performance_state = _dict(data.get("performance"))
        self.gpu_state = _dict(data.get("gpu"))
        self._refresh_error = ""
        self._apply_state()
        if self._updates_active:
            self._maybe_apply_curve()

    def _apply_state(self) -> None:
        selected_before = self.channel_combo.currentData()
        presentation = present_fan_state(
            self.current_state,
            self.performance_state,
            self.gpu_state,
            visible_order=VISIBLE_PWM_ORDER,
            selected_index=selected_before,
            preferred_index=self._preferred_pwm,
        )
        self._sync_fan_channels(presentation)
        self._render_fan_presentation(presentation)
        self._update_selected_metrics()
        self._update_action_availability()
        self._update_curve_summary()

    def _sync_fan_channels(self, presentation: FanStatePresentation) -> None:
        fans = list(presentation.fans)
        entries: list[tuple[str, int]] = []
        for fan in fans:
            index = _integer(fan.get("index"), 0)
            label = fan.get("label") or f"Fan {index}"
            entries.append((f"PWM {index} · {label}", index))
        self.channel_combo.blockSignals(True)
        # The channel list is hardware; it does not change between ticks. Only
        # rebuild the model when it actually differs, because clearing a
        # QComboBox throws away its item model and invalidates the popup's
        # geometry — every three seconds, for a list that never moved.
        current = [
            (self.channel_combo.itemText(row), self.channel_combo.itemData(row))
            for row in range(self.channel_combo.count())
        ]
        if current != entries:
            self.channel_combo.clear()
            for text, index in entries:
                self.channel_combo.addItem(text, index)
        target = presentation.selected_index
        selected_index = self.channel_combo.findData(target)
        if selected_index < 0 and self.channel_combo.count() > 0:
            selected_index = 0
        if selected_index >= 0:
            self.channel_combo.setCurrentIndex(selected_index)
        self.channel_combo.blockSignals(False)
        # A selector with a single possible value adds no information and the
        # native Mint/GTK popup can expand into a large empty surface.  Keep the
        # selected channel name visible and reveal this compact selector only
        # when the hardware actually exposes a choice.
        self.channel_selector_host.setVisible(self.channel_combo.count() > 1)

        for row, channel in zip(self.channel_rows, fans + [None] * (len(self.channel_rows) - len(fans))):
            row.set_channel(channel)

    def _render_fan_presentation(self, presentation: FanStatePresentation) -> None:
        driver = tr(presentation.driver)
        selected_pwm = self.channel_combo.currentData()
        selected_channel_text = f"PWM {selected_pwm}" if selected_pwm is not None else tr("No PWM channel")

        self._render_fan_summary(presentation, driver, selected_channel_text)
        self._render_fan_telemetry(presentation, selected_channel_text)
        self._render_fan_driver(presentation, driver)

    def _render_fan_summary(
        self,
        presentation: FanStatePresentation,
        driver: str,
        selected_channel_text: str,
    ) -> None:
        # The page has one deliberate hierarchy: telemetry answers "what is
        # happening now?"; the control surface below answers "what changes?".
        if self._refresh_error:
            title = tr("Cooling data needs refresh")
            detail = tr("Last valid telemetry is shown; PWM writes are locked.")
            status, tone = tr("Stale"), "orange"
        elif presentation.control:
            title = tr("Live cooling")
            # The common NCT6687 presentation already uses the chip name as
            # the driver label.  Avoid a visually noisy ``nct6687 · nct6687``
            # in the compact overview while retaining a distinct chip when
            # the controller reports one.
            detail_parts = [selected_channel_text, driver]
            chip = str(presentation.chip or "").strip()
            if chip and chip.casefold() != str(driver).strip().casefold():
                detail_parts.append(chip)
            detail = " · ".join(detail_parts)
            status, tone = tr("Writable"), "green"
        elif presentation.chip:
            title = tr("Monitoring only")
            detail = f"{driver} · {presentation.chip}"
            status, tone = tr("Read only"), "blue"
        else:
            title = tr("Cooling controller not detected")
            detail = tr("Prepare PWM or use read-only monitoring to discover NCT sensors.")
            status, tone = tr("Unavailable"), "gray"
        self.overview_title.setText(title)
        self.overview_detail.setText(detail)
        self.overview_status.setText(status)
        self.overview_status.set_tone(tone)
        self.control_status_chip.setText(status)
        self.control_status_chip.set_tone(tone)

    def _render_fan_telemetry(
        self,
        presentation: FanStatePresentation,
        selected_channel_text: str,
    ) -> None:
        main_fan = presentation.main_fan
        gpu_temp = presentation.gpu_temperature
        curve_temp, curve_sensor = select_fan_control_temperature({
            "gpu_temp": gpu_temp,
            "cpu_temp": presentation.cpu_temperature,
        })
        live_target = (
            self._curve_percent_for_temp(curve_temp)
            if curve_temp is not None
            else None
        )

        self.rpm_metric.set_values(
            _rpm_text(main_fan.get("rpm")),
            str(main_fan.get("label") or tr("No reporting fan")),
        )
        self.duty_metric.set_values(
            _percent_text(presentation.selected_percent),
            selected_channel_text,
        )
        self.gpu_temp_metric.set_values(_temperature_text(gpu_temp), tr("Automatic curve input"))
        self.cpu_temp_metric.set_values(
            _temperature_text(presentation.cpu_temperature),
            tr("CPU package sensor"),
        )
        self.telemetry_source.set_values(
            presentation.chip or tr("Not detected"),
            presentation.path or tr("No NCT hwmon route"),
        )
        if self._refresh_error:
            self.telemetry_refresh.set_values(
                tr("Last refresh failed"),
                self._refresh_error,
            )
        else:
            self.telemetry_refresh.set_values(
                datetime.now().strftime("%H:%M:%S"),
                tr("Passive refresh"),
            )
        self.curve_plot.set_live(curve_temp, live_target)
        self.curve_live_value.setText(
            f"{str(curve_sensor).upper()} {curve_temp:.1f} °C"
            if curve_temp is not None
            else f"{tr('CPU temperature')} / {tr('GPU temperature')}: --"
        )
        self.curve_live_target.setText(
            tr_format("Target {value}%", value=live_target)
            if live_target is not None
            else tr("Target -- %")
        )

    def _render_fan_driver(self, presentation: FanStatePresentation, driver: str) -> None:
        control = presentation.control

        self.driver_mode_value.setText(tr(presentation.driver_mode))
        self.driver_mode_detail.setText(
            tr(presentation.summary) if presentation.summary else presentation.path or tr("No NCT hwmon route available.")
        )
        self.chip_status.set_values(presentation.chip or tr("Not detected"), "NCT hardware monitor")
        self.module_status.set_values(driver, presentation.module_raw or tr("No NCT module line in /proc/modules"))
        self.control_status.set_values(tr("Available" if control else "Read only"), presentation.summary or tr("PWM status unavailable"))
        self.path_status.set_values(presentation.path or "--", tr("Detected /sys/class/hwmon route"))
        self.driver_status_chip.setText(tr(presentation.driver_status))
        self.driver_status_chip.set_tone(presentation.driver_tone)


    def _update_selected_metrics(self) -> None:
        selected_fan = self._selected_fan()
        percent = _pwm_to_percent(selected_fan.get("pwm")) if selected_fan else None
        pwm = self.channel_combo.currentData()
        channel_text = f"PWM {pwm}" if pwm is not None else tr("No PWM channel")
        self.duty_metric.set_values(_percent_text(percent), channel_text)
        self.selected_channel_readout.setText(channel_text)
        self.selected_channel_meta.setText(str(
            selected_fan.get("pwm_path")
            or tr("Select a detected PWM channel for BC250 cooling control.")
        ))
        self.channel_combo.setToolTip(self.selected_channel_meta.text())
        rpm = selected_fan.get("rpm") if selected_fan else None
        self.selected_live_rpm.setText(_rpm_text(rpm))
        if (
            selected_fan.get("pwm_user_writable")
            or selected_fan.get("pwm_writable")
            or selected_fan.get("writable")
        ):
            access = tr("User-writable channel")
        elif selected_fan.get("pwm_root_writable"):
            access = tr("Authenticated write required")
        else:
            access = tr("Read-only channel")
        if self._refresh_error:
            access = tr("Sensor data is stale; refresh before a PWM write.")
        self.selected_access.setText(access)
        mode = _integer(selected_fan.get("pwm_enable"), -1) if selected_fan else -1
        if mode == 1:
            mode_text, mode_tone, mode_tip = tr("Manual"), "green", tr("Manual mode")
        elif mode == 2:
            mode_text, mode_tone, mode_tip = tr("Automatic"), "blue", tr("Firmware automatic")
        else:
            mode_text, mode_tone, mode_tip = tr("Unknown mode"), "gray", tr("Unknown mode")
        self.selected_mode.setText(mode_text)
        self.selected_mode.set_tone(mode_tone)
        self.selected_mode.setToolTip(mode_tip)
        if self._refresh_error:
            self.control_status_chip.setText(tr("Stale"))
            self.control_status_chip.set_tone("orange")
        elif self._selected_channel_writable():
            self.control_status_chip.setText(tr("Ready"))
            self.control_status_chip.set_tone("green")
        elif selected_fan:
            self.control_status_chip.setText(tr("Read only"))
            self.control_status_chip.set_tone("blue")

    def _selected_channel_writable(self) -> bool:
        return self._fan_writable_for_pwm(self.channel_combo.currentData())

    def _fan_writable_for_pwm(self, pwm: object) -> bool:
        expected = _integer(pwm, -1)
        fan = next(
            (item for item in self._visible_fans() if _integer(item.get("index"), -1) == expected),
            {},
        )
        if not fan:
            return False
        return bool(
            fan.get("pwm_user_writable")
            or fan.get("pwm_root_writable")
            or fan.get("writable")
            or fan.get("root_writable")
        )

    def _update_action_availability(self) -> None:
        availability = plan_fan_action_availability(
            control_ready=self._fan_control_available(),
            channel_count=self.channel_combo.count(),
            curve_point_count=len(self.curve_points),
            busy=self._busy,
        )
        manual_writable = availability.apply_pwm and self._selected_channel_writable()
        curve_editable = availability.edit_curve and self.curve_enabled.isChecked()
        curve_writable = (
            availability.apply_curve
            and self.curve_enabled.isChecked()
            and self._fan_writable_for_pwm(self._curve_target_pwm)
        )
        self.channel_combo.setEnabled(availability.channel_select)
        self.speed_control.setEnabled(availability.channel_select)
        self.use_live_button.setEnabled(availability.use_live)
        self.apply_pwm_button.setEnabled(manual_writable)
        self.restore_auto_button.setEnabled(manual_writable)
        self.apply_curve_button.setEnabled(curve_writable)
        self.save_curve_button.setEnabled(curve_editable)
        self.curve_use_channel_button.setEnabled(availability.channel_select and self.curve_enabled.isChecked())
        self.curve_daemon_settings_button.setEnabled(not self._busy)
        self.curve_editor_toggle.setEnabled(curve_editable)
        self.manual_mode_button.setEnabled(not self._busy)
        self.curve_mode_button.setEnabled(not self._busy)
        for button in self.manual_preset_buttons:
            button.setEnabled(availability.channel_select)
        self.add_curve_point_button.setEnabled(availability.add_point and curve_editable)
        self.remove_curve_point_button.setEnabled(availability.remove_point and curve_editable)
        for point in self.curve_points:
            point.setEnabled(curve_editable)
        for button in self.curve_preset_buttons:
            button.setEnabled(curve_editable)
        self.curve_enabled.setEnabled(availability.edit_curve)
        self.prepare_button.setEnabled(availability.driver_setup)
        self.read_only_button.setEnabled(availability.driver_setup)
        self.disable_button.setEnabled(availability.driver_setup)
        if self.header.action_button is not None:
            self.header.action_button.setEnabled(availability.driver_setup)

    def _gpu_temperature(self) -> float | None:
        return present_fan_state(
            self.current_state,
            self.performance_state,
            self.gpu_state,
            visible_order=VISIBLE_PWM_ORDER,
            selected_index=self.channel_combo.currentData(),
            preferred_index=self._preferred_pwm,
        ).gpu_temperature

    def _cpu_temperature(self) -> float | None:
        return present_fan_state(
            self.current_state,
            self.performance_state,
            self.gpu_state,
            visible_order=VISIBLE_PWM_ORDER,
            selected_index=self.channel_combo.currentData(),
            preferred_index=self._preferred_pwm,
        ).cpu_temperature

    def _curve_temperature(self) -> tuple[float | None, str | None]:
        return select_fan_control_temperature({
            "gpu_temp": self._gpu_temperature(),
            "cpu_temp": self._cpu_temperature(),
        })

    def _maybe_apply_curve(self) -> None:
        temperature, _sensor = self._curve_temperature()
        now = time.monotonic()
        validation_error = self._curve_validation_error()
        percent = (
            self._curve_percent_for_temp(temperature)
            if temperature is not None and not validation_error
            else None
        )
        decision = plan_automatic_curve(
            busy=self._busy,
            curve_enabled=self.curve_enabled.isChecked(),
            control_ready=self._fan_control_available(),
            validation_error=validation_error,
            temperature=temperature,
            now=now,
            last_apply=self._last_curve_apply,
            last_percent=self._last_curve_percent,
            calculated_percent=percent,
            selected_pwm=(
                self._curve_target_pwm
                if self._fan_writable_for_pwm(self._curve_target_pwm)
                else None
            ),
        )
        if decision.action == "touch":
            self._last_curve_apply = decision.touched_at or now
            return
        if decision.action == "apply":
            self._run_pwm_write(
                decision.pwm,
                decision.percent or 0,
                source="curve",
                automatic=True,
            )

    def _record_event(self, level: str, title: str, detail: str) -> None:
        self._event_sequence += 1

        def operation() -> object:
            if self.activity_service is None:
                raise RuntimeError("FansPage requires an activity service to record events")
            self.activity_service.record("fan", level, title, detail, {})
            return True

        self._background.start(
            f"fan-event:{self._event_sequence}",
            operation,
        )

    def _show_info(
        self,
        title: str,
        message: str,
        *,
        tone: str = "blue",
        parent: QWidget | None = None,
    ) -> None:
        icon_name = "warning_orange" if tone in {"orange", "red"} else "info_blue"
        InfoDialog(
            title,
            message,
            icon_name=icon_name,
            parent=parent or self,
            eyebrow="THERMAL CONTROL",
            button_text="Close",
            notice="No additional hardware command will run automatically.",
            tone=tone,
        ).exec()

    def _show_error(
        self,
        title: str,
        message: str,
        *,
        parent: QWidget | None = None,
    ) -> None:
        self._show_info(title, message, tone="red", parent=parent)
