"""A TV remote control, drawn: the body, its buttons and their symbols.

Everything is painted with the current palette and scale, so the remote follows
the theme and needs no image files. The buttons are ordinary ``QPushButton``s:
Tab reaches them, Space and Enter press them, and each carries an accessible
name and a tooltip, because a symbol alone says nothing to a screen reader.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QPushButton, QSizePolicy, QWidget

# What a button looks like when it is neutral, or says "on" or "off".
TONES = {"neutral": "text", "on": "green", "off": "red"}


def _scale() -> float:
    from ..theme import ACTIVE_SCALE

    return max(0.7, min(1.5, ACTIVE_SCALE / 100.0))


def _color(name: str) -> QColor:
    from ..theme import COLORS

    return QColor(COLORS[name])


def paint_glyph(painter: QPainter, kind: str, area: QRectF, color: QColor) -> None:
    """One of the remote's symbols, centred in ``area``, in ``color``."""
    side = min(area.width(), area.height())
    centre = area.center()
    unit = side / 24.0
    pen = QPen(color, max(1.6, unit * 2.0))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    def point(x: float, y: float) -> QPointF:
        return QPointF(centre.x() + x * unit, centre.y() + y * unit)

    if kind == "power":
        radius = 8.5 * unit
        circle = QRectF(centre.x() - radius, centre.y() - radius + unit, radius * 2, radius * 2)
        # Qt measures angles in sixteenths of a degree, from three o'clock: leave the top open.
        painter.drawArc(circle, 120 * 16, 300 * 16)
        painter.drawLine(point(0, -10), point(0, -1))
    elif kind == "input":
        # An arrow going into a box that is open on the left.
        box = QPainterPath(point(-2, -9))
        box.lineTo(point(9, -9))
        box.lineTo(point(9, 9))
        box.lineTo(point(-2, 9))
        painter.drawPath(box)
        painter.drawLine(point(-10, 0), point(3, 0))
        painter.drawLine(point(-1, -4), point(3, 0))
        painter.drawLine(point(-1, 4), point(3, 0))
    elif kind == "plus":
        painter.drawLine(point(-7, 0), point(7, 0))
        painter.drawLine(point(0, -7), point(0, 7))
    elif kind == "minus":
        painter.drawLine(point(-7, 0), point(7, 0))
    elif kind == "mute":
        painter.setBrush(color)
        speaker = QPainterPath(point(-10, -4))
        speaker.lineTo(point(-5, -4))
        speaker.lineTo(point(1, -9))
        speaker.lineTo(point(1, 9))
        speaker.lineTo(point(-5, 4))
        speaker.lineTo(point(-10, 4))
        speaker.closeSubpath()
        painter.drawPath(speaker)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(point(5, -4), point(11, 4))
        painter.drawLine(point(11, -4), point(5, 4))
    elif kind == "gear":
        # Eight square teeth round a ring, and the axle's hole.
        outline = QPainterPath()
        first = True
        for tooth in range(8):
            for offset, radius in ((-13, 7.2), (-9, 10.2), (9, 10.2), (13, 7.2)):
                angle = math.radians(45 * tooth + offset)
                target = point(radius * math.cos(angle), radius * math.sin(angle))
                if first:
                    outline.moveTo(target)
                    first = False
                else:
                    outline.lineTo(target)
        outline.closeSubpath()
        painter.drawPath(outline)
        painter.drawEllipse(point(0, 0), 3 * unit, 3 * unit)
    elif kind == "back":
        painter.drawLine(point(7, 0), point(-7, 0))
        painter.drawLine(point(-1, -6), point(-7, 0))
        painter.drawLine(point(-1, 6), point(-7, 0))


class GlyphButton(QPushButton):
    """A button that is only a symbol.

    ``shape`` is ``circle``, ``square`` (rounded), ``pill`` (wide), or one half
    of the volume rocker, ``rocker-top`` and ``rocker-bottom``.
    """

    def __init__(self, glyph: str, label: str, *, shape: str = "circle", tone: str = "neutral",
                 width: int = 46, height: int | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.glyph, self.shape, self.tone = glyph, shape, tone
        self._base = (width, height if height is not None else width)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(label)
        self.setAccessibleName(label)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        factor = _scale()
        return QSize(round(self._base[0] * factor), round(self._base[1] * factor))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return self.sizeHint()

    def _outline(self, area: QRectF) -> QPainterPath:
        path = QPainterPath()
        if self.shape == "circle":
            path.addEllipse(area)
        elif self.shape in {"rocker-top", "rocker-bottom"}:
            radius = area.width() / 2
            top = self.shape == "rocker-top"
            # Round only the outer corners: the two halves make one pill.
            path.moveTo(area.left(), area.bottom() if top else area.top())
            if top:
                path.lineTo(area.left(), area.top() + radius)
                path.arcTo(QRectF(area.left(), area.top(), radius * 2, radius * 2), 180, -180)
                path.lineTo(area.right(), area.bottom())
            else:
                path.lineTo(area.left(), area.bottom() - radius)
                path.arcTo(QRectF(area.left(), area.bottom() - radius * 2, radius * 2, radius * 2), 180, 180)
                path.lineTo(area.right(), area.top())
            path.closeSubpath()
        else:
            radius = area.height() / 2 if self.shape == "pill" else area.width() * 0.28
            path.addRoundedRect(area, radius, radius)
        return path

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        enabled = self.isEnabled()
        if not enabled:
            fill, edge, ink = _color("disabled_bg"), _color("border_soft"), _color("disabled_text")
        else:
            fill = _color("control_pressed" if self.isDown() else "control_hover" if self.underMouse() else "control")
            edge = _color("border_strong")
            ink = _color(TONES.get(self.tone, "text"))
        outline = self._outline(area)
        painter.fillPath(outline, fill)
        painter.setPen(QPen(_color("focus") if self.hasFocus() and enabled else edge, 2 if self.hasFocus() else 1))
        painter.drawPath(outline)
        glyph_area = area.adjusted(area.width() * 0.26, area.height() * 0.26, -area.width() * 0.26, -area.height() * 0.26)
        paint_glyph(painter, self.glyph, glyph_area, ink)
        painter.end()


class RemoteBody(QWidget):
    """The remote's silhouette: a tall rounded body with the infrared window on top."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        factor = _scale()
        area = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        radius = 40 * factor
        outline = QPainterPath()
        outline.addRoundedRect(area, radius, radius)
        painter.fillPath(outline, _color("panel_raised"))
        painter.setPen(QPen(_color("border_strong"), 2))
        painter.drawPath(outline)
        # The infrared window every remote has at its top.
        window = QRectF(0, 0, 44 * factor, 6 * factor)
        window.moveCenter(QPointF(area.center().x(), area.top() + 14 * factor))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_color("border"))
        painter.drawRoundedRect(window, 3 * factor, 3 * factor)
        painter.end()

