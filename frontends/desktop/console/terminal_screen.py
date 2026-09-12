"""A terminal screen that interprets the escape sequences our workflows emit.

This is not a general VT220 implementation and does not try to be one. It
covers what the privileged workflows of this application actually produce:
colour and text attributes, carriage-return progress redraws from package
managers, line and screen erasing, absolute and relative cursor moves, scroll
regions, the alternate screen buffer, and window titles. Full-screen curses
programs are out of scope by design; no workflow in this repository starts one.

The module is deliberately free of Qt so the behaviour can be tested as plain
data, which is where terminal emulation bugs are cheapest to find.
"""

from __future__ import annotations

import codecs
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Iterator

# A colour is either None (the theme default), an integer palette index in
# 0-255, or an explicit truecolor triple.
Color = int | tuple[int, int, int] | None

DEFAULT_COLUMNS = 100
DEFAULT_ROWS = 24
DEFAULT_SCROLLBACK = 5000

# Guards against a runaway process filling memory through one absurd escape
# sequence rather than through actual output.
MAX_COLUMNS = 1000
MAX_ROWS = 400


@dataclass(frozen=True)
class CellStyle:
    """The rendering attributes of a single character."""

    foreground: Color = None
    background: Color = None
    bold: bool = False
    dim: bool = False
    italic: bool = False
    underline: bool = False
    inverse: bool = False
    hidden: bool = False
    strike: bool = False

    def resolved(self) -> tuple[Color, Color]:
        """Return (foreground, background) with inverse video already applied."""
        foreground, background = self.foreground, self.background
        if self.inverse:
            foreground, background = background, foreground
            if foreground is None:
                foreground = "inverse-default-foreground"
            if background is None:
                background = "inverse-default-background"
        if self.hidden:
            foreground = background
        return foreground, background


DEFAULT_STYLE = CellStyle()


@dataclass(frozen=True)
class Cell:
    """One character position on the screen."""

    text: str = " "
    style: CellStyle = DEFAULT_STYLE
    # A wide character occupies two columns; the second one is a placeholder
    # that must not be painted or the glyph is drawn twice.
    width: int = 1
    placeholder: bool = False


BLANK = Cell()


@dataclass
class _Cursor:
    x: int = 0
    y: int = 0
    style: CellStyle = DEFAULT_STYLE
    # DECAWM defers the wrap until the next character, so writing the last
    # column does not by itself move to the following line. Progress bars that
    # exactly fill the width depend on this.
    pending_wrap: bool = False


@dataclass
class _Buffer:
    lines: list[list[Cell]] = field(default_factory=list)
    cursor: _Cursor = field(default_factory=_Cursor)
    scroll_top: int = 0
    scroll_bottom: int = 0


def character_width(character: str) -> int:
    """Return how many columns a character occupies."""
    if unicodedata.combining(character):
        return 0
    codepoint = ord(character)
    if codepoint < 0x20 or codepoint == 0x7F:
        return 0
    if unicodedata.east_asian_width(character) in ("W", "F"):
        return 2
    return 1


