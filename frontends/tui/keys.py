"""Key names, so the screen never compares raw curses codes."""

from __future__ import annotations

import curses

NAMES = {
    curses.KEY_UP: "up", curses.KEY_DOWN: "down", curses.KEY_LEFT: "left", curses.KEY_RIGHT: "right",
    curses.KEY_ENTER: "enter", 10: "enter", 13: "enter", 27: "esc", 9: "tab", curses.KEY_BTAB: "btab",
    curses.KEY_PPAGE: "pgup", curses.KEY_NPAGE: "pgdn", curses.KEY_HOME: "home", curses.KEY_END: "end",
    curses.KEY_BACKSPACE: "backspace", 127: "backspace", 8: "backspace", curses.KEY_DC: "delete",
    curses.KEY_RESIZE: "resize", 32: "space",
}

# Vim letters and WASD-free aliases, so a keyboard-less pad mapped to arrows
# and a plain SSH session both work.
ALIASES = {"k": "up", "j": "down", "h": "left", "l": "right", "b": "esc"}


def name_of(code: int) -> str:
    """``code`` as a key name: 'up', 'enter', ... or the character itself."""
    if code in NAMES:
        return NAMES[code]
    if 32 < code < 0x110000:
        try:
            return chr(code)
        except ValueError:
            return ""
    return ""
