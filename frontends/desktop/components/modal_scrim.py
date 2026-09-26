"""The dimmed backdrop behind a modal dialog.

In light mode a white dialog opened over white cards had nothing to separate
it from the page behind it but a hairline border and a faint shadow, so it
read as one more card rather than as the thing waiting for an answer. Every
modal dialog of the window now sits over a translucent scrim instead, the way
desktop and web platforms present a blocking question.

The scrim follows the focused window rather than filtering every event of
the application: a modal dialog takes the focus when it opens and hands it
back when it closes, so ``focusWindowChanged`` is exactly the moment to look.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QGuiApplication, QPainter
from PyQt6.QtWidgets import QDialog, QWidget

#: How dark the backdrop gets. Dark mode needs more to register at all.
LIGHT_OPACITY = 0.30
DARK_OPACITY = 0.46
FADE_MS = 140


class ModalScrim(QWidget):
    """A translucent layer over the whole window while a modal dialog is up."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setObjectName("ModalScrim")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._strength = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(FADE_MS)
        self._animation.valueChanged.connect(self._set_strength)
        self._animation.finished.connect(self._fade_finished)
        self.hide()
        window.installEventFilter(self)
        application = QGuiApplication.instance()
        if application is not None:
            application.focusWindowChanged.connect(self._sync)

    # ----------------------------------------------------------------- state

    def modal_dialogs(self) -> list[QDialog]:
        owner = self.parentWidget()
        if owner is None:
            return []
        return [
            dialog
            for dialog in owner.findChildren(QDialog)
            if dialog.isVisible() and dialog.isModal()
        ]

    @property
    def active(self) -> bool:
        return self.isVisible() and self._animation.endValue() != 0.0

    def _sync(self, *_args) -> None:
        wanted = bool(self.modal_dialogs())
        if wanted == self.active:
            return
        if wanted:
            self._fade_in()
        else:
            self._fade_out()

    def _fade_in(self) -> None:
        owner = self.parentWidget()
        if owner is not None:
            self.setGeometry(owner.rect())
        self.show()
        self.raise_()
        self._animation.stop()
        self._animation.setStartValue(self._strength)
        self._animation.setEndValue(1.0)
        self._animation.start()

    def _fade_out(self) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._strength)
        self._animation.setEndValue(0.0)
        self._animation.start()

    def _fade_finished(self) -> None:
        if self._animation.endValue() == 0.0:
            self.hide()

    def _set_strength(self, value) -> None:
        self._strength = float(value)
        self.update()

    # ----------------------------------------------------------------- Qt

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API name
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.setGeometry(watched.rect())
        return False

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        from ..theme import ACTIVE_MODE, COLORS

        opacity = DARK_OPACITY if ACTIVE_MODE == "dark" else LIGHT_OPACITY
        color = QColor(COLORS.get("scrim", "#000000"))
        color.setAlphaF(max(0.0, min(1.0, opacity * self._strength)))
        painter = QPainter(self)
        painter.fillRect(self.rect(), color)
        painter.end()
