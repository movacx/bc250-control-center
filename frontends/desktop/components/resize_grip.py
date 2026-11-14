"""The "• • •" bar under a text box or table: drag to resize, double-click to fit.

First drawn under each section of the full diagnosis (Black Box); the CPU
session console and the remote-access device table use the same bar.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QFrame, QWidget

from ..i18n import tr
from ..theme import COLORS


class ResizeGrip(QFrame):
    """A bar under a text box: drag it down to make the box taller, up to shorten it.

    Double-click fits the box to its text (and back). It reports where the
    mouse is relative to where it was pressed; the section decides the height.
    """

    pressed = pyqtSignal()
    dragged = pyqtSignal(int)
    double_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("diagGrip", True)
        self.setFixedHeight(14)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip(tr("Drag to resize. Double-click to fit the text."))
        self._press_y = 0

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_y = round(event.globalPosition().y())
            self.pressed.emit()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.dragged.emit(round(event.globalPosition().y()) - self._press_y)
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS["muted"]))
        centre_x, centre_y = self.width() // 2, self.height() // 2
        for offset in (-10, 0, 10):
            painter.drawEllipse(centre_x + offset - 2, centre_y - 1, 4, 4)
