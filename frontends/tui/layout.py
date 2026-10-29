"""Blocks to terminal rows: pure text layout, no curses."""

from __future__ import annotations

from dataclasses import dataclass, field

from .content import (
    Block,
    Choice,
    Columns,
    Field,
    Gap,
    Grid,
    Heading,
    Meter,
    Note,
    Pad,
    Raw,
    Track,
    Trend,
    cell_width,
    clip,
    pad,
    wrap,
)

LABEL_MAX = 30
BAR_MAX = 24


@dataclass(slots=True)
class Glyphs:
    """Characters the terminal can draw. The Linux console has a small font."""

    spark: str = "▁▂▃▄▅▆▇█"
    cursor: str = "›"
    rule: str = "─"
    fill: str = "━"
    #: box drawing: horizontal, vertical, then corners/tees as (left, middle, right) per row kind
    h: str = "─"
    v: str = "│"
    top: tuple = ("┌", "┬", "┐")
    mid: tuple = ("├", "┼", "┤")
    bottom: tuple = ("└", "┴", "┘")

    @classmethod
    def for_terminal(cls, *, unicode_ok: bool) -> "Glyphs":
        if unicode_ok:
            return cls()
        return cls(spark="._:-=+*#", cursor=">", rule="-", fill="=", h="-", v="|",
                   top=("+", "+", "+"), mid=("+", "+", "+"), bottom=("+", "+", "+"))


@dataclass(slots=True)
class Row:
    spans: list[tuple[str, str]]  # (text, tone); tone "" is the default colour
    choice: int | None = None  # index among the page's selectable rows
    bold: bool = False
    plain: bool = False  # a selected row is not drawn in reverse (a Pad marks its own cell)


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
    # A tenth of the value at least: 48-49 °C must not swing from floor to ceiling.
    span = max(high - low, abs(high) * 0.1) or 1.0
    top = len(glyphs.spark) - 1
    body = "".join(glyphs.spark[round((value - low) / span * top)] for value in series)
    return body.rjust(width) if len(series) < width else body


def gauge(start: float, end: float, width: int, tone: str, glyphs: Glyphs) -> list[tuple[str, str]]:
    """Cells ``start``..``end`` (fractions of ``width``) as a heavy line, the rest a dim hairline.

    A line, not a block: bars on consecutive rows (the cores) stay apart instead
    of merging into one slab, and box-drawing lines are drawn by the terminal
    itself in most emulators, so no font stretches them.
    """
    a = max(0, min(width, round(start * width)))
    b = max(a, min(width, round(end * width)))
    return [(glyphs.rule * a, "dim"), (glyphs.fill * (b - a), tone), (glyphs.rule * (width - b), "dim")]


def _join_columns(card_layouts: list[Layout], widths: list[int], gap: str) -> list[Row]:
    height = max(len(item.rows) for item in card_layouts)
    rows = []
    for line in range(height):
        spans: list[tuple[str, str]] = []
        for index, item in enumerate(card_layouts):
            if index:
                spans.append((gap, "dim"))
            if line < len(item.rows):
                used = 0
                for text, tone in item.rows[line].spans:
                    spans.append((text, tone))
                    used += cell_width(text)
                spans.append((" " * max(0, widths[index] - used), ""))
            else:
                spans.append((" " * widths[index], ""))
        rows.append(Row(spans))
    return rows


