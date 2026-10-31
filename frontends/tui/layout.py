"""Blocks to terminal rows: pure text layout, no curses."""

from __future__ import annotations

from dataclasses import dataclass, field

from .content import (
    Block,
    Buttons,
    Chart,
    Choice,
    Columns,
    Field,
    Gap,
    Grid,
    Heading,
    Legend,
    Meter,
    Note,
    Pad,
    Panel,
    Raw,
    Slider,
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


def _framed(inner: Layout, width: int, glyphs: Glyphs, tone: str, head: list[tuple[str, str]],
            head_owners: list[int | None] | None = None) -> Layout:
    """``inner`` inside a box ``width`` wide; ``head`` is its top edge (title, badge, button)."""
    box = Layout()
    box.rows.append(Row(head, owners=head_owners or [None] * len(head)))
    body = Layout()
    _side_by_side(body, [inner], [width - 4])
    box.choices, box.choice_rows = body.choices, [row + 1 for row in body.choice_rows]
    for row in body.rows:
        box.rows.append(Row([(glyphs.v + " ", tone)] + row.spans + [(" " + glyphs.v, tone)],
                            owners=[None] + row.owned() + [None], cells=[(a + 2, b + 2, r, c) for a, b, r, c in row.cells]))
    box.rows.append(Row([(glyphs.bottom[0] + glyphs.h * (width - 2) + glyphs.bottom[2], tone)]))
    return box


def _edge(glyphs: Glyphs, width: int, tone: str, left: list[tuple[str, str]], right: list[tuple[str, str]]):
    """A box's top edge: ``┌─ left ──── right ─┐``, the spans cut to fit."""
    room = width - 7 - sum(cell_width(text) for text, _tone in right)
    title = [(clip(text, max(1, room)), t) for text, t in left]
    fill = width - 6 - sum(cell_width(text) for text, _tone in title + right)
    return [(glyphs.top[0] + glyphs.h + " ", tone)] + title + [(" " + glyphs.h * max(0, fill), tone)] \
        + right + [(glyphs.h + glyphs.top[2], tone)]


def button_spans(choice: Choice, glyphs: Glyphs, width: int, fill: bool = False) -> list[tuple[str, str]]:
    """A compact terminal action: primary/danger emphasis; else ``[ label ]``.

    ``fill`` aligns adjacent actions to their allocated columns.
    """
    tone = "dim" if not choice.enabled else {"primary": "accent", "": "accent"}.get(choice.tone, choice.tone)
    if glyphs.rule == "─" and choice.enabled and choice.tone in ("primary", "bad"):
        text = f" {clip(choice.label, width - 4)} "
        return [(text.center(width) if fill else text, "btn:" + tone)]
    text = clip(choice.label, width - 4)
    return [(f"[{f' {text} '.center(width - 2)}]" if fill else f"[ {text} ]", tone)]


def _columns(blocks, width: int, label_cap: int) -> tuple[int, int]:
    """(label width, value-text width) for ``blocks``: the two columns every row lines up on."""
    label_width = min(label_cap, max(12, width // 2), max(
        [cell_width(b.label) for b in blocks if isinstance(b, (Field, Meter, Trend, Track)) or (
            isinstance(b, Choice) and b.detail)] + [8]))
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
                _side_by_side(layout, parts, [each] * len(group), " | " if glyphs.rule == "-" else " │ ")
                add([("", "")])
        elif isinstance(block, Chart):
            for spans in chart_rows(block, width, glyphs):
                add(spans)
        elif isinstance(block, Pad):
            index = len(layout.choices)
            layout.choices.append(Choice("", block.toggle, pad=block))
            layout.choice_rows.append(len(layout.rows))
            cols = len(block.headers)
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
            widths = [name_w] + [cell_w] * cols + [tail_w]
            g = glyphs

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
            heads = [str(text).split("\n") for text in [block.corner, *block.headers, block.tail_header]]
            for level in range(max(len(head) for head in heads)):
                line([head[level] if level < len(head) else "" for head in heads], ["" if level == 0 else "dim"] * (cols + 2))
            rule(g.mid)
            for r, prow in enumerate(block.rows):  # the token says the state, the colour repeats it
                tones = ["accent"] + [("sel" if (r, c) == block.cursor else cell.tone) for c, cell in enumerate(prow.cells)]
                line([prow.name] + [cell.text for cell in prow.cells] + [prow.tail], tones + [prow.tail_tone], r)
                if notes and any(cell.note for cell in prow.cells):
                    line([""] + [cell.note for cell in prow.cells] + [""], [""] + tones[1:] + [""], r)
            rule(g.bottom)
        elif isinstance(block, Panel):
            tone = "bad" if block.danger else "dim"
            inner = build_layout(([Note(block.subtitle, "dim")] if block.subtitle else []) + list(block.blocks),
                                 width - 4, glyphs, label_cap)
            action = button_spans(block.action, glyphs, width // 3) if block.action else []
            right = ([(f" {block.badge} ", "btn:" + block.badge_tone)] if block.badge else []) \
                + ([(" ", "")] if block.badge and action else []) + action
            head = _edge(glyphs, width, tone, [(block.title, ("bad" if block.danger else "accent") + "!")], right)
            owners = [None] * (len(head) - 1 - len(action)) + [len(inner.choices)] * len(action) + [None]
            if action:
                inner.choices.append(block.action)
                inner.choice_rows.append(-1)  # the title row, once framed
            box = _framed(inner, width, glyphs, tone, head, owners)
            _side_by_side(layout, [box], [width])
        elif isinstance(block, Tiles):
            count = len(block.tiles)
            fit = max(1, min(count, (width + 1) // (block.minimum + 1)))
            each = (width - (fit - 1)) // fit
            for first in range(0, count, fit):
                boxes = []
                for tile in block.tiles[first:first + fit]:
                    box = Layout()
                    tone = "accent" if tile.active else "dim"
                    own = 0 if tile.handler else None
                    if tile.handler:
                        box.choices.append(Choice(tile.label, tile.handler))
                        box.choice_rows.append(0)
                    if tile.edit:  # the pencil sits on the bottom edge, so the name keeps the top one
                        box.choices.append(Choice(tile.edit_label, tile.edit))
                    box.rows.append(Row(_edge(glyphs, each, tone, [(tile.label, "dim")], []), owners=None,
                                        choice=own))
                    lines = [(tile.value, (tile.tone or "") + "!")]
                    if any(item.hint for item in block.tiles[first:first + fit]):
                        lines.append((tile.hint, "dim"))
                    for text, line_tone in lines:
                        box.rows.append(Row([(glyphs.v + " ", tone), (pad(text, each - 4), line_tone), (" " + glyphs.v, tone)],
                                            owners=[own] * 3))
                    label = clip(tile.edit_label, each - 6) if tile.edit else ""
                    fill = glyphs.h * (each - 2 - (cell_width(label) + 3 if label else 0))
                    bottom = [(glyphs.bottom[0] + fill, tone)] + ([(f" {label} ", "accent"), (glyphs.h, tone)] if label else []) \
                        + [(glyphs.bottom[2], tone)]
                    pen = len(box.choices) - 1 if tile.edit else own
                    box.rows.append(Row(bottom, owners=[own] + ([pen, own] if label else []) + [own]))
                    if tile.edit:
                        box.choice_rows.append(len(box.rows) - 1)
                    boxes.append(box)
                _side_by_side(layout, boxes, [each] * len(boxes), " ")
        elif isinstance(block, Buttons):  # the row shared out, as the desktop's; one a row on a phone
            needs = [cell_width(choice.label) + 4 for choice in block.choices]
            fit = next(k for k in range(len(needs), 0, -1)
                                       if k == 1 or all(sum(needs[i:i + k]) + 2 * (k - 1) <= width
                                                        for i in range(0, len(needs), k)))
            for first in range(0, len(block.choices), fit):
                group = needs[first:first + fit]
                spare = max(0, width - sum(group) - 2 * (len(group) - 1))
                spans, owners = [], []
                for position, choice in enumerate(block.choices[first:first + fit]):
                    if spans:
                        spans.append(("  ", ""))
                        owners.append(None)
                    layout.choices.append(choice)
                    layout.choice_rows.append(len(layout.rows))
                    each = group[position] + spare // len(group) + (spare % len(group) if position == len(group) - 1 else 0)
                    parts = button_spans(choice, glyphs, min(width, each), fill=True)
                    spans += parts
                    owners += [len(layout.choices) - 1] * len(parts)
                layout.rows.append(Row(spans, owners=owners))
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
                    cells.append(("●" if glyphs.rule == "─" else "O", "accent"))
                elif at[first] < x < at[last]:
                    cells.append((glyphs.fill, "accent"))
                elif x in at:
                    cells.append(("┼" if glyphs.rule == "─" else "+", "bad" if hot else "dim"))
                else:
                    cells.append((glyphs.rule, "bad" if hot else "dim"))
            add(_runs(cells))
            for parity in (0, 1):
                line = [(" ", "")] * width
                for index in range(parity, len(stops), 2):
                    text = str(stops[index])
                    begin = max(0, min(width - len(text), at[index] - len(text) // 2))
                    if all(char == " " for char, _tone in line[max(0, begin - 1):begin + len(text) + 1]):  # never touch
                        line[begin:begin + len(text)] = [(char, "bad" if red[index] else "dim") for char in text]
                add(_runs(line))
        elif isinstance(block, Legend):
            spans, used = [], 0
            for chip, meaning, tone in block.items:
                size = cell_width(chip) + cell_width(meaning) + 6
                if spans and used + size > width:
                    add(spans)
                    spans, used = [], 0
                spans += [(f" {chip} ", "btn:" + tone), (f" {meaning}   ", "dim")]
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
            label = (pad(block.label, label_width + 2) if cell_width(block.label) <= label_width
                     else block.label + "  ") if detail else clip(block.label, width)
            tone = block.tone if block.enabled else "dim"
            # A button does something; "( )"/"[x]" are options and "›" opens a menu of its own.
            button = not (detail or block.adjust or block.label.startswith(("(", "[")) or block.label.endswith("›"))
            if button:  # it does something, it is not a value
                add(button_spans(block, glyphs, width), choice=index)
            else:
                chip = f" {block.badge} " if block.badge else ""
                room = max(0, width - cell_width(label) - cell_width(chip) - (1 if chip else 0))
                text = clip(detail, room)
                spans = [(label, tone), (text, "accent" if block.adjust else "dim")]
                if chip:
                    spans += [(" " * (room - cell_width(text) + 1), ""), (chip, "btn:" + block.badge_tone)]
                add(spans, choice=index)
    return layout
