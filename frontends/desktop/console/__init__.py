"""Embedded terminal console for the desktop shell.

The application runs privileged workflows that ask for a password with plain
``sudo`` and that draw progress with carriage returns and ANSI colour. Both of
those need a real terminal: ``sudo`` reads the password from ``/dev/tty`` rather
than from standard input, and package managers only draw progress when
``isatty`` is true. A pipe-backed output box would therefore break the very
workflows this console exists to show, so the session below allocates a genuine
pseudo-terminal and this package interprets what comes back from it.
"""

import importlib

# Loaded on first use: the terminal interface imports ``terminal_screen`` from
# here and must not pull in Qt with it.
_LAZY = {
    "ConsoleBeacon": "beacon", "ConsoleCounter": "beacon", "ConsoleHost": "console_host",
    "ConsolePanel": "console_panel", "Cell": "terminal_screen", "CellStyle": "terminal_screen",
    "TerminalScreen": "terminal_screen", "TerminalView": "terminal_view",
}


def __getattr__(name):
    if name in _LAZY:
        return getattr(importlib.import_module(f".{_LAZY[name]}", __name__), name)
    raise AttributeError(name)


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
    "ConsoleBeacon",
    "ConsoleCounter",
    "CellStyle",
    "ConsoleHost",
    "ConsolePanel",
    "TerminalScreen",
    "TerminalView",
]
