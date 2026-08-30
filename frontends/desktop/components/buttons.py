"""Readable action buttons on narrow layouts and with long translations."""

from PyQt6.QtCore import QEvent, QRect, QSize, Qt
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWidgets import QPushButton, QStyle, QStyleOptionButton, QStylePainter


class WrappingButton(QPushButton):
    """Keep native button behavior; wrap copy only when it cannot fit.

    The real text is never shortened or replaced, preserving translations,
    keyboard mnemonics, accessibility and callers that inspect button labels.
    """

    def _text_geometry(self, width):
        native = super().sizeHint()
        metrics = self.fontMetrics()
        text_width = max((metrics.horizontalAdvance(line) for line in self.text().splitlines()), default=0)
        chrome = max(20, native.width() - text_width)
        available = max(1, width - chrome)
        flags = Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextShowMnemonic
        bounds = metrics.boundingRect(QRect(0, 0, available, 10000), flags, self.text())
        unwrapped_height = metrics.boundingRect(self.text()).height()
        height = max(native.height(), bounds.height() + max(12, native.height() - unwrapped_height))
        return native, height, chrome

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._text_geometry(width)[1]

    def sizeHint(self):
        native = super().sizeHint()
        if self.isVisible() and 0 < self.width() < native.width():
            return QSize(self.width(), self.heightForWidth(self.width()))
        return native

    def minimumSizeHint(self):
        native = super().minimumSizeHint()
        return QSize(min(native.width(), 100), native.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_height()

    def setText(self, text):
        super().setText(text)
        if self.isVisible():
            self._sync_height()

    def changeEvent(self, event):
        super().changeEvent(event)
        if self.isVisible() and event.type() in {QEvent.Type.FontChange, QEvent.Type.StyleChange}:
            self._sync_height()

    def _sync_height(self):
        if self.text() and self.minimumHeight() != self.heightForWidth(self.width()):
            self.setMinimumHeight(self.heightForWidth(self.width()))

    def paintEvent(self, event):
        native, _height, chrome = self._text_geometry(self.width())
        if not self.text() or self.width() >= native.width():
            super().paintEvent(event)
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        button_icon = option.icon
        option.text = ""
        option.icon = QIcon()
        painter = QStylePainter(self)
        painter.drawControl(QStyle.ControlElement.CE_PushButton, option)
        content = self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, self)
        icon_width = self.iconSize().width() + 6 if not button_icon.isNull() else 0
        side = max(6, (chrome - icon_width) // 2)
        content = content.adjusted(side, 4, -side, -4)
        if not button_icon.isNull():
            icon_rect = QRect(content.left(), content.center().y() - self.iconSize().height() // 2, self.iconSize().width(), self.iconSize().height())
            button_icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter, QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled)
            content.adjust(icon_width, 0, 0, 0)
        flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextShowMnemonic
        self.style().drawItemText(painter, content, flags, option.palette, self.isEnabled(), self.text(), QPalette.ColorRole.ButtonText)
