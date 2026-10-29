"""Blocks to terminal rows: pure text layout, no curses."""

from __future__ import annotations

from dataclasses import dataclass, field

from .content import (
    Block,
    Choice,
    Field,
    Gap,
    Grid,
    Heading,
    Meter,
    Note,
    Raw,
    Trend,
    cell_width,
    clip,
    pad,
    wrap,
)

LABEL_MAX = 20


@dataclass(slots=True)
class Glyphs:
    """Characters the terminal can draw. The Linux console has a small font."""

    full: str = "█"
    empty: str = "░"
    spark: str = "▁▂▃▄▅▆▇█"
    cursor: str = "›"
    rule: str = "─"
    bullet: str = "•"

    @classmethod
    def for_terminal(cls, *, unicode_ok: bool) -> "Glyphs":
        if unicode_ok:
            return cls()
        return cls(full="#", empty="-", spark="._:-=+*#", cursor=">", rule="-", bullet="*")


@dataclass(slots=True)
class Row:
    spans: list[tuple[str, str]]  # (text, tone); tone "" is the default colour
    choice: int | None = None  # index among the page's selectable rows
    bold: bool = False


@dataclass(slots=True)
class Layout:
    rows: list[Row] = field(default_factory=list)
    choices: list[Choice] = field(default_factory=list)
    choice_rows: list[int] = field(default_factory=list)  # row index of each choice


def sparkline(values, width: int, glyphs: Glyphs) -> str:
    if width <= 0:
        return ""
    series = list(values)[-width:]
    if not series:
        return ""
    low, high = min(series), max(series)
    span = (high - low) or 1.0
    top = len(glyphs.spark) - 1
    body = "".join(glyphs.spark[round((value - low) / span * top)] for value in series)
    return body.rjust(width) if len(series) < width else body


def bar(fraction: float | None, width: int, glyphs: Glyphs) -> str:
    if fraction is None:
        return "·" * 0 + glyphs.empty * width if width > 0 else ""
    filled = max(0, min(width, round(fraction * width)))
    return glyphs.full * filled + glyphs.empty * (width - filled)


def build_layout(blocks: list[Block], width: int, glyphs: Glyphs) -> Layout:
    layout = Layout()
    width = max(20, width)
    label_width = min(
        LABEL_MAX,
        max([cell_width(b.label) for b in blocks if isinstance(b, (Field, Meter, Trend, Choice))] + [8]),
    )

    def add(spans, choice=None, bold=False):
        layout.rows.append(Row(spans, choice, bold))

    for block in blocks:
        if isinstance(block, Heading):
            add([(block.text.upper(), "accent")], bold=True)
            add([(glyphs.rule * min(width, max(8, cell_width(block.text))), "dim")])
        elif isinstance(block, Gap):
            add([("", "")])
        elif isinstance(block, Field):
            value_width = width - label_width - 2
            lines = wrap(block.value, value_width) or [""]
            for index, line in enumerate(lines):
                label = pad(block.label, label_width) if index == 0 else " " * label_width
                add([(label, "dim"), ("  ", ""), (line, block.tone)])
        elif isinstance(block, Meter):
            text = block.text
            text_width = cell_width(text)
            bar_width = max(6, min(40, width - label_width - text_width - 6))
            add([(pad(block.label, label_width), "dim"), ("  ", ""),
                 (bar(block.fraction, bar_width, glyphs), block.tone if block.fraction is not None else "dim"),
                 ("  ", ""), (text, "")])
        elif isinstance(block, Trend):
            text_width = cell_width(block.text)
            spark_width = max(6, min(60, width - label_width - text_width - 6))
            add([(pad(block.label, label_width), "dim"), ("  ", ""),
                 (sparkline(block.values, spark_width, glyphs).ljust(spark_width), block.tone),
                 ("  ", ""), (block.text, "")])
        elif isinstance(block, Note):
            for line in wrap(block.text, width):
                add([(line, block.tone)])
        elif isinstance(block, Raw):
            for line in block.lines:
                add([(clip(str(line), width), block.tone)])
        elif isinstance(block, Grid):
            widths = [cell_width(str(h)) for h in block.headers]
            for row in block.rows:
                for index, cell in enumerate(row):
                    widths[index] = max(widths[index], cell_width(str(cell)))
            add([("  ".join(pad(str(h), widths[i]) for i, h in enumerate(block.headers)), "dim")], bold=True)
            for row in block.rows:
                add([("  ".join(pad(str(c), widths[i]) for i, c in enumerate(row)), "")])
        elif isinstance(block, Choice):
            index = len(layout.choices)
            layout.choices.append(block)
            layout.choice_rows.append(len(layout.rows))
            detail = block.detail
            room = width - 3
            label = clip(block.label, max(8, room - cell_width(detail) - 2)) if detail else clip(block.label, room)
            fill = " " * max(1, room - cell_width(label) - cell_width(detail)) if detail else ""
            tone = block.tone if block.enabled else "dim"
            add([(label, tone), (fill, ""), (detail, "dim")], choice=index)
    return layout
