"""The dashboard footer: Report, Update and the buttons around them.

Split out of ``dashboard_widgets``, which still re-exports every name here."""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSequentialAnimationGroup,
    QSize,
    Qt,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWidgets import QPushButton as IconButton

from .. import theme
from ..i18n import tr, tr_format
from .buttons import WrappingButton as QPushButton
from .widgets import ICON_DIR, apply_shadow, icon


class _FooterActionButton(IconButton):
    """Icon-only action with translated discovery and keyboard accessibility."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.setAccessibleName(tr(text))
        self.setToolTip(tr(text))
        self.setProperty("i18nSourceAccessibleName", text)
        self.setProperty("i18nSourceToolTip", text)
        self.setProperty("dashboardFooterAction", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._refresh_palette()
        apply_shadow(self, blur=4, y=1, alpha=10)
        self._lift = QPropertyAnimation(self.graphicsEffect(), b"blurRadius", self)
        self._lift.setDuration(160)
        self._lift.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _refresh_palette(self) -> None:
        edge = round(22 * theme.ACTIVE_SCALE / 100)
        self.setIconSize(QSize(edge, edge))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self._refresh_palette()

    def _animate_lift(self, active: bool) -> None:
        self._lift.stop()
        self._lift.setStartValue(self.graphicsEffect().blurRadius())
        self._lift.setEndValue(16.0 if active else 4.0)
        self._lift.start()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._animate_lift(True)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._animate_lift(self.hasFocus())

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._animate_lift(True)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._animate_lift(self.underMouse())

    def hideEvent(self, event) -> None:
        self._lift.stop()
        self.graphicsEffect().setBlurRadius(4.0)
        super().hideEvent(event)


class _GlowingFooterButton(_FooterActionButton):
    """A footer button whose outline lights up softly every two seconds.

    The edge and a faint tint fade in and out inside the button's own
    outline: nothing moves, blinks or grows, nothing is drawn outside the
    row (a drop-shadow halo was cut off by the header), and it rests while
    the button is hidden or under the pointer.
    """

    EDGE_ALPHA = 210
    TINT_ALPHA = 34
    #: One glow every two seconds: in, out, and a short rest.
    FADE_MS = 700
    PAUSE_MS = 600

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self._glowing = False
        self._level = 0.0
        self._glow = QSequentialAnimationGroup(self)
        for start, end in ((0.0, 1.0), (1.0, 0.0)):
            fade = QVariantAnimation(self)
            fade.setDuration(self.FADE_MS)
            fade.setStartValue(start)
            fade.setEndValue(end)
            fade.setEasingCurve(QEasingCurve.Type.InOutSine)
            fade.valueChanged.connect(self._set_level)
            self._glow.addAnimation(fade)
        self._glow.addPause(self.PAUSE_MS)
        self._glow.setLoopCount(-1)

    def glow_color(self) -> QColor:
        raise NotImplementedError

    def _set_level(self, value) -> None:
        self._level = float(value)
        self.update()

    def set_glow(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._glowing:
            return
        self._glowing = enabled
        if enabled and self.isVisible():
            self._glow.start()
        elif not enabled:
            self._glow.stop()
            self._set_level(0.0)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        if self._glowing and self._glow.state() != QSequentialAnimationGroup.State.Running:
            self._glow.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().hideEvent(event)
        self._glow.stop()
        self._level = 0.0

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().paintEvent(event)
        if self._level <= 0.0 or self.underMouse() or self.hasFocus():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # The button's own corner (17 px in the stylesheet, halved by formal).
        radius = 17.0 * (theme.FORMAL_RADIUS_FACTOR if theme.ACTIVE_STYLE == "formal" else 1.0)
        radius = min(radius * theme.ACTIVE_SCALE / 100, self.height() / 2)
        rect = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        color = self.glow_color()
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), round(self.TINT_ALPHA * self._level)))
        painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), round(self.EDGE_ALPHA * self._level)), 1.5))
        painter.drawRoundedRect(rect, radius, radius)
        painter.end()

    def glowing(self) -> bool:
        return self._glowing


class _UpdateBadgeButton(_GlowingFooterButton):
    """Appears only when a newer release exists, and glows so it is noticed.

    The other footer buttons are always there, so one appearing in the same
    row is easy to miss on a glance. It lights up like the report button, in
    the active accent, every two seconds while it is shown; hidden, it costs
    nothing because the animation stops with the widget.
    """

    def __init__(self) -> None:
        super().__init__("A newer version is available")
        self.setProperty("updateAvailable", True)
        self.setIcon(QIcon(str(ICON_DIR / "update_badge.png")))
        self._published = ""
        self.hide()
        self.set_glow(True)

    def glow_color(self) -> QColor:
        return QColor(theme.COLORS["blue"])

    def announce(self, published: str) -> None:
        """Show the badge for a specific version, or hide it for none."""
        published = str(published or "")
        self._published = published
        if not published:
            self.setVisible(False)
            return
        detail = tr_format("Version {version} is available", version=published)
        self.setToolTip(detail)
        self.setAccessibleName(detail)
        # The translated text is built here, so the generic retranslation pass
        # must not overwrite it with the untranslated source string.
        self.setProperty("i18nSourceToolTip", None)
        self.setProperty("i18nSourceAccessibleName", None)
        self.setVisible(True)

    @property
    def published_version(self) -> str:
        return self._published

class UpdateCallout(QFrame):
    """A speech bubble that points at the update badge and says what to do.

    A pulsing icon says "look here" and nothing else. This says the rest: that
    a newer version exists, which one, and — the part that actually matters —
    the right way to get it for *this* install. Telling someone who installed
    from the AUR to download a tarball would walk around their package manager.

    It floats as a child of the window rather than sitting in a layout, so it
    can overlap the content beneath it without reserving space or shifting
    anything, and it is drawn rather than styled because a tail pointing at a
    specific widget is not something a stylesheet can express.

    Shown once per session, and again whenever the badge is clicked. The badge
    keeps pulsing either way, so dismissing this is not the same as forgetting.
    """

    #: Height of the triangular tail, in logical pixels.
    TAIL = 8
    #: Half-width of its base.
    TAIL_HALF_WIDTH = 9
    RADIUS = 10

    action_clicked = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("updateCallout")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._tail_x = 0

        self._tail_below = False
        self._root = QVBoxLayout(self)
        # Room for the tail on whichever edge it will be drawn on.
        self._root.setContentsMargins(13, 11 + self.TAIL, 11, 11)
        self._root.setSpacing(3)
        root = self._root

        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel(tr("New update available"))
        self.title.setProperty("updateCalloutTitle", True)
        head.addWidget(self.title, 1)
        self.close_button = QPushButton("")
        self.close_button.setObjectName("updateCalloutClose")
        self.close_button.setIcon(icon("close_gray"))
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setFixedSize(18, 18)
        self.close_button.setToolTip(tr("Close"))
        self.close_button.setProperty("i18nSourceToolTip", "Close")
        self.close_button.clicked.connect(self._dismiss)
        head.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)

        self.detail = QLabel("")
        self.detail.setProperty("updateCalloutDetail", True)
        self.detail.setWordWrap(True)
        root.addWidget(self.detail)

        self.action_button = QPushButton("")
        self.action_button.setObjectName("updateCalloutAction")
        self.action_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_button.clicked.connect(self.action_clicked)
        root.addWidget(self.action_button)
        self.hide()

    # ------------------------------------------------------------- contents

    def set_message(self, *, version: str, detail: str, action: str) -> None:
        self.detail.setText(detail)
        self.action_button.setText(action)
        # Built from a version number, so the generic retranslation pass must
        # not overwrite either with an untranslated source string.
        self.setProperty("updateVersion", version)
        self.detail.setProperty("i18nSourceText", None)
        self.action_button.setProperty("i18nSourceText", None)
        self.adjustSize()

    def retranslate(self) -> None:
        self.title.setText(tr("New update available"))
        self.close_button.setToolTip(tr("Close"))

    # ------------------------------------------------------------ placement

    def _set_tail_side(self, *, below: bool) -> None:
        """Reserve the tail's room on the edge it will be drawn on.

        Margins change the size hint, so this has to settle before the bubble
        is measured and placed.
        """
        if below == self._tail_below and self._root.contentsMargins().top() > 0:
            return
        self._tail_below = below
        top = 11 if below else 11 + self.TAIL
        bottom = 11 + self.TAIL if below else 11
        self._root.setContentsMargins(13, top, 11, bottom)

    def point_at(self, anchor: QWidget) -> bool:
        """Hang off ``anchor`` with the tail pointing at it.

        Below it when there is room, above it when there is not — a bubble that
        clamps itself to the bottom of the window ends up covering the very
        thing its tail is pointing at.

        Returns False when there is no window to float in yet, which happens
        while the dashboard is still being built.
        """
        window = anchor.window()
        if window is None or window is anchor:
            return False
        if self.parentWidget() is not window:
            self.setParent(window)

        top_left = anchor.mapTo(window, QPoint(0, 0))
        centre_x = top_left.x() + anchor.width() // 2
        below_y = top_left.y() + anchor.height() + 4

        # Below if it fits, above if that fits instead, and otherwise not at
        # all. The old rule flipped above whenever below was short and then
        # clamped the result back on screen, which for a badge near the top of
        # the viewport landed the bubble squarely on top of the badge — a
        # label covering the very thing its tail points at.
        self._set_tail_side(below=False)
        self.adjustSize()
        fits_below = below_y + self.height() <= window.height() - 8
        if fits_below:
            y = below_y
        else:
            self._set_tail_side(below=True)
            self.adjustSize()
            above_y = top_left.y() - self.height() - 4
            if above_y < 8:
                # Neither side has room. The badge keeps pulsing on its own,
                # and clicking it asks for the bubble again once there is
                # somewhere to put it.
                self.hide()
                return False
            y = above_y

        # Keep the whole bubble on screen horizontally; the tail then slides
        # within it rather than the bubble hanging off the edge.
        x = max(8, min(centre_x - self.width() // 2, window.width() - self.width() - 8))
        self.move(x, y)
        self._tail_x = max(
            self.RADIUS + self.TAIL_HALF_WIDTH,
            min(centre_x - x, self.width() - self.RADIUS - self.TAIL_HALF_WIDTH),
        )
        self.show()
        self.raise_()
        return True

    # --------------------------------------------------------------- drawing

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._tail_below:
            body = self.rect().adjusted(0, 0, -1, -self.TAIL - 1)
            edge, tip = float(body.bottom()), float(self.rect().bottom())
        else:
            body = self.rect().adjusted(0, self.TAIL, -1, -1)
            edge, tip = float(body.top()), 0.0
        shape = QPainterPath()
        shape.addRoundedRect(float(body.x()), float(body.y()), float(body.width()),
                             float(body.height()), self.RADIUS, self.RADIUS)
        # QPointF, not QPoint: QPolygonF refuses the integer type, and the
        # refusal happens inside paintEvent — a reimplemented C++ virtual,
        # where PyQt6 turns an unhandled exception into qFatal and aborts the
        # whole process rather than logging it.
        tail = QPolygonF([
            QPointF(float(self._tail_x - self.TAIL_HALF_WIDTH), edge),
            QPointF(float(self._tail_x), tip),
            QPointF(float(self._tail_x + self.TAIL_HALF_WIDTH), edge),
        ])
        shape.addPolygon(tail)
        shape = shape.simplified()

        painter.setBrush(QColor(theme.COLORS["panel_raised"]))
        border = QColor(theme.COLORS["blue"])
        painter.setPen(border)
        painter.drawPath(shape)

    # --------------------------------------------------------------- closing

    def _dismiss(self) -> None:
        self.hide()
        self.dismissed.emit()


class _ReportButton(_GlowingFooterButton):
    """The report button, in the amber of its icon, so it is found.

    Settings > General switches the glow off (``settings/report_glow``).
    """

    def glow_color(self) -> QColor:
        return QColor(245, 166, 35)


class DashboardFooter(QWidget):
    """Compact external links embedded in the preparation header."""

    contact_clicked = pyqtSignal()
    telegram_clicked = pyqtSignal()
    report_clicked = pyqtSignal()
    support_clicked = pyqtSignal()
    repositories_clicked = pyqtSignal()
    update_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("dashboardHeaderActions", True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)
        # First in the row, ahead of the always-present links: it only exists
        # at all when there is something to act on, so it earns the lead spot.
        self.update_button = _UpdateBadgeButton()
        self.update_button.clicked.connect(self.update_clicked)
        self.layout.addWidget(self.update_button)
        self.repositories_button = _FooterActionButton("Official repositories")
        self.repositories_button.setIcon(icon("github"))
        self.repositories_button.clicked.connect(self.repositories_clicked)
        self.layout.addWidget(self.repositories_button)
        self.contact_button = _FooterActionButton("BC250 community on Discord")
        self.contact_button.setIcon(icon("discord"))
        self.contact_button.clicked.connect(self.contact_clicked)
        self.layout.addWidget(self.contact_button)
        # The community's Telegram group, beside its Discord.
        self.telegram_button = _FooterActionButton("BC250 community on Telegram")
        self.telegram_button.setIcon(icon("telegram"))
        self.telegram_button.clicked.connect(self.telegram_clicked)
        self.layout.addWidget(self.telegram_button)
        self.report_button = _ReportButton("Report a problem or suggest an idea")
        self.report_button.setIcon(icon("report_amber"))
        self.report_button.clicked.connect(self.report_clicked)
        self.layout.addWidget(self.report_button)
        self.support_button = _FooterActionButton("Buy me a coffee")
        self.support_button.setProperty("donation", True)
        # Official, bundled Ko-fi artwork: no network access needed by the UI.
        self.support_button.setIcon(QIcon(str(ICON_DIR / "kofi_cup.png")))
        self.support_button.clicked.connect(self.support_clicked)
        self.layout.addWidget(self.support_button)

    def set_report_glow(self, enabled: bool) -> None:
        self.report_button.set_glow(enabled)

    def announce_update(self, published: str) -> None:
        """Show or hide the update badge. Empty string means nothing to show."""
        self.update_button.announce(published)