def build_layout(blocks: list[Block], width: int, glyphs: Glyphs, label_cap: int = LABEL_MAX) -> Layout:
    layout = Layout()
    width = max(20, width)
    label_width = min(
        label_cap, max(12, width // 2),
        max([cell_width(b.label) for b in blocks if isinstance(b, (Field, Meter, Trend, Track)) or (
            isinstance(b, Choice) and b.detail)] + [8]),
    )
    meter_text = max([cell_width(b.text) for b in blocks if isinstance(b, (Meter, Track))] + [0])
    bar_width = max(6, min(BAR_MAX, width - label_width - meter_text - 4))

    def add(spans, choice=None, bold=False):
        layout.rows.append(Row(spans, choice, bold))

    for block in blocks:
        if isinstance(block, Heading):  # one row: the title, then a rule to the edge
            title = clip(block.text, width - 2)
            add([(title, "accent"), (" " + glyphs.rule * (width - cell_width(title) - 1), "dim")], bold=True)
        elif isinstance(block, Gap):
            add([("", "")])
        elif isinstance(block, Field):
            value_width = width - label_width - 2
            lines = wrap(block.value, value_width) or [""]
            for index, line in enumerate(lines):
                label = pad(block.label, label_width) if index == 0 else " " * label_width
                add([(label, "dim"), ("  ", ""), (line, block.tone)])
        elif isinstance(block, Meter):
            add([(pad(block.label, label_width), "dim"), ("  ", ""),
                 *gauge(0, block.fraction or 0, bar_width, block.tone, glyphs),
                 ("  ", ""), (block.text.rjust(meter_text), block.tone if block.fraction is not None else "dim")])
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
            gap = " " * block.gap
            add([(gap.join(pad(str(h), widths[i]) for i, h in enumerate(block.headers)), "dim")], bold=True)
            for row in block.rows:
                add([(gap.join(pad(str(c), widths[i]) for i, c in enumerate(row)), "")])
        elif isinstance(block, Track):
            span = (block.high - block.low) or 1.0
            add([(pad(block.label, label_width), "dim"), ("  ", ""),
                 *gauge((block.start - block.low) / span, (block.end - block.low) / span, bar_width, block.tone, glyphs),
                 ("  ", ""), (block.text.rjust(meter_text), block.tone)])
        elif isinstance(block, Columns):
            count = len(block.cards)
            fit = max(1, min(count, (width + 3) // (block.minimum + 3)))
            each = (width - 3 * (fit - 1)) // fit  # a card left alone keeps the grid's width
            for first in range(0, count, fit):
                group = block.cards[first:first + fit]
                parts = []
                for card in group:
                    inner = build_layout([Heading(card.title)] + list(card.blocks), each, glyphs, each // 2)
                    # The headline reading sits on the title row, over a rule the card's width.
                    title = clip(card.title, each - cell_width(card.value) - 1)
                    inner.rows[0:1] = [
                        Row([(title, "accent"), (" " * (each - cell_width(title) - cell_width(card.value)), ""),
                             (card.value, "accent")], bold=True),
                        Row([(glyphs.rule * each, "dim")])]
                    parts.append(inner)
                layout.rows.extend(_join_columns(parts, [each] * len(group), " | " if glyphs.rule == "-" else " │ "))
                add([("", "")])
        elif isinstance(block, Pad):
            index = len(layout.choices)
            layout.choices.append(Choice("", block.toggle, pad=block))
            layout.choice_rows.append(len(layout.rows))
            cols = len(block.headers)
            name_w = max(cell_width(row.name) for row in block.rows) + 2
            tail_w = max([cell_width(row.tail) for row in block.rows] + [cell_width(block.tail_header)]) + 2
            cell_w = max(4, min(10, (width - name_w - tail_w - (cols + 3)) // max(1, cols)))
            widths = [name_w] + [cell_w] * cols + [tail_w]
            g = glyphs

            def rule(kind):
                left, mid, right = kind
                row = [(left, "dim")]
                for position, w in enumerate(widths):
                    row.append((g.h * w, "dim"))
                    row.append((mid if position < len(widths) - 1 else right, "dim"))
                layout.rows.append(Row(row, index, plain=True))

            def line(texts, tones):
                row = [(g.v, "dim")]
                for w, text, tone in zip(widths, texts, tones):
                    row.append((clip(text, w).center(w), tone))
                    row.append((g.v, "dim"))
                layout.rows.append(Row(row, index, plain=True))

            rule(g.top)
            line([""] + [str(h) for h in block.headers] + [block.tail_header], ["dim"] * (cols + 2))
            rule(g.mid)
            for r, prow in enumerate(block.rows):  # one line a row: the token says the state, the colour repeats it
                tones = ["accent"] + [("sel" if (r, c) == block.cursor else cell.tone) for c, cell in enumerate(prow.cells)]
                line([prow.name] + [cell.text for cell in prow.cells] + [prow.tail], tones + [prow.tail_tone])
            rule(g.bottom)
        elif isinstance(block, Choice):
            index = len(layout.choices)
            layout.choices.append(block)
            layout.choice_rows.append(len(layout.rows))
            detail = block.detail
            # A value sits in the same column as every Field's, so a section reads as one table.
            label = (pad(block.label, label_width + 2) if cell_width(block.label) <= label_width
                     else block.label + "  ") if detail else clip(block.label, width)
            tone = block.tone if block.enabled else "dim"
            add([(label, tone), (clip(detail, max(0, width - cell_width(label))), "accent" if block.adjust else "dim")],
                choice=index)
    return layout
