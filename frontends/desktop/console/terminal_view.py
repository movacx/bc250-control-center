"""The widget that draws the terminal grid and forwards typing to the process."""

from __future__ import annotations

from PyQt6.QtCore import QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QGuiApplication,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import QAbstractScrollArea, QMenu, QSizePolicy

from ..theme import COLORS
from .key_bindings import key_sequence, paste_payload
from .palette import brighten_for_bold, resolve
from .terminal_screen import TerminalScreen

# Output arrives in bursts far faster than anyone can read. Repainting on every
# chunk is what makes a naive terminal widget stall the whole interface during
# a package installation, so paints are coalesced onto a fixed cadence.
REPAINT_INTERVAL_MS = 33

MINIMUM_COLUMNS = 20
MINIMUM_ROWS = 3

# Text flush against the frame reads as unfinished, and lines packed at the
# font's own height read as dense. Both are what separates a terminal that
# looks built from one that looks emitted.
PADDING_X = 12
PADDING_TOP = 8
LINE_HEIGHT = 1.32

_MONOSPACE_PREFERENCES = (
    "JetBrains Mono",
    "Cascadia Mono",
    "Fira Code",
    "Source Code Pro",
    "DejaVu Sans Mono",
    "Liberation Mono",
    "Noto Sans Mono",
    "Ubuntu Mono",
)


def console_font(point_size: int = 10) -> QFont:
    """Pick a monospace face, preferring the ones that ship with our targets."""
    available = set(QFontDatabase.families())
    for family in _MONOSPACE_PREFERENCES:
        if family in available:
            font = QFont(family)
            break
    else:
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setStyleHint(QFont.StyleHint.Monospace, QFont.StyleStrategy.PreferQuality)
    font.setFixedPitch(True)
    font.setPointSize(max(6, int(point_size)))
    return font


