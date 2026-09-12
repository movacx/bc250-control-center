"""Embedded terminal console for the desktop shell.

The application runs privileged workflows that ask for a password with plain
``sudo`` and that draw progress with carriage returns and ANSI colour. Both of
those need a real terminal: ``sudo`` reads the password from ``/dev/tty`` rather
than from standard input, and package managers only draw progress when
``isatty`` is true. A pipe-backed output box would therefore break the very
workflows this console exists to show, so the session below allocates a genuine
pseudo-terminal and this package interprets what comes back from it.
"""

from .console_host import ConsoleHost
from .console_panel import ConsolePanel
from .terminal_screen import Cell, CellStyle, TerminalScreen
from .terminal_view import TerminalView


def console_for(widget):
    """The console panel of the window a widget belongs to, if there is one.

    Pages do not own the console and must not assume it exists: it is absent in
    tests, in the headless frontend, and whenever the user has turned it off.
    Callers fall back to whatever they did before.
    """
    window = widget.window() if widget is not None else None
    console = getattr(window, "console", None)
    host = getattr(window, "console_host", None)
    if console is None or (host is not None and not host.enabled):
        return None
    return console


__all__ = [
    "console_for",
    "Cell",
    "CellStyle",
    "ConsoleHost",
    "ConsolePanel",
    "TerminalScreen",
    "TerminalView",
]
