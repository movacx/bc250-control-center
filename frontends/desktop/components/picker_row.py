"""The boxed ``caption ......... value`` selector shared by the module pages.

Drawn for the GPU governor's compatibility methods and reused wherever a
short list belongs in a card (the CPU core mask, for one), so every such
selector looks and behaves the same and is styled in one place
(``pickerRow`` / ``pickerCaption`` / ``pickerValue`` in the theme).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QSizePolicy, QWidget

from ..i18n import tr


class PickerRow(QFrame):
    """A boxed row that reads ``caption ... value`` and opens its options.

    The mockup draws these two selectors with the caption on the left and the
    current value on the right, without a drop-down arrow.  A ``QComboBox``
    cannot render two independently styled halves, so this reimplements just
    enough of its API (``addItem``/``findData``/``setCurrentIndex``/
    ``currentData``/``currentIndexChanged``) for the existing wiring to keep
    working unchanged.
    """

    currentIndexChanged = pyqtSignal(int)  # noqa: N815 (QComboBox-compatible)

    def __init__(self, caption: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._caption_source = caption
        self._items: list[tuple[str, object]] = []
        #: What the row shows for each item when it is shorter than the menu text.
        self._shown: list[str] = []
        self._index = -1
        self.setProperty("pickerRow", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(10)
        self._caption = QLabel(tr(caption))
        self._caption.setProperty("pickerCaption", True)
        self._caption.setMinimumWidth(0)
        # A narrow column wraps the caption instead of clipping it.
        self._caption.setWordWrap(True)
        row.addWidget(self._caption, 1)
        self._value = QLabel("")
        self._value.setProperty("pickerValue", True)
        self._value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self._value, 0)

    # -- QComboBox-compatible surface ---------------------------------------
    def addItem(self, text: str, data: object, shown: str = "") -> None:  # noqa: N802 (Qt naming)
        """``shown`` is the short value for the row; the menu lists ``text``."""
        self._items.append((text, data))
        self._shown.append(shown)
        if self._index < 0:
            self.setCurrentIndex(0)

    def findData(self, data: object) -> int:  # noqa: N802 (Qt naming)
        for index, (_text, value) in enumerate(self._items):
            if value == data:
                return index
        return -1

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802 (Qt naming)
        if not self._items:
            return
        index = max(0, min(len(self._items) - 1, int(index)))
        changed = index != self._index
        self._index = index
        self._value.setText(self._shown[index] or self._items[index][0])
        if changed and not self.signalsBlocked():
            self.currentIndexChanged.emit(index)

    def currentData(self) -> object:  # noqa: N802 (Qt naming)
        if 0 <= self._index < len(self._items):
            return self._items[self._index][1]
        return None

    def currentIndex(self) -> int:  # noqa: N802 (Qt naming)
        return self._index

    def count(self) -> int:
        return len(self._items)

    def itemData(self, index: int) -> object:  # noqa: N802 (Qt naming)
        return self._items[index][1] if 0 <= index < len(self._items) else None

    def itemText(self, index: int) -> str:  # noqa: N802 (Qt naming)
        return self._items[index][0] if 0 <= index < len(self._items) else ""

    def setItemText(self, index: int, text: str) -> None:  # noqa: N802 (Qt naming)
        """Retranslating keeps the choice; the shown value follows its text."""
        if 0 <= index < len(self._items):
            self._items[index] = (text, self._items[index][1])
            if index == self._index:
                self._value.setText(self._shown[index] or text)

    def retranslate(self) -> None:
        self._caption.setText(tr(self._caption_source))

    # -- interaction ---------------------------------------------------------
    def open_options(self) -> None:
        """Show the choices. Reached by a click, a controller, or Enter."""
        if not self._items or not self.isEnabled():
            return
        menu = QMenu(self)
        for index, (text, _data) in enumerate(self._items):
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(index == self._index)
            action.triggered.connect(
                lambda _checked=False, position=index: self.setCurrentIndex(position)
            )
        menu.setMinimumWidth(self.width())
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def gamepad_activate(self) -> None:
        """A controller press must reach the same list.

        Without this the row was a focus stop that answered nothing: it is not
        a QComboBox, so the navigation's fallback of opening a popup never
        applied to it. Written as a method rather than bound to
        ``open_options`` at class level, so that replacing one replaces both.
        """
        self.open_options()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.open_options()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.open_options()
            event.accept()
            return
        super().keyPressEvent(event)
