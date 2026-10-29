"""Blocks to terminal rows: pure text layout, no curses."""

from __future__ import annotations

from dataclasses import dataclass, field

from .content import (
    Block,
    Chart,
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
MIN_BAR = 4


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


_BRAILLE = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))
_SHADES = (" ░▒▓█", " .:+#")


def _runs(cells: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """(char, tone) cells as spans: consecutive cells of one tone share a span."""
    spans: list[tuple[str, str]] = []
    for char, tone in cells:
        if spans and spans[-1][1] == tone:
            spans[-1] = (spans[-1][0] + char, tone)
        else:
            spans.append((char, tone))
    return spans


def chart_rows(chart: Chart, width: int, glyphs: Glyphs) -> list[list[tuple[str, str]]]:
    """``chart`` as rows of spans: the plot, its value axis on the right, the time axis below."""
    braille = glyphs.rule == "─"
    axis = max(cell_width(chart.show(value)) for value in (chart.low, chart.high)) + 3
    plot = max(10, width - axis)
    end = chart.times[-1] if chart.times else 0.0

    def column(moment: float, scale: int) -> int:  # where a sample of that moment lands, in dots or cells
        return round((moment - (end - chart.window)) / chart.window * (plot * scale - 1))

    rows: list[list[tuple[str, str]]] = []
    if chart.heatmap:  # one row per series, the shade is the value
        shades = _SHADES[0 if braille else 1]
        name_w = min(12, max(cell_width(name) for name, _v, _t in chart.series))
        span = (chart.high - chart.low) or 1.0
        for name, values, tone in chart.series:
            cells = [" "] * (plot - name_w - 1)
            for moment, value in zip(chart.times[-len(values):], values):
                x = round((moment - (end - chart.window)) / chart.window * (len(cells) - 1))
                if 0 <= x < len(cells):
                    level = (min(max(value, chart.low), chart.high) - chart.low) / span
                    cells[x] = shades[min(len(shades) - 1, round(level * (len(shades) - 1)))]
            rows.append([(pad(name, name_w) + " ", "dim"), ("".join(cells), tone)])
    else:
        height = max(3, chart.height)
        dots_x, dots_y = (2, 4) if braille else (1, 1)
        masks = [[0] * plot for _ in range(height)]
        tones = [[""] * plot for _ in range(height)]
        span = (chart.high - chart.low) or 1.0

        def y_of(value: float) -> int:
            return height * dots_y - 1 - round((min(max(value, chart.low), chart.high) - chart.low) / span
                                               * (height * dots_y - 1))

        def dot(x: int, y: int, tone: str) -> None:
            cx, cy = x // dots_x, y // dots_y
            if 0 <= cx < plot and 0 <= cy < height:
                masks[cy][cx] |= _BRAILLE[y % 4][x % 2] if braille else 1
                tones[cy][cx] = tone

        last_y = None
        bottoms: dict[int, int] = {}  # dot column -> lowest line dot, for the area under a single series
        for _name, values, tone in chart.series:
            previous = None
            for moment, value in zip(chart.times[-len(values):], values):
                x, y = column(moment, dots_x), y_of(value)
                if previous is not None and 0 < x - previous[0] <= 4 * dots_x:
                    # Join the samples: every dot column between them, and the rows between each step,
                    # so the line reads as one stroke of even weight instead of loose dots.
                    reached = previous[1]
                    for step in range(previous[0] + 1, x + 1):
                        target = round(previous[1] + (y - previous[1]) * (step - previous[0]) / (x - previous[0]))
                        for yy in range(min(reached, target), max(reached, target) + 1):
                            dot(step, yy, tone)
                        bottoms[step] = max(bottoms.get(step, -1), target)
                        reached = target
                dot(x, y, tone)
                bottoms[x] = max(bottoms.get(x, -1), y)
                previous = (x, y)
            last_y = previous[1] // dots_y if previous and last_y is None else last_y
        area = len(chart.series) == 1 and braille
        average_row = y_of(chart.average) // dots_y if chart.average is not None else None
        ticks = {y_of(tick) // dots_y: chart.show(tick) for tick in chart.ticks or (chart.low, chart.high)}
        current = chart.series[0][1][-1] if chart.series and chart.series[0][1] else None
        for r in range(height):
            cells = []
            for c in range(plot):
                if masks[r][c]:
                    cells.append((chr(0x2800 + masks[r][c]) if braille else "*", tones[r][c]))
                elif area and r * 4 > max(bottoms.get(2 * c, 10**6), bottoms.get(2 * c + 1, 10**6)) \
                        and (2 * c in bottoms or 2 * c + 1 in bottoms):  # a faint fill under the line
                    cells.append(("⡀" if r % 2 else "⢀", "dim"))
                elif r == average_row:  # the window's average: a thin dotted rule, labelled at its left
                    cells.append(("╌" if braille else "-", "dim") if c % 2 else (" ", ""))
                elif r in ticks and c % 2 == 0:  # a faint rule at each labelled value
                    cells.append(("·" if braille else ".", "dim"))
                else:
                    cells.append((" ", ""))
            if r == average_row and chart.average is not None and chart.average_label:
                label = f" {chart.average_label} "
                cells[1:1 + len(label)] = [(char, "dim") for char in label]
            if r == last_y and current is not None:
                rows.append(_runs(cells) + [((" ◂ " if braille else " < ") + chart.show(current), "accent")])
            else:
                rows.append(_runs(cells) + [(f" {glyphs.v} {ticks.get(r, '')}", "dim")])
    # time marks every 30 s, counted back from now, as on the desktop
    line = [" "] * plot
    for age in range(0, int(chart.window) + 1, 30):
        text = chart.now if age == 0 else f"-{age // 60}:{age % 60:02d}"
        x = plot - 1 - round(age / chart.window * (plot - 1))
        start = max(0, min(plot - len(text), x - len(text) // 2))
        if all(char == " " for char in line[max(0, start - 1):start + len(text) + 1]):
            line[start:start + len(text)] = list(text)
    rows.append([("".join(line), "dim")])
    return rows


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
    """Cards side by side; every row is cut or padded to exactly its card's width."""
    rows = []
    for line in range(max(len(item.rows) for item in card_layouts)):
        spans: list[tuple[str, str]] = []
        for index, item in enumerate(card_layouts):
            if index:
                spans.append((gap, "dim"))
            room = widths[index]
            for text, tone in item.rows[line].spans if line < len(item.rows) else []:
                if room <= 0:
                    break
                text = clip(text, room) if cell_width(text) > room else text
                spans.append((text, tone))
                room -= cell_width(text)
            spans.append((" " * room, ""))
        rows.append(Row(spans))
    return rows


def _columns(blocks, width: int, label_cap: int) -> tuple[int, int]:
    """(label width, value-text width) for ``blocks``: the two columns every row lines up on."""
    label_width = min(label_cap, max(12, width // 2), max(
        [cell_width(b.label) for b in blocks if isinstance(b, (Field, Meter, Trend, Track)) or (
            isinstance(b, Choice) and b.detail)] + [8]))
    return label_width, max([cell_width(b.text) for b in blocks if isinstance(b, (Meter, Track, Trend))] + [0])


def build_layout(blocks: list[Block], width: int, glyphs: Glyphs, label_cap: int = LABEL_MAX, *,
                 card: bool = False, columns: tuple[int, int] | None = None, touch: bool = False) -> Layout:
    """Rows for ``blocks``. Inside a card a Heading is a group label (THERMAL, POWER…), as on the desktop.

    ``columns`` fixes the label and value widths, so cards side by side (or
    stacked) line up with each other.
    """
    layout = Layout()
    width = max(20, width)
    label_width, meter_text = columns or _columns(blocks, width, label_cap)
    # A narrow column gives up bar first, then label: the reading itself is never cut.
    label_width = max(8, min(label_width, width - meter_text - 4 - MIN_BAR))
    bar_width = max(MIN_BAR, min(BAR_MAX, width - label_width - meter_text - 4))

    def add(spans, choice=None, bold=False):
        layout.rows.append(Row(spans, choice, bold))

    for block in blocks:
        if isinstance(block, Heading) and card:
            if layout.rows:
                add([("", "")])
            add([(clip(block.text.upper(), width), "dim")], bold=True)
        elif isinstance(block, Heading):  # one row: the title, then a rule to the edge
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
        elif isinstance(block, Trend):  # the same columns as a bar: label, graph, reading
            add([(pad(block.label, label_width), "dim"), ("  ", ""),
                 (sparkline(block.values, bar_width, glyphs).ljust(bar_width), block.tone),
                 ("  ", ""), (block.text.rjust(meter_text), "")])
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
            shared = _columns([b for item in block.cards for b in item.blocks], each, each * 11 // 20)
            for first in range(0, count, fit):
                group = block.cards[first:first + fit]
                parts = []
                for item in group:
                    inner = build_layout(list(item.blocks), each, glyphs, card=True, columns=shared)
                    # The headline reading sits on the title row, over a rule the card's width.
                    title = clip(item.title, each - cell_width(item.value) - 1)
                    inner.rows[0:0] = [
                        Row([(title, "accent"), (" " * (each - cell_width(title) - cell_width(item.value)), ""),
                             (item.value, "accent")], bold=True),
                        Row([(glyphs.rule * each, "dim")])]
                    parts.append(inner)
                layout.rows.extend(_join_columns(parts, [each] * len(group), " | " if glyphs.rule == "-" else " │ "))
                add([("", "")])
        elif isinstance(block, Chart):
            for spans in chart_rows(block, width, glyphs):
                add(spans)
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
            # A button does something; "( )"/"[x]" are options and "›" opens a menu of its own.
            button = not (detail or block.adjust or block.label.startswith(("(", "[")) or block.label.endswith("›"))
            if button:
                tone = (tone or "accent") if block.enabled else "dim"
            if button and touch and glyphs.rule == "─":  # a pill as wide as its words; the whole row is the target
                text, tone = clip(block.label, width - 6), tone or "accent"
                add([("▐", tone), (f" {text} ", "btn:" + tone), ("▌", tone)], choice=index)
            else:
                if button:
                    label = f"[ {clip(block.label, width - 4)} ]"  # a button: it does something, it is not a value
                add([(label, tone), (clip(detail, max(0, width - cell_width(label))), "accent" if block.adjust else "dim")],
                    choice=index)
            if touch and not block.dense:  # room between rows, and part of the same target
                add([("", "")], choice=index)
    return layout
