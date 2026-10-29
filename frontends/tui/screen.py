"""The curses application: sidebar, content, console, dialogs and the key loop."""

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
from .runtime import Context, Poller, describe_error
from .support import available_version, report

MIN_WIDTH, MIN_HEIGHT = 60, 14
TOUCH_WIDTH = 110  # narrower than this, and no choice saved: the phone / tablet layout
#: The on-screen keys a phone keyboard lacks: (label, key name), one slim row.
#: The keys a phone keyboard lacks, in order of need. No arrows: a swipe scrolls, a tap selects,
#: and Termux / Termius put their own arrows above the keyboard.
KEYBAR = (("Menu", "menu"), ("Esc", "esc"), ("Enter", "enter"), ("Tab", "tab"), ("Search", "/"), ("Quit", "q"))
TOAST_SECONDS = 6.0
TONE_PAIRS = {"ok": 1, "warn": 2, "bad": 3, "accent": 4}
#: The desktop sidebar: its groups, in its order.
SIDEBAR = (("", ("dashboard",)), ("Hardware", ("cpu", "cu", "gpu", "extras")),
           ("Monitoring", ("performance", "fans", "processes", "black_box")), ("", ("firmware", "settings")))
SIDEBAR_ORDER = tuple(key for _group, keys in SIDEBAR for key in keys)
#: Keys a running command receives as a terminal would send them.
PTY_KEYS = {"enter": b"\r", "backspace": b"\x7f", "tab": b"\t", "esc": b"\x1b", "space": b" ", "up": b"\x1b[A",
            "down": b"\x1b[B", "right": b"\x1b[C", "left": b"\x1b[D", "delete": b"\x1b[3~"}
SPINNER = ("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏", "|/-\\")
EMBEDDED_TERMINAL_NAME = "bc250-tui-console"
SCROLLBACK_ALL = 10**6

