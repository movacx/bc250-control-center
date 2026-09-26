"""Fast strokes for time-series charts.

QPainter strokes a polyline as one outline and then fills that outline. For a
line that swings across the whole plot every second, as a core's clock does,
the outline overlaps itself hundreds of times, and filling it is what cost the
time: one repaint of six per-core clock lines took over a second on the
BC-250, and the whole window froze with it. Drawn as separate flat-capped
segments, each one is a small quad; round points at the vertices put the
round joins back. The picture is the same, in about a hundredth of the time.

An area under a line is filled without antialiasing for the same reason: its
top edge is always covered by the line drawn over it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF


def draw_series(
    painter: QPainter,
    runs: Iterable[Sequence[QPointF]],
    color: QColor,
    width: float,
) -> None:
    """Stroke each run of points as one line with round joins and ends."""
    pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    vertices: list[QPointF] = []
    for run in runs:
        if not run:
            continue
        vertices.extend(run)
        if len(run) > 1:
            painter.drawLines([QLineF(start, end) for start, end in zip(run, run[1:])])
    if vertices:
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPoints(QPolygonF(vertices))


def fill_area(painter: QPainter, points: Sequence[QPointF], baseline: float, brush: QBrush | QColor) -> None:
    """Fill between ``points`` and the horizontal ``baseline`` below them."""
    if len(points) < 2:
        return
    polygon = QPolygonF([QPointF(points[0].x(), baseline), *points, QPointF(points[-1].x(), baseline)])
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(brush)
    painter.drawPolygon(polygon)
    painter.restore()
