"""A floating way back to a console that is still running.

The console can be hidden mid-workflow, and until now that was a one-way
door: preparing dependencies, pressing Hide, and then having no way to watch
the rest of it. This is the way back — a small terminal glyph that floats
above every page while a workflow is running and the panel is closed, and
puts it back on screen when clicked.

It floats rather than docks on purpose: it is a child of the window, not of
any page layout, so no screen has to reserve room for it and none of them
change shape when it appears.
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QWidget

from ..components.widgets import ICON_DIR
from ..i18n import tr
from ..theme import COLORS

#: Diameter of the button itself. The widget is taller so the bounce has room
#: to travel without being clipped.
DIAMETER = 54
#: The terminal glyph inside the circle. Its corners have to clear the rim.
GLYPH = 28
BOUNCE_TRAVEL = 12
MARGIN = 22


class ConsoleCounter(QWidget):
    """Small numeric badge drawn over the beacon when work is queued."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(QSize(22, 22))
        self._count = 0
        self.hide()

    def set_count(self, count: int) -> None:
        count = max(0, int(count))
        if count == self._count:
            return
        self._count = count
        self.setVisible(count > 0)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS["orange"]))
        painter.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(COLORS["on_accent"]))
        painter.drawText(
            self.rect(), Qt.AlignmentFlag.AlignCenter, str(min(self._count, 9))
        )
        painter.end()


class ConsoleBeacon(QWidget):
    """A bouncing terminal button that only exists while there is work to see."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(QSize(DIAMETER + 8, DIAMETER + BOUNCE_TRAVEL + 8))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setToolTip(tr("Show the running workflow"))
        self._offset = 0.0
        self._glyph_cache: QPixmap | None = None
        self._glyph_key: tuple[str, float] | None = None
        self._hovered = False
        self._pressed = False
        self.hide()

        # How many workflows are behind the button. One needs no number; two
        # is the moment the user has to know there is more than one tab
        # waiting on the other side of it.
        self.counter = ConsoleCounter(self)
        self.counter.move(self.width() - self.counter.width(), BOUNCE_TRAVEL - 2)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 110))
        self.setGraphicsEffect(shadow)

        # One loop: a squashy hop. It carries the attention on its own, and a
        # second breathing ring on top of live readings was too much motion.
        self._bounce = QVariantAnimation(self)
        self._bounce.setStartValue(0.0)
        self._bounce.setEndValue(1.0)
        self._bounce.setDuration(1500)
        self._bounce.setLoopCount(-1)
        self._bounce.valueChanged.connect(self._on_bounce)

    # --------------------------------------------------------------- motion

    def _on_bounce(self, value: float) -> None:
        # Up on a bounce curve, down on a fall: a ball, not a sine wave.
        phase = float(value)
        if phase < 0.45:
            eased = QEasingCurve(QEasingCurve.Type.OutQuad).valueForProgress(
                phase / 0.45
            )
            self._offset = -BOUNCE_TRAVEL * eased
        elif phase < 0.75:
            eased = QEasingCurve(QEasingCurve.Type.OutBounce).valueForProgress(
                (phase - 0.45) / 0.30
            )
            self._offset = -BOUNCE_TRAVEL * (1.0 - eased)
        else:
            self._offset = 0.0
        self.counter.move(
            self.width() - self.counter.width(),
            max(0, int(BOUNCE_TRAVEL - 2 + self._offset)),
        )
        self.update()

    def set_count(self, count: int) -> None:
        """Carry the number of running workflows, once there is more than one."""
        self.counter.set_count(count if count > 1 else 0)

    def set_active(self, active: bool) -> None:
        """Show and animate, or stop and disappear."""
        if bool(active) == self.isVisible():
            if not active:
                self._bounce.stop()
            return
        if active:
            self.reposition()
            self.show()
            self.raise_()
            self._bounce.start()
            return
        self._bounce.stop()
        self.hide()

    # ------------------------------------------------------------ placement

    def reposition(self) -> None:
        """Sit against the right edge, vertically centred.

        Not the bottom corner: the console itself slides up from there, and a
        button that is covered by the thing it opens is no way back at all.
        """
        parent = self.parentWidget()
        if parent is None:
            return
        x = parent.width() - self.width() - MARGIN
        y = (parent.height() - self.height()) // 2
        self.move(max(0, x), max(0, y))

    # -------------------------------------------------------------- drawing

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        grow = 3.0 if self._hovered else 0.0
        if self._pressed:
            grow = -1.5
        size = DIAMETER + grow
        left = (self.width() - size) / 2
        top = BOUNCE_TRAVEL + (DIAMETER - size) / 2 + self._offset
        body = QRectF(left, top, size, size)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS["blue"]))
        painter.drawEllipse(body)

        # The glyph is a solid terminal window with the prompt knocked out of
        # it, so tinting it to the accent foreground leaves the caret and the
        # command line showing the blue of the circle underneath.
        glyph = self._glyph(COLORS["on_accent"])
        side = glyph.width() / glyph.devicePixelRatio()
        centre = body.center()
        painter.drawPixmap(
            QPointF(centre.x() - side / 2, centre.y() - side / 2), glyph
        )
        painter.end()

    def _glyph(self, ink: str) -> QPixmap:
        """The terminal icon, tinted, at this screen's pixel density."""
        ratio = self.devicePixelRatioF()
        if self._glyph_cache is None or self._glyph_key != (ink, ratio):
            source = QPixmap(str(ICON_DIR / "console_beacon.png")).scaled(
                round(GLYPH * ratio),
                round(GLYPH * ratio),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            tinted = QPixmap(source.size())
            tinted.fill(Qt.GlobalColor.transparent)
            brush = QPainter(tinted)
            brush.drawPixmap(0, 0, source)
            brush.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceIn
            )
            brush.fillRect(tinted.rect(), QColor(ink))
            brush.end()
            tinted.setDevicePixelRatio(ratio)
            self._glyph_cache, self._glyph_key = tinted, (ink, ratio)
        return self._glyph_cache

    # ---------------------------------------------------------- interaction

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._hovered = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._pressed = True
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        was_pressed = self._pressed
        self._pressed = False
        self.update()
        if was_pressed and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()

    def retranslate(self) -> None:
        self.setToolTip(tr("Show the running workflow"))