#: One-for-one replacements (same column width) for terminals without Unicode.
ASCII_MAP = str.maketrans({
    "…": ".", "·": "-", "│": "|", "─": "-", "┌": "+", "┐": "+", "└": "+", "┘": "+", "├": "+", "┤": "+", "┬": "+",
    "┴": "+", "┼": "+", "▲": "^", "▼": "v", "↑": "^", "↓": "v", "→": ">", "←": "<", "–": "-", "▏": "_", "›": ">",
    "•": "*", "█": "#", "░": "-", "━": "=", "┃": "#", "°": "o", "✓": "+", "✗": "x",
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


class Screen:
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
        self.visited: list[int] = []  # sections opened before, for Esc in the touch layout
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
        self._layout_key: tuple | None = None
        # What the last draw put where, for the mouse: y -> page index / choice index, tab spans.
        self._sidebar_at: dict[int, int] = {}
        self._choice_at: dict[int, int] = {}
        self._tab_at: list[tuple[int, int, str]] = []
        self._hits: list[tuple[int, int, int, str]] = []  # (y, x from, x to, key): taps on keys and strips
        self._row_at: dict[int, tuple[int, str]] = {}  # y -> (x, text) of a drawn item, for "<" / ">" taps
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

    @property
    def touch(self) -> bool:
        """The phone / tablet layout: the saved choice, else on for a narrow terminal."""
        chosen = self.ctx.state("ui").get("touch")
        return bool(chosen) if chosen is not None else self.size()[1] < TOUCH_WIDTH

    @property
    def keybar(self) -> bool:
        return self.touch and self.ctx.state("ui").get("keybar", True) is not False

    def _bottom(self) -> int:
        return 2 if self.keybar else 1

    def sidebar_width(self, width: int) -> int:
        longest = max(cell_width(tr(self.pages[key].title)) for key in self.order) + 5
        return max(16, min(longest, width // 3))

    def _content_box(self) -> tuple[int, int]:
        """(x, width) of the content text: after the sidebar, its rule and the cursor column."""
        width = self.size()[1]
        x = 2 if self.touch else self.sidebar_width(width) + 4
        return x, max(20, width - x - 1)

    # -------------------------------------------------------------- draw

    def build(self) -> Layout:
        content_width = self._content_box()[1]
        tab = self._tab_key()
        with self.ctx.lock:
            data = self.ctx.page_data.get(self.page_key)
            state = self.ctx.page_state.get(self.page_key)
            key = (self.page_key, tab, content_width, self.touch, id(data), len(self.ctx.history.get("gpu_clock", ())),
                   self.ctx.metrics_error, self.ctx.page_error.get(self.page_key), id(self.ctx.metrics),
                   hash(repr(sorted(state.items()))) if state else 0)
            if key == self._layout_key and self._layout is not None:
                return self._layout
            try:
                blocks = self.page.build(self.ctx, data, tab, self)
            except Exception as error:
                from .content import Note

                blocks = [Note(describe_error(error), "bad")]
        self._layout = build_layout(blocks, content_width, self.glyphs, touch=self.touch)
        self._layout_key = key
        return self._layout

    def draw(self) -> None:
        height, width = self.size()
        self.stdscr.erase()
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            text = tr("The terminal is too small ({width}x{height}); it needs at least {min_width}x{min_height}.").format(
                width=width, height=height, min_width=MIN_WIDTH, min_height=MIN_HEIGHT)
            for index, line in enumerate(wrap(text, max(10, width - 2))):
                self.put(index, 1, line, self.attrs["warn"])
            self.stdscr.noutrefresh()
            return
        self._hits, self._row_at = [], {}
        self._draw_title(width)
        if self.touch:
            self.focus = "content"  # no sidebar: the strip and the menu choose the section
            self._draw_strip(width)
        else:
            self._draw_sidebar(height, self.sidebar_width(width))
        console = self.active_console
        if console is not None and (console.has_output or time.monotonic() - console.started > 0.4):
            self._draw_console(console, height, width)
        else:
            self._draw_content(height, width)
            self._draw_footer(height, width)
        if self.keybar and not (self.toast and self.toast[2] > time.monotonic()):
            self._draw_keybar(height, width)
        self.stdscr.noutrefresh()

    def _draw_strip(self, width: int) -> None:
        """Touch layout, row 1: Menu and the sections, scrolled so the open one shows."""
        items = [("menu", f" {tr('Menu')} ")] + [(f"go:{index}", f" {tr(self.pages[key].title)} ")
                                                   for index, key in enumerate(self.order)]
        first = 1
        while sum(cell_width(text) + 1 for _key, text in items[:1] + items[first:self.section + 2]) > width and \
                first <= self.section:
            first += 1
        column = 0
        for key, text in items[:1] + items[first:]:
            selected = key == f"go:{self.section}"
            attr = self.attrs["sel"] if selected else self.attrs["accent"] if key == "menu" else self.attrs["dim"]
            self.put(1, column, text, attr)
            self._hits.append((1, column, column + cell_width(text), key))
            column += cell_width(text) + 1
            if column >= width:
                break

    def _draw_keybar(self, height: int, width: int) -> None:
        """The on-screen keys: two rows tall and spread over the full width, a gap between keys."""
        labels = [(tr(label) if label in ("Menu", "Search", "Quit") else label, key) for label, key in KEYBAR]
        for index, (text, key) in enumerate(labels):  # exact edges: the keys reach both sides, one column apart
            column = index * (width - 1) // len(labels)
            cell = (index + 1) * (width - 1) // len(labels) - column
            attr = (self.attrs["accent"] if key == "menu" else 0) | curses.A_REVERSE | curses.A_BOLD
            for y in (height - 2, height - 1):
                self.put(y, column, clip(text, cell - 1).center(cell - 1) if y == height - 2 else " " * (cell - 1), attr)
                self._hits.append((y, column, column + cell, key))

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
        y = 2
        for group, keys in SIDEBAR:
            keys = [key for key in keys if key in self.order]
            if group and keys and y < height - 2:
                self.put(y, 1, tr(group).upper(), self.attrs["dim"])
                y += 1
            elif not group and y > 2 and keys and height - 2 - y > len(keys):
                y += 1  # breathing room before the last group, as on the desktop
            for key in keys:
                if y >= height - 1:
                    break
                index = self.order.index(key)
                hotkey = str((index + 1) % 10) if index < 10 else ","
                label = f"{hotkey} {tr(self.pages[key].title)}"
                if index != self.section:
                    self.put(y, 1, hotkey, self.attrs["dim"])
                    self.put(y, 3, tr(self.pages[key].title), 0, side - 4)
                elif self.focus == "sidebar" and self.active_console is None:
                    self.put(y, 0, pad(f" {label}", side), self.attrs["sel"])
                else:
                    self.put(y, 0, pad(f"{self.glyphs.cursor}{label}", side), self.attrs["accent"])
                self._sidebar_at[y] = index
                y += 1
        for row in range(1, height - 1):
            self.put(row, side, self.glyphs.v, self.attrs["dim"])

    def _draw_tabs(self, x: int, width: int) -> int:
        """The tab strip; returns the first row below it."""
        self._tab_at = []
        tabs = self._tabs()
        row = 2 if self.touch else 1  # below the touch layout's section strip
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
        return self.size()[0] - (1 + self.touch + 2 * bool(self._tabs())) - self._bottom()

    def _draw_content(self, height: int, width: int) -> None:
        x, _content_width = self._content_box()
        top = self._draw_tabs(x - 2, width)
        layout = self.build()
        view, slot = height - top - self._bottom(), self._slot()
        cursor = self.cursor.get(slot, 0)
        offset = max(0, min(self.scroll.get(slot, 0), max(0, len(layout.rows) - view)))
        self.scroll[slot] = offset
        self._choice_at = {}
        for line, row in enumerate(layout.rows[offset:offset + view]):
            y = top + line
            selected = row.choice is not None and row.choice == cursor and self.focus == "content"
            if row.choice is not None:
                self._choice_at[y] = row.choice
                first = line == 0 or layout.rows[offset + line - 1].choice != row.choice
                if selected and first:
                    self.put(y, x - 2, self.glyphs.cursor, self.attrs["accent"])
            column = x
            if row.choice is not None:
                self._row_at[y] = (x, "".join(text for text, _tone in row.spans))
            for text, tone in row.spans:
                if tone.startswith("btn:"):  # a touch button: the bar is the colour, its text the background
                    attr = self.attrs.get(tone[4:], 0) | curses.A_REVERSE | curses.A_BOLD
                    attr = attr & ~curses.A_REVERSE if selected else attr
                    self.put(y, column, text, attr, limit=width - column - 1)
                    column += cell_width(text)
                    continue
                attr = self.attrs.get(tone, 0) | (curses.A_BOLD if row.bold else 0)
                if selected and not row.plain:
                    attr |= curses.A_REVERSE
                if tone == "sel" and self.focus != "content":
                    attr = self.attrs["accent"]
                self.put(y, column, text, attr, limit=width - column - 1)
                column += cell_width(text)
        if len(layout.rows) > view:  # a scrollbar: the thumb is where this view sits on the page
            size = max(1, view * view // len(layout.rows))
            start = round(offset * (view - size) / max(1, len(layout.rows) - view))
            for line in range(view):
                thumb = start <= line < start + size
                self.put(top + line, width - 1, "┃" if thumb else self.glyphs.v,
                         self.attrs["accent" if thumb else "dim"])

    def _hints(self) -> list[tuple[str, str]]:
        if self.focus == "sidebar":
            return [("↑↓", "Move"), ("Enter", "Open"), ("1-9", "Go to section"), ("/", "Search"), ("?", "Help"),
                    ("q", "Quit")]
        choice = self.current_choice()
        hints = [("↑↓", "Move")]
        if choice is not None and choice.adjust:
            hints.append(("←→", "Adjust"))
        if choice is not None and (choice.handler or choice.pad):
            hints.append(("Enter", "Select" if choice.pad else "Open"))
        if self._tabs():
            hints.append(("[ ]", "Previous / next tab"))
        return hints + [("Esc", "Back"), ("?", "Help")]

    def _draw_footer(self, height: int, width: int) -> None:
        if self.toast and self.toast[2] > time.monotonic():  # over the keys for its few seconds
            self.put(height - 1, 1, pad(self.toast[0], width - 2), self.attrs.get(self.toast[1], 0) | curses.A_BOLD)
        elif not self.keybar:
            self._draw_hints(self._hints())

    def _draw_hints(self, hints: list[tuple[str, str]], tail: str = "", tail_attr: int = 0, *, y: int = -1) -> None:
        """A row of keys in the accent colour with what they do dimmed (the bottom row by default).

        A one-letter key is also a tap target, so ``r`` (report) works without a keyboard.
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
            if len(key) == 1:
                self._hits.append((y, column, column + cell_width(key) + 1 + cell_width(text), key))
            column += cell_width(key) + cell_width(text) + 3
        self.put(y, column, tail, tail_attr)

    def _console_size(self) -> tuple[int, int]:
        rows = self.size()[0] - 3 - self.touch - self._bottom() - (1 if self.keybar else 0)
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
        top = 1 + self.touch
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
        hints = [("Enter Esc", "Close")] if done else [("Ctrl+C", "Interrupt")]
        if done and not console.succeeded:
            hints.append(("r", "Report this problem"))
        self._draw_hints(hints + [("PgUp PgDn", "Scroll")], y=height - self._bottom() - (1 if self.keybar else 0))

    # ------------------------------------------------------------- input

    def current_choice(self):
        """The selected item, if it is on screen: nothing off screen is ever acted on."""
        layout, slot = self.build(), self._slot()
        index = self.cursor.get(slot, 0)
        return layout.choices[index] if self._shown(layout, slot, index) else None

    def handle(self, code: int) -> None:
        if code == 3:
            raise Quit
        self.handle_key(ALIASES.get(name_of(code), name_of(code)))

    def handle_key(self, key: str) -> None:
        """One key by name, from the keyboard or from a tap on an on-screen key."""
        if self.touch:
            self.focus = "content"  # no sidebar to be on
        if key == "menu":
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
        elif key == "tab":
            self._focus("content" if self.focus == "sidebar" else "sidebar")
        elif key == "btab":
            self._focus("sidebar")
        elif key in ("[", "]"):
            self._switch_tab(-1 if key == "[" else 1)
        elif (key.isdigit() and len(key) == 1) or key == ",":
            index = len(self.order) - 1 if key == "," else (int(key) - 1) % 10
            if index < len(self.order):
                self._go(index)
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

    def _back(self) -> None:
        """Esc on a phone: the section seen before this one (the menu has its own key)."""
        if self.visited:
            self._go(self.visited.pop(), remember=False)

    def _go(self, index: int, *, remember: bool = True) -> None:
        index = max(0, min(len(self.order) - 1, index))
        if remember and index != self.section:
            self.visited = (self.visited + [self.section])[-20:]
        self.section = index
        self._layout_key = None
        self._repaint()
        if self.poller:
            self.poller.show(self.page_key, self._tab_key())

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
        self.tab[self.page_key] = to or keys[(keys.index(self._tab_key()) + step) % len(keys)]
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
        if key in ("left", "right") and current is not None and current.adjust:
            current.adjust(self, 1 if key == "right" else -1)
        elif key in ("left", "right") and self._tabs():
            self._switch_tab(1 if key == "right" else -1)
        elif key in ("esc", "left"):
            self._back() if self.touch else self._focus("sidebar")
        elif key in ("up", "down", "pgup", "pgdn", "home", "end"):
            self._step(layout, slot, {"up": -1, "down": 1, "pgup": -view, "pgdn": view, "home": -10**6, "end": 10**6}[key])
        elif key in ("enter", "space") and current is not None:
            self._activate(current)

    def _tap(self) -> tuple[int, int, str] | None:
        """(x, y, what): what is "up"/"down" for the wheel (a swipe on a phone), the key a tap hit, or ""."""
        try:
            _id, x, y, _z, state = curses.getmouse()
        except curses.error:
            return None
        for button, key in ((getattr(curses, "BUTTON4_PRESSED", 0), "up"), (getattr(curses, "BUTTON5_PRESSED", 0), "down")):
            if button and state & button:
                return x, y, key
        return x, y, next((key for row, start, end, key in self._hits if row == y and start <= x < end), "")

    def _mouse(self) -> None:
        """A click or tap on a key, section, tab or item; the wheel (a swipe) scrolls.

        With a mouse, a click selects an item and a second click opens it; a
        tap opens it at once, and a tap on the "<" or ">" of a value steps it.
        """
        tap = self._tap()
        if tap is None:
            return
        x, y, key = tap
        if key in ("up", "down") and self.active_console is not None:
            self.console_scroll += 3 if key == "up" else -3
        elif key in ("up", "down"):  # the wheel, or a swipe on a phone: the page moves, three rows at a time
            self.focus = "content"
            self._step(self.build(), self._slot(), 3 if key == "down" else -3)
        elif key:
            self.handle_key(key)
        elif self.active_console is not None:
            return
        elif not self.touch and x < self.sidebar_width(self.size()[1]) and y in self._sidebar_at:
            self.focus = "sidebar"
            self._go(self._sidebar_at[y])
        elif y in self._choice_at:
            slot, index = self._slot(), self._choice_at[y]
            again = self.focus == "content" and self.cursor.get(slot) == index
            self.focus, self.cursor[slot] = "content", index
            choice = self.build().choices[index]
            left, text = self._row_at.get(y, (0, ""))
            step = {"<": -1, ">": 1}.get(text[x - left:x - left + 1]) if choice.adjust else None
            if step:
                choice.adjust(self, step)
                self._layout_key = None
            elif again or self.touch:
                self._activate(choice)

    def section_menu(self) -> None:
        """Menu: every section, as a list to tap or move through."""
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
            ("Tab", tr("Switch pane")), ("[ ]", tr("Previous / next tab")), ("1-9 0 ,", tr("Go to section")),
            ("/", tr("Search")), ("PgUp PgDn", tr("Scroll")), ("r", tr("Refresh")), ("?", tr("Help")), ("q", tr("Quit")),
        ]
        return "\n".join(f"{pad(key, 12)} {label}" for key, label in rows)

    def _box(self, title: str, lines: list[str], *, width: int = 0, footer: str = "", selected: int | None = None,
             offset: int = 0) -> tuple[int, int, int, int]:
        height, total = self.size()
        if self.touch:  # on a small screen the page behind would read as part of the dialog
            for y in range(1 + self.touch, height - self._bottom()):
                self.put(y, 0, " " * total)
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
        return top, left, box_h, box_w

    def _modal_key(self) -> str:
        """Block for one key (idle wake-ups are skipped). A tap on an on-screen key or target is that key."""
        while True:
            code = self.stdscr.getch()
            if code == -1:
                continue
            if code == 3:  # Ctrl+C leaves any dialog, whatever it was asking
                return "esc"
            key = name_of(code)
            if key != "mouse":
                return key
            tap = self._tap()
            if tap is not None and tap[2]:
                return tap[2]

    def _read(self) -> str:
        """One key for a dialog, with the vim aliases applied."""
        key = self._modal_key()
        return ALIASES.get(key, key)

    def confirm(self, message: str, *, danger: bool = False) -> bool:
        while True:
            width = min(self.size()[1] - 8, 64)
            self.draw()
            lines = wrap(message, max(10, width - 4))
            half = max(8, (width - 4) // 2)
            if self.touch:  # two wide answers to tap, under the question
                lines += ["", f"[ {tr('Yes')} ]".center(half) + f"[ {tr('No')} ]".center(half)]
            top, left, box_h, box_w = self._box(tr("Confirm"), lines, width=width,
                                                footer=f"y {tr('Yes')} · n {tr('No')}" + (" · !" if danger else ""))
            for y in range(top + box_h - 3, top + box_h):
                self._hits += [(y, left, left + 2 + half, "y"), (y, left + 2 + half, left + box_w, "n")]
            self.stdscr.refresh()
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
            if self.touch:
                self._draw_choices_full(title, labels, index)
            else:
                height = self.size()[0]
                offset = max(0, min(index - (height - 8) // 2, max(0, len(labels) - (height - 6))))
                self._box(title, labels, selected=index, offset=offset, footer="Enter · Esc")
            self.stdscr.refresh()
            key = self._read()
            moves = {"up": index - 1, "down": index + 1, "pgup": 0, "home": 0, "pgdn": len(options) - 1,
                     "end": len(options) - 1}
            if key.startswith("pick:"):
                return options[int(key[5:])][0]
            if key in moves:
                index = max(0, min(len(options) - 1, moves[key]))
            elif key in ("enter", "space", "right"):
                return options[index][0]
            elif key in ("esc", "left", "q", "menu"):
                return None

    def _draw_choices_full(self, title: str, labels: list[str], index: int) -> None:
        """A choice over the whole content area: one option every two rows, each row a tap target."""
        height, width = self.size()
        top, bottom = 1 + self.touch, height - self._bottom()
        for y in range(top, bottom):
            self.put(y, 0, " " * width)
        self.put(top, 1, clip(title, width - 2), self.attrs["accent"] | curses.A_BOLD)
        rows = max(1, (bottom - top - 2) // 2)
        offset = max(0, min(index - rows // 2, len(labels) - rows))
        for line, item in enumerate(range(offset, min(len(labels), offset + rows))):
            y = top + 2 + line * 2
            self.put(y, 1, pad(f" {labels[item]}", width - 2), self.attrs["sel"] if item == index else 0)
            self._hits += [(y, 0, width, f"pick:{item}"), (y + 1, 0, width, f"pick:{item}")]

    def ask_text(self, label: str, default: str = "", *, numeric: bool = False) -> str | None:
        value, cursor = default, len(default)
        caret = "▏" if self.unicode else "_"
        while True:
            self.draw()
            lines = [value[:cursor] + caret + value[cursor:]]
            if self.touch:  # answers to tap; the phone keyboard types the value
                lines += ["", f"[ {tr('Apply')} ]".center(23) + f"[ {tr('Cancel')} ]".center(23)]
            top, left, box_h, box_w = self._box(label, lines, width=50, footer="Enter · Esc")
            for y in range(top + box_h - 3, top + box_h):
                self._hits += [(y, left, left + box_w // 2, "enter"), (y, left + box_w // 2, left + box_w, "esc")]
            self.stdscr.refresh()
            key = self._modal_key()
            if key == "enter":
                return value
            if key == "esc":
                return None
            if key == "backspace" and cursor:
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
            lines: list[str] = []
            for line in text.splitlines() or [""]:
                lines.extend(wrap(line, max(10, width - 4 if not compact else 60)) or [""])
            view = max(1, height - 3)
            if compact:
                self.draw()
                self._box(title, lines, offset=offset, footer="Esc")
            else:
                offset = max(0, min(offset, max(0, len(lines) - view)))
                self.stdscr.erase()
                self.put(0, 0, pad(f" {title}", width), curses.A_REVERSE | curses.A_BOLD)
                for index, line in enumerate(lines[offset:offset + view]):
                    self.put(1 + index, 1, line)
                self.put(height - 1, 1, pad(f"{offset + 1}-{min(len(lines), offset + view)}/{len(lines)}  "
                                            f"↑↓ {tr('Scroll')}  PgUp PgDn  Esc", width - 2), self.attrs["dim"])
            self.stdscr.refresh()
            key = self._read()
            if key in ("esc", "q", "left", "enter"):
                return
            step = {"up": -1, "down": 1, "pgup": -view, "pgdn": view, "space": view, "home": -10**6, "end": 10**6}
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
                with console.password_agent(), contextlib.redirect_stdout(console):
                    result = work()
                if isinstance(result, str) and result.strip() and console.has_output:
                    console.write(f"\n{result.strip()}\n")
                console.finish(True, result)
            except Exception as error:
                if console.has_output:
                    console.write(f"\n{describe_error(error)}\n")
                console.finish(False, error)

        threading.Thread(target=job, name="bc250-tui-job", daemon=True).start()
        closed_with = ""
        try:
            while not (console.done.is_set() and console.ok and not console.has_output):
                self.draw()
                self.stdscr.refresh()
                code = self.stdscr.getch()
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
        if key == "mouse":  # a tap on an on-screen key is that key, for the console (not the page behind)
            tap = self._tap()
            if tap is None or not tap[2]:
                return ""
            key = tap[2]
            if key in ("up", "down"):  # the wheel: scroll the output
                self.console_scroll += 3 if key == "up" else -3
                return ""
            code = {"esc": 27, "enter": 10, "tab": 9}.get(key, ord(key) if len(key) == 1 else 0)
        if key in ("pgup", "pgdn"):
            self.console_scroll += (1 if key == "pgup" else -1) * max(1, self.size()[0] - 6)
        elif console.done.is_set():
            if key in ("esc", "enter", "q", "space"):
                return "close"
            if key == "r" and not console.succeeded:
                return "report"
            if key in ("up", "down", "home", "end"):
                self.console_scroll += {"up": 1, "down": -1, "home": 10**6, "end": -10**6}[key]
        elif code == 3:
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
            curses.mouseinterval(0)  # a press is the click: no wait to tell it from a double click
            curses.mousemask(curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED | getattr(curses, "BUTTON4_PRESSED", 0)
                             | getattr(curses, "BUTTON5_PRESSED", 0))
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
            code = self.stdscr.getch()
            if code == -1:
                continue
            try:
                self.handle(code)
            except Quit:
                break
            dirty = True
