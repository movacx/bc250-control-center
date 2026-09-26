"""A small progress ring for work that is still running.

Only ever on screen while something is actually pending: a spinner that is
always there stops meaning anything. It is drawn rather than an animated
image, so it follows the theme's colours and stays crisp at any scale, and
its timer only runs while it is both started and visible.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget

from ..i18n import tr
from ..theme import COLORS

#: One turn a second at roughly 30 frames: smooth enough to read as motion,
#: cheap enough to leave running during a long hardware operation.
_FRAME_MS = 33
_STEP_DEGREES = 12


class BusySpinner(QWidget):
    """An indeterminate ring; hidden unless :meth:`start` was called."""

    def __init__(self, diameter: int = 16, tone: str = "cyan", parent: QWidget | None = None):
        super().__init__(parent)
        self._diameter = max(8, int(diameter))
        self._tone = tone
        self._angle = 0
        self._running = False
        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._advance)
        self.setFixedSize(self._diameter, self._diameter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return QSize(self._diameter, self._diameter)

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        self._running = True
        self.show()
        self._timer.start()

    def stop(self) -> None:
        self._running = False
        self._timer.stop()
        self.hide()

    def set_running(self, running: bool) -> None:
        self.start() if running else self.stop()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        if self._running and not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API name
        # A page switched away from must not keep a timer ticking for it.
        self._timer.stop()
        super().hideEvent(event)

    def _advance(self) -> None:
        self._angle = (self._angle + _STEP_DEGREES) % 360
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width = max(1.5, self._diameter / 8)
        inset = width / 2 + 0.5
        bounds = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        color = QColor(COLORS.get(self._tone, COLORS["blue"]))
        track = QColor(color)
        track.setAlpha(55)
        pen = QPen(track, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(bounds)
        pen.setColor(color)
        painter.setPen(pen)
        # Qt measures arcs in sixteenths of a degree, counter-clockwise from
        # three o'clock; a negative start turns the arc clockwise.
        painter.drawArc(bounds, -self._angle * 16, 100 * 16)
        painter.end()


class BusyBadge(QFrame):
    """A status pill with a spinner: "this is still being worked on"."""

    def __init__(self, text: str = "", tone: str = "cyan", parent: QWidget | None = None):
        super().__init__(parent)
        self._source_text = ""
        self.setProperty("busyBadge", True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 3, 9, 3)
        row.setSpacing(6)
        self.spinner = BusySpinner(12, tone, self)
        row.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignVCenter)
        self.label = QLabel()
        self.label.setProperty("busyBadgeText", True)
        row.addWidget(self.label, 0, Qt.AlignmentFlag.AlignVCenter)
        foreground = COLORS.get(tone, COLORS["blue"])
        background = COLORS.get(f"{tone}_soft", COLORS["blue_soft"])
        border = COLORS.get(f"{tone}_border", COLORS["border"])
        # Selector-scoped, like PillLabel: a bare declaration list would also
        # reach the tooltip window.
        self.setStyleSheet(
            f"QFrame[busyBadge='true'] {{ background:{background}; border:1px solid {border};"
            " border-radius:8px; }"
            f" QLabel[busyBadgeText='true'] {{ color:{foreground}; background:transparent;"
            " border:none; font-size:10px; font-weight:780; }"
        )
        self.set_text(text)
        self.hide()

    def set_text(self, text: str) -> None:
        self._source_text = str(text)
        self.label.setText(tr(self._source_text))

    def retranslate(self) -> None:
        self.label.setText(tr(self._source_text))

    def set_running(self, running: bool) -> None:
        self.spinner.set_running(running)
        self.setVisible(bool(running))
