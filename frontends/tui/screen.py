"""Keyboard-first curses interface for a physical TTY or SSH terminal."""

from __future__ import annotations

import contextlib
import curses
import locale
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from bc250cc.shared.failure_text import describe_failure

from .console import Console
from .content import cell_width, clip, number, pad, wrap
from .i18n import tr, tr_format
from .keys import ALIASES, name_of
from .layout import Glyphs, Layout, build_layout
from .pointer import PointerSupport, character_at
from .runtime import Context, Poller, describe_error
from .support import available_version, report

MIN_WIDTH, MIN_HEIGHT = 60, 14
TOAST_SECONDS = 6.0
TONE_PAIRS = {"ok": 1, "warn": 2, "bad": 3, "accent": 4}
#: The desktop sidebar: its groups, in its order.
SIDEBAR = (("", ("dashboard",)), ("Hardware", ("cpu", "cu", "gpu", "extras")),
           ("Monitoring", ("performance", "fans", "processes")), ("System", ("black_box", "remote")),
           ("", ("firmware", "settings")))
SIDEBAR_ORDER = tuple(key for _group, keys in SIDEBAR for key in keys)
SHORTCUTS = dict(zip("1234567890.,", ("dashboard", "cpu", "cu", "gpu", "extras", "performance", "fans",
                                    "processes", "black_box", "firmware", "remote", "settings")))
#: Keys a running command receives as a terminal would send them.
PTY_KEYS = {"enter": b"\r", "backspace": b"\x7f", "tab": b"\t", "esc": b"\x1b", "space": b" ", "up": b"\x1b[A",
            "down": b"\x1b[B", "right": b"\x1b[C", "left": b"\x1b[D", "delete": b"\x1b[3~"}
SPINNER = ("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏", "|/-\\")
EMBEDDED_TERMINAL_NAME = "bc250-tui-console"
SCROLLBACK_ALL = 10**6

#: One-for-one replacements (same column width) for terminals without Unicode.
ASCII_MAP = str.maketrans({
    "…": ".", "·": "-", "│": "|", "─": "-", "┌": "+", "┐": "+", "└": "+", "┘": "+", "├": "+", "┤": "+", "┬": "+",
    "┴": "+", "┼": "+", "▲": "^", "▼": "v", "↑": "^", "↓": "v", "→": ">", "←": "<", "–": "-", "—": "-", "▏": "_", "›": ">",
    "•": "*", "█": "#", "░": "-", "━": "=", "┃": "#", "▴": "^", "▾": "v", "●": "*", "°": "o", "✓": "+", "✗": "x",
})


class Quit(Exception):
    pass


def detect_light_background(environ=None) -> bool:
    """COLORFGBG ('fg;bg') says whether the terminal is light; unknown is dark."""
    value = (environ or os.environ).get("COLORFGBG", "")
    try:
        return int(value.rsplit(";", 1)[-1]) in (7, 15)
    except ValueError:
        return False


