"""A guided walk over the application, pointing at the real controls.

The update badge already had a bubble with a tail that hangs off a specific
widget, and it turned out to be the clearest thing in the interface: it says
what a control is while the control is on screen, rather than describing it in
a manual nobody opens. This is that idea made general.

Two pieces. A spotlight, which dims the whole window except a hole cut around
the widget being talked about — so the eye has one place to go and the page
behind stays recognisable. And a callout, which is the bubble: a step count, a
title, a sentence, and the three controls a tour owes its user (back, next,
and out).

The tour never operates the application. It navigates between pages, because
that is how it reaches the next anchor, and it touches nothing else: a guided
tour that changes clocks and voltages on a board while explaining itself would
be a very poor first impression.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import theme as theme_module
from ..i18n import tr

logger = logging.getLogger(__name__)

#: Breathing room left around the highlighted widget, in logical pixels.
SPOTLIGHT_PADDING = 8
SPOTLIGHT_RADIUS = 12.0
#: How dark the rest of the window goes, per mode. Enough to send the eye to
#: the hole, light enough that the page is still recognisable as the page — a
#: dark palette needs more of it, because the veil and the page start closer
#: together.
SPOTLIGHT_ALPHA = {"light": 132, "dark": 178}
MOVE_MS = 320
#: A page changes before the anchor on it can be measured; one layout pass is
#: not always enough with scroll areas, so the tour waits a beat.
SETTLE_MS = 90
#: And once more after the scroll has run, because scrolling moves the anchor.
RESETTLE_MS = 220
#: How often the tour re-measures where its anchor actually is. Pages refresh
#: on their own timers, the window can be resized, a panel can grow a row —
#: any of which moves a control out from under a bubble that was placed once
#: and never looked again.
FOLLOW_MS = 160
#: Space left between the highlighted control and the bubble.
CALLOUT_GAP = 12
#: And between the bubble and the edge of the window.
WINDOW_MARGIN = 10


@dataclass(frozen=True)
class TourStop:
    """One stop: where to be, what to point at, and what to say.

    ``anchor`` is resolved when the stop is reached rather than when the tour
    is written, because most of these widgets do not exist until their page is
    built, and some move when the sidebar collapses.
    """

    page: str
    #: The control to highlight. May answer with several widgets, in which
    #: case the spotlight opens over all of them at once — the dashboard's
    #: readings are one subject spread over two separate blocks, and cutting
    #: them apart would say they were two.
    anchor: Callable[[object], object]
    title: str
    body: str
    #: Run before the anchor is measured: select the tab it lives on, open the
    #: panel it is inside. A stop that points at a control on a tab nobody has
    #: opened would otherwise point at a hidden widget and be skipped.
    arrange: Callable[[object], None] | None = None
    #: Run when the tour moves on from this stop, or ends on it: close the
    #: drawer ``arrange`` opened, so the next stop starts from a clean page.
    leave: Callable[[object], None] | None = None
    #: A list under the sentence, for the few stops that have to compare
    #: things or give steps in order: the firmware images, the flash on the
    #: board. The bubble widens to hold it.
    points: tuple[str, ...] = ()
    #: Number the points: they are steps to follow, not items to compare.
    ordered: bool = False
    #: One last line in small type, under the list.
    footnote: str = ""
    #: Set on the stops that introduce a newer feature, so the people who
    #: took the tour before it existed can be shown just those stops once.
    feature: str = ""


def reveal_in_scroll_area(anchor: QWidget) -> bool:
    """Scroll ``anchor`` into view inside whichever scroll area holds it.

    Several of the pages this tour visits are taller than the window — the
    dashboard's preparation panel is most of a screen on its own — so a stop
    pointing at one of them would otherwise highlight a strip at the bottom
    edge, or nothing at all. Returns True when the view actually moved, which
    is the caller's cue to measure again rather than immediately.

    A control shorter than the viewport is centred; one taller than it is
    aligned near the top, because the top is where its heading is.
    """
    node = anchor.parentWidget()
    while node is not None:
        if isinstance(node, QAbstractScrollArea):
            viewport = node.viewport()
            if viewport is not None and viewport.isAncestorOf(anchor):
                break
        node = node.parentWidget()
    else:
        return False

    bar = node.verticalScrollBar()
    if bar is None or not bar.isEnabled():
        return False
    viewport = node.viewport()
    top_in_viewport = anchor.mapTo(viewport, QPoint(0, 0)).y()
    absolute_top = bar.value() + top_in_viewport
    if anchor.height() <= viewport.height():
        target = absolute_top - (viewport.height() - anchor.height()) // 2
    else:
        target = absolute_top - 24
    target = max(bar.minimum(), min(int(target), bar.maximum()))
    if target == bar.value():
        return False
    bar.setValue(target)
    return True


class Spotlight(QWidget):
    """Everything dimmed, except a rounded hole around one widget."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("tourSpotlight")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._hole = QRectF()
        self._target = QRectF()
        self._from = QRectF()
        self.hide()

        # The hole slides from one anchor to the next rather than jumping, so
        # the eye can follow it and keep its place on the page.
        self._travel = QVariantAnimation(self)
        self._travel.setDuration(MOVE_MS)
        self._travel.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._travel.valueChanged.connect(self._on_travel)

    def hole(self) -> QRect:
        """Where the hole is right now, mid-travel included."""
        return self._hole.toRect()

    def target(self) -> QRect:
        """Where the hole is going, which is what a bubble must point at.

        ``hole()`` is the animating rectangle: for the whole of the travel it
        still reports the *previous* anchor. Placing the bubble against that
        put every label next to the control before the one being described —
        which looked exactly like a bubble that had landed at random.
        """
        return self._target.toRect()

    def move_to(self, rect: QRect) -> None:
        """Open the hole over ``rect``, travelling from wherever it was."""
        target = QRectF(rect.adjusted(
            -SPOTLIGHT_PADDING, -SPOTLIGHT_PADDING,
            SPOTLIGHT_PADDING, SPOTLIGHT_PADDING,
        ))
        self._travel.stop()
        if self._hole.isNull() or not self.isVisible():
            self._hole = target
            self._target = target
            self.update()
            return
        self._target = target
        # Before start(), never after: the animation can emit its first value
        # synchronously, and it reads this.
        self._from = QRectF(self._hole)
        self._travel.setStartValue(0.0)
        self._travel.setEndValue(1.0)
        self._travel.start()

    def _on_travel(self, value: float) -> None:
        progress = float(value)
        start = self._from
        self._hole = QRectF(
            start.x() + (self._target.x() - start.x()) * progress,
            start.y() + (self._target.y() - start.y()) * progress,
            start.width() + (self._target.width() - start.width()) * progress,
            start.height() + (self._target.height() - start.height()) * progress,
        )
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        veil = QPainterPath()
        veil.addRect(QRectF(self.rect()))
        if not self._hole.isNull():
            cut = QPainterPath()
            cut.addRoundedRect(self._hole, SPOTLIGHT_RADIUS, SPOTLIGHT_RADIUS)
            veil = veil.subtracted(cut)
        shade = QColor("#03060B" if theme_module.ACTIVE_MODE == "dark" else "#0D1422")
        shade.setAlpha(SPOTLIGHT_ALPHA.get(theme_module.ACTIVE_MODE, 150))
        painter.fillPath(veil, shade)
        if not self._hole.isNull():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(theme_module.COLORS["blue"]), 1.6))
            painter.drawRoundedRect(self._hole, SPOTLIGHT_RADIUS, SPOTLIGHT_RADIUS)
        painter.end()


