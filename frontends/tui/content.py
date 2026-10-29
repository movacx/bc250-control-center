"""What a page shows, independent of how it is drawn.

A page builds a list of blocks; ``screen`` lays them out and paints them with
curses. Keeping the two apart lets every page be tested without a terminal.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# Tones ("", ok, warn, bad, dim, accent) map to terminal palette colours, so a
# light or dark terminal keeps its own contrast: no background is ever painted.


def cell_width(text: str) -> int:
    """Columns ``text`` takes on a terminal (wide glyphs 2, marks 0)."""
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in "WF" else 1
    return width


def clip(text: str, width: int) -> str:
    """``text`` cut to ``width`` columns, with an ellipsis when it was cut."""
    if width <= 0:
        return ""
    if cell_width(text) <= width:
        return text
    out, used = [], 0
    for char in text:
        step = 0 if unicodedata.combining(char) else (2 if unicodedata.east_asian_width(char) in "WF" else 1)
        if used + step > width - 1:
            break
        out.append(char)
        used += step
    return "".join(out) + "…"


def pad(text: str, width: int) -> str:
    text = clip(text, width)
    return text + " " * max(0, width - cell_width(text))


def wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap that counts terminal columns, not characters."""
    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        current, used = [], 0
        for word in paragraph.split(" "):
            size = cell_width(word)
            if current and used + 1 + size > width:
                lines.append(" ".join(current))
                current, used = [], 0
            while size > width > 0:  # a word longer than the line
                piece = clip(word, width + 1)[:-1] or word[:1]
                lines.append(piece)
                word = word[len(piece):]
                size = cell_width(word)
            used = used + 1 + size if current else size
            current.append(word)
        lines.append(" ".join(current))
    return lines


@dataclass(slots=True)
class Heading:
    text: str


@dataclass(slots=True)
class Field:
    label: str
    value: str
    tone: str = ""


@dataclass(slots=True)
class Meter:
    """A labelled bar. ``fraction`` None means the reading is unavailable."""

    label: str
    fraction: float | None
    text: str = ""
    tone: str = ""


@dataclass(slots=True)
class Trend:
    label: str
    values: Sequence[float]
    text: str = ""
    tone: str = "accent"


@dataclass(slots=True)
class Note:
    text: str
    tone: str = ""


@dataclass(slots=True)
class Grid:
    """A small table. Column widths follow the content, last column flexes."""

    headers: Sequence[str]
    rows: Sequence[Sequence[str]]
    gap: int = 2


@dataclass(slots=True)
class Raw:
    """Pre-formatted text (a backend's own table), shown without wrapping."""

    lines: Sequence[str]
    tone: str = ""


@dataclass(slots=True)
class Gap:
    pass


@dataclass(slots=True)
class Card:
    """One titled column of a ``Columns`` block (read-only blocks only)."""

    title: str
    blocks: Sequence["Block"]
    value: str = ""  # the card's headline reading, right-aligned on its title


@dataclass(slots=True)
class Columns:
    """Cards side by side when the width allows, stacked when it does not."""

    cards: Sequence[Card]
    minimum: int = 36


@dataclass(slots=True)
class Track:
    """A range drawn over its scale: ``500 |----[===]----| 2400``."""

    label: str
    low: float
    high: float
    start: float
    end: float
    text: str = ""
    tone: str = "accent"


@dataclass(slots=True)
class PadCell:
    text: str
    tone: str = ""


@dataclass(slots=True)
class PadRow:
    name: str
    cells: Sequence[PadCell]
    tail: str = ""
    tail_tone: str = ""


@dataclass(slots=True)
class Pad:
    """A grid of cells moved with the arrows and toggled with Enter/Space.

    The grid is one selectable item: the arrows move inside it until they run
    out of cells, and only then leave it for the next item.
    """

    headers: Sequence[str]
    rows: Sequence[PadRow]
    cursor: tuple[int, int]
    move: Callable[[int, int], bool]
    toggle: Callable[[object], None]
    tail_header: str = ""


@dataclass(slots=True)
class Chart:
    """The last ``window`` seconds of one or more series, placed by their sample times.

    Lines are drawn in braille (2x4 dots a cell) with the axis on the right
    and time underneath; ``heatmap`` draws one shaded row per series instead.
    """

    series: Sequence[tuple[str, Sequence[float], str]]  # (name, values, tone), aligned to the end of ``times``
    times: Sequence[float]
    low: float
    high: float
    height: int = 10
    show: Callable[[float], str] = str
    average: float | None = None
    heatmap: bool = False
    window: float = 120.0
    ticks: Sequence[float] = ()  # round values to label and rule across the plot
    now: str = "Now"


@dataclass(slots=True)
class Choice:
    """A selectable row. Enter runs ``handler``; left/right call ``adjust``."""

    label: str
    handler: Callable[[object], None] | None = None
    detail: str = ""
    tone: str = ""
    enabled: bool = True
    adjust: Callable[[object, int], None] | None = None
    pad: "Pad | None" = None


Block = Heading | Field | Meter | Trend | Note | Grid | Raw | Gap | Choice | Card | Columns | Track | Pad | Chart


def percent(value: object, default: float | None = None) -> float | None:
    try:
        return max(0.0, min(1.0, float(value) / 100.0))
    except (TypeError, ValueError):
        return default


def number(value: object, unit: str = "", digits: int = 0, missing: str = "--") -> str:
    try:
        shown = f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return missing
    return f"{shown} {unit}".rstrip()


def size(value: object, missing: str = "--") -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return missing
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(amount) < 1024 or unit == "TiB":
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return missing


def heat_tone(celsius: object, warm: float = 75.0, hot: float = 90.0) -> str:
    try:
        value = float(celsius)
    except (TypeError, ValueError):
        return "dim"
    return "bad" if value >= hot else "warn" if value >= warm else "ok"


def load_tone(percent_value: object) -> str:
    try:
        value = float(percent_value)
    except (TypeError, ValueError):
        return "dim"
    return "bad" if value >= 95 else "warn" if value >= 80 else "ok"
