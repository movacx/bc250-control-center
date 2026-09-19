"""The dashboard's instrument vocabulary.

The screen this replaces had grown three shapes for the same job: a graphics
card five times the size of every other panel, holding sensors that belonged
to the processor and to the drive; wide rows where the number ended up an
inch from its own name; and strips whose meaning changed with the board.

What is here instead is the shape a control panel actually uses:

* a **header** that answers "what is this machine" in one line,
* an **instrument panel** per physical domain, all built the same way: the
  domain's headline number, a rule in the domain's accent, and its readings
  in named groups,
* a **reading** as one short row — name left, number right, unit after it —
  so a column of them is read by running down the numbers.

Rows, not cells: the eye compares a column of right-aligned figures far
faster than a grid of boxes, and a row costs 25 px where a box cost 59.
Nothing here knows where its numbers come from; the page hands them over.
"""

from __future__ import annotations

from typing import Iterable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import theme as theme_module
from ..i18n import tr
from .buttons import WrappingButton as QPushButton
from .core_monitor import CoreGrid
from .widgets import ICON_DIR, PillLabel, apply_shadow, icon

#: Width reserved for the unit, so every number in a column ends on the same
#: pixel whether or not its own unit is short.
UNIT_WIDTH = 30


class HeadingLabel(QLabel):
    """A label that stays upper case however its text is set.

    Qt style sheets have no ``text-transform``, and upper-casing once at
    construction breaks live language switching: the runtime localizer looks
    the stored source string up again and writes the translation back in
    normal case. Doing it here means every path — construction, retranslation,
    a runtime value — comes out as a heading.
    """

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API name
        super().setText(str(text).upper())


def _heading(value: str, role: str) -> HeadingLabel:
    label = HeadingLabel()
    # The localizer translates from ``source_text`` when a widget offers one,
    # which is what keeps an upper-cased heading switchable: the stored source
    # stays the catalogue key rather than the shouted text on screen.
    label.source_text = value
    # setText, not the constructor: only the override upper-cases.
    label.setText(tr(value))
    label.setProperty(role, True)
    label.setMinimumWidth(0)
    return label


def _text(value: str, role: str, *, wrap: bool = False) -> QLabel:
    label = QLabel(tr(value))
    label.setProperty(role, True)
    label.setWordWrap(wrap)
    label.setMinimumWidth(0)
    return label


def _rule(role: str = "instrumentHairline") -> QFrame:
    line = QFrame()
    line.setProperty(role, True)
    line.setFixedHeight(2 if role == "instrumentAccent" else 1)
    return line


class Reading(QFrame):
    """One measurement: name on the left, number and unit on the right."""

    #: Suffixes worth setting in small type after the number rather than
    #: inside it, so a column of readings lines up on its digits.
    UNITS = ("°C", "MHz", "GHz", "RPM", "mV", "W", "V", "A", "%")

    #: Characters a value may take before it is shortened. Chosen so the
    #: longest real reading on this board — a governor backend name — stops
    #: dictating how wide its column has to be.
    LONGEST_VALUE = 20

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("reading", True)
        self.setMinimumWidth(0)
        # Minimum, not Fixed: a label that had to wrap must be allowed to make
        # its row taller instead of being cut off inside it.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(8)

        # Wraps rather than clips: on a phone-width window the label has to
        # give way to the number, not disappear behind it.
        self.label = _text(label, "readingLabel", wrap=True)
        row.addWidget(self.label, 1)

        values = QVBoxLayout()
        values.setContentsMargins(0, 0, 0, 0)
        values.setSpacing(0)
        # The number never wraps: a governor name broken over three lines is
        # unreadable. The label beside it gives way instead.
        self.value = _text("--", "readingValue")
        self.value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.detail = _text("", "readingDetail")
        self.detail.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.detail.setVisible(False)
        values.addWidget(self.value)
        values.addWidget(self.detail)
        row.addLayout(values, 0)

        self.unit = _text("", "readingUnit")
        self.unit.setFixedWidth(UNIT_WIDTH)
        self.unit.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self.unit, 0)

    def set_value(self, text: str, detail: str = "") -> None:
        """Show a formatted reading, lifting its unit out of the number."""
        value = str(text).strip()
        unit = ""
        for candidate in self.UNITS:
            if value.endswith(candidate) and len(value) > len(candidate):
                value, unit = value[: -len(candidate)].strip(), candidate
                break
        else:
            # Units are translated too — "3850 MHz" is "3850 МГц" in Russian —
            # so the English list is only the fast path. A trailing word with
            # no digits, after a part that has them, is the unit whatever the
            # language: "No detected" keeps its word, "40 / 40" keeps both.
            head, separator, tail = value.rpartition(" ")
            if (
                separator
                and tail
                and not any(character.isdigit() for character in tail)
                and any(character.isdigit() for character in head)
            ):
                value, unit = head, tail
        # A long identifier would otherwise widen its column and squeeze the
        # one beside it; the whole string stays one hover away.
        shown = tr(value)
        if len(shown) > self.LONGEST_VALUE:
            self.value.setToolTip(shown)
            shown = shown[: self.LONGEST_VALUE - 1].rstrip("-· ") + "…"
        else:
            self.value.setToolTip("")
        self.value.setText(shown)
        self.unit.setText(unit)
        # An empty unit gives its column back instead of reserving it, which
        # matters on a panel only three hundred pixels wide.
        self.unit.setFixedWidth(UNIT_WIDTH if unit else 0)
        self.detail.setText(tr(detail))
        self.detail.setVisible(bool(detail))

    def set_label(self, label: str) -> None:
        self.label.setText(tr(label))

    def set_tone(self, tone: str) -> None:
        if self.property("tone") == tone:
            return
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


