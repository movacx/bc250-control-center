"""Translation from Qt key events to the bytes a terminal expects.

Kept apart from the widget on purpose. Key handling is the part of a terminal
users notice immediately when it is wrong — a Ctrl+C that does not interrupt,
an arrow key that prints ``^[[A`` into a password prompt — and as a pure
function it can be checked exhaustively without a running interface.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt

_MODIFIER = Qt.KeyboardModifier
_KEY = Qt.Key

# Cursor and edit keys. Cursor keys have a second form that a program selects
# with DECCKM; readline and most TUIs accept either, but sending the wrong one
# to a program in application mode inserts stray characters.
_CURSOR_KEYS = {
    _KEY.Key_Up: ("A", True),
    _KEY.Key_Down: ("B", True),
    _KEY.Key_Right: ("C", True),
    _KEY.Key_Left: ("D", True),
    _KEY.Key_Home: ("H", True),
    _KEY.Key_End: ("F", True),
}

_TILDE_KEYS = {
    _KEY.Key_Insert: 2,
    _KEY.Key_Delete: 3,
    _KEY.Key_PageUp: 5,
    _KEY.Key_PageDown: 6,
}

_FUNCTION_KEYS = {
    _KEY.Key_F1: b"\x1bOP",
    _KEY.Key_F2: b"\x1bOQ",
    _KEY.Key_F3: b"\x1bOR",
    _KEY.Key_F4: b"\x1bOS",
    _KEY.Key_F5: b"\x1b[15~",
    _KEY.Key_F6: b"\x1b[17~",
    _KEY.Key_F7: b"\x1b[18~",
    _KEY.Key_F8: b"\x1b[19~",
    _KEY.Key_F9: b"\x1b[20~",
    _KEY.Key_F10: b"\x1b[21~",
    _KEY.Key_F11: b"\x1b[23~",
    _KEY.Key_F12: b"\x1b[24~",
}

# The control characters that are not simply Ctrl plus a letter.
_CONTROL_PUNCTUATION = {
    _KEY.Key_Space: b"\x00",
    _KEY.Key_At: b"\x00",
    _KEY.Key_BracketLeft: b"\x1b",
    _KEY.Key_Backslash: b"\x1c",
    _KEY.Key_BracketRight: b"\x1d",
    _KEY.Key_AsciiCircum: b"\x1e",
    _KEY.Key_Underscore: b"\x1f",
    _KEY.Key_Question: b"\x7f",
}


def _modifier_parameter(modifiers: _MODIFIER) -> int:
    """The xterm modifier encoding: 1 plus a bit per held modifier."""
    value = 1
    if modifiers & _MODIFIER.ShiftModifier:
        value += 1
    if modifiers & _MODIFIER.AltModifier:
        value += 2
    if modifiers & _MODIFIER.ControlModifier:
        value += 4
    return value


def key_sequence(
    key: int,
    modifiers: _MODIFIER,
    text: str,
    *,
    application_cursor: bool = False,
) -> bytes | None:
    """Return the bytes for one key press, or None when there is nothing to send.

    None means the widget should handle the key itself (a shortcut, or a key
    with no terminal meaning); it never means "send nothing and swallow input".
    """
    control = bool(modifiers & _MODIFIER.ControlModifier)
    alt = bool(modifiers & _MODIFIER.AltModifier)
    shift = bool(modifiers & _MODIFIER.ShiftModifier)
    other = _modifier_parameter(modifiers) > 1

    if key in (_KEY.Key_Control, _KEY.Key_Shift, _KEY.Key_Alt, _KEY.Key_Meta):
        return None

    if key in _CURSOR_KEYS:
        final, allows_application = _CURSOR_KEYS[key]
        if other:
            return f"\x1b[1;{_modifier_parameter(modifiers)}{final}".encode()
        if application_cursor and allows_application:
            return f"\x1bO{final}".encode()
        return f"\x1b[{final}".encode()

    if key in _TILDE_KEYS:
        number = _TILDE_KEYS[key]
        if other:
            return f"\x1b[{number};{_modifier_parameter(modifiers)}~".encode()
        return f"\x1b[{number}~".encode()

    if key in _FUNCTION_KEYS:
        return _FUNCTION_KEYS[key]

    if key == _KEY.Key_Return or key == _KEY.Key_Enter:
        # Carriage return is what a terminal line discipline expects; it turns
        # the byte into a newline for the program on the other side.
        return b"\x1b\r" if alt else b"\r"

    if key == _KEY.Key_Backspace:
        if control:
            return b"\x08"
        return b"\x1b\x7f" if alt else b"\x7f"

    if key == _KEY.Key_Tab:
        return b"\t"

    if key == _KEY.Key_Backtab or (key == _KEY.Key_Tab and shift):
        return b"\x1b[Z"

    if key == _KEY.Key_Escape:
        return b"\x1b"

    if control:
        if _KEY.Key_A <= key <= _KEY.Key_Z:
            return bytes([key - _KEY.Key_A + 1])
        if key in _CONTROL_PUNCTUATION:
            return _CONTROL_PUNCTUATION[key]

    if not text:
        return None

    encoded = text.encode("utf-8")
    if alt:
        # Meta as a prefix escape, which is what bash and readline read.
        return b"\x1b" + encoded
    return encoded


def paste_payload(text: str, *, bracketed: bool = False) -> bytes:
    """Prepare pasted text for the child process.

    Newlines become carriage returns because that is what the terminal driver
    would have produced from the keyboard. When the program asked for bracketed
    paste, the markers let it tell a paste from typing and refuse to execute it
    — which is exactly the protection wanted when the panel is showing a shell
    running as root.
    """
    normalized = str(text).replace("\r\n", "\r").replace("\n", "\r")
    if not bracketed:
        return normalized.encode("utf-8")
    # A payload containing the end marker could close the bracket early and
    # let the rest run as typed input.
    normalized = normalized.replace("\x1b[201~", "")
    return b"\x1b[200~" + normalized.encode("utf-8") + b"\x1b[201~"