class TerminalView(QAbstractScrollArea):
    """A scrollable view of a :class:`TerminalScreen`, with keyboard input."""

    size_changed = pyqtSignal(int, int)
    input_ready = pyqtSignal(bytes)
    bell = pyqtSignal()

    def __init__(self, parent=None, *, point_size: int = 10, scrollback: int = 5000) -> None:
        super().__init__(parent)
        self.setObjectName("embeddedTerminalView")
        # A controller cannot type into a grid. The panel's answer row is the
        # way in, so navigation must not offer this as a stop it has to leave.
        self.setProperty("gamepadSkip", True)
        self.screen = TerminalScreen(80, 24, scrollback=scrollback)
        self._cell_width = 8.0
        self._cell_height = 16.0
        self._ascent = 12.0
        self._baseline = 12.0
        self._point_size = point_size
        self._selection: tuple[tuple[int, int], tuple[int, int]] | None = None
        self._selecting = False
        self._follow_output = True
        self._bell_pending = False
        self._expected_height = 0
        self._input_elsewhere = False
        self._colors: dict[str, QColor] = {}
        # The grid is measured and painted with this font, never with
        # ``self.font()``: the application stylesheet gives every widget its
        # interface face, and a proportional face painted over a monospace
        # grid left the cursor columns past the end of the text it follows
        # ("[sudo] password for …:" and then a gap before the caret).
        self._grid_font = console_font(point_size)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFrameShape(QAbstractScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._repaint_timer = QTimer(self)
        self._repaint_timer.setSingleShot(True)
        self._repaint_timer.setInterval(REPAINT_INTERVAL_MS)
        self._repaint_timer.timeout.connect(self._flush)

        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(530)
        self._cursor_timer.timeout.connect(self._blink)
        self._cursor_on = True

        self.apply_theme()
        self.verticalScrollBar().valueChanged.connect(self._scrolled)

    # ------------------------------------------------------------------ theme

    def apply_theme(self, point_size: int | None = None) -> None:
        """Re-read the palette and font metrics after an appearance change."""
        if point_size is not None:
            self._point_size = int(point_size)
        font = console_font(self._point_size)
        self.setFont(font)
        self.viewport().setFont(font)
        metrics = QFontMetricsF(font)
        # A rounded advance keeps every column on a whole pixel; a fractional
        # one accumulates and the grid visibly shears at the right edge.
        # A terminal is a grid, and every glyph has to land on it. A monospace
        # advance is rarely a whole number of pixels — DejaVu Sans Mono at this
        # size advances 7.8125px — so a rounded cell and the font's own advance
        # drift apart by a fraction per column. Over eighty columns that is two
        # whole characters, and the cursor, the selection and the coloured cell
        # backgrounds all end up somewhere the text is not. Absolute letter
        # spacing closes the gap once, at the source.
        natural = metrics.horizontalAdvance("M")
        self._cell_width = max(1.0, round(natural))
        font.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing, self._cell_width - natural
        )
        self.setFont(font)
        self.viewport().setFont(font)
        self._grid_font = QFont(font)
        metrics = QFontMetricsF(font)
        glyph_height = metrics.height()
        self._cell_height = max(1.0, round(glyph_height * LINE_HEIGHT))
        self._ascent = metrics.ascent()
        # The extra leading is split above and below, so the glyphs sit in the
        # middle of their row instead of hanging from the top of it.
        self._baseline = (self._cell_height - glyph_height) / 2 + metrics.ascent()
        self._colors = {
            "background": QColor(COLORS["console_bg"]),
            "text": QColor(COLORS["console_text"]),
            "border": QColor(COLORS["console_border"]),
            "accent": QColor(COLORS["blue"]),
        }
        selection = QColor(COLORS["blue"])
        selection.setAlpha(90)
        self._colors["selection"] = selection
        self.viewport().update()
        self._recalculate_geometry()

    # -------------------------------------------------------------- geometry

    @property
    def columns(self) -> int:
        return self.screen.columns

    @property
    def rows(self) -> int:
        return self.screen.rows

    def _visible_columns(self) -> int:
        width = max(1, self.viewport().width() - PADDING_X * 2)
        return max(MINIMUM_COLUMNS, int(width // self._cell_width))

    def _visible_rows(self) -> int:
        return max(MINIMUM_ROWS, int(self._effective_height() // self._cell_height))

    def _effective_height(self) -> int:
        """The height to size the grid for.

        While the panel slides into place its viewport is a few pixels tall.
        Sizing the grid from that gives the child process a three-row terminal
        for the first moments of a workflow, and every line it prints in that
        window scrolls straight out of view. The panel therefore announces the
        height it is heading for, and the announcement is dropped as soon as
        the viewport has actually reached it.
        """
        actual = max(1, self.viewport().height() - PADDING_TOP)
        if self._expected_height and actual < self._expected_height:
            return max(1, self._expected_height - PADDING_TOP)
        return actual

    def set_input_elsewhere(self, elsewhere: bool) -> None:
        """Say that another widget is the place to answer right now.

        A terminal draws a cursor to mean "type here". While the panel's answer
        row is holding the keyboard, the grid drawing one too shows two places
        to type for one prompt — which is exactly as confusing as it sounds
        when the prompt is asking for a password.
        """
        elsewhere = bool(elsewhere)
        if elsewhere != self._input_elsewhere:
            self._input_elsewhere = elsewhere
            self.viewport().update()

    def set_expected_height(self, height: int) -> None:
        """Tell the view how tall its viewport is about to become."""
        self._expected_height = max(0, int(height))
        self._recalculate_geometry()

    def _recalculate_geometry(self) -> None:
        columns, rows = self._visible_columns(), self._visible_rows()
        if (columns, rows) != (self.screen.columns, self.screen.rows):
            self.screen.resize(columns, rows)
            self.size_changed.emit(self.screen.columns, self.screen.rows)
        self._update_scrollbar()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        if self._expected_height and self.viewport().height() >= self._expected_height:
            self._expected_height = 0
        self._recalculate_geometry()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return QSize(int(self._cell_width * 100), int(self._cell_height * 14))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return QSize(int(self._cell_width * MINIMUM_COLUMNS), int(self._cell_height * MINIMUM_ROWS))

    def _update_scrollbar(self) -> None:
        bar = self.verticalScrollBar()
        maximum = max(0, len(self.screen.scrollback))
        was_following = self._follow_output
        bar.blockSignals(True)
        bar.setRange(0, maximum)
        bar.setPageStep(self.screen.rows)
        bar.setSingleStep(1)
        if was_following:
            bar.setValue(maximum)
        bar.blockSignals(False)

    def _scrolled(self, value: int) -> None:
        self._follow_output = value >= self.verticalScrollBar().maximum()
        self.viewport().update()

    def scroll_to_bottom(self) -> None:
        self._follow_output = True
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.viewport().update()

    # ------------------------------------------------------------------ input

    def feed(self, data: bytes) -> None:
        """Take a chunk of process output and schedule one repaint for it."""
        before = self.screen.bell_count
        self.screen.feed(data)
        response = self.screen.take_response()
        if response:
            self.input_ready.emit(response.encode("utf-8"))
        if self.screen.bell_count != before:
            self._bell_pending = True
        if not self._repaint_timer.isActive():
            self._repaint_timer.start()

    def _flush(self) -> None:
        self._update_scrollbar()
        self.viewport().update()
        if self._bell_pending:
            self._bell_pending = False
            self.bell.emit()

    def clear(self) -> None:
        self.screen.reset()
        self._selection = None
        self._follow_output = True
        self._flush()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        modifiers = event.modifiers()
        control_shift = (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        )
        if modifiers & control_shift == control_shift:
            if event.key() == Qt.Key.Key_C:
                self.copy_selection()
                return
            if event.key() == Qt.Key.Key_V:
                self.paste_clipboard()
                return
            if event.key() == Qt.Key.Key_A:
                self.select_all()
                return
        if event.key() == Qt.Key.Key_PageUp and modifiers & Qt.KeyboardModifier.ShiftModifier:
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() - bar.pageStep())
            return
        if event.key() == Qt.Key.Key_PageDown and modifiers & Qt.KeyboardModifier.ShiftModifier:
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() + bar.pageStep())
            return

        payload = key_sequence(
            event.key(),
            modifiers,
            event.text(),
            application_cursor=self.screen.application_cursor,
        )
        if payload is None:
            super().keyPressEvent(event)
            return
        # Typing means the user wants to see what happens next.
        self.scroll_to_bottom()
        self.input_ready.emit(payload)
        event.accept()

    def paste_clipboard(self) -> None:
        clipboard = QGuiApplication.clipboard()
        text = clipboard.text() if clipboard is not None else ""
        if not text:
            return
        self.scroll_to_bottom()
        self.input_ready.emit(paste_payload(text, bracketed=self.screen.bracketed_paste))

    # -------------------------------------------------------------- selection

    def _position_at(self, point) -> tuple[int, int]:
        top = self.verticalScrollBar().value()
        row = int(max(0.0, point.y() - PADDING_TOP) // self._cell_height) + top
        column = int(round(max(0.0, point.x() - PADDING_X) / self._cell_width))
        total = len(self.screen.scrollback) + self.screen.rows
        row = max(0, min(row, total - 1))
        return row, max(0, min(column, self.screen.columns))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton:
            position = self._position_at(event.position())
            self._selection = (position, position)
            self._selecting = True
            self.viewport().update()
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            # The X11 primary-selection paste people expect in a terminal.
            clipboard = QGuiApplication.clipboard()
            text = clipboard.text(clipboard.Mode.Selection) if clipboard else ""
            if text:
                self.input_ready.emit(
                    paste_payload(text, bracketed=self.screen.bracketed_paste)
                )
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._selecting and self._selection is not None:
            self._selection = (self._selection[0], self._position_at(event.position()))
            self.viewport().update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._selecting:
            self._selecting = False
            text = self.selected_text()
            clipboard = QGuiApplication.clipboard()
            if text and clipboard is not None:
                clipboard.setText(text, clipboard.Mode.Selection)
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API name
        """Select the whole line, which is how an error message gets copied."""
        row, _column = self._position_at(event.position())
        self._selection = ((row, 0), (row, self.screen.columns))
        self.viewport().update()

    def select_all(self) -> None:
        lines = self.screen.all_lines()
        if not lines:
            return
        self._selection = ((0, 0), (len(lines) - 1, self.screen.columns))
        self.viewport().update()

    def _ordered_selection(self):
        if self._selection is None:
            return None
        start, end = self._selection
        return (start, end) if start <= end else (end, start)

    def selected_text(self) -> str:
        ordered = self._ordered_selection()
        if ordered is None:
            return ""
        (start_row, start_column), (end_row, end_column) = ordered
        if (start_row, start_column) == (end_row, end_column):
            return ""
        lines = self.screen.all_lines()
        collected: list[str] = []
        for row in range(start_row, min(end_row, len(lines) - 1) + 1):
            line = lines[row]
            first = start_column if row == start_row else 0
            last = end_column if row == end_row else len(line)
            text = "".join(
                "" if cell.placeholder else (cell.text or " ")
                for cell in line[first:last]
            )
            collected.append(text.rstrip())
        return "\n".join(collected)

    def copy_selection(self) -> bool:
        text = self.selected_text()
        clipboard = QGuiApplication.clipboard()
        if not text or clipboard is None:
            return False
        clipboard.setText(text)
        return True

    def copy_everything(self) -> bool:
        clipboard = QGuiApplication.clipboard()
        text = self.screen.full_text()
        if not text or clipboard is None:
            return False
        clipboard.setText(text)
        return True

    def _show_context_menu(self, point) -> None:
        menu = QMenu(self)
        copy = menu.addAction(self._label("Copy"))
        copy.setEnabled(bool(self.selected_text()))
        copy.triggered.connect(self.copy_selection)
        menu.addAction(self._label("Copy everything")).triggered.connect(self.copy_everything)
        menu.addAction(self._label("Paste")).triggered.connect(self.paste_clipboard)
        menu.addSeparator()
        menu.addAction(self._label("Select all")).triggered.connect(self.select_all)
        menu.exec(self.mapToGlobal(point))

    @staticmethod
    def _label(text: str) -> str:
        from ..i18n import tr

        return tr(text)

    # --------------------------------------------------------------- painting

    def focusInEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().focusInEvent(event)
        self._cursor_on = True
        self._cursor_timer.start()
        self.viewport().update()

    def focusOutEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().focusOutEvent(event)
        self._cursor_timer.stop()
        self.viewport().update()

    def _blink(self) -> None:
        self._cursor_on = not self._cursor_on
        self.viewport().update()

    def _color(self, value, default: str, *, bold: bool = False) -> QColor:
        if bold:
            value = brighten_for_bold(value)
        return QColor(resolve(value, default))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self.viewport())
        painter.setFont(self._grid_font)
        painter.fillRect(event.rect(), self._colors["background"])
        # Everything below draws in grid coordinates; the inset is applied once.
        painter.translate(PADDING_X, PADDING_TOP)

        lines = self.screen.all_lines()
        top = self.verticalScrollBar().value()
        visible = self._visible_rows()
        default_text = COLORS["console_text"]
        default_background = COLORS["console_bg"]
        selection = self._ordered_selection()

        for offset in range(visible):
            index = top + offset
            if index >= len(lines):
                break
            y = offset * self._cell_height
            if selection is not None:
                # Behind the glyphs, so selected text stays readable.
                self._paint_selection(painter, index, y, selection, len(lines[index]))
            self._paint_line(
                painter, lines[index], y, default_text, default_background
            )

        self._paint_cursor(painter, top, len(lines))
        painter.end()

    def _paint_line(self, painter, line, y, default_text, default_background) -> None:
        baseline = y + self._baseline
        for column, text, style in TerminalScreen.runs(line):
            foreground, background = style.resolved()
            x = column * self._cell_width
            width = len(text) * self._cell_width
            if background is not None:
                brush = (
                    QColor(default_text)
                    if background == "inverse-default-background"
                    else self._color(background, default_background)
                )
                painter.fillRect(QRect(int(x), int(y), int(width) + 1, int(self._cell_height)), brush)
            if style.hidden:
                continue
            pen = (
                QColor(default_background)
                if foreground == "inverse-default-foreground"
                else self._color(foreground, default_text, bold=style.bold)
            )
            if style.dim:
                pen.setAlpha(150)
            painter.setPen(pen)
            font = painter.font()
            if font.bold() != style.bold or font.italic() != style.italic:
                font.setBold(style.bold)
                font.setItalic(style.italic)
                painter.setFont(font)
            painter.drawText(int(x), int(baseline), text)
            if style.underline or style.strike:
                line_y = baseline + 2 if style.underline else y + self._cell_height / 2
                painter.drawLine(int(x), int(line_y), int(x + width), int(line_y))
        font = painter.font()
        if font.bold() or font.italic():
            font.setBold(False)
            font.setItalic(False)
            painter.setFont(font)

    def _paint_selection(self, painter, index, y, selection, line_length) -> None:
        (start_row, start_column), (end_row, end_column) = selection
        if not start_row <= index <= end_row:
            return
        first = start_column if index == start_row else 0
        last = end_column if index == end_row else max(line_length, 1)
        if last <= first:
            return
        painter.fillRect(
            QRect(
                int(first * self._cell_width),
                int(y),
                int((last - first) * self._cell_width),
                int(self._cell_height),
            ),
            self._colors["selection"],
        )

    def _paint_cursor(self, painter, top, total_lines) -> None:
        """Solid block while focused, hollow outline while not.

        The hollow form is how a terminal says "this is where typing would go,
        but your keystrokes are going somewhere else right now" — worth having
        when the panel shares a window with the rest of the interface.
        """
        if not self.screen.cursor_visible:
            return
        focused = self.hasFocus()
        if self._input_elsewhere and not focused:
            # The answer row owns the keyboard; it is the only cursor.
            return
        if focused and not self._cursor_on:
            return
        row = len(self.screen.scrollback) + self.screen.cursor.y
        offset = row - top
        if not 0 <= offset < self._visible_rows():
            return
        y = offset * self._cell_height
        rectangle = QRect(
            int(self.screen.cursor.x * self._cell_width),
            int(y),
            max(2, int(self._cell_width)),
            int(self._cell_height) - 1,
        )
        accent = self._colors["accent"]
        if not focused:
            pen = QPen(accent)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rectangle.adjusted(0, 0, -1, 0))
            return
        painter.fillRect(rectangle, accent)
        cell = self.screen.lines[self.screen.cursor.y][self.screen.cursor.x]
        if cell.text.strip():
            painter.setPen(QColor(COLORS["console_bg"]))
            painter.drawText(rectangle.x(), int(y + self._baseline), cell.text)

    # ------------------------------------------------------------------ misc

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            step = 1 if event.angleDelta().y() > 0 else -1
            self.apply_theme(max(6, min(24, self._point_size + step)))
            event.accept()
            return
        super().wheelEvent(event)

    def shutdown(self) -> None:
        self._repaint_timer.stop()
        self._cursor_timer.stop()
