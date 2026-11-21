"""The dashboard footer: Report, Update and the buttons around them.

Split out of ``dashboard_widgets``, which still re-exports every name here."""

from __future__ import annotations

import math
import random

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSequentialAnimationGroup,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWidgets import QPushButton as IconButton

from .. import theme
from ..i18n import tr, tr_format
from .buttons import WrappingButton as QPushButton
from .outline_glow import OutlineGlow
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

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self._outline = OutlineGlow(self)
        self._glow = self._outline.cycle

    @property
    def _level(self) -> float:
        return self._outline.level

    def glow_color(self) -> QColor:
        raise NotImplementedError

    def set_glow(self, enabled: bool) -> None:
        self._outline.set_enabled(enabled)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        self._outline.shown()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().hideEvent(event)
        self._outline.hidden()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().paintEvent(event)
        # The button's own corner (17 px in the stylesheet, halved by formal).
        radius = 17.0 * (theme.FORMAL_RADIUS_FACTOR if theme.ACTIVE_STYLE == "formal" else 1.0)
        self._outline.paint(self.glow_color(), radius * theme.ACTIVE_SCALE / 100)

    def glowing(self) -> bool:
        return self._outline.glowing()


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


class _PaintedMotionButton(_FooterActionButton):
    """A footer button whose icon is painted, so it can move without resizing.

    Subclasses give the moves; the icon's scale, tilt, position and stretch,
    a wash of colour inside the outline and how bright its edge is follow
    them. The button keeps its size, the motion rests while it is hidden or
    under the pointer, and Settings > General (Alert animations) turns it off.

    The animated buttons take turns, one at a time, in random order: the
    footer picks the next one (never the same twice in a row) once the last
    has finished, and each plays its moves once per turn.
    """

    COLOR = QColor(240, 106, 106)
    WASH_ALPHA = 60
    #: Whether the footer gives it turns; the update badge keeps its own loop.
    TURNS = True

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self._scale = 1.0
        self._angle = 0.0
        self._wash = 0.0
        self._edge = 0.0
        self._ping = 0.0
        #: Where the icon sits (offsets in icon units: 1.0 is a whole icon)
        #: and how it is stretched, for hops, squishes and flights.
        self._dx = self._dy = 0.0
        self._sx = self._sy = 1.0
        self._moving = False
        self.motion = QSequentialAnimationGroup(self)
        self._build_motion()
        self.motion.setLoopCount(1 if self.TURNS else -1)
        if self.TURNS:
            self.motion.finished.connect(self._rest)

    def _build_motion(self) -> None:
        for move in self._moves():
            self.motion.addAnimation(move)

    def _moves(self) -> list:
        raise NotImplementedError

    def _together(self, *steps) -> QParallelAnimationGroup:
        group = QParallelAnimationGroup(self)
        for step in steps:
            group.addAnimation(step)
        return group

    def _start(self) -> None:
        self.motion.start()

    def playing(self) -> bool:
        return self.motion.state() == QSequentialAnimationGroup.State.Running

    def can_play(self) -> bool:
        """Free for a turn: switched on, on screen, not under the pointer, idle."""
        return (self.TURNS and self._moving and self.isVisible()
                and not self.underMouse() and not self.playing())

    def play(self) -> bool:
        """Play the moves once (the footer's turn); False when it cannot now."""
        if not self.can_play():
            return False
        self._start()
        return True

    def _step(self, attribute: str, start: float, end: float, duration: int,
              curve: QEasingCurve.Type = QEasingCurve.Type.InOutSine) -> QVariantAnimation:
        step = QVariantAnimation(self)
        step.setDuration(duration)
        step.setStartValue(float(start))
        step.setEndValue(float(end))
        step.setEasingCurve(curve)
        step.valueChanged.connect(lambda value, name=attribute: self._set(name, value))
        return step

    def _set(self, attribute: str, value) -> None:
        setattr(self, attribute, float(value))
        self.update()

    def _rest(self) -> None:
        self._reset()
        self.update()

    def _reset(self) -> None:
        self._scale, self._angle, self._wash, self._edge, self._ping = 1.0, 0.0, 0.0, 0.0, 0.0
        self._dx = self._dy = 0.0
        self._sx = self._sy = 1.0

    def set_glow(self, enabled: bool) -> None:
        """Start or stop the motion (the name matches the other buttons)."""
        enabled = bool(enabled)
        if enabled == self._moving:
            return
        self._moving = enabled
        if enabled and self.isVisible() and not self.TURNS:
            self._start()
        elif not enabled:
            self.motion.stop()
            self._rest()

    def glowing(self) -> bool:
        return self._moving

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        if self._moving and not self.TURNS and not self.playing():
            self._start()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().hideEvent(event)
        self.motion.stop()
        self._reset()

    def _at_rest(self) -> bool:
        return (self._scale == 1.0 and self._angle == 0.0 and self._wash <= 0.0
                and self._edge <= 0.0 and self._ping <= 0.0 and self._dx == 0.0
                and self._dy == 0.0 and self._sx == 1.0 and self._sy == 1.0)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._at_rest() or self.underMouse() or self.hasFocus():
            super().paintEvent(event)
            return
        # The button without its icon, then the icon as the motion has it.
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.icon = QIcon()
        painter = QStylePainter(self)
        painter.drawControl(QStyle.ControlElement.CE_PushButton, option)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        radius = 17.0 * (theme.FORMAL_RADIUS_FACTOR if theme.ACTIVE_STYLE == "formal" else 1.0)
        radius = min(radius * theme.ACTIVE_SCALE / 100, self.height() / 2)
        rect = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        wash = QColor(self.COLOR)
        wash.setAlpha(round(self.WASH_ALPHA * max(0.0, min(1.0, self._wash))))
        painter.setBrush(wash)
        if self._edge > 0.0:
            edge = QColor(self.COLOR)
            edge.setAlpha(round(255 * min(1.0, self._edge)))
            painter.setPen(QPen(edge, 2.0))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, radius, radius)
        if 0.0 < self._ping < 1.0:
            # A ring that leaves the icon and fades on its way to the edge.
            inner = self.iconSize().width() * 0.45
            outer = min(self.width(), self.height()) / 2 - 1.5
            ring_radius = inner + (outer - inner) * self._ping
            ring = QColor(self.COLOR)
            ring.setAlpha(round(230 * (1.0 - self._ping) ** 1.3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(ring, 2.0))
            painter.drawEllipse(QPointF(self.width() / 2, self.height() / 2), ring_radius, ring_radius)
        icon_px = float(self.iconSize().width())
        edge_px = icon_px * self._scale
        width, height = edge_px * self._sx, edge_px * self._sy
        ratio = self.devicePixelRatioF()
        pixmap = self.icon().pixmap(QSize(max(1, round(edge_px * ratio)), max(1, round(edge_px * ratio))))
        # Inside the button only: a plane that flies off leaves through its edge.
        outline = QPainterPath()
        outline.addRoundedRect(rect, radius, radius)
        painter.setClipPath(outline)
        painter.translate(self.width() / 2 + self._dx * icon_px, self.height() / 2 + self._dy * icon_px)
        painter.rotate(self._angle)
        # A squish keeps the icon standing on the same line.
        painter.drawPixmap(QRectF(-width / 2, edge_px / 2 - height, width, height), pixmap, QRectF(pixmap.rect()))
        painter.end()


class _HeartbeatButton(_PaintedMotionButton):
    """Ko-fi: the cup beats like a heart, two quick beats and a rest."""

    COLOR = QColor(255, 94, 91)
    #: (scale, milliseconds to reach it): lub, dub, then a rest.
    BEATS = ((1.17, 130), (1.0, 150), (1.10, 110), (1.0, 230))
    PEAK = 1.17

    def _moves(self) -> list:
        moves, start, rise = [], 1.0, self.PEAK - 1.0
        for scale, duration in self.BEATS:
            curve = QEasingCurve.Type.OutQuad if scale > start else QEasingCurve.Type.InOutSine
            moves.append(self._together(
                self._step("_scale", start, scale, duration, curve),
                self._step("_wash", (start - 1) / rise, (scale - 1) / rise, duration, curve),
            ))
            start = scale
        return moves


class _BroadcastButton(_PaintedMotionButton):
    """The developer's note, a megaphone: it speaks, and sound waves spread out.

    The megaphone gives a small kick back, as when it speaks, and three
    amber arcs leave its mouth one after another, growing towards the edge
    and fading, inside the button's outline.
    """

    COLOR = QColor(245, 184, 61)
    WASH_ALPHA = 40
    WAVE_MS = 1100
    WAVES = 3
    #: Where the mouth is in the icon (24 px grid): the waves start there.
    MOUTH = (17.6, 12.0)

    def __init__(self, text: str) -> None:
        self._wave = 0.0
        super().__init__(text)

    def _moves(self) -> list:
        kick = QSequentialAnimationGroup(self)
        kick.addAnimation(self._together(
            self._step("_scale", 1.0, 1.1, 90, QEasingCurve.Type.OutQuad),
            self._step("_angle", 0.0, -7.0, 90, QEasingCurve.Type.OutQuad),
        ))
        kick.addAnimation(self._together(
            self._step("_scale", 1.1, 1.0, 260, QEasingCurve.Type.OutBack),
            self._step("_angle", -7.0, 0.0, 260, QEasingCurve.Type.OutBack),
        ))
        wash = QSequentialAnimationGroup(self)
        wash.addAnimation(self._step("_wash", 0.0, 1.0, 120, QEasingCurve.Type.OutQuad))
        wash.addAnimation(self._step("_wash", 1.0, 0.0, self.WAVE_MS - 120))
        return [
            self._together(kick, wash, self._step("_wave", 0.0, 1.0, self.WAVE_MS, QEasingCurve.Type.Linear)),
            self._step("_wave", 0.0, 0.0, 1),
        ]

    def _reset(self) -> None:
        super()._reset()
        self._wave = 0.0

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().paintEvent(event)
        if not 0.0 < self._wave < 1.0 or self.underMouse() or self.hasFocus():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = 17.0 * (theme.FORMAL_RADIUS_FACTOR if theme.ACTIVE_STYLE == "formal" else 1.0)
        radius = min(radius * theme.ACTIVE_SCALE / 100, self.height() / 2)
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0), radius, radius)
        painter.setClipPath(outline)
        icon_px = float(self.iconSize().width())
        unit = icon_px / 24.0
        mouth = QPointF(self.width() / 2 + (self.MOUTH[0] - 12.0) * unit,
                        self.height() / 2 + (self.MOUTH[1] - 12.0) * unit)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for index in range(self.WAVES):
            phase = (self._wave - index * 0.2) / 0.6
            if not 0.0 < phase < 1.0:
                continue
            # Born just past the icon's own waves, gone before the edge.
            reach = icon_px * (0.3 + 0.3 * phase)
            colour = QColor(self.COLOR)
            colour.setAlphaF(math.sin(math.pi * phase) * 0.95)
            pen = QPen(colour, 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            # An arc facing right, opening a little as it travels.
            span = 70.0 + 20.0 * phase
            painter.drawArc(QRectF(mouth.x() - reach, mouth.y() - reach, reach * 2, reach * 2),
                            round(-span / 2 * 16), round(span * 16))
        painter.end()


class _TakingTurnsButton(_PaintedMotionButton):
    """A community link: it moves in its turn, with no colour wash (links,
    not alerts)."""

    WASH_ALPHA = 0


class _HopButton(_TakingTurnsButton):
    """GitHub: the cat hops twice and lands with a little squash."""

    def _moves(self) -> list:
        up, down = QEasingCurve.Type.OutQuad, QEasingCurve.Type.InQuad
        return [
            self._step("_dy", 0.0, -0.26, 190, up),
            self._step("_dy", -0.26, 0.0, 170, down),
            self._together(self._step("_sx", 1.0, 1.12, 80), self._step("_sy", 1.0, 0.86, 80)),
            self._together(self._step("_sx", 1.12, 1.0, 120), self._step("_sy", 0.86, 1.0, 120)),
            self._step("_dy", 0.0, -0.1, 120, up),
            self._step("_dy", -0.1, 0.0, 110, down),
        ]


class _JellyButton(_TakingTurnsButton):
    """Discord: the face wobbles like jelly, wide then tall, then settles."""

    WOBBLE = ((1.18, 0.84, 120), (0.9, 1.12, 130), (1.07, 0.94, 120), (0.97, 1.03, 110), (1.0, 1.0, 120))

    def _moves(self) -> list:
        moves, sx, sy = [], 1.0, 1.0
        for to_x, to_y, duration in self.WOBBLE:
            moves.append(self._together(self._step("_sx", sx, to_x, duration), self._step("_sy", sy, to_y, duration)))
            sx, sy = to_x, to_y
        return moves


class _FlightButton(_TakingTurnsButton):
    """Telegram: the plane flies off to the top right and comes back from below."""


    def _moves(self) -> list:
        return [
            self._together(
                self._step("_dx", 0.0, -0.08, 140, QEasingCurve.Type.OutQuad),
                self._step("_dy", 0.0, 0.08, 140, QEasingCurve.Type.OutQuad),
            ),
            self._together(
                self._step("_dx", -0.08, 1.3, 300, QEasingCurve.Type.InQuad),
                self._step("_dy", 0.08, -1.3, 300, QEasingCurve.Type.InQuad),
            ),
            self._together(self._step("_dx", -1.3, -1.3, 1), self._step("_dy", 1.3, 1.3, 1)),
            self._together(
                self._step("_dx", -1.3, 0.0, 380, QEasingCurve.Type.OutBack),
                self._step("_dy", 1.3, 0.0, 380, QEasingCurve.Type.OutBack),
            ),
        ]


class _SupportButton(_PaintedMotionButton):
    """Support: report a problem or suggest an idea, in teal, with a sonar ping.

    A ring leaves the headset and fades on its way to the edge while the
    icon nods once, then a rest: someone is listening. The other buttons
    glow nothing like it: the note rings, Ko-fi beats.
    """

    COLOR = QColor(46, 196, 166)
    WASH_ALPHA = 45
    PING_MS = 1000

    def _moves(self) -> list:
        ping = QParallelAnimationGroup(self)
        ping.addAnimation(self._step("_ping", 0.0, 1.0, self.PING_MS, QEasingCurve.Type.OutCubic))
        nod = QSequentialAnimationGroup(self)
        nod.addAnimation(self._step("_scale", 1.0, 1.08, 160, QEasingCurve.Type.OutQuad))
        nod.addAnimation(self._step("_scale", 1.08, 1.0, 260))
        ping.addAnimation(nod)
        wash = QSequentialAnimationGroup(self)
        wash.addAnimation(self._step("_wash", 0.0, 1.0, 180, QEasingCurve.Type.OutQuad))
        wash.addAnimation(self._step("_wash", 1.0, 0.0, self.PING_MS - 180))
        ping.addAnimation(wash)
        # The ring ends at 1.0, which is drawn as nothing; back to rest.
        return [ping, self._step("_ping", 0.0, 0.0, 1)]


class _UpdateBadgeButton(_PaintedMotionButton):
    """Appears only when a newer release exists, and launches so it is noticed.

    The best moment the row has, so the best animation: a comet of light runs
    one lap around the edge, and as it closes the lap the board hops, three
    chevrons rise through it and a burst of sparks flies out. Then a breath,
    and again. It keeps its own time (not the others' turns) and the alert
    switch leaves it on: a new version is the one thing worth seeing.
    """

    TURNS = False
    COMET_MS = 900
    POP_MS = 720
    REST_MS = 1000
    #: The two colours of the light: the accent and a bright cyan.
    SPARK = QColor(140, 225, 255)
    SPARKS = 8

    def __init__(self) -> None:
        self._comet = 0.0
        self._rise = 0.0
        self._burst = 0.0
        super().__init__("A newer version is available")
        self.setProperty("updateAvailable", True)
        self.setIcon(QIcon(str(ICON_DIR / "update_badge.png")))
        self._published = ""
        self._glow = self.motion
        self.hide()
        self.set_glow(True)

    # -- the timeline -------------------------------------------------------

    def _build_motion(self) -> None:
        self.motion.addAnimation(self._step("_comet", 0.0, 1.0, self.COMET_MS, QEasingCurve.Type.InOutCubic))
        hop = QSequentialAnimationGroup(self)
        hop.addAnimation(self._together(
            self._step("_scale", 1.0, 1.16, 170, QEasingCurve.Type.OutBack),
            self._step("_dy", 0.0, -0.12, 170, QEasingCurve.Type.OutQuad),
        ))
        hop.addAnimation(self._together(
            self._step("_scale", 1.16, 1.0, 320, QEasingCurve.Type.OutBounce),
            self._step("_dy", -0.12, 0.0, 320, QEasingCurve.Type.OutBounce),
        ))
        wash = QSequentialAnimationGroup(self)
        wash.addAnimation(self._step("_wash", 0.0, 1.0, 120, QEasingCurve.Type.OutQuad))
        wash.addAnimation(self._step("_wash", 1.0, 0.0, self.POP_MS - 120))
        self.motion.addAnimation(self._together(
            hop, wash,
            self._step("_rise", 0.0, 1.0, self.POP_MS, QEasingCurve.Type.Linear),
            self._step("_burst", 0.0, 1.0, self.POP_MS - 100, QEasingCurve.Type.OutCubic),
        ))
        # Everything back to rest before the breath.
        self.motion.addAnimation(self._together(
            self._step("_comet", 0.0, 0.0, 1), self._step("_rise", 0.0, 0.0, 1), self._step("_burst", 0.0, 0.0, 1),
        ))
        self.motion.addPause(self.REST_MS)

    def _reset(self) -> None:
        super()._reset()
        self._comet = self._rise = self._burst = 0.0

    @property
    def _level(self) -> float:
        """How far the light has gone (0 at rest)."""
        return max(self._comet if self._comet < 1.0 else 0.0, self._rise, self._burst)

    def glow_color(self) -> QColor:
        return QColor(theme.COLORS["blue"])

    # -- drawing ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        # The wash in the active accent, which can change while it is shown.
        self.COLOR = self.glow_color()
        super().paintEvent(event)
        if self.underMouse() or self.hasFocus():
            return
        comet = 0.0 < self._comet < 1.0
        if not (comet or 0.0 < self._rise < 1.0 or 0.0 < self._burst < 1.0):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = 17.0 * (theme.FORMAL_RADIUS_FACTOR if theme.ACTIVE_STYLE == "formal" else 1.0)
        radius = min(radius * theme.ACTIVE_SCALE / 100, self.height() / 2)
        rect = QRectF(self.rect()).adjusted(1.25, 1.25, -1.25, -1.25)
        outline = QPainterPath()
        outline.addRoundedRect(rect, radius, radius)
        centre = QPointF(self.width() / 2, self.height() / 2)
        accent = self.glow_color()
        icon_px = float(self.iconSize().width())
        if comet:
            self._paint_comet(painter, outline, centre, accent)
        painter.setClipPath(outline)
        if 0.0 < self._rise < 1.0:
            self._paint_chevrons(painter, centre, accent, icon_px)
        if 0.0 < self._burst < 1.0:
            self._paint_sparks(painter, centre, accent, icon_px)
        painter.end()

    def _paint_comet(self, painter: QPainter, outline: QPainterPath, centre: QPointF, accent: QColor) -> None:
        """A head of light running clockwise from the top, its tail fading behind."""
        progress = self._comet
        fade = min(1.0, progress * 6.0) * (1.0 if progress < 0.8 else (1.0 - progress) / 0.2)
        head = 90.0 - 360.0 * progress
        for width, strength, tail in ((6.0, 0.28, 0.34), (2.4, 1.0, 0.26)):
            gradient = QConicalGradient(centre, head)
            bright = QColor(self.SPARK)
            bright.setAlphaF(strength * fade)
            mid = QColor(accent)
            mid.setAlphaF(strength * fade * 0.7)
            clear = QColor(accent)
            clear.setAlphaF(0.0)
            gradient.setColorAt(0.0, bright)
            gradient.setColorAt(tail * 0.35, mid)
            gradient.setColorAt(tail, clear)
            gradient.setColorAt(1.0, clear)
            pen = QPen(QBrush(gradient), width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(outline)

    def _paint_chevrons(self, painter: QPainter, centre: QPointF, accent: QColor, icon_px: float) -> None:
        """Three ^ rising through the board, one after another."""
        half = icon_px * 0.2
        travel = self.height() * 0.95
        for index in range(3):
            phase = (self._rise - index * 0.18) / 0.64
            if not 0.0 < phase < 1.0:
                continue
            y = centre.y() + travel / 2 - travel * phase
            colour = QColor(self.SPARK if index % 2 == 0 else accent)
            colour.setAlphaF(math.sin(math.pi * phase) * 0.95)
            pen = QPen(colour, 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            chevron = QPainterPath(QPointF(centre.x() - half, y + half * 0.6))
            chevron.lineTo(centre.x(), y - half * 0.4)
            chevron.lineTo(centre.x() + half, y + half * 0.6)
            painter.drawPath(chevron)

    def _paint_sparks(self, painter: QPainter, centre: QPointF, accent: QColor, icon_px: float) -> None:
        """A ring of sparks flying out from the board and fading."""
        burst = self._burst
        reach = icon_px * (0.3 + 0.55 * burst)
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(self.SPARKS):
            angle = math.radians(index * 360.0 / self.SPARKS + 22.5)
            # Every other spark flies a little further, so the ring sparkles.
            distance = reach * (1.0 if index % 2 == 0 else 0.82)
            colour = QColor(self.SPARK if index % 2 == 0 else accent)
            colour.setAlphaF(max(0.0, 1.0 - burst) ** 1.2)
            painter.setBrush(colour)
            size = 2.4 * (1.0 - burst * 0.6)
            painter.drawEllipse(QPointF(centre.x() + math.cos(angle) * distance,
                                        centre.y() - math.sin(angle) * distance), size, size)

    # -- the version --------------------------------------------------------

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


#: Older name, still exported by ``dashboard_widgets``.
_ReportButton = _SupportButton


class DashboardFooter(QWidget):
    """Compact external links embedded in the preparation header."""

    contact_clicked = pyqtSignal()
    telegram_clicked = pyqtSignal()
    report_clicked = pyqtSignal()
    note_clicked = pyqtSignal()
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
        self.repositories_button = _HopButton("Official repositories")
        self.repositories_button.setIcon(icon("github"))
        self.repositories_button.clicked.connect(self.repositories_clicked)
        self.layout.addWidget(self.repositories_button)
        self.contact_button = _JellyButton("BC250 community on Discord")
        self.contact_button.setIcon(icon("discord"))
        self.contact_button.clicked.connect(self.contact_clicked)
        self.layout.addWidget(self.contact_button)
        # The community's Telegram group, beside its Discord.
        self.telegram_button = _FlightButton("BC250 community on Telegram")
        self.telegram_button.setIcon(icon("telegram"))
        self.telegram_button.clicked.connect(self.telegram_clicked)
        self.layout.addWidget(self.telegram_button)
        self.report_button = _SupportButton("Report a problem or suggest an idea")
        self.report_button.setIcon(icon("support_headset"))
        self.report_button.clicked.connect(self.report_clicked)
        self.layout.addWidget(self.report_button)
        # Between reporting a problem and Ko-fi: what is going on with support.
        self.note_button = _BroadcastButton("A note from the developer")
        self.note_button.setIcon(icon("note_heart"))
        self.note_button.clicked.connect(self.note_clicked)
        self.layout.addWidget(self.note_button)
        self.support_button = _HeartbeatButton("Buy me a coffee")
        self.support_button.setProperty("donation", True)
        # Official, bundled Ko-fi artwork: no network access needed by the UI.
        self.support_button.setIcon(QIcon(str(ICON_DIR / "kofi_cup.png")))
        self.support_button.clicked.connect(self.support_clicked)
        self.layout.addWidget(self.support_button)
        # The animated buttons take turns at random, one at a time.
        self._random = random.Random()
        self._last_turn = None
        self._turns = QTimer(self)
        self._turns.setInterval(self.TURN_TICK_MS)
        self._turns.timeout.connect(self.take_turn)

    #: How often the footer looks for the next turn once the last one ended.
    TURN_TICK_MS = 120

    def _animated(self) -> list:
        return [self.repositories_button, self.contact_button, self.telegram_button,
                self.report_button, self.note_button, self.support_button]

    def take_turn(self) -> _PaintedMotionButton | None:
        """Animate one button at random, if none is moving; never the same twice running."""
        animated = self._animated()
        if any(button.playing() for button in animated):
            return None
        free = [button for button in animated if button.can_play()]
        if len(free) > 1 and self._last_turn in free:
            free.remove(self._last_turn)
        if not free:
            return None
        chosen = self._random.choice(free)
        chosen.play()
        self._last_turn = chosen
        return chosen

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        self._turns.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().hideEvent(event)
        self._turns.stop()

    def set_report_glow(self, enabled: bool) -> None:
        """The footer's animations: support pings, the note rings, Ko-fi beats,
        and GitHub, Discord and Telegram take turns moving."""
        for button in (self.report_button, self.note_button, self.support_button,
                       self.repositories_button, self.contact_button, self.telegram_button):
            button.set_glow(enabled)

    set_alert_animations = set_report_glow

    # --- a narrow window: Telegram folds away before the buttons overlap ----

    def _row_width(self, *, with_telegram: bool) -> int:
        buttons = [
            self.layout.itemAt(index).widget() for index in range(self.layout.count())
        ]
        shown = [
            button for button in buttons
            if button is not None and (not button.isHidden() or (with_telegram and button is self.telegram_button))
            and not (button is self.telegram_button and not with_telegram)
        ]
        spacing = self.layout.spacing() * max(0, len(shown) - 1)
        return sum(button.sizeHint().width() for button in shown) + spacing

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        # Squeezed below what the row needs (a phone-width window at a large
        # scale): Discord already reaches the community, so Telegram goes first.
        if not self.telegram_button.isHidden() and self.width() + 1 < self._row_width(with_telegram=True):
            self._telegram_folded = True
            self.telegram_button.hide()
            self.updateGeometry()

    def fit_to(self, available: int) -> None:
        """The header's room changed: bring Telegram back once it fits again."""
        if getattr(self, "_telegram_folded", False) and available >= self._row_width(with_telegram=True):
            self._telegram_folded = False
            self.telegram_button.show()
            self.updateGeometry()

    def announce_update(self, published: str) -> None:
        """Show or hide the update badge. Empty string means nothing to show."""
        self.update_button.announce(published)
