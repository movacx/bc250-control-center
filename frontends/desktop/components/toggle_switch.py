"""An on/off switch that looks like one.

Settings used to style a plain ``QCheckBox`` indicator into a rounded bar. Qt
style sheets cannot draw a knob inside an indicator, so "on" was a solid
accent pill and "off" a grey one, and nothing on screen said which side was
which. This paints a real track and knob, animates between them, and keeps
every ``QCheckBox`` behaviour — the ``toggled`` signal, Space to toggle, the
gamepad's activation, accessibility — because it still is one.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QCheckBox, QWidget

TRACK_WIDTH = 40
TRACK_HEIGHT = 22
KNOB_MARGIN = 3
FOCUS_RING = 2
ANIMATION_MS = 130


def _scale() -> float:
    from ..theme import ACTIVE_SCALE

    return max(0.7, min(1.5, ACTIVE_SCALE / 100.0))


class ToggleSwitch(QCheckBox):
    """A ``QCheckBox`` drawn as a switch: accent track and white knob when on."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("toggleSwitch", True)
        self._position = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(ANIMATION_MS)
        self._animation.valueChanged.connect(self._set_position)
        self.toggled.connect(self._animate_to)

    # ------------------------------------------------------------- geometry

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        factor = _scale()
        pad = FOCUS_RING * 2
        return QSize(round(TRACK_WIDTH * factor) + pad, round(TRACK_HEIGHT * factor) + pad)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return self.sizeHint()

    def hitButton(self, pos) -> bool:  # noqa: N802 - Qt API name
        return self.rect().contains(pos)

    # ------------------------------------------------------------ animation

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt API name
        super().setChecked(checked)
        # A programmatic change (settings restored, a signal blocker in place)
        # lands without a slide: only the user's own click animates.
        if self.signalsBlocked() or not self.isVisible():
            self._animation.stop()
            self._position = 1.0 if self.isChecked() else 0.0
            self.update()

    def _animate_to(self, checked: bool) -> None:
        if not self.isVisible():
            self._position = 1.0 if checked else 0.0
            return
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def _set_position(self, value) -> None:
        self._position = float(value)
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        if self._animation.state() != QVariantAnimation.State.Running:
            self._position = 1.0 if self.isChecked() else 0.0

    # --------------------------------------------------------------- paint

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        from ..theme import ACTIVE_MODE, COLORS

        factor = _scale()
        width = TRACK_WIDTH * factor
        height = TRACK_HEIGHT * factor
        x = (self.width() - width) / 2.0
        y = (self.height() - height) / 2.0
        track = QRectF(x, y, width, height)
        radius = height / 2.0

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        enabled = self.isEnabled()
        if not enabled:
            painter.setOpacity(0.45)

        off_fill = QColor(COLORS["control_pressed"])
        on_fill = QColor(COLORS["blue"])
        fill = QColor(
            round(off_fill.red() + (on_fill.red() - off_fill.red()) * self._position),
            round(off_fill.green() + (on_fill.green() - off_fill.green()) * self._position),
            round(off_fill.blue() + (on_fill.blue() - off_fill.blue()) * self._position),
        )
        border = QColor(COLORS["border_strong"]) if self._position < 0.5 else on_fill
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(fill)
        painter.drawRoundedRect(track.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        knob_diameter = height - 2 * KNOB_MARGIN * factor
        travel = width - knob_diameter - 2 * KNOB_MARGIN * factor
        knob_x = x + KNOB_MARGIN * factor + travel * self._position
        knob_y = y + KNOB_MARGIN * factor
        knob = QColor("#FFFFFF")
        if ACTIVE_MODE == "dark" and self._position < 0.5:
            knob = QColor(COLORS["muted"])
        shadow = QColor(0, 0, 0, 40 if ACTIVE_MODE == "light" else 90)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow)
        painter.drawEllipse(QRectF(knob_x, knob_y + 0.8, knob_diameter, knob_diameter))
        painter.setBrush(knob)
        painter.drawEllipse(QRectF(knob_x, knob_y, knob_diameter, knob_diameter))

        if self.hasFocus() and self.focusPolicy() != Qt.FocusPolicy.NoFocus:
            ring = QColor(COLORS["focus"])
            painter.setOpacity(1.0)
            painter.setPen(QPen(ring, FOCUS_RING))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            outer = track.adjusted(-FOCUS_RING / 2.0, -FOCUS_RING / 2.0,
                                   FOCUS_RING / 2.0, FOCUS_RING / 2.0)
            painter.drawRoundedRect(outer, radius + 1, radius + 1)
        painter.end()

    def knob_center(self) -> QPointF:
        """Where the knob is drawn; for tests that check which side it is on."""
        factor = _scale()
        width = TRACK_WIDTH * factor
        height = TRACK_HEIGHT * factor
        x = (self.width() - width) / 2.0
        knob_diameter = height - 2 * KNOB_MARGIN * factor
        travel = width - knob_diameter - 2 * KNOB_MARGIN * factor
        return QPointF(x + KNOB_MARGIN * factor + travel * self._position + knob_diameter / 2.0,
                       self.height() / 2.0)
