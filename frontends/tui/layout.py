"""Blocks to terminal rows: pure text layout, no curses."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .content import (
    Block,
    Buttons,
    Card,
    Chart,
    Choice,
    Columns,
    Field,
    Gap,
    Gauges,
    Grid,
    Heading,
    Legend,
    Meter,
    Note,
    Pad,
    Panel,
    Raw,
    Slider,
    Spans,
    Split,
    Tiles,
    Track,
    Trend,
    cell_width,
    clip,
    pad,
    wrap,
)

LABEL_MAX = 30
LABEL_MIN = 24
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
    top: tuple = ("╭", "┬", "╮")
    mid: tuple = ("├", "┼", "┤")
    bottom: tuple = ("╰", "┴", "╯")

    @classmethod
    def for_terminal(cls, *, unicode_ok: bool, square: bool = False) -> "Glyphs":
        if unicode_ok and square:
            return cls(top=("┌", "┬", "┐"), bottom=("└", "┴", "┘"))
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
    #: one owner per span when a row holds several items (buttons side by side, cards in columns):
    #: a choice index, ``-1 - index`` for one drawn plain, or None
    owners: list[int | None] | None = None
    cells: list[tuple[int, int, int, int]] = field(default_factory=list)  # Pad cells: (x0, x1, row, column)

    def owned(self) -> list[int | None]:
        if self.owners is not None:
            return list(self.owners)
        mark = None if self.choice is None else -1 - self.choice if self.plain else self.choice
        return [mark] * len(self.spans)


@dataclass(slots=True)
class Layout:
    rows: list[Row] = field(default_factory=list)
    choices: list[Choice] = field(default_factory=list)
    choice_rows: list[int] = field(default_factory=list)  # row index of each choice


def choice_column(layout: Layout, index: int) -> int:
    """The horizontal centre of a keyboard target, including framed buttons."""
    row = layout.rows[layout.choice_rows[index]]
    column, first, last = 0, None, 0
    for (text, _tone), owner in zip(row.spans, row.owned()):
        width = cell_width(text)
        if owner is not None and (owner if owner >= 0 else -1 - owner) == index:
            if first is None:
                first = column
            last = column + width
        column += width
    return (first + last) // 2 if first is not None else 0


def _reading_order(layout: Layout) -> Layout:
    order = sorted(range(len(layout.choices)), key=lambda i: (layout.choice_rows[i], choice_column(layout, i)))
    mapping = {old: new for new, old in enumerate(order)}
    def remap(owner):
        if owner is None:
            return None
        return mapping[owner] if owner >= 0 else -1 - mapping[-1 - owner]
    for row in layout.rows:
        if row.choice is not None:
            row.choice = mapping[row.choice]
        if row.owners is not None:
            row.owners = [remap(owner) for owner in row.owners]
    layout.choices = [layout.choices[i] for i in order]
    layout.choice_rows = [layout.choice_rows[i] for i in order]
    return layout


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
    tone = tone if tone in ("warn", "bad") else "bar"
    a = max(0, min(width, round(start * width)))
    b = max(a, min(width, round(end * width)))
    return [(glyphs.rule * a, "edge"), (glyphs.fill * (b - a), tone), (glyphs.rule * (width - b), "edge")]


def _shift(owner: int | None, base: int) -> int | None:
    return None if owner is None else owner + base if owner >= 0 else owner - base


def _side_by_side(layout: Layout, parts: list[Layout], widths: list[int], gap: str = "") -> None:
    """Append ``parts`` next to each other, each row cut or padded to its part's width.

    Their items join ``layout``'s in order (left part first), so Enter, taps and
    the arrows reach every button of every card.
    """
    top, bases = len(layout.rows), []
    for part in parts:
        bases.append(len(layout.choices))
        layout.choices.extend(part.choices)
        layout.choice_rows.extend(top + row for row in part.choice_rows)
    for line in range(max((len(part.rows) for part in parts), default=0)):
        spans: list[tuple[str, str]] = []
        owners: list[int | None] = []
        cells: list[tuple[int, int, int, int]] = []
        column = 0
        for index, part in enumerate(parts):
            if index and gap:
                spans.append((gap, "dim"))
                owners.append(None)
                column += cell_width(gap)
            room = widths[index]
            row = part.rows[line] if line < len(part.rows) else Row([])
            cells += [(column + a, column + b, r, c) for a, b, r, c in row.cells]
            for (text, tone), owner in zip(row.spans, row.owned()):
                if room <= 0:
                    break
                text = clip(text, room) if cell_width(text) > room else text
                spans.append((text, tone + "!" if row.bold and not tone.endswith("!") else tone))
                owners.append(_shift(owner, bases[index]))
                room -= cell_width(text)
                column += cell_width(text)
            spans.append((" " * room, ""))
            owners.append(None)
            column += room
        layout.rows.append(Row(spans, owners=owners, cells=cells))


def _section(inner: Layout, width: int, glyphs: Glyphs, title: str, right: list[tuple[str, str]], *, tone: str = "",
             right_owners: list[int | None] | None = None) -> Layout:
    """``inner`` under its heading: the title, a hairline to the edge, and what the section says about itself."""
    room = width - sum(cell_width(text) for text, _tone in right) - (1 if right else 0)
    name = clip(title, max(1, room - 2))
    line = max(0, room - cell_width(name) - 1)
    out = Layout()
    if title or right:
        out.rows.append(Row([(name, tone + "!"), (" " + glyphs.h * line, "edge"), *([(" ", "")] if right else []), *right],
                            owners=[None, None, *([None] if right else []), *(right_owners or [None] * len(right))]))
    body = Layout()
    _side_by_side(body, [inner], [width])
    out.choices, out.choice_rows = body.choices, [row + len(out.rows) for row in body.choice_rows]
    out.rows += body.rows
    out.rows.append(Row([("", "")]))
    return out


def _card(item: Card, width: int, glyphs: Glyphs, columns: tuple[int, int] | None = None) -> Layout:
    columns = columns or _columns(item.blocks, width, width * 11 // 20)
    inner = build_layout(list(item.blocks), width, glyphs, card=True, columns=columns)
    return _section(inner, width, glyphs, item.title, [(item.value, "!")] if item.value else [])


def button_spans(choice: Choice, glyphs: Glyphs, width: int) -> list[tuple[str, str]]:
    """An action: a plain line of text. Its weight says whether it is the page's main one."""
    tone = "dim" if not choice.enabled else {"primary": "!", "accent": "!"}.get(choice.tone, choice.tone if choice.tone != "ok" else "")
    text = clip(choice.label, width)
    return [(text, tone), (" " * (width - cell_width(text)), "")]


