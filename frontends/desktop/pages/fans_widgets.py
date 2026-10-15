"""Standalone widgets of the Fans page: gauges, curve editor, profile cards and the PWM paths dialog."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSettings,
    Qt,
    QThread,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from bc250cc.platform.init.services import detect_init_manager

from ..components.buttons import WrappingButton as QPushButton
from ..components.card_navigation import EditableCardNavigation
from ..components.dashboard_instruments import Reading
from ..components.dialogs import (
    center_dialog,
    enable_adaptive_dialog,
    reflow_wrapped_labels,
)
from ..components.widgets import IconBadge, icon
from ..core.preferences import application_settings
from ..i18n import localize_widget_tree, shipped_name, tr, tr_format
from ..theme import COLORS, application_stylesheet
from .fans_helpers import _dict, _hairline, _integer, _percent_to_pwm, _pwm_to_percent  # noqa: E402


class LevelBar(QWidget):
    """A thin gauge: how far a reading has come toward its maximum."""

    TONES = {"": "green", "warning": "orange", "danger": "red", "accent": "blue"}

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.fraction: float | None = None
        self.tone = ""
        self.setFixedHeight(6)
        self.setMinimumWidth(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_level(self, fraction: float | None, tone: str = "") -> None:
        fraction = None if fraction is None else max(0.0, min(1.0, float(fraction)))
        if (fraction, tone) == (self.fraction, self.tone):
            return
        self.fraction, self.tone = fraction, tone
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802  # pragma: no cover - visual rendering
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(self.rect())
        radius = rect.height() / 2
        painter.setBrush(QColor(COLORS["progress_track"]))
        painter.drawRoundedRect(rect, radius, radius)
        if self.fraction is None:
            return
        fill = QRectF(rect.left(), rect.top(), max(rect.height(), rect.width() * self.fraction), rect.height())
        painter.setBrush(QColor(COLORS[self.TONES.get(self.tone, "green")]))
        painter.drawRoundedRect(fill, radius, radius)


class BarReading(Reading):
    """A reading with a gauge between its name and its number."""

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(label, parent)
        row = self.layout()
        self.label.setWordWrap(False)
        row.setStretchFactor(self.label, 0)
        self.bar = LevelBar(self)
        row.insertWidget(1, self.bar, 1, Qt.AlignmentFlag.AlignVCenter)
        self.value.setMinimumWidth(self.value.fontMetrics().horizontalAdvance("100.0") + 4)

    def set_level(self, fraction: float | None, tone: str = "") -> None:
        self.bar.set_level(fraction, tone)
        self.set_tone("" if tone == "accent" else tone)


class FieldRow(QFrame):
    """A list row whose right side is a control or a live value, not a number."""

    def __init__(self, label: str, *, rule: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("fanFieldRow", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        if rule:
            box.addWidget(_hairline())
        self.row = QHBoxLayout()
        self.row.setContentsMargins(0, 5, 0, 5)
        self.row.setSpacing(10)
        self.label = QLabel(tr(label))
        self.label.setProperty("readingLabel", True)
        self.label.setMinimumWidth(0)
        self.row.addWidget(self.label, 1)
        box.addLayout(self.row)

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self.row.addWidget(widget, stretch, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)


@dataclass
class FanProfile:
    """A named fixed speed the user can rename and retune."""

    key: str
    name: str
    percent: int

    def summary(self) -> str:
        return f"{self.percent} %"

    def detail(self) -> str:
        return tr_format("Raw PWM {raw} / 255", raw=_percent_to_pwm(self.percent))


#: Three tiers, each saved under a preset key the fan service accepts, so the
#: speed a user gives a profile is the speed it restores from boot.
DEFAULT_FAN_PROFILES: tuple[FanProfile, ...] = (
    FanProfile("quiet", "Quiet", 45),
    FanProfile("balanced", "Balanced", 60),
    FanProfile("maximum", "Maximum", 100),
)


def _fan_profile_prefix(index: int) -> str:
    return f"fans/profile_{index}/"


def load_fan_profiles(settings: QSettings | None = None) -> list[FanProfile]:
    """The user's profile edits, falling back to the shipped tier per slot."""
    settings = settings or application_settings()
    profiles: list[FanProfile] = []
    for index, default in enumerate(DEFAULT_FAN_PROFILES):
        prefix = _fan_profile_prefix(index)
        name = str(settings.value(prefix + "name", "") or "").strip()
        if not name or str(settings.value(prefix + "key", "") or "") != default.key:
            profiles.append(replace(default))
            continue
        percent = max(0, min(100, _integer(settings.value(prefix + "percent", default.percent), default.percent)))
        # A default saved in some language is the shipped name again.
        profiles.append(replace(default, name=shipped_name(name, default.name), percent=percent))
    return profiles


