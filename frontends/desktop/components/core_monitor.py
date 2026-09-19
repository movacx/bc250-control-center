"""The eight physical core positions, read left to right.

Built for the CPU workspace and then wanted verbatim on the dashboard, so it
lives here rather than in either page: which core, how fast, how busy, with
the two a stock firmware leaves switched off still on screen saying so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

from ..i18n import tr
from ..theme import COLORS

#: Every BC-250 has eight physical core positions. A stock firmware exposes
#: six of them to Linux, and the other two are the point of the unlock.
CORE_COUNT = 8


@dataclass(frozen=True)
class CoreReading:
    index: int
    frequency_mhz: float = 0.0
    usage_percent: float = 0.0
    threads: str = ""
    online: bool = False


def _frequency_text(value: float) -> str:
    """Per-core clocks read better in GHz, the way the dashboard shows them."""
    return "--" if value <= 0 else f"{value / 1000:.2f} GHz"


class UsageBar(QWidget):
    """A slim rounded track with the core's utilisation filled in."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._ratio = 0.0
        self._active = False
        self.setFixedHeight(4)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_usage(self, percent: float, *, active: bool) -> None:
        ratio = max(0.0, min(1.0, float(percent) / 100.0))
        if (ratio, active) == (self._ratio, self._active):
            return
        self._ratio, self._active = ratio, active
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        # Ended explicitly rather than left to garbage collection: these rows
        # sit inside a card that carries a drop-shadow effect, which renders
        # the subtree into a pixmap, and a painter still open on the widget
        # when that happens takes the process down.
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            radius = self.height() / 2
            track = QPainterPath()
            track.addRoundedRect(QRectF(self.rect()), radius, radius)
            painter.fillPath(track, QColor(COLORS["neutral_soft"]))
            if not self._active or self._ratio <= 0:
                return
            width = max(float(self.height()), self.width() * self._ratio)
            fill = QPainterPath()
            fill.addRoundedRect(
                QRectF(0.0, 0.0, width, float(self.height())), radius, radius
            )
            painter.fillPath(fill, QColor(COLORS["blue"]))
        finally:
            painter.end()


class CoreRow(QFrame):
    """One physical core, read left to right: which, how fast, how busy.

    A row rather than a card. Eight identical boxes made the eye compare
    boxes; a column of aligned rows makes it compare numbers, which is what
    the reading is for.
    """

    NAME_WIDTH = 26
    CLOCK_WIDTH = 74
    LOAD_WIDTH = 40

    def __init__(self, index: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._first = False
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(10)

        self.name = QLabel(f"N{index + 1}")
        self.name.setFixedWidth(self.NAME_WIDTH)
        row.addWidget(self.name, 0)

        self.frequency = QLabel("--")
        self.frequency.setFixedWidth(self.CLOCK_WIDTH)
        row.addWidget(self.frequency, 0)

        self.bar = UsageBar()
        row.addWidget(self.bar, 1)

        self.usage = QLabel("")
        self.usage.setFixedWidth(self.LOAD_WIDTH)
        self.usage.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self.usage, 0)
        self.set_offline()

    #: Below this the bar is a stub; the row still reads without it.
    BAR_FLOOR = 210

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        wanted = event.size().width() >= self.BAR_FLOOR
        if self.bar.isHidden() == wanted:
            self.bar.setVisible(wanted)

    def set_first(self, first: bool) -> None:
        if first == self._first:
            return
        self._first = first
        self._refresh_border()

    def _refresh_border(self) -> None:
        border = (
            "border:none;" if self._first
            else f"border:none; border-top:1px solid {COLORS['border_soft']};"
        )
        self.setStyleSheet(f"QFrame {{ background:transparent; {border} }}")

    def set_reading(self, reading: CoreReading) -> None:
        self.name.setStyleSheet(
            f"color:{COLORS['muted']}; font-size:11px; font-weight:800;"
            " background:transparent; border:none;"
        )
        self.frequency.setText(_frequency_text(reading.frequency_mhz))
        self.frequency.setStyleSheet(
            f"color:{COLORS['text']}; font-size:12px; font-weight:750;"
            " background:transparent; border:none;"
        )
        self.usage.setText(f"{reading.usage_percent:.0f} %")
        self.usage.setStyleSheet(
            f"color:{COLORS['muted']}; font-size:11px; font-weight:700;"
            " background:transparent; border:none;"
        )
        self.bar.set_usage(reading.usage_percent, active=True)
        # Composed rather than formatted through a catalogue key: the label
        # is translated, the thread numbers are not text to translate.
        self.setToolTip(
            f"{tr('logical threads')}: {reading.threads}" if reading.threads else ""
        )
        self._refresh_border()

    def set_offline(self) -> None:
        for label in (self.name, self.frequency, self.usage):
            label.setStyleSheet(
                f"color:{COLORS['disabled_text']}; font-size:11px; font-weight:700;"
                " background:transparent; border:none;"
            )
        self.frequency.setText(tr("Hidden"))
        self.usage.setText("")
        self.bar.set_usage(0, active=False)
        self.setToolTip("")
        self._refresh_border()


class CoreGrid(QWidget):
    """The eight physical core positions, in one or two columns of rows."""

    # Two columns wherever they fit: the dashboard's processor panel is half
    # the width of the CPU workspace, and eight rows in one column made that
    # panel twice the height of its neighbours.
    MINIMUM_COLUMN = 165

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(18)
        self._grid.setVerticalSpacing(0)
        self.rows = [CoreRow(index) for index in range(CORE_COUNT)]
        self._apply_columns(2)

    def set_readings(self, readings: Sequence[CoreReading]) -> None:
        """Fill the measured positions; every position past them reads hidden.

        A stock board exposes six of eight cores, and the two it does not are
        the entire point of the unlock below — so they stay on screen saying
        what they are instead of being omitted.
        """
        online = sorted(
            (reading for reading in readings if reading.online),
            key=lambda reading: reading.index,
        )
        for position, row in enumerate(self.rows):
            if position < len(online):
                row.set_reading(online[position])
            else:
                row.set_offline()

    def _apply_columns(self, columns: int) -> None:
        columns = 2 if columns >= 2 else 1
        if columns == self._columns:
            return
        self._columns = columns
        for row in self.rows:
            self._grid.removeWidget(row)
        per_column = (CORE_COUNT + columns - 1) // columns
        for index, row in enumerate(self.rows):
            column, line = divmod(index, per_column)
            self._grid.addWidget(row, line, column)
            # Only the top row of each column carries no hairline above it.
            row.set_first(line == 0)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1 if columns == 2 else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        spacing = self._grid.horizontalSpacing()
        self._apply_columns((self.width() + spacing) // (self.MINIMUM_COLUMN + spacing))