def _acts(choice: Choice) -> bool:
    """A row that does something, as opposed to one holding a value, an option or a menu."""
    return not (choice.detail or choice.adjust or choice.badge or choice.mark is not None or choice.dense
                or choice.label.startswith(("(", "[")) or choice.label.endswith("›"))


def _columns(blocks, width: int, label_cap: int) -> tuple[int, int]:
    """(label width, value-text width) for ``blocks``: the two columns every row lines up on."""
    label_width = min(label_cap, max(12, width // 2), max(
        [cell_width(b.label) + (4 if isinstance(b, Choice) and b.mark is not None else 0)
         for b in blocks if isinstance(b, (Field, Meter, Trend, Track)) or (isinstance(b, Choice) and b.detail)] + [8]))
    if width >= WORK_MIN and any(isinstance(b, Choice) and b.detail for b in blocks):
        label_width = max(label_width, LABEL_MIN)  # one value column down the page, not one per section
    return label_width, max([cell_width(b.text) for b in blocks if isinstance(b, (Meter, Track, Trend))] + [0])


def build_layout(blocks: list[Block], width: int, glyphs: Glyphs, label_cap: int = LABEL_MAX, *,
                 card: bool = False, columns: tuple[int, int] | None = None) -> Layout:
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

    valued = False  # the last row asked for a value: what acts on it starts after a blank line
    for block in blocks:
        acts = isinstance(block, Buttons) or (isinstance(block, Choice) and _acts(block))
        if acts and valued:
            add([("", "")])
        valued = isinstance(block, (Slider, Grid)) or (isinstance(block, Choice) and bool(block.detail))
        if isinstance(block, Heading) and card:
            if layout.rows:
                add([("", "")])
            add([(clip(block.text, width), "dim")], bold=True)
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
                add([(label, "dim"), ("  ", ""), (line, "" if block.tone in ("ok", "accent") else block.tone)])
        elif isinstance(block, Meter):
            add([(pad(block.label, label_width), "dim"), ("  ", ""),
                 *gauge(0, block.fraction or 0, bar_width, block.tone, glyphs),
                 ("  ", ""), (block.text.rjust(meter_text), (block.tone if block.tone in ("warn", "bad") else "") if block.fraction is not None else "dim")])
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
            numeric = [index > 0 and all(str(row[index])[:1].isdigit() or str(row[index]) in ("", "--", "—", "-") for row in block.rows)
                       for index in range(len(block.headers))]

            def cells(values):
                return gap.join(" " * (widths[i] - cell_width(str(v))) + str(v) if numeric[i] else pad(str(v), widths[i])
                                for i, v in enumerate(values))

            add([(cells(block.headers), "dim")])
            for row in block.rows:
                add([(cells(row), "")])
        elif isinstance(block, Spans):
            for spans in block.lines:
                add(list(spans))
        elif isinstance(block, Gauges):
            fit = max(1, min(len(block.items), (width + 3) // (block.minimum + 3)))
            each = (width - 3 * (fit - 1)) // fit
            names = max(cell_width(item.label) for item in block.items)
            texts = max(cell_width(item.text) for item in block.items)
            bar = max(MIN_BAR, each - names - texts - 3)
            for first in range(0, len(block.items), fit):
                spans = []
                for item in block.items[first:first + fit]:
                    spans += [("   ", "")] if spans else []
                    spans += [(pad(item.label, names) + " ", "dim"), *gauge(0, item.fraction or 0, bar, item.tone, glyphs),
                              ("  " + item.text.rjust(texts), (item.tone if item.tone in ("warn", "bad") else "") if item.fraction is not None else "dim")]
                add(spans)
        elif isinstance(block, Track):
            span = (block.high - block.low) or 1.0
            add([(pad(block.label, label_width), "dim"), ("  ", ""),
                 *gauge((block.start - block.low) / span, (block.end - block.low) / span, bar_width, block.tone, glyphs),
                 ("  ", ""), (block.text.rjust(meter_text), block.tone)])
        elif isinstance(block, Card):
            _side_by_side(layout, [_card(block, width, glyphs)], [width])
        elif isinstance(block, Columns):
            count = len(block.cards)
            fit = max(1, min(count, (width + 3) // (block.minimum + 3)))
            each = (width - (fit - 1)) // fit  # a card left alone keeps the grid's width
            shared = _columns([b for item in block.cards for b in item.blocks], each - 4, (each - 4) * 11 // 20)
            for first in range(0, count, fit):
                parts = []
                for item in block.cards[first:first + fit]:
                    parts.append(_card(item, each, glyphs, shared))
                _side_by_side(layout, parts, [each] * len(parts), " ")
        elif isinstance(block, Chart):
            for spans in chart_rows(block, width, glyphs):
                add(spans)
        elif isinstance(block, Pad):
            index = len(layout.choices)
            layout.choices.append(Choice("", block.toggle, pad=block, info=block.info, id="pad:" + str(block.corner)))
            layout.choice_rows.append(len(layout.rows))
            cols = len(block.headers)
            extra = list(block.extra)
            # The values set the columns' widths; headers widen them only while the cells keep room for a note.
            name_w = max(cell_width(row.name) for row in block.rows) + 2
            tail_w = max(cell_width(row.tail) for row in block.rows) + 2
            note_w = max([cell_width(cell.note) + 2 for row in block.rows for cell in row.cells] + [4])
            heads = max(cell_width(part) + 2 for part in block.corner.split("\n")), \
                max(cell_width(part) + 2 for part in str(block.tail_header).split("\n"))
            if width - heads[0] - heads[1] - (cols + 3) >= note_w * cols:
                name_w, tail_w = max(name_w, heads[0]), max(tail_w, heads[1])
            cell_w = max(4, min(18, (width - name_w - tail_w - (cols + 3)) // max(1, cols)))
            notes = cell_w >= note_w  # too narrow for "ROUTED": the token and its colour say it
            extra_w = [max([cell_width(head)] + [cell_width(row.extra[i][0]) for row in block.rows if i < len(row.extra)]) + 2
                       for i, head in enumerate(extra)]
            if block.classic:
                cell_w = min(cell_w, 6)
                while extra_w and name_w + cell_w * cols + sum(extra_w) + tail_w + cols + len(extra_w) + 3 > width:
                    if cell_w > 4:
                        cell_w -= 1
                    else:  # a narrow terminal keeps the cells and gives up the registers, last first
                        extra_w.pop()
                        extra.pop()
            widths = [name_w] + [cell_w] * cols + extra_w + [tail_w]
            g = Glyphs.for_terminal(unicode_ok=False) if block.classic else glyphs

            def rule(kind):
                left, mid, right = kind
                row = [(left, "dim")]
                for position, w in enumerate(widths):
                    row.append((g.h * w, "dim"))
                    row.append((mid if position < len(widths) - 1 else right, "dim"))
                layout.rows.append(Row(row, index, plain=True))

            def line(texts, tones, r=None):
                row, cells, x = [(g.v, "dim")], [], 1
                for c, (w, text, tone) in enumerate(zip(widths, texts, tones)):
                    row.append((clip(text, w).center(w), tone))
                    row.append((g.v, "dim"))
                    if r is not None and 0 < c <= cols:
                        cells.append((x, x + w, r, c - 1))
                    x += w + 1
                layout.rows.append(Row(row, index, plain=True, cells=cells))

            rule(g.top)
            heads = [str(text).split("\n") for text in [block.corner, *block.headers, *extra, block.tail_header]]
            for level in range(max(len(head) for head in heads)):
                line([head[level] if level < len(head) else "" for head in heads], ["" if level == 0 else "dim"] * len(widths))
            rule(g.mid)
            for r, prow in enumerate(block.rows):  # the token says the state, the colour repeats it
                tones = [""] + [("sel" if (r, c) == block.cursor else cell.tone)
                                                               for c, cell in enumerate(prow.cells)]
                more = list(prow.extra)[:len(extra)]
                line([prow.name] + [cell.text for cell in prow.cells] + [text for text, _tone in more] + [prow.tail],
                     tones + [tone for _text, tone in more] + [prow.tail_tone], r)
                if notes and any(cell.note for cell in prow.cells):
                    line([""] + [cell.note for cell in prow.cells] + [""] * (len(extra) + 1), [""] + tones[1:] + [""] * (len(extra) + 1), r)
            rule(g.bottom)
        elif isinstance(block, Panel):
            inner = build_layout(([Note(block.subtitle, "dim")] if block.subtitle else []) + list(block.blocks),
                                 width, glyphs, label_cap)
            badge_tone = "" if block.badge_tone == "accent" else block.badge_tone
            right = [(block.badge, badge_tone)] if block.badge else []
            owners: list[int | None] = [None] * len(right)
            if block.action:
                right += ([("  ", "")] if right else []) + [(block.action.label, "accent")]
                owners += ([None] if block.badge else []) + [len(inner.choices)]
                inner.choices.append(block.action)
                inner.choice_rows.append(-1)  # the title row, once it has one
            box = _section(inner, width, glyphs, block.title, right, tone="bad" if block.danger else "", right_owners=owners)
            _side_by_side(layout, [box], [width])
        elif isinstance(block, Tiles):  # readings as plain lines; a profile as one of a set
            rows: list[Block] = []
            for tile in block.tiles:
                value = " · ".join(part for part in (tile.value, tile.hint) if part)
                rows.append(Choice(tile.label, tile.handler, value, mark=tile.active, edit=tile.edit) if tile.handler
                            else Field(tile.label, value, tile.tone))
            _side_by_side(layout, [build_layout(rows, width, glyphs, label_cap, card=card)], [width])
        elif isinstance(block, Buttons):  # one under the other: up and down reach every one of them
            for choice in block.choices:
                layout.choices.append(choice)
                layout.choice_rows.append(len(layout.rows))
                add(button_spans(choice, glyphs, width), choice=len(layout.choices) - 1)
        elif isinstance(block, Slider):  # the rail, then the stop labels on two staggered rows
            stops = list(block.stops)
            span = max(1, len(stops) - 1)
            at = [round(index * (width - 1) / span) for index in range(len(stops))]
            first = min(range(len(stops)), key=lambda i: abs(stops[i] - block.start))
            last = min(range(len(stops)), key=lambda i: abs(stops[i] - block.end))
            red = [block.danger is not None and stop > block.danger for stop in stops]
            cells = []
            for x in range(width):
                index = max(i for i in range(len(at)) if at[i] <= x)  # the stop at or left of this cell
                hot = red[min(len(stops) - 1, index + (x > at[index]))]
                if x in (at[first], at[last]):
                    cells.append(("●" if glyphs.rule == "─" else "O", "bad" if red[last] and x == at[last] else ""))
                elif at[first] < x < at[last]:
                    cells.append((glyphs.fill, "bad" if hot else "bar"))
                elif x in at:
                    cells.append(("┼" if glyphs.rule == "─" else "+", "dim"))
                else:
                    cells.append((glyphs.rule, "edge"))
            add(_runs(cells))
            for parity in (0, 1):
                line = [(" ", "")] * width
                for index in range(parity, len(stops), 2):
                    text = str(stops[index])
                    begin = max(0, min(width - len(text), at[index] - len(text) // 2))
                    if all(char == " " for char, _tone in line[max(0, begin - 1):begin + len(text) + 1]):  # never touch
                        line[begin:begin + len(text)] = [(char, "" if index in (first, last) else "dim") for char in text]
                add(_runs(line))
        elif isinstance(block, Legend):
            spans, used = [], 0
            for chip, meaning, tone in block.items:
                size = cell_width(chip) + cell_width(meaning) + 6
                if spans and used + size > width:
                    add(spans)
                    spans, used = [], 0
                spans += [(f" {chip}", tone + "!"), (f" {meaning}   ", "dim")]
                used += size
            if spans:
                add(spans)
        elif isinstance(block, Split):
            if width >= block.minimum:
                left = max(20, int((width - 2) * block.ratio))
                parts = [build_layout(list(side), size, glyphs, label_cap)
                         for side, size in ((block.left, left), (block.right, width - 2 - left))]
                _side_by_side(layout, parts, [left, width - 2 - left], "  ")
            else:
                for side in (block.left, block.right):
                    _side_by_side(layout, [build_layout(list(side), width, glyphs, label_cap)], [width])
        elif isinstance(block, Choice):
            index = len(layout.choices)
            layout.choices.append(block)
            layout.choice_rows.append(len(layout.rows))
            detail = block.detail
            # A value sits in the same column as every Field's, so a section reads as one table.
            name = block.label if block.mark is None else \
                ("(" + ("●" if glyphs.rule == "─" else "*") + ") " if block.mark else "( ) ") + block.label
            label = (pad(name, label_width + 2) if cell_width(name) <= label_width
                     else name + "  ") if detail else clip(name, width)
            tone = ("" if block.tone in ("ok", "accent", "primary") else block.tone) if block.enabled else "dim"
            if block.mark:
                tone = tone or "!"
            if detail.startswith("< ") and block.adjust:  # the arrows are drawn on the row that has the cursor
                detail = detail.removeprefix("< ").removesuffix(" >").replace(" >  ", "  ")
            # A button does something; "( )"/"[x]" are options and "›" opens a menu of its own.
            button = not (detail or block.adjust or block.info or block.mark is not None or block.label.startswith(("(", "[")) or block.label.endswith("›"))
            if button:  # it does something, it is not a value
                add(button_spans(block, glyphs, width), choice=index)
            else:
                chip = f" {block.badge} " if block.badge else ""
                if chip and cell_width(label) + cell_width(chip) > width - 1:  # the state is never the part that is cut
                    label = clip(label, max(8, width - cell_width(chip) - 1))
                room = max(0, width - cell_width(label) - cell_width(chip) - (1 if chip else 0))
                text = clip(detail, room)
                spans = [(label, tone), (text, "dim" if not block.enabled else block.tone if block.adjust and block.tone in ("warn", "bad") else "")]
                # The whole line is the target, so the whole line is what lights up.
                spans.append((" " * max(0, room - cell_width(text) + (1 if chip else 0)), ""))
                if chip:
                    spans.append((chip, "" if block.badge_tone == "accent" else block.badge_tone))
                add(spans, choice=index)
    return _reading_order(layout)


#: A group needs this many columns before a second column of groups is worth having.
GROUP_MIN = 50
COLUMN_GAP = 4


def page_groups(blocks: list[Block]) -> list[tuple[bool, list[Block]]]:
    """A page's top-level blocks as (boxed, blocks) units, in order.

    A Heading starts a group that runs to the next heading, and a Panel is one
    already; what follows a Panel without a heading (its Apply button) stays
    with it. Everything else keeps the whole width.
    """
    units: list[tuple[bool, list[Block]]] = []
    heading: Panel | None = None
    for block in blocks:
        if isinstance(block, Heading):
            heading = Panel(block.text, [])
            units.append((True, [heading]))
        elif isinstance(block, Card):
            heading = None
            units.append((True, [block]))
        elif isinstance(block, Columns):
            heading = None
            units += [(True, [card]) for card in block.cards]
        elif isinstance(block, (Panel, Split, Chart, Pad)):
            heading = None
            # A wide table (the fan channels) is unreadable in half a screen.
            wide = isinstance(block, Panel) and any(isinstance(b, Pad) and len(b.headers) > 5 for b in block.blocks)
            wide = wide or (isinstance(block, Panel) and block.wide)
            units.append((isinstance(block, Panel) and not wide, [block]))
        elif heading is not None:
            heading.blocks.append(block)
        elif isinstance(block, Gap):
            continue
        elif units and units[-1][0] and isinstance(units[-1][1][0], Panel) and isinstance(block, (Buttons, Choice, Note)):
            panel = units[-1][1][0]  # its Apply button, drawn inside its box
            units[-1][1][0] = replace(panel, blocks=[*panel.blocks, block])
        else:
            units.append((False, [block]))
    for _boxed, unit in units:
        for block in unit:
            if isinstance(block, Panel) and isinstance(block.blocks, list):
                while block.blocks and isinstance(block.blocks[-1], Gap):
                    block.blocks.pop()
    return units


#: The column a person works in: wide enough for a value, narrow enough to read across.
WORK_MIN, WORK_MAX, SIDE_MIN = 58, 92, 40


def _interactive(blocks) -> bool:
    for block in blocks:
        if isinstance(block, (Choice, Buttons, Pad)) or getattr(block, "action", None) is not None:
            return True
        for name in ("blocks", "left", "right", "cards"):
            if _interactive(getattr(block, name, None) or ()):
                return True
        if isinstance(block, Tiles) and any(tile.handler for tile in block.tiles):
            return True
    return False


def build_page(blocks: list[Block], width: int, glyphs: Glyphs) -> Layout:
    """A whole page: what can be operated in one column, what is only read beside it.

    One column for the cursor means up and down are the only way to go; a page
    with nothing to operate (the dashboard) uses the width for its readings.
    """
    layout = Layout()
    width = max(20, width)
    units = [unit for _boxed, unit in page_groups(blocks)]
    work = [unit for unit in units if _interactive(unit)]
    read = [unit for unit in units if not _interactive(unit)]
    if read and all(isinstance(block, Note) for unit in read for block in unit):
        work, read = [*read, *work], []  # a line or two is a preface, not a column
    wide = any(isinstance(block, (Chart, Pad)) or getattr(block, "wide", False) for unit in units for block in unit)

    def stack(parts: list[list[Block]], size: int) -> Layout:
        column = Layout()
        for part in parts:
            _side_by_side(column, [build_layout(part, size, glyphs)], [size])
        return column

    mostly_read = sum(len(build_layout(unit, 60, glyphs).rows) for unit in read) > \
        2 * sum(len(build_layout(unit, 60, glyphs).rows) for unit in work)
    if mostly_read and width >= 2 * GROUP_MIN + COLUMN_GAP:
        count = min(len(units), 3 if width >= 3 * 56 + 2 * COLUMN_GAP else 2)
        each = (width - COLUMN_GAP * (count - 1)) // count
        boxes = [build_layout(unit, each, glyphs) for unit in units]
        columns = []
        for part in _balance([len(box.rows) for box in boxes], count):
            column = Layout()
            for position in part:
                _side_by_side(column, [boxes[position]], [each])
            columns.append(column)
        _side_by_side(layout, columns, [each] * len(columns), " " * COLUMN_GAP)
    elif work and read and width >= WORK_MIN + SIDE_MIN + COLUMN_GAP:
        left = min(WORK_MAX if not wide else width - SIDE_MIN - COLUMN_GAP, max(WORK_MIN, (width - COLUMN_GAP) * 3 // 5))
        right = min(width - left - COLUMN_GAP, 72)
        _side_by_side(layout, [stack(work, left), stack(read, right)], [left, right], " " * COLUMN_GAP)
    else:
        size = width if wide else min(width, WORK_MAX + 8)
        _side_by_side(layout, [stack(units, size)], [size])
    return _reading_order(layout)


def _balance(heights: list[int], count: int) -> list[list[int]]:
    """Boxes split over ``count`` columns in reading order, the tallest column as short as possible."""
    if count <= 1:
        return [list(range(len(heights)))]
    low, high = max(heights), sum(heights)
    while low < high:  # the smallest height that fits
        limit = (low + high) // 2
        columns, used = 1, 0
        for height in heights:
            if used and used + height > limit:
                columns, used = columns + 1, 0
            used += height
        low, high = (low, limit) if columns <= count else (limit + 1, high)
    out: list[list[int]] = [[]]
    used = 0
    for position, height in enumerate(heights):
        if used and used + height > low and len(out) < count:
            out.append([])
            used = 0
        out[-1].append(position)
        used += height
    return out