def save_fan_profile(index: int, profile: FanProfile, settings: QSettings | None = None) -> None:
    settings = settings or application_settings()
    prefix = _fan_profile_prefix(index)
    settings.setValue(prefix + "key", profile.key)
    settings.setValue(prefix + "name", profile.name)
    settings.setValue(prefix + "percent", int(profile.percent))
    settings.sync()


class FanProfileCard(EditableCardNavigation, QFrame):
    """A click stages the profile's speed; the pencil edits its name and speed.

    The same card the CPU and GPU modules use for their profiles. It stands in
    for the preset button it replaced: ``payload`` is its speed, the
    ``fanPreset`` property its service key, and it is "checked" while the
    staged speed is its own.
    """

    selected = pyqtSignal(object)
    changed = pyqtSignal(object)

    def __init__(self, profile: FanProfile, default: FanProfile, parent: QWidget | None = None):
        super().__init__(parent)
        self._profile = profile
        self._default = default
        self._checked = False
        self.setProperty("profileCard", True)
        self.setProperty("fanPreset", profile.key)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Its own height, not the row's: while one card shows its editor the
        # others keep their compact face instead of stretching around a gap.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root = QVBoxLayout(self)
        root.setContentsMargins(11, 10, 11, 11)
        root.setSpacing(0)

        self._view = QWidget()
        view = QVBoxLayout(self._view)
        view.setContentsMargins(0, 0, 0, 0)
        view.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(6)
        self._name_label = QLabel()
        self._name_label.setProperty("profileTitle", True)
        self._name_label.setMinimumWidth(0)
        head.addWidget(self._name_label, 1)
        self._edit_button = QPushButton()
        self._edit_button.setIcon(icon("edit_gray"))
        self._edit_button.setFixedSize(24, 24)
        self._edit_button.setToolTip(tr("Edit profile"))
        self._edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_button.setProperty("iconOnlyButton", True)
        self._edit_button.clicked.connect(self.begin_edit)
        head.addWidget(self._edit_button, 0)
        view.addLayout(head)
        self._install_card_navigation(self._edit_button)
        self._value_label = QLabel()
        self._value_label.setProperty("rangeReadout", True)
        view.addWidget(self._value_label)
        self._detail_label = QLabel()
        self._detail_label.setProperty("readingDetail", True)
        view.addWidget(self._detail_label)
        root.addWidget(self._view)

        self._editor = QWidget()
        editor = QVBoxLayout(self._editor)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setSpacing(8)
        editor_head = QHBoxLayout()
        eyebrow = QLabel(tr("EDITING PROFILE"))
        eyebrow.setProperty("eyebrow", True)
        editor_head.addWidget(eyebrow, 1)
        reset = QPushButton(tr("Reset"))
        reset.setProperty("linkButton", True)
        reset.setProperty("quiet", True)
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.clicked.connect(self._restore_default)
        editor_head.addWidget(reset, 0)
        editor.addLayout(editor_head)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(tr("Profile name"))
        self._name_edit.setMaxLength(24)
        editor.addWidget(self._name_edit)
        speed_label = QLabel(tr("Fan speed"))
        speed_label.setProperty("fieldLabel", True)
        editor.addWidget(speed_label)
        self._percent_spin = QSpinBox()
        self._percent_spin.setRange(0, 100)
        self._percent_spin.setSuffix(" %")
        editor.addWidget(self._percent_spin)
        save = QPushButton(tr("Save profile"))
        save.setProperty("cardAction", True)
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self._commit)
        editor.addWidget(save)
        self._editor.setVisible(False)
        root.addWidget(self._editor)
        self._sync_view()

    # -- the preset-button surface the page already speaks --------------------
    @property
    def payload(self) -> int:
        return self._profile.percent

    @property
    def profile(self) -> FanProfile:
        return self._profile

    def set_profile(self, profile: FanProfile) -> None:
        """Show another name and speed in this slot (an imported profile)."""
        self._profile = replace(profile, key=self._profile.key)
        self._sync_view()

    def isChecked(self) -> bool:  # noqa: N802 - mirrors QAbstractButton
        return self._checked

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - mirrors QAbstractButton
        checked = bool(checked)
        if checked == self._checked:
            return
        self._checked = checked
        self.setProperty("selectedProfile", checked)
        self.style().unpolish(self)
        self.style().polish(self)

    # -- editing ----------------------------------------------------------------
    def begin_edit(self) -> None:
        self._name_edit.setText(tr(self._profile.name))
        self._percent_spin.setValue(self._profile.percent)
        self._view.setVisible(False)
        self._editor.setVisible(True)
        self._card_enter_edit()
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def cancel_edit(self) -> None:
        # Focus goes back to the card before its fields disappear: hiding the
        # focused field first hands focus to the next card along, which then
        # wears the focus ring for an edit it had nothing to do with.
        self._card_leave_edit()
        self._editor.setVisible(False)
        self._view.setVisible(True)

    def retranslate(self) -> None:
        self._sync_view()

    def _restore_default(self) -> None:
        self._name_edit.setText(tr(self._default.name))
        self._percent_spin.setValue(self._default.percent)

    def _commit(self) -> None:
        # A name left as the shipped one, in any language, stays the source
        # string, so it keeps following the interface language.
        name = shipped_name(self._name_edit.text(), self._default.name)
        self._profile = replace(self._profile, name=name, percent=self._percent_spin.value())
        self.cancel_edit()
        self._sync_view()
        self.changed.emit(self._profile)

    def _sync_view(self) -> None:
        self._name_label.setText(tr(self._profile.name))
        self._value_label.setText(self._profile.summary())
        self._detail_label.setText(self._profile.detail())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().mouseReleaseEvent(event)
        if self._editor.isVisible():
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._profile)


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
        # Label, value, detail — the reading needs nothing else. The coloured
        # marker dot that used to lead each label said nothing the label did
        # not, and four of them in a row read as decoration.
        self.label = QLabel(tr(label))
        self.label.setProperty("fanSignalLabel", True)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.value = QLabel(tr(value))
        self.value.setProperty("fanSignalValue", True)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail = QLabel(tr(detail))
        self.detail.setProperty("fanSignalDetail", True)
        self.detail.setWordWrap(True)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)
        self.mirror = None  # the list row that shows this reading

    def set_values(self, value: str, detail: str | None = None) -> None:
        self.value.setText(tr(value))
        if detail is not None:
            self.detail.setText(tr(detail))
        if self.mirror is not None:
            # Number only, like every other row of the list: a second line
            # made these two rows taller than the rest.
            self.mirror.set_value(self.value.text())


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
    """Paint the daemon's discrete response against measured axes.

    The temperature axis follows the curve instead of a fixed 30–95 °C
    window, so eight points spread across the plot instead of piling into one
    corner, and the live reading is tagged on the chart itself. Each point is
    numbered the way the editor below numbers it, and the pointer reads the
    exact step it is over, so a curve with many points stays legible.
    """

    MIN_TEMPERATURE = 30.0
    MAX_TEMPERATURE = 95.0
    MINIMUM_HEIGHT = 420
    COMPACT_HEIGHT = 320
    #: How close, in pixels, the pointer has to come to a point to read it.
    HOVER_RADIUS = 16.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points: list[tuple[int, int]] = [(50, 70), (65, 100), (70, 100)]
        self.live_temperature: float | None = None
        self.live_duty: int | None = None
        self.live_sensor = ""
        self.target_pwm: int | None = None
        self.enabled = False
        self.compact = False
        self.hovered: int | None = None
        self._plot = QRectF()
        self.setMinimumHeight(self.MINIMUM_HEIGHT)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_state(
        self,
        points: list[tuple[int, int]],
        temperature: float | None,
        duty: int | None,
        enabled: bool,
        sensor: str = "",
        target_pwm: int | None = None,
    ) -> None:
        self.points = sorted(points, key=lambda item: item[0]) or [(50, 70)]
        self.live_temperature = temperature
        self.live_duty = duty
        self.live_sensor = str(sensor or "")
        self.target_pwm = target_pwm
        self.enabled = bool(enabled)
        if self.hovered is not None and self.hovered >= len(self.points):
            self.hovered = None
        self.update()

    def set_compact(self, compact: bool) -> None:
        self.compact = bool(compact)
        self.setMinimumHeight(self.COMPACT_HEIGHT if self.compact else self.MINIMUM_HEIGHT)
        self.updateGeometry()
        self.update()

    def temperature_range(self) -> tuple[float, float]:
        """Axis bounds in whole 5 °C steps around the points and the reading."""
        temperatures = [float(temperature) for temperature, _speed in self.points]
        if self.live_temperature is not None:
            temperatures.append(float(self.live_temperature))
        low = min([self.MIN_TEMPERATURE, *(value - 5 for value in temperatures)])
        high = max([self.MAX_TEMPERATURE, *(value + 5 for value in temperatures)])
        low = max(0.0, math.floor(low / 5) * 5)
        high = min(120.0, math.ceil(high / 5) * 5)
        return low, max(low + 10.0, high)

    @staticmethod
    def _bounded_duty(duty: float) -> float:
        return max(0.0, min(100.0, float(duty)))

    def _point_positions(self) -> list[QPointF]:
        if self._plot.isEmpty():
            return []
        low, high = self.temperature_range()
        span = high - low
        plot = self._plot
        return [
            QPointF(
                plot.left() + (max(low, min(high, float(temperature))) - low) / span * plot.width(),
                plot.bottom() - self._bounded_duty(duty) / 100.0 * plot.height(),
            )
            for temperature, duty in self.points
        ]

    def point_at(self, position: QPointF) -> int | None:
        """The point under the pointer, if one is close enough to read."""
        best, best_distance = None, self.HOVER_RADIUS
        for index, point in enumerate(self._point_positions()):
            distance = math.hypot(point.x() - position.x(), point.y() - position.y())
            if distance <= best_distance:
                best, best_distance = index, distance
        return best

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        hovered = self.point_at(event.position())
        if hovered != self.hovered:
            self.hovered = hovered
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self.hovered is not None:
            self.hovered = None
            self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # pragma: no cover - visual rendering
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = painter.font()
        font.setPixelSize(10 if self.compact else 11)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        low, high = self.temperature_range()
        span = high - low
        # A band above the plot holds the live tag, so it never sits on the
        # 100 % line where the top points are; the right margin fits the last
        # temperature label instead of cutting it at the edge.
        tag_height = metrics.height() + 8
        left = float(metrics.horizontalAdvance("100%") + 14)
        top = float(tag_height + 14)
        right = float(metrics.horizontalAdvance(f"{int(high)} °C") / 2 + 10)
        bottom = float(metrics.height() + 14)
        plot = QRectF(
            left,
            top,
            max(40.0, self.width() - left - right),
            max(60.0, self.height() - top - bottom),
        )
        self._plot = plot

        def x_for(temperature: float) -> float:
            bounded = max(low, min(high, float(temperature)))
            return plot.left() + (bounded - low) / span * plot.width()

        def y_for(duty: float) -> float:
            return plot.bottom() - self._bounded_duty(duty) / 100.0 * plot.height()

        grid = QColor(COLORS["chart_grid"])
        minor = QColor(grid)
        minor.setAlpha(90)
        # Duty: a line every 10 %, labelled every 20 % (every 10 % when the
        # plot is tall enough to hold the words).
        label_every = 10 if plot.height() / 10 >= 38 else 20
        for duty in range(0, 101, 10):
            y = y_for(duty)
            painter.setPen(QPen(grid if duty % 20 == 0 else minor, 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            if duty % label_every == 0:
                painter.setPen(QColor(COLORS["subtle"]))
                painter.drawText(
                    QRectF(0, y - 8, left - 8, 16),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    f"{duty}%",
                )
        # Temperature: a line every 5 °C, labelled every 5 or 10 °C as the
        # width allows.
        first = int(math.ceil(low / 5) * 5)
        ticks = list(range(first, int(high) + 1, 5))
        per_step = plot.width() / max(1, len(ticks) - 1)
        name_step = 5 if per_step >= metrics.horizontalAdvance("100 °C") + 12 else 10
        for temperature in ticks:
            x = x_for(temperature)
            painter.setPen(QPen(grid if temperature % 10 == 0 else minor, 1))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            if temperature % name_step:
                continue
            text = f"{temperature} °C"
            width = metrics.horizontalAdvance(text) + 6
            painter.setPen(QColor(COLORS["subtle"]))
            painter.drawText(
                QRectF(x - width / 2, plot.bottom() + 6, width, metrics.height()),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                text,
            )
        painter.setPen(QPen(QColor(COLORS["chart_axis"]), 1))
        painter.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))

        points = self.points or [(50, 70)]
        # The interface accent when the curve drives the fan, neutral grey
        # while it is only a preview: the state reads from the line itself.
        line_color = QColor(COLORS["blue"] if self.enabled else COLORS["subtle"])
        # The exact step response the daemon applies, as one path: the line
        # and a faint fill under it, so the duty at any temperature is the
        # height of the shaded area rather than something to trace by eye.
        previous_duty = points[0][1]
        response = QPainterPath(QPointF(plot.left(), y_for(previous_duty)))
        for threshold, duty in points[1:]:
            x = x_for(threshold)
            response.lineTo(QPointF(x, y_for(previous_duty)))
            response.lineTo(QPointF(x, y_for(duty)))
            previous_duty = duty
        response.lineTo(QPointF(plot.right(), y_for(previous_duty)))
        area = QPainterPath(response)
        area.lineTo(QPointF(plot.right(), plot.bottom()))
        area.lineTo(QPointF(plot.left(), plot.bottom()))
        area.closeSubpath()
        fill = QColor(line_color)
        fill.setAlpha(28 if self.enabled else 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawPath(area)
        painter.setPen(QPen(
            line_color, 2.2, Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin,
        ))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(response)

        # Numbered points, the numbers the editor rows carry. Small enough
        # to sit five degrees apart; the hovered one is drawn larger.
        number_font = painter.font()
        number_font.setPixelSize(9)
        number_font.setBold(True)
        painter.setFont(number_font)
        for index, (threshold, duty) in enumerate(points):
            center = QPointF(x_for(threshold), y_for(duty))
            radius = 10.0 if index == self.hovered else 8.0
            painter.setPen(QPen(line_color, 2))
            painter.setBrush(QColor(COLORS["panel_raised"]))
            painter.drawEllipse(center, radius, radius)
            painter.setPen(QColor(COLORS["text"]))
            painter.drawText(
                QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2),
                Qt.AlignmentFlag.AlignCenter,
                str(index + 1),
            )
        painter.setFont(font)

        if self.live_temperature is not None:
            live_x = x_for(self.live_temperature)
            live_duty = self.live_duty if self.live_duty is not None else points[0][1]
            accent = QColor(COLORS["orange"])
            painter.setPen(QPen(accent, 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(live_x, plot.top()), QPointF(live_x, plot.bottom()))
            painter.setPen(QPen(QColor(COLORS["panel"]), 2))
            painter.setBrush(accent)
            painter.drawEllipse(QPointF(live_x, y_for(live_duty)), 5.0, 5.0)
            tag = self.live_tag()
            tag_width = metrics.horizontalAdvance(tag) + 16
            tag_x = min(max(plot.left(), live_x - tag_width / 2), plot.right() - tag_width)
            tag_rect = QRectF(tag_x, 4, tag_width, tag_height)
            painter.setPen(QPen(accent, 1))
            painter.setBrush(QColor(COLORS["panel_raised"]))
            painter.drawRoundedRect(tag_rect, 5, 5)
            painter.setPen(QColor(COLORS["text"]))
            painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, tag)

        if self.hovered is not None and self.hovered < len(points):
            threshold, duty = points[self.hovered]
            center = QPointF(x_for(threshold), y_for(duty))
            text = tr_format("Point {index}", index=self.hovered + 1) + f" · {threshold} °C → {duty}%"
            width = metrics.horizontalAdvance(text) + 16
            height = metrics.height() + 10
            box_x = min(max(plot.left(), center.x() - width / 2), plot.right() - width)
            box_y = center.y() + 14 if center.y() - 14 - height < plot.top() else center.y() - 14 - height
            box = QRectF(box_x, box_y, width, height)
            painter.setPen(QPen(QColor(COLORS["border"]), 1))
            painter.setBrush(QColor(COLORS["panel_raised"]))
            painter.drawRoundedRect(box, 6, 6)
            painter.setPen(QColor(COLORS["text"]))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def live_tag(self) -> str:
        """The live reading as tagged: which channel, what input, which duty."""
        if self.live_temperature is None:
            return ""
        duty = self.live_duty if self.live_duty is not None else (self.points or [(0, 0)])[0][1]
        sensor = f"{self.live_sensor.upper()} " if self.live_sensor else ""
        channel = f"PWM {self.target_pwm} · " if self.target_pwm else ""
        return f"{channel}{sensor}{self.live_temperature:.1f} °C → {int(duty)}%"


