"""Two small buttons at the foot of the GPU screen: Modern | Classic.

The same choice as Settings › Appearance › Interface style, offered where
the screen is, so switching back does not mean finding the setting again.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QSizePolicy, QWidget

from ..i18n import tr

#: (value, label) in the order they are shown.
STYLES = (("modern", "Modern design"), ("original", "Classic design"))


class InterfaceStyleSwitch(QWidget):
    chosen = pyqtSignal(str)

    def __init__(self, current: str = "modern", parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addStretch(1)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for value, label in STYLES:
            button = QPushButton(tr(label))
            button.setCheckable(True)
            button.setProperty("layoutSwitch", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, item=value: self._pick(item))
            self._group.addButton(button)
            row.addWidget(button)
            self.buttons[value] = button
        self.set_current(current)

    def set_current(self, value: str) -> None:
        for key, button in self.buttons.items():
            button.setChecked(key == value)

    def current(self) -> str:
        return next((key for key, button in self.buttons.items() if button.isChecked()), "modern")

    def _pick(self, value: str) -> None:
        self.set_current(value)
        self.chosen.emit(value)

    def retranslate(self) -> None:
        for value, label in STYLES:
            self.buttons[value].setText(tr(label))