class Screen(PointerSupport):
    """Draws the interface and answers the pages' requests (the ``UI`` contract)."""

    def __init__(
        self, stdscr, ctx: Context, pages: dict[str, Any], poller: Poller | None = None,
        *, theme: str = "auto", order: tuple[str, ...] = SIDEBAR_ORDER,
        foreground: Callable[[str, Callable[[], Any]], tuple[bool, Any]] | None = None,
    ) -> None:
        self.stdscr = stdscr
        self.ctx = ctx
        self.pages = pages
        self.poller = poller
        self.order = tuple(key for key in order if key in pages)
        self.focus = "sidebar"
        self.section = 0
        self.tab: dict[str, str] = {}
        self.cursor: dict[tuple[str, str], int] = {}
        self.scroll: dict[tuple[str, str], int] = {}
        self.toast: tuple[str, str, float] | None = None
        self.unicode = self._unicode_ok()
        self.glyphs = Glyphs.for_terminal(unicode_ok=self.unicode)
        self.attrs: dict[str, int] = {}
        self._foreground = foreground  # tests run work directly through this
        self.active_console: Console | None = None
        self.console_scroll = 0
        self._layout: Layout | None = None
        self._rendered_layout: Layout | None = None
        self._rendered_data = None
        self._rendered_slot = None
        self._layout_key: tuple | None = None
        # What the last draw put where, for the mouse: y -> page index / choice index, tab spans.
        self._sidebar_at: dict[int, int] = {}
        self._choice_at: dict[int, list[tuple[int, int, int]]] = {}  # y -> (x0, x1, choice index)
        self._cells_at: dict[int, list[tuple[int, int, int, int]]] = {}  # y -> Pad cells (x0, x1, row, column)
        self._tab_at: list[tuple[int, int, str]] = []
        self._hits: list[tuple[int, int, int, str]] = []  # (y, x from, x to, key): legacy row geometry
        self._row_at: dict[int, tuple[int, str]] = {}  # y -> (x, text) of a drawn item, for terminal row inspection
        self._pointer_drag = None
        self._geometry_size = self.size()
        self._reset_pointer_regions()
        self.apply_theme(theme)
        if self.poller:
            self.poller.show(self.order[self.section], self._tab_key())

    # ------------------------------------------------------------ set-up

    @staticmethod
    def _unicode_ok() -> bool:
        encoding = (locale.getpreferredencoding(False) or "").upper().replace("-", "")
        return "UTF8" in encoding and os.environ.get("TERM", "") != "linux"

    def apply_theme(self, theme: str) -> None:
        self.theme = theme
        colour = theme != "mono" and "NO_COLOR" not in os.environ
        try:
            colour = colour and curses.has_colors()
        except curses.error:  # curses was not started (tests)
            colour = False
        light = theme == "light" or (theme == "auto" and detect_light_background())
        attrs = {"": curses.A_NORMAL, "dim": curses.A_DIM, "accent": curses.A_BOLD, "sel": curses.A_REVERSE | curses.A_BOLD,
                 "ok": curses.A_NORMAL, "warn": curses.A_BOLD, "bad": curses.A_BOLD | curses.A_UNDERLINE}
        if colour:
            try:
                curses.use_default_colors()
                palette = {1: curses.COLOR_GREEN, 2: curses.COLOR_MAGENTA if light else curses.COLOR_YELLOW,
                           3: curses.COLOR_RED, 4: curses.COLOR_BLUE if light else curses.COLOR_CYAN}
                for pair, color in palette.items():
                    curses.init_pair(pair, color, -1)  # -1: the terminal's own background
                for tone, pair in TONE_PAIRS.items():
                    attrs[tone] = curses.color_pair(pair) | (curses.A_BOLD if tone in ("accent", "bad") else 0)
                if curses.COLORS >= 256:  # softer tones, and buttons filled the way the desktop fills them
                    text = (28, 130, 160, 61) if light else (114, 221, 210, 147)
                    fills = {"ok": 29, "warn": 136, "bad": 167, "accent": 62, "dim": 240}
                    for (tone, pair), color in zip(TONE_PAIRS.items(), text):
                        curses.init_pair(pair, color, -1)
                    for offset, (tone, color) in enumerate(fills.items()):
                        curses.init_pair(10 + offset, 255, color)
                        curses.init_pair(20 + offset, color, -1)
                        attrs["btn:" + tone] = curses.color_pair(10 + offset)
                        attrs["edge:" + tone] = curses.color_pair(20 + offset)
                    curses.init_pair(30, 243 if light else 246, -1)  # secondary text: grey, not the font's dim
                    attrs["dim"] = curses.color_pair(30)
            except curses.error:
                pass
        self.attrs = attrs

    # ----------------------------------------------------------- helpers

    @property
    def page_key(self) -> str:
        return self.order[self.section]

    @property
    def page(self):
        return self.pages[self.page_key]

    def _tabs(self) -> list[tuple[str, str]]:
        return self.page.tabs(self.ctx)

    def _tab_key(self) -> str:
        tabs = self._tabs()
        if not tabs:
            return ""
        current = self.tab.get(self.page_key)
        return current if current in dict(tabs) else tabs[0][0]

    def _slot(self) -> tuple[str, str]:
        return self.page_key, self._tab_key()

    def size(self) -> tuple[int, int]:
        return self.stdscr.getmaxyx()

    def put(self, y: int, x: int, text: str, attr: int = 0, limit: int | None = None) -> None:
        height, width = self.size()
        if not 0 <= y < height or x >= width:
            return
        room = (width - x) if limit is None else min(limit, width - x)
        if y == height - 1:
            room -= 1  # curses cannot write the bottom-right cell
        text = clip(text, room) if cell_width(text) > room else text
        if not self.unicode:
            text = text.translate(ASCII_MAP)
        try:
            self.stdscr.addstr(y, x, text, attr)
        except curses.error:
            pass

    def notify(self, message: str, tone: str = "") -> None:
        self.toast = (message, tone, time.monotonic() + TOAST_SECONDS)

    def refresh(self) -> None:
        """Read everything again now, including what pages only poll every few seconds."""
        self._layout_key = None
        with self.ctx.lock:
            for state in self.ctx.page_state.values():
                for key in [key for key in state if key.endswith("_at")]:
                    del state[key]
        if self.poller:
            self.poller.refresh()


    def _bottom(self) -> int:
        return 1

    def sidebar_width(self, width: int) -> int:
        longest = max(cell_width(tr(self.pages[key].title)) for key in self.order) + 5
        return max(16, min(longest, width // 3))

    def _content_box(self) -> tuple[int, int]:
        """(x, width) of the content text: after the sidebar, its rule and the cursor column."""
        width = self.size()[1]
        x = self.sidebar_width(width) + 4
        return x, max(20, width - x - 1)

    # -------------------------------------------------------------- draw

    def build(self) -> Layout:
        content_width = self._content_box()[1]
        tab = self._tab_key()
        with self.ctx.lock:
            data = self.ctx.page_data.get(self.page_key)
            state = self.ctx.page_state.get(self.page_key)
            key = (self.page_key, tab, content_width, id(data), len(self.ctx.history.get("gpu_clock", ())),
                   self.ctx.metrics_error, self.ctx.page_error.get(self.page_key), id(self.ctx.metrics),
                   hash(repr(sorted(state.items()))) if state else 0)
            if key == self._layout_key and self._layout is not None:
                return self._layout
            try:
                blocks = self.page.build(self.ctx, data, tab, self)
            except Exception as error:
                from .content import Note

                blocks = [Note(describe_error(error), "bad")]
        self._layout = build_layout(blocks, content_width, self.glyphs)
        self._layout_key = key
        return self._layout

    def draw(self) -> None:
        height, width = self.size()
        self.stdscr.erase()
        self._geometry_size = (height, width)
        self._reset_pointer_regions()
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            text = tr("The terminal is too small ({width}x{height}); it needs at least {min_width}x{min_height}.").format(
                width=width, height=height, min_width=MIN_WIDTH, min_height=MIN_HEIGHT)
            for index, line in enumerate(wrap(text, max(10, width - 2))):
                self.put(index, 1, line, self.attrs["warn"])
            self.stdscr.noutrefresh()
            return
        self._hits, self._row_at = [], {}
        self._draw_title(width)
        self._draw_sidebar(height, self.sidebar_width(width))
        console = self.active_console
        if console is not None:
            self._draw_console(console, height, width)
        else:
            self._draw_content(height, width)
            self._draw_footer(height, width)
        self.stdscr.noutrefresh()


    def _draw_title(self, width: int) -> None:
        metrics = self.ctx.metrics or {}
        gpu, cpu = metrics.get("gpu") or {}, metrics.get("cpu") or {}
        status = (f"GPU {number(gpu.get('frequency_mhz'), 'MHz')} {number(gpu.get('temperature_c'), '°C')}   "
                  f"CPU {number(cpu.get('frequency_mhz'), 'MHz')} {number(cpu.get('temperature_c'), '°C')} ")
        title = " BC250 Control Center"
        version = available_version(self.ctx)
        if version:  # the desktop's update badge: Settings › About installs it
            title += "   ↑ " + tr_format("Version {version} is available", version=version)
        gap = width - cell_width(title) - cell_width(status)
        self.put(0, 0, title + " " * gap + status if gap > 1 else pad(title, width), curses.A_REVERSE | curses.A_BOLD)

    def _draw_sidebar(self, height: int, side: int) -> None:
        self._sidebar_at = {}
        pinned = [key for key in ("firmware", "settings") if key in self.order]
        entries = []
        for group, keys in SIDEBAR:
            available = [key for key in keys if key in self.order and key not in pinned]
            if group and available:
                entries.append((None, tr(group).upper()))
            entries.extend((self.order.index(key), tr(self.pages[key].title)) for key in available)
        view = max(1, height - 6)
        selected = next((i for i, (index, _) in enumerate(entries) if index == self.section), 0)
        offset = max(0, min(selected - view + 1, len(entries) - view))

        def entry(y, index, label):
            shortcut = next((hotkey for hotkey, key in SHORTCUTS.items() if key == self.order[index]), " ")
            text = pad(f" {shortcut} {label}", side)
            attr = self.attrs["sel"] if index == self.section and self.focus == "sidebar" else \
                self.attrs["accent"] if index == self.section else 0
            self.put(y, 0, text, attr)
            self._sidebar_at[y] = index

        for y, (index, label) in enumerate(entries[offset:offset + view], 2):
            if index is None:
                self.put(y, 1, label, self.attrs["dim"], side - 2)
            else:
                entry(y, index, label)
        for key, y in (("firmware", height - 4), ("settings", height - 2)):
            if key in self.order:
                entry(y, self.order.index(key), tr(self.pages[key].title))
        self.put(height - 3, 1, self.glyphs.rule * max(0, side - 2), self.attrs["dim"])
        for row in range(1, height - 1):
            self.put(row, side, self.glyphs.v, self.attrs["dim"])

    def _draw_tabs(self, x: int, width: int) -> int:
        """The tab strip; returns the first row below it."""
        self._tab_at = []
        tabs = self._tabs()
        row = 1
        if not tabs:
            return row
        column, current = x, self._tab_key()
        keys = [key for key, _label in tabs]
        while sum(cell_width(label) + 3 for _key, label in tabs[:keys.index(current) + 1]) > width - x and len(tabs) > 1 \
                and tabs[0][0] != current:
            tabs, keys = tabs[1:], keys[1:]  # the strip scrolls so the open tab is never cut off
        for key, label in tabs:
            text = f" {label} "
            selected = key == current
            attr = (self.attrs["sel"] if self.focus == "content" else self.attrs["accent"] | curses.A_REVERSE) \
                if selected else self.attrs["dim"]
            self.put(row, column, text, attr, width - column)
            self._hits.append((row, column, column + cell_width(text), f"tab:{key}"))
            column += cell_width(text) + 1
        self.put(row + 1, x, self.glyphs.h * max(0, width - x - 1), self.attrs["dim"])
        return row + 2

    def _view(self) -> int:
        """Rows the content has between the tab strip and the foot."""
        return self.size()[0] - (1 + 2 * bool(self._tabs())) - self._bottom()

    def _draw_content(self, height: int, width: int) -> None:
        x, _content_width = self._content_box()
        top = self._draw_tabs(x - 2, width)
        layout = self.build()
        self._rendered_layout = layout
        self._rendered_data = self.ctx.page_data.get(self.page_key)
        self._rendered_slot = self._slot()
        view, slot = height - top - self._bottom(), self._slot()
        cursor = self.cursor.get(slot, 0)
        offset = max(0, min(self.scroll.get(slot, 0), max(0, len(layout.rows) - view)))
        self.scroll[slot] = offset
        self._choice_at, self._cells_at = {}, {}
        for line, row in enumerate(layout.rows[offset:offset + view]):
            y = top + line
            owners = row.owned()
            if row.choice is not None:
                first = line == 0 or layout.rows[offset + line - 1].choice != row.choice
                if row.choice == cursor and self.focus == "content" and first:
                    self.put(y, x - 2, self.glyphs.cursor, self.attrs["accent"])
            if any(owner is not None for owner in owners):
                self._row_at[y] = (x, "".join(text for text, _tone in row.spans))
            self._cells_at[y] = [(x + a, x + b, r, c) for a, b, r, c in row.cells]
            column = x
            for (text, tone), owner in zip(row.spans, owners):
                width_ = cell_width(text)
                if owner is not None:
                    index = owner if owner >= 0 else -1 - owner
                    self._choice_at.setdefault(y, []).append((column, column + width_, index))
                selected = owner is not None and owner == cursor and self.focus == "content"  # a plain owner is < 0
                bold = row.bold or tone.endswith("!")
                tone = tone.rstrip("!")
                if tone.startswith("btn:"):  # a filled button or badge: white words on its colour
                    own = self.attrs.get(tone)
                    attr = (own if own is not None else self.attrs.get(tone[4:], 0) | curses.A_REVERSE) | curses.A_BOLD
                    attr ^= curses.A_REVERSE if selected else 0
                elif tone.startswith("edge:"):  # legacy edge emphasis
                    attr = self.attrs.get(tone, self.attrs.get(tone[5:], 0))
                else:
                    attr = self.attrs.get(tone, 0) | (curses.A_BOLD if bold else 0) | (curses.A_REVERSE if selected else 0)
                    if tone == "sel" and self.focus != "content":
                        attr = self.attrs["accent"]
                self.put(y, column, text, attr, limit=width - column - 1)
                column += width_
        if len(layout.rows) > view:  # a scrollbar: the thumb is where this view sits on the page
            size = max(1, view * view // len(layout.rows))
            start = round(offset * (view - size) / max(1, len(layout.rows) - view))
            self._scroll_track = ("content", width - 1, top, view, size, len(layout.rows) - view, offset)
            for line in range(view):
                thumb = start <= line < start + size
                self.put(top + line, width - 1, "┃" if thumb else self.glyphs.v,
                         self.attrs["accent" if thumb else "dim"])

    def _hints(self) -> list[tuple[str, str]]:
        if self.focus == "sidebar":
            return [("↑↓", "Move"), ("Enter", "Open"), ("F2", "Go to section"), ("/", "Search"), ("?", "Help"),
                    ("q", "Quit")]
        choice = self.current_choice()
        hints = [("↑↓", "Move")]
        if choice is not None and choice.adjust:
            hints.append(("←→", "Adjust"))
        if choice is not None and (choice.handler or choice.pad):
            hints.append(("Enter", "Select" if choice.pad else "Open"))
        if self._tabs():
            hints.append(("[ ] F3", "Views"))
        return hints + [("Esc", "Back"), ("?", "Help")]

    def _draw_footer(self, height: int, width: int) -> None:
        if self.toast and self.toast[2] > time.monotonic():  # over the keys for its few seconds
            self.put(height - 1, 1, pad(self.toast[0], width - 2), self.attrs.get(self.toast[1], 0) | curses.A_BOLD)
        else:
            self._draw_hints(self._hints())

    def _draw_hints(self, hints: list[tuple[str, str]], tail: str = "", tail_attr: int = 0, *, y: int = -1) -> None:
        """A row of keys in the accent colour with what they do dimmed (the bottom row by default).

        Hints remain plain keyboard instructions; no pointer targets are enabled.
        """
        height, width = self.size()
        y = height - 1 if y < 0 else y
        column = 1
        for key, label in hints:
            text = tr(label)
            if column + cell_width(key) + cell_width(text) + 3 >= width:
                break
            self.put(y, column, key, self.attrs["accent"])
            self.put(y, column + cell_width(key) + 1, text, self.attrs["dim"])
            command = {"↑↓": "down", "Enter": "enter", "Esc": "esc", "F2": "f2", "F3": "f3",
                       "[ ] F3": "f3", "Enter Esc": "enter", "Esc Ctrl+C": "esc", "PgUp": "pgup",
                       "PgDn": "pgdn"}.get(key, key if len(key) == 1 else "")
            if command:
                self._hits.append((y, column, min(width, column + cell_width(key) + 1 + cell_width(text)), command))
            column += cell_width(key) + cell_width(text) + 3
        self.put(y, column, tail, tail_attr)

    def _console_size(self) -> tuple[int, int]:
        rows = self.size()[0] - 3 - self._bottom()
        return max(1, rows), self._content_box()[1] + 2

    def _draw_console(self, console: Console, height: int, width: int) -> None:
        x, content_width = self._content_box()[0] - 2, self._console_size()[1]
        done = console.done.is_set()
        if not done:
            frames = SPINNER[0 if self.unicode else 1]
            mark, tone = frames[int(time.monotonic() * 8) % len(frames)], "accent"
        else:
            mark, tone = ("✓", "ok") if console.succeeded else ("✗", "bad")
        elapsed = int((console.finished_at or time.monotonic()) - console.started)
        clock = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
        status = (tr("Completed") if console.succeeded else tr("The workflow did not finish successfully.")) if done else ""
        # Top: what ran, how it ended and how long it took; below it, where the full log is.
        top = 1
        self.put(top, x, f"{mark} {console.label}" + (f"  ·  {status}" if status else ""), self.attrs[tone] | curses.A_BOLD,
                 content_width - 8)
        self.put(top, width - 1 - len(clock), clock, self.attrs["dim"])
        home = os.path.expanduser("~")
        log = f"{tr('Full log saved to')} {console.log_file.replace(home, '~', 1)}" if console.log_file else ""
        rule = clip(log, content_width) if log else ""
        self.put(top + 1, x, rule + self.glyphs.h * (content_width - cell_width(rule)), self.attrs["dim"])
        view = self._console_size()[0]
        console.resize(view, content_width)
        lines, self.console_scroll = console.view(view, self.console_scroll)
        for index, runs in enumerate(lines):
            column = x
            for text, run_tone, bold in runs:
                self.put(top + 2 + index, column, text, self.attrs.get(run_tone, 0) | (curses.A_BOLD if bold else 0),
                         limit=width - column - 1)
                column += cell_width(text)
        total = console.line_count()
        if total > view:
            thumb = max(1, view * view // total)
            maximum = total - view
            offset = maximum - self.console_scroll
            start = round(offset * (view - thumb) / max(1, maximum))
            self._scroll_track = ("console", width - 1, top + 2, view, thumb, maximum, offset)
            for line in range(view):
                self.put(top + 2 + line, width - 1, "┃" if start <= line < start + thumb else self.glyphs.v,
                         self.attrs["accent" if start <= line < start + thumb else "dim"])
        hints = [("Enter Esc", "Close")] if done else [("Esc Ctrl+C", "Cancel")]
        if done and not console.succeeded:
            hints.append(("r", "Report this problem"))
        self._draw_hints(hints + [("PgUp", "Scroll"), ("PgDn", "Scroll")], y=height - self._bottom())

    # ------------------------------------------------------------- input

    def current_choice(self):
        """The selected item, if it is on screen: nothing off screen is ever acted on."""
        layout, slot = self.build(), self._slot()
        index = self.cursor.get(slot, 0)
        return layout.choices[index] if self._shown(layout, slot, index) else None

    def _getch(self) -> int:
        reader = getattr(self.stdscr, "get_wch", None)
        if reader is None:
            return self.stdscr.getch()
        try:
            value = reader()
        except curses.error:
            return -1
        return ord(value) if isinstance(value, str) else value

    def handle(self, code: int) -> None:
        if code == 12:
            self._repaint()
            return
        if code == 3:
            raise Quit
        self.handle_key(ALIASES.get(name_of(code), name_of(code)))

    def handle_key(self, key: str) -> None:
        """One normalized keyboard event."""
        if key in ("menu", "f2"):
            self.section_menu()
        elif key.startswith("go:"):
            self._go(int(key[3:]))
        elif key.startswith("tab:"):
            self._switch_tab(0, key[4:])
        elif key == "resize":
            self._layout_key = None
        elif key == "mouse":
            self._mouse()
        elif key == "q":
            raise Quit
        elif key == "?":
            self.show_text(tr("Keyboard shortcuts"), self.help_text(), compact=True)
        elif key == "r":
            self.refresh()
            self.notify(tr("Refreshing…"))
        elif key == "/":
            self.search()
        elif key == "f3":
            self.tab_menu()
        elif key == "f6":
            self._focus("content" if self.focus == "sidebar" else "sidebar")
        elif key == "tab":
            self._focus("content") if self.focus == "sidebar" else self._next_choice(1)
        elif key == "btab":
            self._next_choice(-1) if self.focus == "content" else self._focus("content")
        elif key in ("[", "]"):
            self._switch_tab(-1 if key == "[" else 1)
        elif key in SHORTCUTS:
            target = SHORTCUTS[key]
            if target in self.order:
                self._go(self.order.index(target))
        else:
            (self._sidebar_key if self.focus == "sidebar" else self._content_key)(key)

    def _focus(self, where: str) -> None:
        """Move between the panes; entering the content picks the first item in view."""
        if where == "content" and self.focus != "content":
            layout, slot = self.build(), self._slot()
            if not self._shown(layout, slot, self.cursor.get(slot, 0)):
                self.cursor[slot] = self._first_shown(layout, slot, 1)
        self.focus = where

    def _shown(self, layout: Layout, slot, index: int) -> bool:
        offset = self.scroll.get(slot, 0)
        return 0 <= index < len(layout.choice_rows) and offset <= layout.choice_rows[index] < offset + self._view()

    def _first_shown(self, layout: Layout, slot, direction: int) -> int:
        """The first item in view from the top (or bottom); -1 when none is."""
        indexes = range(len(layout.choices)) if direction > 0 else range(len(layout.choices) - 1, -1, -1)
        return next((index for index in indexes if self._shown(layout, slot, index)), -1)

    def _reveal(self, slot, row: int) -> None:
        offset, view = self.scroll.get(slot, 0), self._view()
        self.scroll[slot] = row if row < offset else row - view + 1 if row >= offset + view else offset

    def _step(self, layout: Layout, slot, step: int) -> None:
        """Arrows move between items in view and scroll the page past rows that have none.

        A long page (the dashboard's cards) is read by scrolling; the cursor
        never jumps off screen to the next button, and Enter only acts on an
        item that can be seen.
        """
        cursor = self.cursor.get(slot, -1)
        target = cursor + step if self._shown(layout, slot, cursor) else self._first_shown(layout, slot, step)
        if abs(step) == 1 and 0 <= target < len(layout.choices):
            row, offset = layout.choice_rows[target], self.scroll.get(slot, 0)
            if offset - 1 <= row <= offset + self._view():  # in view, or on the line just past its edge
                self.cursor[slot] = target
                self._reveal(slot, row)
                return
        limit = max(0, len(layout.rows) - self._view())
        self.scroll[slot] = max(0, min(limit, self.scroll.get(slot, 0) + step))
        if not self._shown(layout, slot, self.cursor.get(slot, -1)):
            self.cursor[slot] = self._first_shown(layout, slot, step)


    def _go(self, index: int, *, remember: bool = True) -> None:
        index = max(0, min(len(self.order) - 1, index))
        self.section = index
        self._layout_key = None
        self._repaint()
        if self.poller:
            self.poller.show(self.page_key, self._tab_key())

    def show_tab(self, key: str) -> None:
        """Open a tab of the page on screen (a button that leads to it, as "Open laboratory")."""
        self._switch_tab(0, key)

    def goto(self, page_key: str) -> None:
        if page_key in self.order:
            self._go(self.order.index(page_key))

    def _sidebar_key(self, key: str) -> None:
        moves = {"up": self.section - 1, "down": self.section + 1, "home": 0, "end": len(self.order) - 1}
        if key in moves:
            self._go(moves[key])
        elif key in ("enter", "right", "space"):
            self._focus("content")

    def _switch_tab(self, step: int, to: str | None = None) -> None:
        keys = [name for name, _label in self._tabs()]
        if not keys:
            return
        self.tab[self.page_key] = to if to in keys else keys[(keys.index(self._tab_key()) + step) % len(keys)]
        self._layout_key = None
        if self.poller:
            self.poller.show(self.page_key, self.tab[self.page_key])

    def _repaint(self) -> None:
        """Ask curses to redraw every cell, so stale ones cannot linger in the terminal."""
        with contextlib.suppress(AttributeError, curses.error):
            self.stdscr.clearok(True)

    def _activate(self, choice) -> None:
        if not (choice.enabled and choice.handler is not None):
            return
        try:
            choice.handler(self)
        except Quit:
            raise
        except Exception as error:
            self.notify(describe_error(error), "bad")
        self._layout_key = None

    def _content_key(self, key: str) -> None:
        layout = self.build()
        slot = self._slot()
        current = self.current_choice()
        view = max(1, self._view() - 1)
        if current is not None and current.pad is not None:
            step = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}.get(key)
            if step and current.pad.move(*step):
                self._layout_key = None
                return
        sibling = self.cursor.get(slot, 0) + (1 if key == "right" else -1)
        if key in ("left", "right") and current is not None and not current.adjust and current.pad is None \
                and 0 <= sibling < len(layout.choices) \
                and layout.choice_rows[sibling] == layout.choice_rows[self.cursor.get(slot, 0)]:
            self.cursor[slot] = sibling  # buttons side by side: the arrows go along the row
        elif key in ("left", "right") and current is not None and current.adjust:
            current.adjust(self, 1 if key == "right" else -1)
        elif key in ("esc", "left"):
            self._focus("sidebar")
        elif key in ("up", "down", "pgup", "pgdn", "home", "end"):
            self._step(layout, slot, {"up": -1, "down": 1, "pgup": -view, "pgdn": view, "home": -10**6, "end": 10**6}[key])
        elif key in ("enter", "space") and current is not None:
            self._activate(current)


    def _present(self) -> None:
        """Commit page and dialog changes in the same frame, including idle jobs."""
        self.stdscr.noutrefresh()
        with contextlib.suppress(curses.error):
            curses.doupdate()

    def _next_choice(self, direction: int) -> None:
        layout, slot = self.build(), self._slot()
        indexes = [i for i, choice in enumerate(layout.choices) if choice.enabled]
        if not indexes:
            return
        current = self.cursor.get(slot, -1)
        if current in indexes:
            target = indexes[(indexes.index(current) + direction) % len(indexes)]
        else:
            target = indexes[0 if direction > 0 else -1]
        self.cursor[slot] = target
        self._reveal(slot, layout.choice_rows[target])

    def tab_menu(self) -> None:
        picked = self.choose(tr("Views"), self._tabs())
        if picked is not None:
            self._switch_tab(0, picked)

    def section_menu(self) -> None:
        """F2: every section in a keyboard selection list."""
        index = self.choose(tr("Menu"), [(index, tr(self.pages[key].title)) for index, key in enumerate(self.order)])
        if index is not None:
            self._go(index)

    def search(self) -> None:
        """Jump to the first item, then section, whose name contains what was typed."""
        query = (self.ask_text(tr("Search")) or "").strip().casefold()
        if not query:
            return
        layout = self.build()
        for index, choice in enumerate(layout.choices):
            if query in choice.label.casefold():
                self.focus, self.cursor[self._slot()] = "content", index
                self._reveal(self._slot(), layout.choice_rows[index])
                return
        for index, key in enumerate(self.order):
            if query in tr(self.pages[key].title).casefold():
                self._go(index)
                return
        self.notify(f"{tr('No results')}: {query}", "warn")

    # ------------------------------------------------------------ dialogs

    def help_text(self) -> str:
        rows = [
            ("↑ ↓  j k", tr("Move")), ("→ Enter l", tr("Open")), ("← Esc h", tr("Back")),
            ("Tab / S-Tab", tr("Move")), ("F6", tr("Switch pane")),
            ("F2", tr("Go to section")), ("F3", tr("Views")), ("[ ]", tr("Previous / next tab")), ("1-9 0 ,", tr("Go to section")),
            ("/", tr("Search")), ("PgUp PgDn", tr("Scroll")), ("r", tr("Refresh")), ("?", tr("Help")), ("q", tr("Quit")),
        ]
        return "\n".join(f"{pad(key, 12)} {label}" for key, label in rows)

    def _box(self, title: str, lines: list[str], *, width: int = 0, footer: str = "", selected: int | None = None,
             offset: int = 0) -> tuple[int, int, int, int]:
        height, total = self.size()
        inner = max([cell_width(line) for line in lines] + [cell_width(title), cell_width(footer)]) + 2
        box_w = min(total - 2, max(width, inner + 2, 30))
        box_h = min(height - 2, len(lines) + 2)
        top, left = max(0, (height - box_h) // 2), max(0, (total - box_w) // 2)
        g, accent = self.glyphs, self.attrs["accent"]
        self.put(top, left, g.top[0] + g.h * (box_w - 2) + g.top[2], accent)
        self.put(top, left + 2, f" {clip(title, box_w - 6)} ", accent)
        for row in range(1, box_h - 1):
            index = offset + row - 1
            line = lines[index] if index < len(lines) else ""
            self.put(top + row, left, g.v, accent)
            self.put(top + row, left + 1, pad(f" {line}", box_w - 2), curses.A_REVERSE if index == selected else 0)
            self.put(top + row, left + box_w - 1, g.v, accent)
        self.put(top + box_h - 1, left, g.bottom[0] + g.h * (box_w - 2) + g.bottom[2], accent)
        if footer:
            self.put(top + box_h - 1, left + 2, f" {clip(footer, box_w - 6)} ", self.attrs["dim"])
        self._dialog_rect = top, left, box_h, box_w
        return top, left, box_h, box_w

    def _modal_key(self) -> str:
        """Wait for one keyboard event; ignore idle wakeups and pointer events."""
        while True:
            code = self._getch()
            if code == -1:
                visible = self.ctx.state("remote").get("visible_until", 0)
                if self.page_key == "remote" and 0 < visible <= time.monotonic():
                    self.ctx.state("remote")["visible_until"] = 0
                    self.draw()
                    self._present()
                    return "esc"  # do not leave credentials behind an idle dialog
                continue
            if code == 3:  # Ctrl+C leaves any dialog, whatever it was asking
                return "esc"
            key = name_of(code)
            if key != "mouse":
                return key
            key = self._modal_mouse()
            if key:
                return key

    def _read(self) -> str:
        """One key for a dialog, with the vim aliases applied."""
        key = self._modal_key()
        return ALIASES.get(key, key)

    def _answers(self, y: int, left: int, box_w: int, answers: list[tuple[str, str, str]]) -> None:
        keys = {"enter": "Enter", "esc": "Esc"}
        column, limit = left + 2, left + box_w - 2
        for label, key, tone in answers:
            text = f"[{keys.get(key, key.upper())}] {label}"
            shown = clip(text, max(0, limit - column))
            self.put(y, column, shown, self.attrs.get(tone, self.attrs["accent"]))
            self._dialog_hits.append((y, column, column + cell_width(shown), key))
            column += cell_width(shown) + 3

    def confirm(self, message: str, *, danger: bool = False) -> bool:
        """The action as the title, what it will do underneath, then Yes / No."""
        title, _sep, body = message.partition(": ")
        if not body or cell_width(title) > 48:
            title, body = tr("Confirm"), message
        while True:
            width = min(self.size()[1] - 4, 56)
            self.draw()
            lines = wrap(body, max(10, width - 4)) + ["", ""]
            top, left, box_h, box_w = self._box(title, lines, width=width)
            self._answers(top + box_h - 2, left, box_w, [(tr("Yes"), "y", "bad" if danger else "accent"),
                                                         (tr("No"), "n", "dim")])
            self._present()
            key = self._modal_key()
            # A dangerous action needs an explicit "y": Enter alone is not consent.
            if key in ("y", "Y") or (key == "enter" and not danger):
                return True
            if key in ("n", "N", "esc", "q"):
                return False

    def choose(self, title: str, options: list[tuple[Any, str]]) -> Any:
        if not options:
            return None
        index = 0
        while True:
            labels = [label for _value, label in options]
            self.draw()
            height = self.size()[0]
            visible = max(1, height - 6)
            offset = max(0, min(index - visible // 2, max(0, len(labels) - visible)))
            top, left, height, width = self._box(title, labels, selected=index, offset=offset,
                                               footer="↑↓ / PgUp PgDn · Enter · Esc")
            self._dialog_hits += [(top + line + 1, left + 1, left + width - 1, f"pick:{offset + line}")
                                  for line in range(min(height - 2, len(labels) - offset))]
            self._present()
            key = self._read()
            moves = {"wheelup": index - 3, "wheeldown": index + 3, "up": index - 1, "down": index + 1, "pgup": 0, "home": 0, "pgdn": len(options) - 1,
                     "end": len(options) - 1}
            if key.startswith("pick:"):
                return options[int(key[5:])][0]
            if key in moves:
                index = max(0, min(len(options) - 1, moves[key]))
            elif key in ("enter", "space", "right"):
                return options[index][0]
            elif key in ("esc", "left", "q", "menu"):
                return None


    def ask_text(self, label: str, default: str = "", *, numeric: bool = False) -> str | None:
        value, cursor = default, len(default)
        caret = "▏" if self.unicode else "_"
        while True:
            self.draw()
            field_width = max(8, min(self.size()[1] - 8, 46))
            start = 0
            while start < cursor and cell_width(value[start:cursor]) >= field_width:
                start += 1
            visible = value[start:cursor] + caret + value[cursor:]
            lines = [visible, "", ""]
            top, left, box_h, box_w = self._box(label, lines, width=min(self.size()[1] - 4, 50))
            self._answers(top + box_h - 2, left, box_w, [(tr("Apply"), "enter", "accent"), (tr("Cancel"), "esc", "dim")])
            for col in range(max(0, box_w - 4)):
                at, _char = character_at(visible, col)
                before_caret = cursor - start
                target = start + at - (1 if at > before_caret else 0)
                self._dialog_hits.append((top + 1, left + 2 + col, left + 3 + col,
                                          f"cursor:{max(0, min(len(value), target))}"))
            self._present()
            key = self._modal_key()
            if key == "enter":
                return value
            if key == "esc":
                return None
            if key.startswith("cursor:"):
                cursor = int(key[7:])
            elif key == "backspace" and cursor:
                value, cursor = value[:cursor - 1] + value[cursor:], cursor - 1
            elif key == "delete":
                value = value[:cursor] + value[cursor + 1:]
            elif key in ("left", "right", "home", "end"):
                cursor = {"left": max(0, cursor - 1), "right": min(len(value), cursor + 1), "home": 0,
                          "end": len(value)}[key]
            elif key == "space" and not numeric:
                value, cursor = value[:cursor] + " " + value[cursor:], cursor + 1
            elif len(key) == 1 and (key.isdigit() or (not numeric and key.isprintable()) or (numeric and key == "-")):
                value, cursor = value[:cursor] + key + value[cursor:], cursor + 1

    def ask_int(self, label: str, minimum: int, maximum: int, default: int) -> int | None:
        text = str(default)
        while True:
            answer = self.ask_text(f"{label} [{minimum}–{maximum}]", text, numeric=True)
            if answer is None:
                return None
            try:
                number_ = int(answer)
            except ValueError:
                self.notify(tr("Enter a whole number."), "warn")
                text = answer
                continue
            if minimum <= number_ <= maximum:
                return number_
            self.notify(tr("The value must be between {low} and {high}.").format(low=minimum, high=maximum), "warn")
            text = answer

    def show_text(self, title: str, text: str, *, compact: bool = False) -> None:
        """A pager. Long text takes the whole screen; short text a small box."""
        offset = 0
        while True:
            height, width = self.size()
            self._geometry_size = (height, width)
            self._scroll_track = None
            lines: list[str] = []
            for line in text.splitlines() or [""]:
                lines.extend(wrap(line, max(10, width - 4 if not compact else 60)) or [""])
            view = max(1, height - 3)
            self._dialog_hits = []
            self._dialog_rect = (0, 0, height, width)
            if compact:
                self.draw()
                top, left, box_h, box_w = self._box(title, lines, offset=offset, footer="Esc")
                self._dialog_hits.append((top + box_h - 1, left + 2, left + 7, "esc"))
            else:
                offset = max(0, min(offset, max(0, len(lines) - view)))
                self.stdscr.erase()
                self.put(0, 0, pad(f" {title}", width), curses.A_REVERSE | curses.A_BOLD)
                for index, line in enumerate(lines[offset:offset + view]):
                    self.put(1 + index, 1, line)
                self.put(height - 1, 1, pad(f"{offset + 1}-{min(len(lines), offset + view)}/{len(lines)}  "
                                            f"↑↓ {tr('Scroll')}  PgUp PgDn  Esc", width - 2), self.attrs["dim"])
            if not compact:
                self._dialog_hits.append((height - 1, 0, width, "esc"))
            self._present()
            key = self._read()
            if key in ("esc", "q", "left", "enter"):
                return
            step = {"wheelup": -3, "wheeldown": 3, "up": -1, "down": 1, "pgup": -view, "pgdn": view, "space": view, "home": -10**6, "end": 10**6}
            offset = max(0, min(offset + step.get(key, 0), max(0, len(lines) - view)))

    # ------------------------------------------------------------- console

    def run(self, label: str, work: Callable[[], Any]) -> tuple[bool, Any]:
        """Run a service call or workflow with its output in the console pane.

        Workflows the repositories start reach the same pane through
        ``launch_workflow``, and their password prompts are answered there.
        """
        if self._foreground is not None:
            return self._foreground(label, work)
        console = Console(label, *self._console_size())  # the pty starts at the pane's size, not 80x24
        self.active_console, self.console_scroll = console, 0

        def job() -> None:
            try:
                with console.password_agent(), contextlib.redirect_stdout(console), contextlib.redirect_stderr(console):
                    result = work()
                if isinstance(result, str) and result.strip():
                    console.write(f"\n{result.strip()}\n")
                console.finish(True, result)
            except Exception as error:  # said in the console even when nothing else was: never an empty failure
                console.write(f"\n{describe_error(error)}\n")
                console.finish(False, error)

        threading.Thread(target=job, name="bc250-tui-job", daemon=True).start()
        closed_with = ""
        try:
            while not (console.done.is_set() and console.succeeded and not console.has_output):
                self.draw()
                self._present()
                code = self._getch()
                closed_with = self._console_key(console, code) if code != -1 else ""
                if closed_with:
                    break
        finally:
            self.active_console = None
            self._layout_key = None
            self._repaint()
        if closed_with == "report":  # the failed workflow's own log goes with the report
            log = "\n".join("".join(run[0] for run in line).rstrip() for line in console.view(SCROLLBACK_ALL)[0])
            report(self, title=label, log=log)
        return console.succeeded, console.result

    def _console_key(self, console: Console, code: int) -> str:
        """Keys while the console is up; "close" or "report" closes it (only once the job is done)."""
        key = name_of(code)
        if key == "mouse":
            key = self._console_mouse()
            code = {"esc": 27, "enter": 10}.get(key, 0)
        if key in ("pgup", "pgdn"):
            self.console_scroll += (1 if key == "pgup" else -1) * max(1, self.size()[0] - 6)
        elif console.done.is_set():
            if key in ("esc", "enter", "q", "space"):
                return "close"
            if key == "r" and not console.succeeded:
                return "report"
            if key in ("up", "down", "home", "end"):
                self.console_scroll += {"up": 1, "down": -1, "home": 10**6, "end": -10**6}[key]
        elif code == 3 or key == "esc":  # Esc and Ctrl+C both request cancellation
            console.interrupt()
        elif key in PTY_KEYS:
            console.send(PTY_KEYS[key])
        elif 0 < code < 32 or len(key) == 1:
            console.send(bytes([code]) if code < 32 else key.encode())
        return ""

    def launch_workflow(self, request):
        """The repositories' embedded launcher: the workflow runs in the open console pane."""
        from bc250cc.application.system.workflow_console import TerminalLaunchResult

        console = self.active_console
        if console is None:
            return None  # nothing on screen to show it in: the repository decides
        console.log_file = request.log_file or console.log_file
        status = console.run(list(request.argv), request.log_file)
        console.failed = console.failed or status != 0
        return TerminalLaunchResult(terminal=EMBEDDED_TERMINAL_NAME, title=request.title,
                                    pid=console.process.pid if console.process else None,
                                    status_file=request.status_file, log_file=request.log_file)

    def shell(self, command: str) -> str:
        """Run a reviewed command line in the console pane of the running job."""
        console = self.active_console
        if console is None:
            raise RuntimeError(tr("The workflow did not finish successfully."))
        status = console.run(["bash", "-c", command])
        if status:
            raise RuntimeError(describe_failure(status, "", "", translate=tr))
        return ""

    # ---------------------------------------------------------------- loop

    def loop(self) -> None:
        self.stdscr.keypad(True)
        curses.raw()  # Ctrl+C arrives as a key: it interrupts a running command, never kills the screen
        self.stdscr.timeout(200)
        with contextlib.suppress(curses.error):
            curses.curs_set(0)
        with contextlib.suppress(AttributeError, curses.error):
            curses.set_escdelay(25)
        with contextlib.suppress(curses.error):
            curses.mouseinterval(0)
            curses.mousemask(curses.ALL_MOUSE_EVENTS | getattr(curses, "REPORT_MOUSE_POSITION", 0))
        dirty = True
        while True:
            if self.poller is not None and self.poller.dirty.is_set():
                self.poller.dirty.clear()
                dirty = True
            if self.toast and self.toast[2] <= time.monotonic():
                self.toast, dirty = None, True
            if dirty:
                self.draw()
                curses.doupdate()
                dirty = False
            code = self._getch()
            if code == -1:
                continue
            try:
                self.handle(code)
            except Quit:
                break
            dirty = True
