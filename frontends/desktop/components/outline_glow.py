"""The soft outline glow shared by every report button.

The dashboard's report button and an error window's "Report this problem"
light up the same way: the edge and a faint tint fade in and out inside the
button's own outline, once every two seconds.
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QObject,
    QRectF,
    QSequentialAnimationGroup,
    Qt,
    QVariantAnimation,
)
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

#: The amber of the report icon.
REPORT_AMBER = QColor(245, 166, 35)


class OutlineGlow(QObject):
    """Drives the glow level of one button; the button paints it."""

    EDGE_ALPHA = 255
    TINT_ALPHA = 70
    #: A softer second ring just inside the edge, so the glow reads as light.
    HALO_ALPHA = 110
    #: One glow every two seconds: in, out, and a short rest.
    FADE_MS = 700
    PAUSE_MS = 600

    def __init__(self, button: QWidget) -> None:
        super().__init__(button)
        self._button = button
        self._glowing = False
        self.level = 0.0
        self.cycle = QSequentialAnimationGroup(self)
        for start, end in ((0.0, 1.0), (1.0, 0.0)):
            fade = QVariantAnimation(self)
            fade.setDuration(self.FADE_MS)
            fade.setStartValue(start)
            fade.setEndValue(end)
            fade.setEasingCurve(QEasingCurve.Type.InOutSine)
            fade.valueChanged.connect(self._set_level)
            self.cycle.addAnimation(fade)
        self.cycle.addPause(self.PAUSE_MS)
        self.cycle.setLoopCount(-1)

    def _set_level(self, value) -> None:
        self.level = float(value)
        self._button.update()

    def glowing(self) -> bool:
        return self._glowing

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._glowing:
            return
        self._glowing = enabled
        if enabled and self._button.isVisible():
            self.cycle.start()
        elif not enabled:
            self.cycle.stop()
            self._set_level(0.0)

    def shown(self) -> None:
        if self._glowing and self.cycle.state() != QSequentialAnimationGroup.State.Running:
            self.cycle.start()

    def hidden(self) -> None:
        self.cycle.stop()
        self.level = 0.0

    def paint(self, color: QColor, radius: float) -> None:
        button = self._button
        if self.level <= 0.0 or button.underMouse() or button.hasFocus():
            return
        painter = QPainter(button)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = min(radius, button.height() / 2)
        rect = QRectF(button.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), round(self.TINT_ALPHA * self.level)))
        painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), round(self.EDGE_ALPHA * self.level)), 2.0))
        painter.drawRoundedRect(rect, radius, radius)
        halo = rect.adjusted(2.5, 2.5, -2.5, -2.5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), round(self.HALO_ALPHA * self.level)), 3.0))
        painter.drawRoundedRect(halo, max(radius - 2.5, 0), max(radius - 2.5, 0))
        painter.end()