class ReadingGroup(QWidget):
    """A named run of readings, separated by hairlines."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 9, 0, 0)
        box.setSpacing(0)
        self.title = _heading(title, "groupTitle")
        box.addWidget(self.title)
        box.addSpacing(4)
        self._box = box
        self.readings: dict[str, Reading] = {}

    def add(self, key: str, label: str) -> Reading:
        if self.readings:
            self._box.addWidget(_rule())
        reading = Reading(label)
        self.readings[key] = reading
        self._box.addWidget(reading)
        return reading


class ReadingBook(QWidget):
    """Groups of readings, laid out in one or two columns."""

    def __init__(self, columns: int = 1, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(22)
        self._wanted_columns = max(1, columns)
        self._columns = []
        for _ in range(self._wanted_columns):
            column = QVBoxLayout()
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(0)
            row.addLayout(column, 1)
            self._columns.append(column)
        for column in self._columns:
            column.addStretch(1)
        self.groups: dict[str, ReadingGroup] = {}
        self.readings: dict[str, Reading] = {}
        self._placement: list[tuple[ReadingGroup, int]] = []
        self._packed = self._wanted_columns

    def group(self, title: str, column: int = 0) -> ReadingGroup:
        group = self.groups.get(title)
        if group is None:
            group = ReadingGroup(title)
            self.groups[title] = group
            self._placement.append((group, column))
            self._packed = 0
            self._repack(self.width() or 460)
        return group

    def _repack(self, width: int) -> None:
        """Two columns of readings need room; below it they become one."""
        # 360 px is the narrowest a pair of reading columns stays readable:
        # a label wrapping to two lines beats a panel twice as tall.
        columns = self._wanted_columns if width >= 360 else 1
        if columns == self._packed:
            return
        self._packed = columns
        for group, _preferred in self._placement:
            for column in self._columns:
                column.removeWidget(group)
        for group, preferred in self._placement:
            target = self._columns[min(preferred, columns - 1)]
            target.insertWidget(target.count() - 1, group)
        for index, column in enumerate(self._columns):
            column.setEnabled(True)
            for position in range(column.count()):
                item = column.itemAt(position).widget()
                if item is not None:
                    item.setVisible(True)
            if index >= columns:
                column.setContentsMargins(0, 0, 0, 0)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._repack(event.size().width())

    def add(self, key: str, label: str, *, group: str, column: int = 0) -> Reading:
        reading = self.group(group, column).add(key, label)
        self.readings[key] = reading
        return reading

    def __getitem__(self, key: str) -> Reading:
        return self.readings[key]


class Headline(QWidget):
    """The number a domain is judged by, beside its name.

    Never a sentence: at this size "Not detected" is wider than the panel, so
    an absent reading is a dash and the explanation lives in the status pill.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addStretch(1)
        self.value = _text("--", "headlineValue")
        self.unit = _text("", "headlineUnit")
        row.addWidget(self.value)
        row.addWidget(self.unit, 0, Qt.AlignmentFlag.AlignBottom)
        self.items: dict[str, tuple[QLabel, QLabel, QLabel]] = {}

    def add(self, key: str, label: str, unit: str) -> None:
        """The first reading added is the headline; the rest are its record."""
        if not self.items:
            self.unit.setText(tr(unit))
        self.items[key] = (self.value, self.unit, self.value)

    def seal(self) -> None:
        """Kept for callers that used to close a horizontal row."""

    def set_value(self, key: str, text: str) -> None:
        if key in self.items and self.items[key][0] is self.value:
            self.value.setText(tr(text))


