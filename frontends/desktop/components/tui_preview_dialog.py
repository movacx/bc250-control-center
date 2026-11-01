"""Screenshots of the terminal interface, one at a time, with previous / next."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..i18n import tr
from .buttons import WrappingButton as QPushButton

SCREENSHOTS = Path(__file__).resolve().parents[3] / "assets" / "screenshots"
#: (file, caption): the captions are the names of the sidebar's own pages.
SHOTS = (
    ("tui-dashboard.png", "Dashboard"),
    ("tui-cpu.png", "CPU / SMU"),
    ("tui-compute-units.png", "Compute Units"),
    ("tui-gpu.png", "GPU Governor"),
    ("tui-performance.png", "Performance"),
)


class TuiPreviewDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Terminal interface preview"))
        self.resize(1100, 760)
        self._index = 0
        layout = QVBoxLayout(self)
        self.caption = QLabel()
        self.caption.setProperty("cardTitle", True)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(1, 1)
        row = QHBoxLayout()
        self.previous = QPushButton(tr("Previous"))
        self.next = QPushButton(tr("Next"))
        self.previous.clicked.connect(lambda _checked=False: self._go(-1))
        self.next.clicked.connect(lambda _checked=False: self._go(1))
        row.addWidget(self.previous)
        row.addStretch(1)
        row.addWidget(self.next)
        layout.addWidget(self.caption)
        layout.addWidget(self.image, 1)
        layout.addLayout(row)
        self._show()

    def _go(self, step: int) -> None:
        self._index = (self._index + step) % len(SHOTS)
        self._show()

    def _show(self) -> None:
        name, caption = SHOTS[self._index]
        self.caption.setText(f"{tr(caption)}  ·  {self._index + 1}/{len(SHOTS)}")
        self._pixmap = QPixmap(str(SCREENSHOTS / name))
        if self._pixmap.isNull():
            self.image.setText(tr("Preview image is unavailable."))
        self._fit()

    def _fit(self) -> None:
        if not self._pixmap.isNull():
            self.image.setPixmap(self._pixmap.scaled(
                self.image.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._fit()