class TourCallout(QFrame):
    """The bubble: a tail into the anchor, a sentence, and the way onward.

    Drawn rather than styled, for the same reason the update bubble is: a
    stylesheet has no way to express a tail that points at a particular widget,
    and the tail is the whole point — it is what turns a floating tooltip into
    a label attached to a control.
    """

    TAIL = 9
    TAIL_HALF_WIDTH = 10
    RADIUS = 12.0
    WIDTH = 340
    #: For a stop that carries a list: wide enough that a step reads as one
    #: or two lines, narrow enough to sit beside the panel it describes.
    WIDE_WIDTH = 520

    back_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    end_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Measured to fit its text; Compact density leaves it alone.
        self.setProperty("densityLocked", True)
        self.setObjectName("tourCallout")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedWidth(self.WIDTH)
        self._side = "top"
        self._hole = QRect()
        # True when the bubble had to sit on top of what it describes, so the
        # tail would point at itself.
        self._tailless = False

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

        self._slide = QPropertyAnimation(self, b"pos", self)
        self._slide.setDuration(MOVE_MS)
        self._slide.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._root = QVBoxLayout(self)
        self._root.setSpacing(6)
        self._apply_margins()

        head = QHBoxLayout()
        head.setSpacing(8)
        self.step_label = QLabel("", self)
        self.step_label.setObjectName("tourStep")
        head.addWidget(self.step_label)
        head.addStretch(1)
        self.end_button = QPushButton(tr("End tour"), self)
        self.end_button.setObjectName("tourGhost")
        self.end_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.end_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.end_button.clicked.connect(self.end_clicked)
        head.addWidget(self.end_button)
        self._root.addLayout(head)

        self.title = QLabel("", self)
        self.title.setObjectName("tourTitle")
        self.title.setWordWrap(True)
        self._root.addWidget(self.title)

        self.body = QLabel("", self)
        self.body.setObjectName("tourBody")
        self.body.setWordWrap(True)
        self._root.addWidget(self.body)

        self.points = QFrame(self)
        self.points.setObjectName("tourPoints")
        self._points_box = QVBoxLayout(self.points)
        self._points_box.setContentsMargins(0, 8, 0, 0)
        self._points_box.setSpacing(6)
        self._point_rows: list[QWidget] = []
        self.points.hide()
        self._root.addWidget(self.points)
        self.footnote = QLabel("", self)
        self.footnote.setObjectName("tourFootnote")
        self.footnote.setWordWrap(True)
        self.footnote.hide()
        self._root.addWidget(self.footnote)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch(1)
        self.back_button = QPushButton(tr("Back"), self)
        self.back_button.setObjectName("tourSecondary")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(self.back_clicked)
        actions.addWidget(self.back_button)
        self.next_button = QPushButton(tr("Next"), self)
        self.next_button.setObjectName("tourPrimary")
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button.setDefault(True)
        self.next_button.clicked.connect(self.next_clicked)
        actions.addWidget(self.next_button)
        self._root.addLayout(actions)
        self.hide()

    # ------------------------------------------------------------- contents

    def set_stop(
        self,
        *,
        title: str,
        body: str,
        index: int,
        total: int,
        last: bool,
        points: tuple[str, ...] = (),
        ordered: bool = False,
        footnote: str = "",
    ) -> None:
        self.title.setText(title)
        self.body.setText(body)
        self.step_label.setText(f"{index} / {total}")
        self.back_button.setVisible(index > 1)
        self.next_button.setText(tr("Finish") if last else tr("Next"))
        self.setFixedWidth(self.WIDE_WIDTH if points else self.WIDTH)
        self._set_points(points, ordered)
        self.footnote.setText(footnote)
        self.footnote.setVisible(bool(footnote))

    def _set_points(self, points: tuple[str, ...], ordered: bool) -> None:
        for row in self._point_rows:
            self._points_box.removeWidget(row)
            row.deleteLater()
        self._point_rows = []
        for number, text in enumerate(points, start=1):
            row = QWidget(self.points)
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(8)
            marker = QLabel(f"{number}." if ordered else "\u2013", row)
            marker.setObjectName("tourPointMarker")
            marker.setFixedWidth(16)
            marker.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            line.addWidget(marker, 0, Qt.AlignmentFlag.AlignTop)
            label = QLabel(text, row)
            label.setObjectName("tourPoint")
            label.setWordWrap(True)
            line.addWidget(label, 1)
            self._points_box.addWidget(row)
            self._point_rows.append(row)
        self.points.setVisible(bool(points))

    def retranslate(self) -> None:
        self.end_button.setText(tr("End tour"))
        self.back_button.setText(tr("Back"))

    # ------------------------------------------------------------ placement

    def _apply_margins(self) -> None:
        top = 14 + (self.TAIL if self._side == "top" else 0)
        bottom = 14 + (self.TAIL if self._side == "bottom" else 0)
        left = 16 + (self.TAIL if self._side == "left" else 0)
        right = 14 + (self.TAIL if self._side == "right" else 0)
        self._root.setContentsMargins(left, top, right, bottom)

    def _set_side(self, side: str) -> None:
        if side == self._side:
            return
        self._side = side
        self._apply_margins()

    def _fit(self) -> None:
        """Resize to the height this text really needs at this width.

        ``adjustSize()`` asks the layout for its size hint, and a wrapped
        QLabel reports that hint for the width *it* would have picked, not for
        the one it is given. The bubble is a fixed width, so the only honest
        question is "how tall at this width" — and the answer comes back a
        line taller the moment a translation runs longer than the English,
        which is why the last line was being cut off in some languages.
        """
        layout = self._root
        layout.activate()
        width = self.width()
        self.resize(
            width,
            max(layout.totalHeightForWidth(width), layout.totalMinimumSize().height()),
        )

    def point_at(self, hole: QRect) -> None:
        """Sit beside ``hole`` and point at it, in whatever room there is.

        The old rule was "below, then above, then to the sides, and if none of
        them fits, put it below anyway and clamp". That last clause is what
        produced bubbles sitting on top of the very control they pointed at,
        and bubbles pinned to a corner of a small window: the clamp moved them
        somewhere they had never been measured for.

        This measures the free band on each side of the hole first. A side is
        only offered if the bubble genuinely fits in its band; when none does,
        the widest band wins rather than a fixed fallback, so the bubble ends
        up where there is most room instead of where the list happened to end.
        """
        window = self.parentWidget()
        if window is None:
            return

        # Measured once per side, because the margins — and therefore the
        # height — change with which edge carries the tail.
        sizes = {}
        for side in ("bottom", "top", "right", "left"):
            self._set_side(self._tail_for(side))
            self._fit()
            sizes[side] = (self.width(), self.height())

        bands = {
            "bottom": window.height() - hole.bottom() - CALLOUT_GAP - WINDOW_MARGIN,
            "top": hole.top() - CALLOUT_GAP - WINDOW_MARGIN,
            "right": window.width() - hole.right() - CALLOUT_GAP - WINDOW_MARGIN,
            "left": hole.left() - CALLOUT_GAP - WINDOW_MARGIN,
        }

        for side in ("bottom", "top", "right", "left"):
            width, height = sizes[side]
            needed = height if side in ("bottom", "top") else width
            if bands[side] >= needed:
                self._tailless = False
                self._set_side(self._tail_for(side))
                self._fit()
                self._place(self._corner_for(side, hole, window), hole, window)
                return

        # Nothing fits beside it: a small window, or a control that fills most
        # of one — the whole top strip of the dashboard on a 640-pixel screen.
        # Sit inside the highlighted area, low enough to leave its heading
        # readable, and drop the tail: an arrow pointing at the thing the
        # bubble is already sitting on top of reads as a drawing error.
        self._tailless = True
        self._set_side("top")
        self._fit()
        self._place(
            QPoint(
                hole.center().x() - self.width() // 2,
                hole.bottom() - self.height() - CALLOUT_GAP,
            ),
            hole,
            window,
        )

    @staticmethod
    def _tail_for(side: str) -> str:
        """Which edge of the bubble carries the tail, given where it sits.

        A bubble below the control points upwards out of its own top edge.
        """
        return {"bottom": "top", "top": "bottom", "right": "left", "left": "right"}[side]

    def _corner_for(self, side: str, hole: QRect, window: QWidget) -> QPoint:
        if side == "bottom":
            return QPoint(hole.center().x() - self.width() // 2, hole.bottom() + CALLOUT_GAP)
        if side == "top":
            return QPoint(
                hole.center().x() - self.width() // 2,
                hole.top() - self.height() - CALLOUT_GAP,
            )
        if side == "right":
            return QPoint(hole.right() + CALLOUT_GAP, hole.center().y() - self.height() // 2)
        return QPoint(
            hole.left() - self.width() - CALLOUT_GAP,
            hole.center().y() - self.height() // 2,
        )

    def _place(self, point: QPoint, hole: QRect, window: QWidget) -> None:
        x = max(WINDOW_MARGIN, min(point.x(), window.width() - self.width() - WINDOW_MARGIN))
        y = max(WINDOW_MARGIN, min(point.y(), window.height() - self.height() - WINDOW_MARGIN))
        # Kept so the tail can be worked out from wherever the bubble happens
        # to be during the glide, rather than only from where it ends up.
        self._hole = QRect(hole)
        target = QPoint(x, y)
        first_time = self.isHidden()
        self.show()
        self.raise_()
        self._slide.stop()
        if first_time:
            self.move(target)
        else:
            # Glide rather than jump. The spotlight is travelling to the same
            # place over the same span, so the two move together and the eye
            # can follow one control to the next instead of losing both.
            self._slide.setStartValue(self.pos())
            self._slide.setEndValue(target)
            self._slide.start()
        self.update()

    def _tail_offset(self) -> int:
        """Where along its edge the tail sits, for the bubble's position now.

        Computed per paint rather than stored once, so during the glide the
        tail stays pointing at the control instead of at where the bubble is
        going to be.
        """
        if self._hole.isNull():
            return int(self.RADIUS + self.TAIL_HALF_WIDTH)
        if self._side in ("top", "bottom"):
            centre = self._hole.center().x() - self.x()
            span = self.width()
        else:
            centre = self._hole.center().y() - self.y()
            span = self.height()
        return int(max(
            self.RADIUS + self.TAIL_HALF_WIDTH,
            min(centre, span - self.RADIUS - self.TAIL_HALF_WIDTH),
        ))

    # --------------------------------------------------------------- drawing

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect()
        if self._side == "top":
            body = QRectF(rect.adjusted(0, self.TAIL, -1, -1))
            edge, tip = body.top(), 0.0
        elif self._side == "bottom":
            body = QRectF(rect.adjusted(0, 0, -1, -self.TAIL - 1))
            edge, tip = body.bottom(), float(rect.bottom())
        elif self._side == "left":
            body = QRectF(rect.adjusted(self.TAIL, 0, -1, -1))
            edge, tip = body.left(), 0.0
        else:
            body = QRectF(rect.adjusted(0, 0, -self.TAIL - 1, -1))
            edge, tip = body.right(), float(rect.right())

        shape = QPainterPath()
        shape.addRoundedRect(body, self.RADIUS, self.RADIUS)
        if self._tailless:
            painter.setBrush(QColor(theme_module.COLORS["panel_raised"]))
            painter.setPen(QPen(QColor(theme_module.COLORS["blue"]), 1.4))
            painter.drawPath(shape)
            painter.end()
            return
        half = float(self.TAIL_HALF_WIDTH)
        at = float(self._tail_offset())
        if self._side in ("top", "bottom"):
            tail = QPolygonF([
                QPointF(at - half, edge), QPointF(at, tip), QPointF(at + half, edge),
            ])
        else:
            tail = QPolygonF([
                QPointF(edge, at - half), QPointF(tip, at), QPointF(edge, at + half),
            ])
        shape.addPolygon(tail)
        shape = shape.simplified()

        painter.setBrush(QColor(theme_module.COLORS["panel_raised"]))
        painter.setPen(QPen(QColor(theme_module.COLORS["blue"]), 1.4))
        painter.drawPath(shape)
        painter.end()


class TourGuide(QObject):
    """Runs the stops in order over a window that already exists."""

    finished = pyqtSignal()

    def __init__(self, window: QWidget, stops: tuple[TourStop, ...], parent: QObject | None = None) -> None:
        super().__init__(parent or window)
        self._window = window
        self._stops = tuple(stops)
        self._index = -1
        self._running = False
        self._placed_at = QRect()
        #: +1 while moving forward, -1 after Back: a stop whose control is not
        #: on this board is skipped in the direction the user was going,
        #: instead of Back bouncing straight forward again.
        self._direction = 1
        self.spotlight = Spotlight(window)
        self.callout = TourCallout(window)
        self.callout.next_clicked.connect(self.go_next)
        self.callout.back_clicked.connect(self.go_back)
        self.callout.end_clicked.connect(self.stop)

        # The anchor is measured once when a stop opens, and the interface
        # does not hold still afterwards: pages refresh on their own timers,
        # a panel grows a row, the window is resized, the sidebar collapses at
        # a breakpoint. Any of those moves a control out from under a bubble
        # that was placed once and never looked again — which is exactly how a
        # label ends up floating somewhere it does not belong. This keeps
        # asking where the anchor is, and only moves anything when it answers
        # differently.
        self._follow = QTimer(self)
        self._follow.setInterval(FOLLOW_MS)
        self._follow.timeout.connect(self._follow_anchor)

    @property
    def running(self) -> bool:
        return self._running

    @property
    def index(self) -> int:
        return self._index

    def start(self) -> None:
        if not self._stops:
            self.finished.emit()
            return
        self._running = True
        self.spotlight.setGeometry(self._window.rect())
        self.spotlight.show()
        self.spotlight.raise_()
        self._index = -1
        self._follow.start()
        self.go_next()

    def go_next(self) -> None:
        self._direction = 1
        if self._index + 1 >= len(self._stops):
            self.stop()
            return
        self._show(self._index + 1)

    def go_back(self) -> None:
        self._direction = -1
        if self._index <= 0:
            return
        self._show(self._index - 1)

    def _skip(self) -> None:
        """Pass over a stop with nothing to point at, the way the user was going."""
        if self._direction < 0 and self._index > 0:
            self.go_back()
        else:
            self.go_next()

    def _leave_current(self) -> None:
        if not (0 <= self._index < len(self._stops)):
            return
        leave = self._stops[self._index].leave
        if leave is None:
            return
        try:
            leave(self._window)
        except Exception:
            logger.debug("A tour stop could not tidy up after itself", exc_info=True)

    def stop(self) -> None:
        if not self._running:
            return
        self._leave_current()
        self._running = False
        self._follow.stop()
        self._placed_at = QRect()
        self.callout.hide()
        self.spotlight.hide()
        self.finished.emit()

    def reposition(self) -> None:
        """Follow the window when it is resized mid-tour."""
        if not self._running:
            return
        self.spotlight.setGeometry(self._window.rect())
        self._settle()

    def _show(self, index: int) -> None:
        if index != self._index:
            self._leave_current()
        self._index = index
        self._placed_at = QRect()
        stop = self._stops[index]
        navigate = getattr(self._window, "navigate", None)
        if stop.page and callable(navigate):
            navigate(stop.page)
        if stop.arrange is not None:
            # Open the tab the control lives on before looking for it: a
            # control on a tab nobody selected is not visible, and an
            # invisible anchor is a skipped stop.
            try:
                stop.arrange(self._window)
            except Exception:
                logger.debug("A tour stop could not arrange its page", exc_info=True)
        self.callout.set_stop(
            title=stop.title,
            body=stop.body,
            index=index + 1,
            total=len(self._stops),
            last=index == len(self._stops) - 1,
            points=stop.points,
            ordered=stop.ordered,
            footnote=stop.footnote,
        )
        # The page has just changed; its widgets have no geometry until Qt has
        # laid them out, and measuring now would point the tail at (0, 0).
        QTimer.singleShot(SETTLE_MS, self._settle)

    def _settle(self) -> None:
        if not self._running or not (0 <= self._index < len(self._stops)):
            return
        anchors = self._anchor()
        if not anchors:
            # A module that is not on this board, or a control the current
            # layout folded away. Skipping beats pointing at nothing.
            QTimer.singleShot(0, self._skip)
            return
        if reveal_in_scroll_area(anchors[0]):
            # The view moved, so every coordinate taken before it is stale.
            # Measure again once the scroll has been laid out.
            QTimer.singleShot(RESETTLE_MS, self._settle)
            return
        self._place_on(anchors)

    def _anchor(self) -> list[QWidget]:
        """The widgets this stop points at; empty when none is on screen."""
        stop = self._stops[self._index]
        try:
            found = stop.anchor(self._window)
        except Exception:
            logger.debug("A tour stop could not find its anchor", exc_info=True)
            return []
        candidates = list(found) if isinstance(found, (list, tuple)) else [found]
        return [
            widget for widget in candidates
            if widget is not None and widget.isVisible() and widget.width() > 0
        ]

    def _anchor_rect(self, anchors: list[QWidget]) -> QRect:
        """Where the anchors are in the window, clipped to what can be seen.

        Clipped for two reasons. A control taller than its scroll area would
        otherwise open a hole running off the bottom of the window, and one
        scrolled halfway out of its viewport would have a hole covering the
        page above it — in both cases highlighting space the control does not
        actually occupy.
        """
        total = QRect()
        for anchor in anchors:
            rect = QRect(anchor.mapTo(self._window, QPoint(0, 0)), anchor.size())
            visible = self._window.rect()
            node = anchor.parentWidget()
            while node is not None and node is not self._window:
                if isinstance(node, QAbstractScrollArea):
                    viewport = node.viewport()
                    if viewport is not None:
                        band = QRect(
                            viewport.mapTo(self._window, QPoint(0, 0)), viewport.size()
                        )
                        visible = visible.intersected(band)
                node = node.parentWidget()
            clipped = rect.intersected(visible)
            if not clipped.isEmpty():
                total = clipped if total.isNull() else total.united(clipped)
        return total

    def _place_on(self, anchors: list[QWidget]) -> None:
        rect = self._anchor_rect(anchors)
        if rect.isEmpty():
            QTimer.singleShot(0, self._skip)
            return
        self._placed_at = QRect(rect)
        self.spotlight.setGeometry(self._window.rect())
        self.spotlight.show()
        self.spotlight.raise_()
        self.spotlight.move_to(rect)
        # target(), not hole(): the hole is still travelling from the last
        # anchor and would place this bubble beside the previous control.
        self.callout.point_at(self.spotlight.target())
        self.callout.raise_()

    def _follow_anchor(self) -> None:
        """Re-place the spotlight and the bubble when the anchor has moved."""
        if not self._running or not (0 <= self._index < len(self._stops)):
            return
        anchors = self._anchor()
        if not anchors:
            return
        rect = self._anchor_rect(anchors)
        if rect.isEmpty() or rect == self._placed_at:
            return
        self._place_on(anchors)
