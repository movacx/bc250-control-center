"""Frosted glass over the application, drawn rather than composited.

The welcome screen has to hide the application without replacing it: a first
run that opens onto a blank modal says nothing about the thing being set up,
and one that leaves the shell legible behind a plain scrim invites the user to
try to click it. Frosted glass answers both — the colours, the shape and the
density of the real interface stay visible, and not one word of it is legible.

Qt has no ``backdrop-filter``. What it does have is ``QGraphicsBlurEffect``,
which can be applied to a snapshot of the window and painted underneath the
card. The snapshot is taken once per appearance rather than per frame, because
nothing behind the glass moves while the glass is up.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QWidget,
)

#: Blur radius, in the coordinates of the half-size working copy. Twelve there
#: is twenty-four on screen, which is the upper half of the 10–20 px the style
#: asks for and the point where 15 px type stops resolving into words.
BLUR_RADIUS = 14.0
#: The snapshot is blurred at half resolution. A blur is a low-pass filter, so
#: the detail thrown away by the downscale is detail the blur would have
#: removed anyway — and it costs a quarter of the pixels (measured: 4 ms for a
#: 1200×700 window rather than 34).
WORKING_SCALE = 2


def frosted(source: QPixmap, *, radius: float = BLUR_RADIUS) -> QPixmap:
    """Blur ``source`` into a new pixmap of the same size.

    Returns the source untouched when it is too small to halve, which happens
    in tests and during the first layout pass, before the window has a size.
    """
    if source.isNull() or source.width() < 4 or source.height() < 4:
        return source

    working = source.scaled(
        max(1, source.width() // WORKING_SCALE),
        max(1, source.height() // WORKING_SCALE),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(working)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(float(radius))
    # Quality over speed: the alternative setting is visibly banded, and this
    # runs once per appearance rather than once per frame.
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene.addItem(item)

    blurred = QPixmap(working.size())
    blurred.fill(QColor(0, 0, 0, 0))
    painter = QPainter(blurred)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    scene.render(painter, QRectF(blurred.rect()), QRectF(working.rect()))
    painter.end()
    # The item still owns the effect; dropping the scene first would delete the
    # effect out from under it.
    scene.removeItem(item)

    return blurred.scaled(
        source.size(),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def frosted_snapshot(widget: QWidget) -> QPixmap:
    """Grab ``widget`` as it stands and return it frosted.

    The grab happens on whatever the widget currently shows, so callers take it
    *before* they disable or cover anything: a snapshot of a greyed-out shell
    would be a snapshot of a state the user never saw.
    """
    if widget is None or widget.width() <= 0 or widget.height() <= 0:
        return QPixmap()
    return frosted(widget.grab())
