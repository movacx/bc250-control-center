"""The curses application: sidebar, content, dialogs and the key loop."""

from __future__ import annotations

import contextlib
import curses
import locale
import os
import subprocess  # nosec B404 - fallback for a terminal without a graphical session
import threading
import time
from collections.abc import Callable
from typing import Any

from .console import Console
from .content import cell_width, clip, pad, wrap
from .i18n import tr
from .keys import ALIASES, name_of
from .layout import Glyphs, Layout, build_layout
from .runtime import Context, Poller, describe_error

MIN_WIDTH, MIN_HEIGHT = 60, 14
TOAST_SECONDS = 6.0
TONE_PAIRS = {"ok": 1, "warn": 2, "bad": 3, "accent": 4}

SIDEBAR_ORDER = (
    "dashboard", "cpu", "gpu", "extras", "cu", "performance", "fans", "processes",
    "black_box", "firmware", "settings",
)


#: One-for-one replacements (same column width) for terminals without Unicode.
ASCII_MAP = str.maketrans({
    "…": ".", "·": "|", "│": "|", "─": "-", "┌": "+", "┐": "+", "└": "+", "┘": "+", "▲": "^", "▼": "v",
    "↑": "^", "↓": "v", "→": ">", "←": "<", "–": "-", "▏": "_", "›": ">", "•": "*", "█": "#", "░": "-", "°": "o",
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
        self.theme = theme
        self.focus = "sidebar"
        self.section = 0
        self.tab: dict[str, str] = {}
        self.cursor: dict[tuple[str, str], int] = {}
        self.scroll: dict[tuple[str, str], int] = {}
        self.toast: tuple[str, str, float] | None = None
        self.unicode = self._unicode_ok()
        self.glyphs = Glyphs.for_terminal(unicode_ok=self.unicode)
        self.attrs: dict[str, int] = {}
        self._foreground = foreground
        self.active_console: Console | None = None
        self._layout: Layout | None = None
        self._layout_key: tuple | None = None
        self.running = True
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
            colours_available = curses.has_colors()
        except curses.error:  # curses was not started (tests)
            colours_available = False
        light = theme == "light" or (theme == "auto" and detect_light_background())
        attrs = {"": curses.A_NORMAL, "dim": curses.A_DIM, "accent": curses.A_BOLD,
                 "sel": curses.A_REVERSE | curses.A_BOLD}
        if colour and colours_available:
            try:
                curses.use_default_colors()
                palette = {
                    1: curses.COLOR_GREEN, 2: curses.COLOR_MAGENTA if light else curses.COLOR_YELLOW,
                    3: curses.COLOR_RED, 4: curses.COLOR_BLUE if light else curses.COLOR_CYAN,
                }
                for pair, color in palette.items():
                    curses.init_pair(pair, color, -1)  # -1: the terminal's own background
                for tone, pair in TONE_PAIRS.items():
                    attrs[tone] = curses.color_pair(pair) | (curses.A_BOLD if tone in ("accent", "bad") else 0)
            except curses.error:
                colour = False
        if not (colour and colours_available):
            attrs.update({"ok": curses.A_NORMAL, "warn": curses.A_BOLD, "bad": curses.A_BOLD | curses.A_UNDERLINE,
                          "accent": curses.A_BOLD})
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
        height, width = self.stdscr.getmaxyx()
        return height, width

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
        self._layout_key = None
        if self.poller:
            self.poller.refresh()

    # -------------------------------------------------------------- draw

    def build(self) -> Layout:
        height, width = self.size()
        content_width = max(20, width - self.sidebar_width(width) - 6)
        tab = self._tab_key()
        with self.ctx.lock:
            data = self.ctx.page_data.get(self.page_key)
            blocks_key = (self.page_key, tab, content_width, id(data), len(self.ctx.history.get("gpu_clock", ())),
                          self.ctx.metrics_error, self.ctx.page_error.get(self.page_key),
                          id(self.ctx.metrics), self._state_signature())
            if blocks_key == self._layout_key and self._layout is not None:
                return self._layout
            try:
                blocks = self.page.build(self.ctx, data, tab, self)
            except Exception as error:
                from .content import Note

                blocks = [Note(describe_error(error), "bad")]
        self._layout = build_layout(blocks, content_width, self.glyphs)
        self._layout_key = blocks_key
        return self._layout

    def _state_signature(self) -> int:
        state = self.ctx.page_state.get(self.page_key)
        return hash(repr(sorted(state.items()))) if state else 0

    @staticmethod
    def sidebar_width(width: int) -> int:
        return max(18, min(26, width // 4))

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
        side = self.sidebar_width(width)
        self._draw_title(width)
        self._draw_sidebar(height, side)
        self._draw_content(height, width, side)
        self._draw_footer(height, width)
        self.stdscr.noutrefresh()

    def _draw_title(self, width: int) -> None:
        from bc250cc.shared.version import __version__

        title = f" BC250 Control Center  ·  {tr('Terminal mode')}  ·  v{__version__}"
        self.put(0, 0, pad(title, width), self.attrs["accent"] | curses.A_REVERSE)

    def _draw_sidebar(self, height: int, side: int) -> None:
        self.put(1, 1, tr("Sections").upper(), self.attrs["dim"])
        for index, key in enumerate(self.order):
            y = 2 + index
            if y >= height - 2:
                break
            number = str((index + 1) % 10) if index < 10 else " "
            label = f"{number} {tr(self.pages[key].title)}"
            selected = index == self.section
            if selected and self.focus == "sidebar":
                self.put(y, 0, pad(f" {label}", side), curses.A_REVERSE)
            elif selected:
                self.put(y, 0, pad(f"{self.glyphs.cursor}{label}", side), self.attrs["accent"])
            else:
                self.put(y, 0, f" {label}", 0, side - 1)
        for y in range(1, height - 1):
            self.put(y, side, "│" if self.glyphs.rule == "─" else "|", self.attrs["dim"])

    def _draw_content(self, height: int, width: int, side: int) -> None:
        x = side + 2
        top = 1
        tabs = self._tabs()
        if tabs:
            column = x
            current = self._tab_key()
            for key, label in tabs:
                text = f" {label} "
                attr = curses.A_REVERSE if key == current else self.attrs["dim"]
                self.put(top, column, text, attr)
                column += cell_width(text) + 1
            top += 2
        layout = self.build()
        view = height - top - 1
        slot = self._slot()
        cursor = self.cursor.get(slot, 0)
        cursor = max(0, min(cursor, len(layout.choices) - 1)) if layout.choices else 0
        self.cursor[slot] = cursor
        offset = self.scroll.get(slot, 0)
        if layout.choices:
            row = layout.choice_rows[cursor]
            if row < offset:
                offset = row
            elif row >= offset + view:
                offset = row - view + 1
        offset = max(0, min(offset, max(0, len(layout.rows) - view)))
        self.scroll[slot] = offset
        for line, row in enumerate(layout.rows[offset:offset + view]):
            y = top + line
            column = x
            selected = row.choice is not None and row.choice == cursor and self.focus == "content"
            if row.choice is not None:
                first = line == 0 or layout.rows[offset + line - 1].choice != row.choice
                marker = self.glyphs.cursor if selected and first else " "
                self.put(y, column, marker, self.attrs["accent"])
            column += 2
            for text, tone in row.spans:
                if tone.startswith("bar:"):
                    attr = self.attrs.get(tone[4:], 0) | curses.A_REVERSE
                else:
                    attr = self.attrs.get(tone, 0) | (curses.A_BOLD if row.bold and tone != "accent" else 0)
                if selected and not row.plain:
                    attr |= curses.A_REVERSE
                if tone == "sel" and self.focus != "content":
                    attr = self.attrs["accent"]
                self.put(y, column, text, attr, limit=width - column)
                column += cell_width(text)
        if len(layout.rows) > view:
            self.put(top, width - 1, "▲" if offset else " ", self.attrs["dim"])
            self.put(top + view - 1, width - 1, "▼" if offset + view < len(layout.rows) else " ", self.attrs["dim"])

    def _draw_footer(self, height: int, width: int) -> None:
        now = time.monotonic()
        if self.toast and self.toast[2] > now:
            self.put(height - 1, 1, pad(self.toast[0], width - 2), self.attrs.get(self.toast[1], 0) | curses.A_BOLD)
            return
        hints = [("↑↓", "Move"), ("Enter", "Open"), ("Tab", "Switch pane"), ("r", "Refresh"), ("?", "Help"), ("q", "Quit")]
        text = "  ".join(f"{key} {tr(label)}" for key, label in hints)
        self.put(height - 1, 1, pad(text, width - 2), self.attrs["dim"])

    # ------------------------------------------------------------- input

    def handle(self, code: int) -> None:
        if code == 3:
            raise Quit
        key = name_of(code)
        if key in ALIASES and self.focus in ("sidebar", "content"):
            key = ALIASES[key]
        if key == "resize":
            self._layout_key = None
            return
        if key == "q":
            raise Quit
        if key == "?":
            self.show_text(tr("Keyboard shortcuts"), self.help_text(), compact=True)
            return
        if key == "r":
            self.refresh()
            self.notify(tr("Refreshing…"))
            return
        if key == "tab":
            self.focus = "content" if self.focus == "sidebar" else "sidebar"
            return
        if key == "btab":
            self.focus = "sidebar"
            return
        if key in ("[", "]"):
            self._switch_tab(-1 if key == "[" else 1)
            return
        if key.isdigit() and len(key) == 1 and self.focus == "sidebar":
            index = (int(key) - 1) % 10
            if index < len(self.order):
                self._go(index)
            return
        (self._sidebar_key if self.focus == "sidebar" else self._content_key)(key)

    def _go(self, index: int) -> None:
        self.section = max(0, min(len(self.order) - 1, index))
        self._layout_key = None
        self._repaint()
        if self.poller:
            self.poller.show(self.page_key, self._tab_key())

    def _sidebar_key(self, key: str) -> None:
        if key == "up":
            self._go(self.section - 1)
        elif key == "down":
            self._go(self.section + 1)
        elif key == "home":
            self._go(0)
        elif key == "end":
            self._go(len(self.order) - 1)
        elif key in ("enter", "right", "space"):
            self.focus = "content"

    def _switch_tab(self, step: int) -> None:
        tabs = self._tabs()
        if not tabs:
            return
        keys = [name for name, _label in tabs]
        index = (keys.index(self._tab_key()) + step) % len(keys)
        self.tab[self.page_key] = keys[index]
        self._layout_key = None
        if self.poller:
            self.poller.show(self.page_key, keys[index])

    def _repaint(self) -> None:
        """Ask curses to redraw every cell, so stale ones cannot linger in the terminal."""
        try:
            self.stdscr.clearok(True)
        except (AttributeError, curses.error):
            pass

    def goto(self, page_key: str) -> None:
        if page_key in self.order:
            self._go(self.order.index(page_key))

    def _content_key(self, key: str) -> None:
        layout = self.build()
        slot = self._slot()
        cursor = self.cursor.get(slot, 0)
        view = max(1, self.size()[0] - 4)
        current = layout.choices[cursor] if layout.choices else None
        if current is not None and current.pad is not None:
            step = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}.get(key)
            if step and current.pad.move(*step):
                self._layout_key = None
                return
        if key in ("esc", "left") and not (key == "left" and layout.choices and layout.choices[cursor].adjust):
            if key == "left" and self._tabs():
                self._switch_tab(-1)
            else:
                self.focus = "sidebar"
        elif key == "right":
            choice = layout.choices[cursor] if layout.choices else None
            if choice is not None and choice.adjust:
                choice.adjust(self, 1)
            elif self._tabs():
                self._switch_tab(1)
        elif key == "left":
            layout.choices[cursor].adjust(self, -1)
        elif key in ("up", "down"):
            step = -1 if key == "up" else 1
            if layout.choices:
                self.cursor[slot] = max(0, min(len(layout.choices) - 1, cursor + step))
            else:
                self.scroll[slot] = max(0, self.scroll.get(slot, 0) + step)
        elif key in ("pgup", "pgdn"):
            step = -view if key == "pgup" else view
            if layout.choices:
                self.cursor[slot] = max(0, min(len(layout.choices) - 1, cursor + step))
            else:
                self.scroll[slot] = max(0, self.scroll.get(slot, 0) + step)
        elif key in ("home", "end"):
            self.cursor[slot] = 0 if key == "home" else max(0, len(layout.choices) - 1)
            self.scroll[slot] = 0 if key == "home" else 10**6
        elif key in ("enter", "space") and layout.choices:
            choice = layout.choices[cursor]
            if choice.enabled and choice.handler is not None:
                try:
                    choice.handler(self)
                except Quit:
                    raise
                except Exception as error:
                    self.notify(describe_error(error), "bad")
                self._layout_key = None

    # ------------------------------------------------------------ dialogs

    def help_text(self) -> str:
        rows = [
            ("↑ ↓  j k", tr("Move")), ("→ Enter l", tr("Open")), ("← Esc h", tr("Back")),
            ("Tab", tr("Switch pane")), ("[ ]", tr("Previous / next tab")), ("1-9 0", tr("Go to section")),
            ("PgUp PgDn", tr("Scroll")), ("r", tr("Refresh")), ("?", tr("Help")), ("q", tr("Quit")),
        ]
        return "\n".join(f"{pad(key, 14)} {label}" for key, label in rows)

    def _box(self, title: str, lines: list[str], *, width: int = 0, footer: str = "", selected: int | None = None,
             offset: int = 0) -> tuple[int, int, int, int]:
        height, total = self.size()
        inner = max([cell_width(line) for line in lines] + [cell_width(title), cell_width(footer)]) + 2
        box_w = min(total - 2, max(width, inner + 2, 30))
        box_h = min(height - 2, len(lines) + 2)
        top, left = max(0, (height - box_h) // 2), max(0, (total - box_w) // 2)
        for row in range(box_h):
            self.put(top + row, left, " " * box_w, curses.A_REVERSE if False else 0)
        horizontal = "─" * (box_w - 2) if self.glyphs.rule == "─" else "-" * (box_w - 2)
        self.put(top, left, f"┌{horizontal}┐" if self.glyphs.rule == "─" else f"+{horizontal}+", self.attrs["accent"])
        self.put(top, left + 2, f" {clip(title, box_w - 6)} ", self.attrs["accent"])
        visible = lines[offset:offset + box_h - 2]
        for index, line in enumerate(visible):
            row = top + 1 + index
            side = "│" if self.glyphs.rule == "─" else "|"
            self.put(row, left, side, self.attrs["accent"])
            self.put(row, left + box_w - 1, side, self.attrs["accent"])
            attr = curses.A_REVERSE if selected is not None and index + offset == selected else 0
            self.put(row, left + 1, pad(f" {line}", box_w - 2), attr)
        bottom = top + box_h - 1
        for row in range(top + 1 + len(visible), bottom):
            side = "│" if self.glyphs.rule == "─" else "|"
            self.put(row, left, side, self.attrs["accent"])
            self.put(row, left + box_w - 1, side, self.attrs["accent"])
        self.put(bottom, left, f"└{horizontal}┘" if self.glyphs.rule == "─" else f"+{horizontal}+", self.attrs["accent"])
        if footer:
            self.put(bottom, left + 2, f" {clip(footer, box_w - 6)} ", self.attrs["dim"])
        return top, left, box_h, box_w

    def _modal_key(self) -> str:
        """Block for one key; redraw the page underneath on every wake-up."""
        while True:
            code = self.stdscr.getch()
            if code == -1:
                continue
            key = name_of(code)
            if key == "resize":
                return "resize"
            return key

    def confirm(self, message: str, *, danger: bool = False) -> bool:
        while True:
            width = min(self.size()[1] - 8, 64)
            lines = wrap(message, max(10, width - 4))
            self.draw()
            self._box(tr("Confirm"), lines, width=width,
                      footer=f"y {tr('Yes')} · n {tr('No')}" + (" · !" if danger else ""))
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
            height = self.size()[0]
            offset = max(0, min(index - (height - 8) // 2, max(0, len(labels) - (height - 6))))
            self._box(title, labels, selected=index, offset=offset, footer="Enter · Esc")
            self.stdscr.refresh()
            key = self._read()
            if key == "up":
                index = max(0, index - 1)
            elif key == "down":
                index = min(len(options) - 1, index + 1)
            elif key in ("pgup", "home"):
                index = 0
            elif key in ("pgdn", "end"):
                index = len(options) - 1
            elif key in ("enter", "space", "right"):
                return options[index][0]
            elif key in ("esc", "left", "q"):
                return None

    def _read(self) -> str:
        """One key for a dialog, with the vim aliases applied."""
        key = self._modal_key()
        return ALIASES.get(key, key)

    def ask_text(self, label: str, default: str = "", *, numeric: bool = False) -> str | None:
        value, cursor = default, len(default)
        while True:
            self.draw()
            shown = value[:cursor] + "▏" + value[cursor:] if self.glyphs.rule == "─" else value[:cursor] + "_" + value[cursor:]
            self._box(label, [shown], width=50, footer="Enter · Esc")
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
            elif key == "left":
                cursor = max(0, cursor - 1)
            elif key == "right":
                cursor = min(len(value), cursor + 1)
            elif key == "home":
                cursor = 0
            elif key == "end":
                cursor = len(value)
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
                number = int(answer)
            except ValueError:
                self.notify(tr("Enter a whole number."), "warn")
                text = answer
                continue
            if minimum <= number <= maximum:
                return number
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
            if compact:
                self.draw()
                self._box(title, lines, offset=offset, footer="Esc")
                self.stdscr.refresh()
            else:
                view = max(1, height - 3)
                offset = max(0, min(offset, max(0, len(lines) - view)))
                self.stdscr.erase()
                self.put(0, 0, pad(f" {title}", width), self.attrs["accent"] | curses.A_REVERSE)
                for index, line in enumerate(lines[offset:offset + view]):
                    self.put(1 + index, 1, line)
                self.put(height - 1, 1, pad(
                    f"{offset + 1}-{min(len(lines), offset + view)}/{len(lines)}  "
                    f"↑↓ {tr('Scroll')}  PgUp PgDn  Esc", width - 2), self.attrs["dim"])
                self.stdscr.refresh()
            view = max(1, height - 3)
            key = self._read()
            if key in ("esc", "q", "left", "enter"):
                return
            if key == "up":
                offset -= 1
            elif key == "down":
                offset += 1
            elif key == "pgup":
                offset -= view
            elif key in ("pgdn", "space"):
                offset += view
            elif key == "home":
                offset = 0
            elif key == "end":
                offset = len(lines)
            offset = max(0, min(offset, max(0, len(lines) - view)))

    # ---------------------------------------------------------- foreground

    def run(self, label: str, work: Callable[[], Any]) -> tuple[bool, Any]:
        """Run a service call or workflow. It reports inside the interface when it can.

        A privilege prompt (pkexec) needs a graphical Polkit agent to stay off
        this screen; on a bare TTY there is none, so the screen is handed to the
        terminal for the call instead.
        """
        if self._foreground is not None:
            return self._foreground(label, work)
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            return self._run_in_console(label, work)
        return self._suspend_and_run(label, work)

    def execute(self, command: str) -> int:
        """Run a reviewed workflow command: in the console pane, else on this terminal."""
        console = self.active_console
        if console is None:
            return subprocess.run(["bash", "-c", command], check=False).returncode  # nosec B603 B607
        height, width = self.size()
        return console.run_command(command, (max(5, height - 2), max(20, width - 2)))

    def _run_in_console(self, label: str, work: Callable[[], Any]) -> tuple[bool, Any]:
        console = Console(label)
        self.active_console = console

        def job() -> None:
            try:
                with contextlib.redirect_stdout(console):
                    console.result = work()
            except Exception as error:
                console.ok, console.result = False, error
            finally:
                console.done.set()

        threading.Thread(target=job, name="bc250-tui-job", daemon=True).start()
        shown, finished_text = False, False
        try:
            while True:
                finished = console.done.is_set()
                if finished and not finished_text:
                    finished_text = True
                    if console.ok and isinstance(console.result, str) and console.result.strip():
                        console.write(("\n" if console.has_output else "") + console.result.strip() + "\n")
                    elif not console.ok:
                        from .runtime import describe_error
                        console.write(("\n" if console.has_output else "") + describe_error(console.result) + "\n")
                if finished and console.ok and not console.has_output:
                    break  # nothing worth reading: the toast says it
                shown = shown or finished or console.has_output or time.monotonic() - console.started > 0.6
                if shown:
                    self._draw_console(console, finished)
                code = self.stdscr.getch()
                if code == -1:
                    continue
                key = name_of(code)
                if finished:
                    if key in ("esc", "enter", "q"):
                        break
                    continue
                if code == 3:
                    console.interrupt()
                elif console.input_fd is not None:
                    data = {"enter": b"\n", "backspace": b"\x7f", "space": b" ", "tab": b"\t"}.get(key)
                    if data is None and len(key) == 1:
                        data = key.encode("utf-8")
                    if data:
                        console.send(data)
        finally:
            self.active_console = None
            self._layout_key = None
            self.stdscr.clearok(True)
        return console.ok, console.result

    def _draw_console(self, console: Console, finished: bool) -> None:
        height, width = self.size()
        self.stdscr.erase()
        self.put(0, 0, pad(f" {console.label}", width), self.attrs["accent"] | curses.A_REVERSE)
        lines = console.snapshot()
        while lines and not lines[-1].strip() and len(lines) > 1 and finished:
            lines.pop()
        view = max(1, height - 2)
        for index, line in enumerate(lines[-view:]):
            self.put(1 + index, 0, line.replace("\x00", ""))
        if finished:
            footer = ("OK" if console.ok else tr("Error")) + f" · Esc {tr('Back')}"
        else:
            footer = f"{tr('Waiting for data…')}  ·  Ctrl+C"
        self.put(height - 1, 1, pad(footer, width - 2), self.attrs["dim"])
        self.stdscr.refresh()

    def _suspend_and_run(self, label: str, work: Callable[[], Any]) -> tuple[bool, Any]:
        """Hand the terminal back for ``work``: privilege prompts and output need it."""
        curses.def_prog_mode()
        curses.endwin()
        ok, result = True, None
        try:
            print(f"\n== {label} ==\n", flush=True)
            try:
                result = work()
                if isinstance(result, str) and result.strip():
                    print(result.strip())
            except Exception as error:
                ok, result = False, error
                print(describe_error(error))
            input(f"\n{tr('Press Enter to return')}")
        except (EOFError, KeyboardInterrupt):
            pass
        finally:
            curses.reset_prog_mode()
            self.stdscr.refresh()
            self._layout_key = None
        return ok, result

    # ---------------------------------------------------------------- loop

    def loop(self) -> None:
        self.stdscr.keypad(True)
        curses.raw()  # Ctrl+C arrives as a key: it interrupts a running command, never kills the screen
        self.stdscr.timeout(200)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        try:
            curses.set_escdelay(25)
        except (AttributeError, curses.error):
            pass
        dirty = True
        while self.running:
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