class TerminalScreen:
    """A grid of styled cells fed with the raw bytes of a pseudo-terminal."""

    def __init__(
        self,
        columns: int = DEFAULT_COLUMNS,
        rows: int = DEFAULT_ROWS,
        *,
        scrollback: int = DEFAULT_SCROLLBACK,
    ) -> None:
        self.columns = max(1, min(int(columns), MAX_COLUMNS))
        self.rows = max(1, min(int(rows), MAX_ROWS))
        self.scrollback_limit = max(0, int(scrollback))
        self.scrollback: list[list[Cell]] = []
        self.title = ""
        self.cursor_visible = True
        self.bracketed_paste = False
        self.autowrap = True
        # DECCKM. A program that turns this on expects SS3 rather than CSI for
        # the arrow keys, and receives literal characters if we ignore it.
        self.application_cursor = False
        self.bell_count = 0
        # Replies the host must write back to the pseudo-terminal, for the few
        # queries a shell prompt may send (cursor position, device attributes).
        self.pending_response = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._primary = _Buffer()
        self._alternate: _Buffer | None = None
        self._saved_cursor: _Cursor | None = None
        self._state = "ground"
        self._parameters = ""
        self._intermediate = ""
        self._string = ""
        self._string_kind = ""
        self.reset()

    # ------------------------------------------------------------------ setup

    def reset(self) -> None:
        self._primary = _Buffer(
            lines=[self._blank_line() for _ in range(self.rows)],
            cursor=_Cursor(),
            scroll_top=0,
            scroll_bottom=self.rows - 1,
        )
        self._alternate = None
        self._saved_cursor = None
        self.scrollback.clear()
        self.cursor_visible = True
        self.autowrap = True
        self.bracketed_paste = False
        self.application_cursor = False
        self._state = "ground"

    def _blank_line(self) -> list[Cell]:
        return [BLANK] * self.columns

    @property
    def _buffer(self) -> _Buffer:
        return self._alternate if self._alternate is not None else self._primary

    @property
    def lines(self) -> list[list[Cell]]:
        return self._buffer.lines

    @property
    def cursor(self) -> _Cursor:
        return self._buffer.cursor

    @property
    def in_alternate_screen(self) -> bool:
        return self._alternate is not None

    def resize(self, columns: int, rows: int) -> None:
        """Change the grid size, keeping the content anchored at the top left.

        Real terminals reflow wrapped lines on resize. This one does not: it
        pads or truncates each line and clamps the cursor. Output already
        printed keeps its line breaks where they were, which is honest about
        what happened rather than pretending the process wrote it differently.
        """
        columns = max(1, min(int(columns), MAX_COLUMNS))
        rows = max(1, min(int(rows), MAX_ROWS))
        if columns == self.columns and rows == self.rows:
            return
        self.columns = columns
        self.rows = rows
        for buffer in (self._primary, self._alternate):
            if buffer is None:
                continue
            for index, line in enumerate(buffer.lines):
                if len(line) < columns:
                    buffer.lines[index] = line + [BLANK] * (columns - len(line))
                elif len(line) > columns:
                    buffer.lines[index] = line[:columns]
            while len(buffer.lines) > rows:
                # Drop from the top so the most recent output stays visible,
                # and keep it in the scrollback of the primary screen.
                dropped = buffer.lines.pop(0)
                if buffer is self._primary:
                    self._push_scrollback(dropped)
                buffer.cursor.y = max(0, buffer.cursor.y - 1)
            while len(buffer.lines) < rows:
                # Take the history back before padding. Without this, a panel
                # that grows shows one line of output over a field of blanks:
                # everything printed while it was small stayed stranded in the
                # scrollback and the screen was filled with empty rows instead.
                if buffer is self._primary and self.scrollback:
                    recovered = self.scrollback.pop()
                    if len(recovered) < columns:
                        recovered = recovered + [BLANK] * (columns - len(recovered))
                    buffer.lines.insert(0, recovered)
                    buffer.cursor.y += 1
                else:
                    buffer.lines.append(self._blank_line())
            buffer.scroll_top = 0
            buffer.scroll_bottom = rows - 1
            buffer.cursor.x = min(buffer.cursor.x, columns - 1)
            buffer.cursor.y = min(buffer.cursor.y, rows - 1)
            buffer.cursor.pending_wrap = False
        for index, line in enumerate(self.scrollback):
            if len(line) > columns:
                self.scrollback[index] = line[:columns]

    # ------------------------------------------------------------------ input

    def feed(self, data: bytes | str) -> None:
        """Interpret a chunk of terminal output.

        Multi-byte characters split across chunks are held by the incremental
        decoder, so a UTF-8 sequence arriving in two reads is not corrupted.
        """
        if isinstance(data, bytes):
            text = self._decoder.decode(data)
        else:
            text = data
        for character in text:
            self._feed_character(character)

    def take_response(self) -> str:
        """Drain and return whatever the screen owes the process."""
        response, self.pending_response = self.pending_response, ""
        return response

    def _feed_character(self, character: str) -> None:
        state = self._state
        if state == "ground":
            self._ground(character)
        elif state == "escape":
            self._escape(character)
        elif state == "csi":
            self._csi(character)
        elif state == "string":
            self._string_sequence(character)
        elif state == "charset":
            # A designator such as ESC ( B. We render Unicode directly, so the
            # selected character set is consumed and ignored.
            self._state = "ground"

    # ----------------------------------------------------------------- ground

    def _ground(self, character: str) -> None:
        code = ord(character)
        if code == 0x1B:
            self._state = "escape"
            self._parameters = ""
            self._intermediate = ""
            return
        if code == 0x0D:
            self.cursor.x = 0
            self.cursor.pending_wrap = False
            return
        if code == 0x0A or code == 0x0B or code == 0x0C:
            self._line_feed()
            return
        if code == 0x08:
            self.cursor.pending_wrap = False
            self.cursor.x = max(0, self.cursor.x - 1)
            return
        if code == 0x09:
            self._tab()
            return
        if code == 0x07:
            self.bell_count += 1
            return
        if code < 0x20 or code == 0x7F:
            return
        self._write(character)

    def _tab(self) -> None:
        self.cursor.pending_wrap = False
        target = ((self.cursor.x // 8) + 1) * 8
        self.cursor.x = min(target, self.columns - 1)

    def _write(self, character: str) -> None:
        width = character_width(character)
        if width == 0:
            # A combining mark belongs to the character already written.
            self._combine(character)
            return
        if self.cursor.pending_wrap:
            self.cursor.x = 0
            self._line_feed()
            self.cursor.pending_wrap = False
        if width == 2 and self.cursor.x == self.columns - 1:
            # A double-width glyph never straddles the right margin.
            if self.autowrap:
                self.cursor.x = 0
                self._line_feed()
            else:
                return
        line = self.lines[self.cursor.y]
        style = self.cursor.style
        self._clear_placeholder_at(line, self.cursor.x)
        line[self.cursor.x] = Cell(character, style, width)
        if width == 2 and self.cursor.x + 1 < self.columns:
            line[self.cursor.x + 1] = Cell("", style, 0, placeholder=True)
        advance = self.cursor.x + width
        if advance >= self.columns:
            if self.autowrap:
                self.cursor.x = self.columns - 1
                self.cursor.pending_wrap = True
            else:
                self.cursor.x = self.columns - 1
        else:
            self.cursor.x = advance

    def _clear_placeholder_at(self, line: list[Cell], column: int) -> None:
        """Overwriting half of a wide glyph must erase the other half too."""
        cell = line[column]
        if cell.placeholder and column > 0:
            line[column - 1] = Cell(" ", line[column - 1].style)
        elif cell.width == 2 and column + 1 < len(line):
            line[column + 1] = Cell(" ", cell.style)

    def _combine(self, character: str) -> None:
        column = self.cursor.x - 1
        line = self.lines[self.cursor.y]
        while column >= 0 and line[column].placeholder:
            column -= 1
        if column < 0:
            return
        base = line[column]
        line[column] = Cell(base.text + character, base.style, base.width, base.placeholder)

    def _line_feed(self) -> None:
        self.cursor.pending_wrap = False
        buffer = self._buffer
        if self.cursor.y == buffer.scroll_bottom:
            self._scroll_up(1)
        elif self.cursor.y < self.rows - 1:
            self.cursor.y += 1

    def _scroll_up(self, count: int) -> None:
        buffer = self._buffer
        top, bottom = buffer.scroll_top, buffer.scroll_bottom
        for _ in range(max(0, count)):
            dropped = buffer.lines.pop(top)
            if buffer is self._primary and top == 0 and bottom == self.rows - 1:
                self._push_scrollback(dropped)
            buffer.lines.insert(bottom, self._blank_line())

    def _scroll_down(self, count: int) -> None:
        buffer = self._buffer
        top, bottom = buffer.scroll_top, buffer.scroll_bottom
        for _ in range(max(0, count)):
            buffer.lines.pop(bottom)
            buffer.lines.insert(top, self._blank_line())

    def _push_scrollback(self, line: list[Cell]) -> None:
        if self.scrollback_limit <= 0:
            return
        # Trailing blanks carry no information and dominate the memory a long
        # installation log would otherwise hold.
        end = len(line)
        while end > 0 and line[end - 1] == BLANK:
            end -= 1
        self.scrollback.append(line[:end])
        overflow = len(self.scrollback) - self.scrollback_limit
        if overflow > 0:
            del self.scrollback[:overflow]

    # ----------------------------------------------------------------- escape

    def _escape(self, character: str) -> None:
        if character == "[":
            self._state = "csi"
            self._parameters = ""
            self._intermediate = ""
            return
        if character in "]P^_X":
            self._state = "string"
            self._string = ""
            self._string_kind = character
            return
        if character in "()*+-./":
            self._state = "charset"
            return
        self._state = "ground"
        if character == "7":
            self._save_cursor()
        elif character == "8":
            self._restore_cursor()
        elif character == "D":
            self._line_feed()
        elif character == "E":
            self.cursor.x = 0
            self._line_feed()
        elif character == "M":
            self._reverse_index()
        elif character == "c":
            self.reset()
        elif character == "\\":
            pass  # A string terminator with no string open.

    def _reverse_index(self) -> None:
        buffer = self._buffer
        if self.cursor.y == buffer.scroll_top:
            self._scroll_down(1)
        elif self.cursor.y > 0:
            self.cursor.y -= 1

    def _save_cursor(self) -> None:
        self._saved_cursor = replace(self.cursor)

    def _restore_cursor(self) -> None:
        saved = self._saved_cursor
        if saved is None:
            self.cursor.x = 0
            self.cursor.y = 0
            self.cursor.style = DEFAULT_STYLE
            return
        self.cursor.x = min(saved.x, self.columns - 1)
        self.cursor.y = min(saved.y, self.rows - 1)
        self.cursor.style = saved.style
        self.cursor.pending_wrap = False

    # -------------------------------------------------------------- CSI / OSC

    def _csi(self, character: str) -> None:
        code = ord(character)
        if 0x30 <= code <= 0x3F:
            self._parameters += character
            return
        if 0x20 <= code <= 0x2F:
            self._intermediate += character
            return
        self._state = "ground"
        if 0x40 <= code <= 0x7E:
            self._dispatch_csi(character)

    def _string_sequence(self, character: str) -> None:
        code = ord(character)
        if code == 0x07:
            self._finish_string()
            return
        if code == 0x1B:
            # Expect the backslash of a string terminator.
            self._string += "\x1b"
            return
        if character == "\\" and self._string.endswith("\x1b"):
            self._string = self._string[:-1]
            self._finish_string()
            return
        if code < 0x20 and code not in (0x08, 0x09):
            return
        self._string += character

    def _finish_string(self) -> None:
        payload, kind = self._string, self._string_kind
        self._string = ""
        self._state = "ground"
        if kind != "]":
            return  # DCS, APC, PM and SOS carry nothing we render.
        parts = payload.split(";", 1)
        if len(parts) == 2 and parts[0] in ("0", "1", "2"):
            self.title = parts[1]

    def _numbers(self, default: int = 0) -> list[int]:
        raw = self._parameters.lstrip("?<>=")
        values: list[int] = []
        for part in raw.split(";"):
            part = part.split(":", 1)[0]
            if not part:
                values.append(default)
                continue
            try:
                values.append(int(part))
            except ValueError:
                values.append(default)
        return values or [default]

    def _first(self, default: int = 1) -> int:
        value = self._numbers(0)[0]
        return value if value > 0 else default

    def _dispatch_csi(self, final: str) -> None:
        private = self._parameters.startswith("?")
        if private and final in "hl":
            self._set_mode(self._numbers(0), final == "h")
            return
        handler = {
            "A": self._cursor_up,
            "B": self._cursor_down,
            "C": self._cursor_forward,
            "D": self._cursor_back,
            "E": self._cursor_next_line,
            "F": self._cursor_previous_line,
            "G": self._cursor_column,
            "`": self._cursor_column,
            "d": self._cursor_row,
            "H": self._cursor_position,
            "f": self._cursor_position,
            "J": self._erase_display,
            "K": self._erase_line,
            "L": self._insert_lines,
            "M": self._delete_lines,
            "P": self._delete_characters,
            "@": self._insert_characters,
            "X": self._erase_characters,
            "S": self._scroll_up_command,
            "T": self._scroll_down_command,
            "m": self._select_graphic_rendition,
            "r": self._set_scroll_region,
            "s": lambda: self._save_cursor(),
            "u": lambda: self._restore_cursor(),
            "n": self._device_status,
            "c": self._device_attributes,
            "h": lambda: self._set_ansi_mode(True),
            "l": lambda: self._set_ansi_mode(False),
        }.get(final)
        if handler is not None:
            handler()

    # ---------------------------------------------------------- cursor motion

    def _cursor_up(self) -> None:
        self.cursor.pending_wrap = False
        self.cursor.y = max(self._buffer.scroll_top, self.cursor.y - self._first())

    def _cursor_down(self) -> None:
        self.cursor.pending_wrap = False
        self.cursor.y = min(self._buffer.scroll_bottom, self.cursor.y + self._first())

    def _cursor_forward(self) -> None:
        self.cursor.pending_wrap = False
        self.cursor.x = min(self.columns - 1, self.cursor.x + self._first())

    def _cursor_back(self) -> None:
        self.cursor.pending_wrap = False
        self.cursor.x = max(0, self.cursor.x - self._first())

    def _cursor_next_line(self) -> None:
        self._cursor_down()
        self.cursor.x = 0

    def _cursor_previous_line(self) -> None:
        self._cursor_up()
        self.cursor.x = 0

    def _cursor_column(self) -> None:
        self.cursor.pending_wrap = False
        self.cursor.x = max(0, min(self.columns - 1, self._first() - 1))

    def _cursor_row(self) -> None:
        self.cursor.pending_wrap = False
        self.cursor.y = max(0, min(self.rows - 1, self._first() - 1))

    def _cursor_position(self) -> None:
        values = self._numbers(1)
        row = values[0] if values and values[0] > 0 else 1
        column = values[1] if len(values) > 1 and values[1] > 0 else 1
        self.cursor.pending_wrap = False
        self.cursor.y = max(0, min(self.rows - 1, row - 1))
        self.cursor.x = max(0, min(self.columns - 1, column - 1))

    # ---------------------------------------------------------------- erasing

    def _blank_cell(self) -> Cell:
        # Erasing keeps the current background so a coloured band stays whole.
        style = CellStyle(background=self.cursor.style.background)
        return BLANK if style == DEFAULT_STYLE else Cell(" ", style)

    def _erase_display(self) -> None:
        mode = self._numbers(0)[0]
        blank = self._blank_cell()
        if mode == 0:
            self._erase_in_line(0)
            for index in range(self.cursor.y + 1, self.rows):
                self.lines[index] = [blank] * self.columns
        elif mode == 1:
            self._erase_in_line(1)
            for index in range(0, self.cursor.y):
                self.lines[index] = [blank] * self.columns
        elif mode in (2, 3):
            for index in range(self.rows):
                self.lines[index] = [blank] * self.columns
            if mode == 3:
                self.scrollback.clear()
        self.cursor.pending_wrap = False

    def _erase_line(self) -> None:
        self._erase_in_line(self._numbers(0)[0])
        self.cursor.pending_wrap = False

    def _erase_in_line(self, mode: int) -> None:
        line = self.lines[self.cursor.y]
        blank = self._blank_cell()
        if mode == 0:
            for index in range(self.cursor.x, self.columns):
                line[index] = blank
        elif mode == 1:
            for index in range(0, min(self.cursor.x + 1, self.columns)):
                line[index] = blank
        elif mode == 2:
            self.lines[self.cursor.y] = [blank] * self.columns

    def _erase_characters(self) -> None:
        line = self.lines[self.cursor.y]
        blank = self._blank_cell()
        for index in range(self.cursor.x, min(self.cursor.x + self._first(), self.columns)):
            line[index] = blank

    def _insert_characters(self) -> None:
        line = self.lines[self.cursor.y]
        blank = self._blank_cell()
        for _ in range(self._first()):
            line.insert(self.cursor.x, blank)
            line.pop()

    def _delete_characters(self) -> None:
        line = self.lines[self.cursor.y]
        blank = self._blank_cell()
        for _ in range(self._first()):
            if self.cursor.x < len(line):
                line.pop(self.cursor.x)
                line.append(blank)

    def _insert_lines(self) -> None:
        buffer = self._buffer
        if not buffer.scroll_top <= self.cursor.y <= buffer.scroll_bottom:
            return
        for _ in range(self._first()):
            buffer.lines.pop(buffer.scroll_bottom)
            buffer.lines.insert(self.cursor.y, self._blank_line())

    def _delete_lines(self) -> None:
        buffer = self._buffer
        if not buffer.scroll_top <= self.cursor.y <= buffer.scroll_bottom:
            return
        for _ in range(self._first()):
            buffer.lines.pop(self.cursor.y)
            buffer.lines.insert(buffer.scroll_bottom, self._blank_line())

    def _scroll_up_command(self) -> None:
        self._scroll_up(self._first())

    def _scroll_down_command(self) -> None:
        self._scroll_down(self._first())

    def _set_scroll_region(self) -> None:
        values = self._numbers(0)
        top = values[0] - 1 if values and values[0] > 0 else 0
        bottom = values[1] - 1 if len(values) > 1 and values[1] > 0 else self.rows - 1
        top = max(0, min(top, self.rows - 1))
        bottom = max(0, min(bottom, self.rows - 1))
        if top >= bottom:
            top, bottom = 0, self.rows - 1
        buffer = self._buffer
        buffer.scroll_top, buffer.scroll_bottom = top, bottom
        self.cursor.x = 0
        self.cursor.y = top
        self.cursor.pending_wrap = False

    # ------------------------------------------------------------------ modes

    def _set_ansi_mode(self, enabled: bool) -> None:
        for value in self._numbers(0):
            if value == 4:
                pass  # Insert mode: no workflow here uses it.

    def _set_mode(self, values: list[int], enabled: bool) -> None:
        for value in values:
            if value == 1:
                self.application_cursor = enabled
            elif value == 25:
                self.cursor_visible = enabled
            elif value == 7:
                self.autowrap = enabled
            elif value == 2004:
                self.bracketed_paste = enabled
            elif value in (47, 1047, 1049):
                self._switch_alternate(enabled, save_cursor=value == 1049)

    def _switch_alternate(self, enabled: bool, *, save_cursor: bool) -> None:
        if enabled:
            if self._alternate is not None:
                return
            if save_cursor:
                self._save_cursor()
            self._alternate = _Buffer(
                lines=[self._blank_line() for _ in range(self.rows)],
                cursor=_Cursor(style=self.cursor.style),
                scroll_top=0,
                scroll_bottom=self.rows - 1,
            )
            return
        if self._alternate is None:
            return
        self._alternate = None
        if save_cursor:
            self._restore_cursor()

    def _device_status(self) -> None:
        value = self._numbers(0)[0]
        if value == 5:
            self.pending_response += "\x1b[0n"
        elif value == 6:
            self.pending_response += f"\x1b[{self.cursor.y + 1};{self.cursor.x + 1}R"

    def _device_attributes(self) -> None:
        # Answer as a plain VT100 so a shell does not assume features we lack.
        self.pending_response += "\x1b[?1;2c"

    # -------------------------------------------------------------------- SGR

    def _select_graphic_rendition(self) -> None:
        raw = self._parameters
        if raw.startswith("?"):
            return
        values, colon_colours = self._sgr_values(raw)
        style = self.cursor.style
        index = 0
        while index < len(values):
            value = values[index]
            if index in colon_colours:
                colour = colon_colours[index]
                if colour is not None:
                    field_name = "foreground" if value == 38 else "background"
                    style = replace(style, **{field_name: colour})
                index += 1
                continue
            if value == 0:
                style = DEFAULT_STYLE
            elif value == 1:
                style = replace(style, bold=True)
            elif value == 2:
                style = replace(style, dim=True)
            elif value == 3:
                style = replace(style, italic=True)
            elif value == 4:
                style = replace(style, underline=True)
            elif value == 7:
                style = replace(style, inverse=True)
            elif value == 8:
                style = replace(style, hidden=True)
            elif value == 9:
                style = replace(style, strike=True)
            elif value == 21:
                style = replace(style, bold=False)
            elif value == 22:
                style = replace(style, bold=False, dim=False)
            elif value == 23:
                style = replace(style, italic=False)
            elif value == 24:
                style = replace(style, underline=False)
            elif value == 27:
                style = replace(style, inverse=False)
            elif value == 28:
                style = replace(style, hidden=False)
            elif value == 29:
                style = replace(style, strike=False)
            elif 30 <= value <= 37:
                style = replace(style, foreground=value - 30)
            elif value == 39:
                style = replace(style, foreground=None)
            elif 40 <= value <= 47:
                style = replace(style, background=value - 40)
            elif value == 49:
                style = replace(style, background=None)
            elif 90 <= value <= 97:
                style = replace(style, foreground=value - 90 + 8)
            elif 100 <= value <= 107:
                style = replace(style, background=value - 100 + 8)
            elif value in (38, 48):
                colour, consumed = self._extended_colour(values, index)
                index += consumed
                if colour is not False:
                    field_name = "foreground" if value == 38 else "background"
                    style = replace(style, **{field_name: colour})
            index += 1
        self.cursor.style = style

    @classmethod
    def _sgr_values(cls, raw: str) -> tuple[list[int], dict[int, Color]]:
        """Split the parameters, resolving the colon form of 38 and 48 in place.

        The two spellings are not interchangeable. ``38;2;r;g;b`` is five
        parameters, while ``38:2::r:g:b`` is one parameter whose third field is
        an optional colour space that must be skipped rather than read as red.
        Flattening both into one list silently shifts the channels, which is
        how ``38:2::12:34:56`` used to arrive as the colour (0, 12, 34).
        """
        values: list[int] = []
        colon_colours: dict[int, Color] = {}
        for part in raw.split(";"):
            pieces = part.split(":")
            if len(pieces) > 1 and cls._as_int(pieces[0]) in (38, 48):
                colon_colours[len(values)] = cls._colon_colour(pieces)
                values.append(cls._as_int(pieces[0]))
                continue
            for piece in pieces:
                values.append(cls._as_int(piece))
        return (values or [0]), colon_colours

    @staticmethod
    def _as_int(piece: str) -> int:
        try:
            return int(piece)
        except ValueError:
            return 0

    @classmethod
    def _colon_colour(cls, pieces: list[str]) -> Color:
        kind = cls._as_int(pieces[1]) if len(pieces) > 1 else 0
        if kind == 5 and len(pieces) > 2:
            return max(0, min(255, cls._as_int(pieces[2])))
        if kind == 2:
            # Either 38:2:<space>:r:g:b or the shorter 38:2:r:g:b.
            channels = pieces[3:6] if len(pieces) >= 6 else pieces[2:5]
            if len(channels) == 3:
                return tuple(max(0, min(255, cls._as_int(value))) for value in channels)
        return None

    @staticmethod
    def _extended_colour(values: list[int], index: int) -> tuple[Color | bool, int]:
        if index + 1 >= len(values):
            return False, 0
        kind = values[index + 1]
        if kind == 5 and index + 2 < len(values):
            return max(0, min(255, values[index + 2])), 2
        if kind == 2 and index + 4 < len(values):
            red, green, blue = values[index + 2 : index + 5]
            return (
                max(0, min(255, red)),
                max(0, min(255, green)),
                max(0, min(255, blue)),
            ), 4
        return False, 1

    # ------------------------------------------------------------------ views

    def visible_text(self) -> str:
        """The screen as plain text, trailing blanks removed."""
        return "\n".join(_line_text(line) for line in self.lines)

    def full_text(self) -> str:
        """Scrollback plus screen, for copying an entire run."""
        rendered = [_line_text(line) for line in self.scrollback]
        rendered.extend(_line_text(line) for line in self.lines)
        while rendered and not rendered[-1]:
            rendered.pop()
        return "\n".join(rendered)

    def all_lines(self) -> list[list[Cell]]:
        return self.scrollback + self.lines

    @staticmethod
    def runs(line: list[Cell]) -> Iterator[tuple[int, str, CellStyle]]:
        """Yield (column, text, style) for each stretch sharing one style.

        Painting per cell is what makes a naive terminal widget slow. Grouping
        by style lets the view draw a whole coloured segment in one call.
        """
        column = 0
        start = 0
        buffer: list[str] = []
        current: CellStyle | None = None
        for cell in line:
            if cell.placeholder:
                column += 1
                continue
            if current is None or cell.style != current:
                if buffer:
                    yield start, "".join(buffer), current or DEFAULT_STYLE
                buffer = []
                start = column
                current = cell.style
            buffer.append(cell.text or " ")
            column += 1
        if buffer:
            yield start, "".join(buffer), current or DEFAULT_STYLE


def _line_text(line: list[Cell]) -> str:
    text = "".join("" if cell.placeholder else (cell.text or " ") for cell in line)
    return text.rstrip()
