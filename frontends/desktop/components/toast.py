"""A quiet, non-modal notice for the outcome of an action the user just took.

After a click the change itself is usually the confirmation: the fans are
audible, the chip turns green, the number moves. A modal "Success" window on
top of that is one more thing to dismiss, and after a password prompt it made
one click cost three windows. A toast says the same thing from the corner of
the window and goes away on its own; errors and anything the user must read
before carrying on still use a dialog.

``show_toast`` finds the window of the widget it is given and stacks the
notice in its bottom-right corner. It never takes focus, so it does not steal
the keyboard or the controller from the page.
"""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from ..theme import COLORS
from .buttons import WrappingButton as QPushButton

#: Toasts shown at once; the oldest goes when a fourth arrives.
MAX_TOASTS = 3
#: Distance from the window's bottom-right corner.
MARGIN = 20
TOAST_WIDTH = 360
MIN_DURATION_MS = 3200
MAX_DURATION_MS = 9000

_TONES = {
    "blue": "blue",
    "green": "green",
    "orange": "orange",
    "red": "red",
    "purple": "purple",
    "gray": "subtle",
}


def toast_duration(title: str, message: str) -> int:
    """Long enough to read at a relaxed pace, never a minute on screen."""
    reading = 2600 + 45 * (len(title) + len(message))
    return max(MIN_DURATION_MS, min(MAX_DURATION_MS, reading))


class Toast(QFrame):
    """One notice: a tone stripe, a title, an optional line, a close cross."""

    def __init__(
        self,
        title: str,
        message: str = "",
        *,
        tone: str = "blue",
        duration_ms: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AppToast")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedWidth(TOAST_WIDTH)
        self.key = (title, message)
        self.tone = tone if tone in _TONES else "blue"
        self._duration = duration_ms or toast_duration(title, message)
        self._closing = False

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 8, 0)
        row.setSpacing(12)
        stripe = QFrame()
        stripe.setObjectName("AppToastStripe")
        stripe.setFixedWidth(4)
        stripe.setStyleSheet(
            f"background: {COLORS[_TONES[self.tone]]}; border: none;"
            " border-top-left-radius: 10px; border-bottom-left-radius: 10px;"
        )
        row.addWidget(stripe)

        text = QVBoxLayout()
        text.setContentsMargins(0, 11, 0, 11)
        text.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("AppToastTitle")
        self.title.setWordWrap(True)
        text.addWidget(self.title)
        self.message = QLabel(message)
        self.message.setObjectName("AppToastMessage")
        self.message.setWordWrap(True)
        self.message.setVisible(bool(message))
        text.addWidget(self.message)
        row.addLayout(text, 1)

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("AppToastClose")
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setToolTip(tr("Close"))
        self.close_button.setFixedSize(24, 24)
        self.close_button.clicked.connect(self.dismiss)
        row.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        row.setAlignment(self.close_button, Qt.AlignmentFlag.AlignTop)

        self.setAccessibleName(title)
        self.setAccessibleDescription(message)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)

    def present(self) -> None:
        self._fade.stop()
        self._fade.setDuration(160)
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(1.0)
        self._fade.start()
        self.restart()

    def restart(self) -> None:
        """Show the notice for its whole reading time again."""
        if self._closing:
            return
        self._timer.start(self._duration)

    def dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._timer.stop()
        self._fade.stop()
        self._fade.setDuration(200)
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._remove)
        self._fade.start()

    def _remove(self) -> None:
        host = self.parentWidget()
        self.hide()
        self.deleteLater()
        if isinstance(host, ToastHost):
            host.forget(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        # Anywhere on the notice puts it away; the cross is only the obvious spot.
        self.dismiss()
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        # Reading it keeps it: the timer waits while the pointer is on it.
        self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if not self._closing:
            self._timer.start(max(1500, self._duration // 2))
        super().leaveEvent(event)


class ToastHost(QWidget):
    """The stack in a window's bottom-right corner, sized to its toasts."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setObjectName("AppToastHost")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._toasts: list[Toast] = []
        self._watcher = _WindowWatcher(self)
        window.installEventFilter(self._watcher)
        self.hide()

    def toasts(self) -> list[Toast]:
        return list(self._toasts)

    def add(self, toast: Toast) -> Toast:
        for existing in self._toasts:
            if existing.key == toast.key and existing.tone == toast.tone:
                # The same outcome twice: keep one notice and give it back
                # its full time, instead of stacking copies.
                toast.deleteLater()
                existing.restart()
                return existing
        while len(self._toasts) >= MAX_TOASTS:
            oldest = self._toasts.pop(0)
            oldest.hide()
            oldest.deleteLater()
        toast.setParent(self)
        self._layout.addWidget(toast)
        self._toasts.append(toast)
        toast.show()
        self.show()
        self.reposition()
        self.raise_()
        toast.present()
        return toast

    def forget(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        if not self._toasts:
            self.hide()
        else:
            self.reposition()

    def reposition(self) -> None:
        window = self.parentWidget()
        if window is None:
            return
        self._layout.activate()
        size = self._layout.sizeHint()
        width = min(size.width(), max(0, window.width() - 2 * MARGIN))
        height = size.height()
        self.setGeometry(
            max(MARGIN, window.width() - width - MARGIN),
            max(MARGIN, window.height() - height - MARGIN),
            width,
            height,
        )
        self.raise_()


class _WindowWatcher(QObject):
    """Keeps the stack in the corner as the window is resized."""

    def __init__(self, host: ToastHost) -> None:
        super().__init__(host)
        self._host = host

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API name
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show) and self._host.isVisible():
            self._host.reposition()
        return False


def toast_host(window: QWidget) -> ToastHost:
    """The window's toast stack, created the first time it is needed."""
    host = window.findChild(ToastHost, "AppToastHost", Qt.FindChildOption.FindDirectChildrenOnly)
    return host if host is not None else ToastHost(window)


def show_toast(
    anchor: QWidget | None,
    title: str,
    message: str = "",
    *,
    tone: str = "blue",
    duration_ms: int | None = None,
) -> Toast | None:
    """Show a short, self-dismissing notice in ``anchor``'s window.

    ``title`` and ``message`` are catalogue keys or already translated text,
    the same contract as :class:`InfoDialog`.
    """
    window = anchor.window() if anchor is not None else QApplication.activeWindow()
    if window is None:
        return None
    toast = Toast(tr(title), tr(message) if message else "", tone=tone, duration_ms=duration_ms)
    return toast_host(window).add(toast)