class InstrumentPanel(QFrame):
    """One physical domain, reported the way its neighbours are."""

    activated = pyqtSignal(str)
    action_requested = pyqtSignal(str)

    def __init__(
        self,
        key: str,
        title: str,
        *,
        columns: int = 1,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.key = key
        self.setProperty("instrumentPanel", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        apply_shadow(self, blur=18, y=3, alpha=13)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 15, 18, 15)
        root.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(10)
        self.heading_icon = _heading(title, "instrumentTitle")
        head.addWidget(self.heading_icon, 1)
        # No pill here. "actual", "en ejecución", "PWM listo" said nothing the
        # readings below do not already say, and three of them across the row
        # competed with the numbers they sat beside. The one state worth a
        # badge — whether the whole board is fine — lives in the header.
        self.status = PillLabel("Not detected", "gray")
        self.status.hide()
        self.headline = Headline()
        head.addWidget(self.headline, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(head)
        root.addSpacing(7)

        self.accent = _rule("instrumentAccent")
        root.addWidget(self.accent)

        self.details = ReadingBook(columns)
        root.addWidget(self.details)

        #: Where a domain puts a block of its own — the per-core grid, say.
        self.extras = QVBoxLayout()
        self.extras.setContentsMargins(0, 0, 0, 0)
        self.extras.setSpacing(0)
        root.addLayout(self.extras)
        root.addSpacing(13)

        self.actions = QHBoxLayout()
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(8)
        root.addLayout(self.actions)
        self.action_buttons: list[QPushButton] = []

    def add_action(
        self, text: str, *, action: str = "", module: str = ""
    ) -> QPushButton:
        """A button that opens a module, or asks for a named action."""
        button = QPushButton(tr(text))
        button.setProperty("dashboardCardAction", True)
        button.setMinimumWidth(0)
        if not self.action_buttons:
            # The first action is what this panel is for, so it wears the
            # accent — the one from the user's appearance settings, not a
            # colour invented per panel.
            button.setProperty("accented", True)
        if action:
            button.clicked.connect(lambda: self.action_requested.emit(action))
        else:
            target = module or self.key
            button.clicked.connect(lambda: self.activated.emit(target))
        self.actions.addWidget(button, 1)
        self.action_buttons.append(button)
        return button

    def set_status(self, text: str, tone: str) -> None:
        self.status.setText(tr(text))
        self.status.set_tone(tone)


class InstrumentBand(QFrame):
    """A subsystem that is not a domain of its own: memory, power delivery."""

    def __init__(
        self,
        title: str,
        *,
        columns: int = 4,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("instrumentPanel", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 15)
        root.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(_heading(title, "instrumentTitle"), 1)
        self.note = _text("", "bandNote", wrap=True)
        head.addWidget(self.note, 0, Qt.AlignmentFlag.AlignVCenter)
        self.head = head
        root.addLayout(head)
        # No accent rule across a band this wide: a two-pixel coloured line
        # running the width of the window pulls the eye away from the
        # readings under it. The memory band never had one either, and the
        # two sit one above the other.
        root.addSpacing(9)

        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(24)
        self.grid.setVerticalSpacing(0)
        root.addLayout(self.grid)
        self.readings: dict[str, Reading] = {}
        self._order: list[str] = []
        self._wanted_columns = max(1, columns)
        self._columns = 0

    def add(self, key: str, label: str) -> Reading:
        reading = Reading(label)
        # A rule above every cell, broken by the gap between columns — the
        # same grid the memory devices are read in, one band above this one.
        reading.setProperty("banded", True)
        reading.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        reading.layout().setContentsMargins(0, 7, 0, 6)
        self.readings[key] = reading
        self._order.append(key)
        self._columns = 0
        self._reflow(self.width() or 1200)
        return reading

    def __getitem__(self, key: str) -> Reading:
        return self.readings[key]

    def set_note(self, text: str) -> None:
        self.note.setText(tr(text))
        self.note.setVisible(bool(text))

    def _reflow(self, width: int) -> None:
        if not self._order:
            return
        columns = self._wanted_columns if width >= 900 else 2 if width >= 460 else 1
        columns = max(1, min(columns, len(self._order)))
        if columns == self._columns:
            return
        self._columns = columns
        for reading in self.readings.values():
            self.grid.removeWidget(reading)
        rows = -(-len(self._order) // columns)
        for index, key in enumerate(self._order):
            row, column = index % rows, index // rows
            self.grid.addWidget(self.readings[key], row, column)
        for column in range(max(columns, self.grid.columnCount())):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._reflow(event.size().width())


class CoreMonitor(QWidget):
    """The processor's cores, in the shape the CPU workspace already uses.

    One widget for both screens: the same eight positions, the same bar, the
    same wording for the two a stock firmware leaves off.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 9, 0, 0)
        box.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        self.title = _heading("Live core monitor", "groupTitle")
        head.addWidget(self.title, 1)
        self.shape = _text("--", "readingValue")
        head.addWidget(self.shape, 0, Qt.AlignmentFlag.AlignRight)
        box.addLayout(head)
        box.addSpacing(4)
        self.grid = CoreGrid()
        box.addWidget(self.grid)

    def set_shape(self, text: str) -> None:
        self.shape.setText(tr(text))

    def set_readings(self, readings) -> None:
        self.grid.set_readings(readings)


class BoardHeader(QFrame):
    """What this machine is, before anything about what it is doing."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("boardHeader", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._row = QHBoxLayout(self)
        row = self._row
        row.setContentsMargins(20, 15, 20, 15)
        row.setSpacing(14)

        # The board itself rather than its initials: the icon set ships a
        # flat silhouette of a BC-250, which says what this screen is about
        # without a caption.
        self.mark = QLabel()
        self.mark.setProperty("boardMark", True)
        self.mark.setFixedSize(42, 42)
        self.mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh_palette()
        row.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(3)
        self.name = _text("AMD BC-250", "boardName")
        self.spec = _text("", "boardSpec", wrap=True)
        text.addWidget(self.name)
        text.addWidget(self.spec)
        row.addLayout(text, 1)

        # No badges here either. The hottest reading is already a reading,
        # and it is coloured where it lives; a second copy in the header was
        # one more number to reconcile.
        self.hotspot = PillLabel("Not detected", "gray")
        self.status = PillLabel("Not detected", "gray")
        for pill in (self.hotspot, self.status):
            pill.hide()

    def _refresh_palette(self) -> None:
        """Pick the silhouette that is legible against the current theme.

        The SVG is drawn in a pale grey for dark panels; on a light one it
        nearly disappears. Light mode gets the dark-on-light raster instead,
        which brings its own rounded tile, so the label's own tile steps out
        of the way rather than framing a second one.
        """
        if theme_module.ACTIVE_MODE == "dark":
            self.mark.setStyleSheet("")
            self.mark.setPixmap(icon("bc250_board").pixmap(30, 30))
            return
        self.mark.setStyleSheet("background: transparent; border: none;")
        self.mark.setPixmap(
            QPixmap(str(ICON_DIR / "bc250_board_light.png")).scaled(
                42, 42,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def set_specification(self, parts: Iterable[str]) -> None:
        self.spec.setText(" · ".join(part for part in parts if part))

    def set_status(self, text: str, tone: str) -> None:
        self.status.setText(tr(text))
        self.status.set_tone(tone)

    def set_hotspot(self, text: str, tone: str) -> None:
        self.hotspot.setText(tr(text))
        self.hotspot.set_tone(tone)