class FanCurvePlot(QWidget):
    """The response chart alone: no caption rows competing with the data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = [(50, 70), (65, 100), (70, 100)]
        self.live_temperature: float | None = None
        self.live_duty: int | None = None
        self.live_sensor = ""
        self.target_pwm: int | None = None
        self.enabled = False
        self.compact = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.scale = FanCurveScale(self)
        root.addWidget(self.scale)
        self._render()

    def set_curve(self, points: list[tuple[int, int]]) -> None:
        self.points = sorted(points, key=lambda item: item[0]) or [(50, 70)]
        self._render()

    def set_live(self, temperature: float | None, duty: int | None, sensor: str = "") -> None:
        self.live_temperature = temperature
        self.live_duty = duty
        self.live_sensor = str(sensor or "")
        self._render()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self._render()

    def set_target(self, pwm: int | None) -> None:
        """The channel the curve drives, named in the live tag."""
        self.target_pwm = pwm
        self._render()

    def set_compact(self, compact: bool) -> None:
        self.compact = bool(compact)
        self.scale.set_compact(self.compact)
        self.updateGeometry()

    def retranslate(self) -> None:
        self._render()

    def live_text(self) -> str:
        """The reading the chart tags, for tests and accessibility."""
        return self.scale.live_tag()

    def _render(self) -> None:
        self.scale.set_state(
            self.points,
            self.live_temperature,
            self.live_duty,
            self.enabled,
            self.live_sensor,
            self.target_pwm,
        )
        self.setAccessibleDescription(self.live_text())


class FanModeStack(QStackedWidget):
    """A mode stack whose height follows only the page currently in use."""

    #: The page on screen now needs a different height than the one the stack
    #: is pinned to: a profile card opened its editor, a row wrapped. Whoever
    #: pins the stack has to measure again, or the page is squeezed into the
    #: old height and its widgets are drawn over each other.
    page_height_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Fixed means “use the current page's natural hint”, not a manually
        # cached pixel height.  It keeps a maximized window from donating all
        # of its spare vertical room to the slider.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.currentChanged.connect(lambda _index: self.updateGeometry())

    def addWidget(self, widget: QWidget) -> int:  # noqa: N802 - Qt API name
        index = super().addWidget(widget)
        widget.installEventFilter(self)
        return index

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API name
        if event.type() == QEvent.Type.LayoutRequest and watched is self.currentWidget():
            wanted = max(watched.minimumSizeHint().height(), watched.sizeHint().height())
            # Compared with the pin, not the current height: the pin is set at
            # once, the geometry only once the parent lays out again, and
            # comparing with that would ask for the same measurement forever.
            if wanted != self.maximumHeight():
                self.page_height_changed.emit()
        return super().eventFilter(watched, event)

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
        eyebrow.setStyleSheet(f".QLabel {{ color:{COLORS['blue']}; }}")
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
