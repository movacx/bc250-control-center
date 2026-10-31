"""Mouse events and hit testing shared by the TUI screen and its local dialogs."""
from __future__ import annotations

import curses
from dataclasses import dataclass

from .content import cell_width


def character_at(text: str, column: int) -> tuple[int, str]:
    """A terminal column as a Python character index (including wide text)."""
    used = 0
    for index, char in enumerate(text):
        width = cell_width(char)
        if used + width > column:
            return index, char
        used += width
    return len(text), ''


@dataclass(frozen=True)
class Mouse:
    x: int
    y: int
    kind: str
    shift: bool = False


def read_mouse() -> Mouse | None:
    try:
        _device, x, y, _z, state = curses.getmouse()
    except curses.error:
        return None
    def flags(name):
        return getattr(curses, name, 0)
    kind = ''
    if state & flags('BUTTON4_PRESSED'):
        kind = 'up'
    elif state & flags('BUTTON5_PRESSED'):
        kind = 'down'
    elif state & (flags('BUTTON3_PRESSED') | flags('BUTTON3_CLICKED')):
        kind = 'back'
    elif state & flags('REPORT_MOUSE_POSITION'):
        kind = 'move'
    elif state & flags('BUTTON1_RELEASED'):
        kind = 'release'
    elif state & (flags('BUTTON1_PRESSED') | flags('BUTTON1_CLICKED') | flags('BUTTON1_DOUBLE_CLICKED')):
        kind = 'press'
    return Mouse(x, y, kind, bool(state & flags('BUTTON_SHIFT'))) if kind else None


class PointerSupport:
    """Mixin: the screen supplies its layout, focus, draw geometry and actions."""

    def _reset_pointer_regions(self):
        self._dialog_hits = []
        self._dialog_rect = None
        self._scroll_track = None

    def _event(self):
        if self._geometry_size != self.size():
            self._pointer_drag = None
            self._layout_key = None
            return None
        return read_mouse()

    def _track_pointer(self, event):
        track = self._scroll_track
        if event.kind == 'release':
            self._pointer_drag = None
            return False
        if track is None:
            self._pointer_drag = None
            return False
        kind, x, top, view, thumb, maximum, offset = track
        if event.kind == 'press' and event.x == x and top <= event.y < top + view:
            start = round(offset * (view - thumb) / max(1, maximum))
            grab = event.y - top - start
            self._pointer_drag = (kind, grab if 0 <= grab < thumb else thumb // 2)
        elif event.kind != 'move' or self._pointer_drag is None:
            return False
        drag_kind, grab = self._pointer_drag
        if drag_kind != kind:
            self._pointer_drag = None
            return False
        value = round((event.y - top - grab) * maximum / max(1, view - thumb))
        value = max(0, min(maximum, value))
        if kind == 'console':
            self.console_scroll = maximum - value
        else:
            self.scroll[self._slot()] = value
            self.cursor[self._slot()] = self._first_shown(self.build(), self._slot(), 1)
        return True

    def _mouse(self):
        event = self._event()
        if event is None or event.shift:
            return
        if self._track_pointer(event):
            return
        if event.kind == 'back':
            self._focus('sidebar')
            return
        if event.kind in ('up', 'down'):
            step = 1 if event.kind == 'down' else -1
            if event.x < self.sidebar_width(self.size()[1]):
                self._go(self.section + step)
            elif event.y == 1 and self._tabs():
                self._switch_tab(step)
            else:
                self.focus = 'content'
                self._step(self.build(), self._slot(), 3 * step)
            return
        if event.kind != 'press':
            return
        if event.x < self.sidebar_width(self.size()[1]) and event.y in self._sidebar_at:
            self.focus = 'content'
            self._go(self._sidebar_at[event.y])
            return
        hit = next((key for y, start, end, key in self._hits
                    if y == event.y and start <= event.x < end), '')
        if hit:
            self.handle_key(hit)
            return
        index = next((index for start, end, index in self._choice_at.get(event.y, ())
                      if start <= event.x < end), None)
        if index is None:
            return
        layout, slot = self._rendered_layout, self._slot()
        if layout is None or self._rendered_slot != slot or self.ctx.page_data.get(self.page_key) is not self._rendered_data:
            return
        if not 0 <= index < len(layout.choices) or not self._shown(layout, slot, index):
            return
        self.focus, self.cursor[slot] = 'content', index
        choice = layout.choices[index]
        if not choice.enabled:
            return
        if choice.pad:
            cell = next(((row, column) for start, end, row, column in self._cells_at.get(event.y, ())
                         if start <= event.x < end), None)
            if cell is None or choice.pad.place is None:
                return
            choice.pad.place(*cell)
        elif choice.adjust:
            left, text = self._row_at.get(event.y, (0, ''))
            _index, char = character_at(text, event.x - left)
            if char in ('<', '>'):
                choice.adjust(self, -1 if char == '<' else 1)
                self._layout_key = None
                return
        self._activate(choice)

    def _modal_mouse(self):
        """Only current dialog targets are eligible; never dispatch to the page behind it."""
        event = self._event()
        if event is None or event.shift:
            return ''
        if event.kind == 'back':
            return 'esc'
        if self._dialog_rect:
            top, left, height, width = self._dialog_rect
            if not (top <= event.y < top + height and left <= event.x < left + width):
                return ''
        if event.kind in ('up', 'down'):
            return 'wheelup' if event.kind == 'up' else 'wheeldown'
        if event.kind == 'press':
            return next((key for y, start, end, key in self._dialog_hits
                         if y == event.y and start <= event.x < end), '')
        return ''

    def _console_mouse(self):
        event = self._event()
        if event is None or event.shift:
            return ''
        if self._track_pointer(event):
            return ''
        # A console owns the input until the action completes: sidebar/page
        # clicks cannot run another operation or answer a password prompt.
        if event.kind in ('up', 'down') and event.x >= self._content_box()[0] - 2:
            self.console_scroll += 3 if event.kind == 'up' else -3
            return ''
        if event.kind == 'back':
            return 'esc'
        if event.kind == 'press':
            return next((key for y, start, end, key in self._hits
                         if y == self.size()[0] - 1 == event.y and start <= event.x < end), '')
        return ''
