"""Entry point of the terminal interface."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from bc250cc.shared.version import __version__

MISSING_CURSES = (
    "The terminal interface needs Python's curses module, which this Python was built without.\n"
    "Install it with your package manager (for example: python3-curses or python3-libs), "
    "or use the desktop application / bc250-control-center-cli."
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bc250-control-center-tui",
        description="BC250 Control Center in the terminal (works over SSH and on a plain TTY)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--theme", choices=("auto", "light", "dark", "mono"), default="auto",
                        help="auto follows the terminal; mono draws without colour")
    parser.add_argument("--lang", default="", help="Interface language code (default: the saved setting)")
    parser.add_argument("--page", default="", help="Open this section first (dashboard, cpu, gpu, ...)")
    return parser


def _quiet_logging() -> None:
    """Keep log lines off the screen: curses owns stdout/stderr while it runs."""
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "bc250-control-center"
    handler: logging.Handler
    try:
        state.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(state / "tui.log", encoding="utf-8")
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        import curses
    except ImportError:
        print(MISSING_CURSES, file=sys.stderr)
        return 3
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("The terminal interface needs an interactive terminal. "
              "Use bc250-control-center-cli for scripts.", file=sys.stderr)
        return 2
    _quiet_logging()

    from bc250cc.application import ApplicationContainer
    from bc250cc.application.system.workflow_console import (
        set_embedded_terminal_launcher,
    )

    from .i18n import set_language
    from .pages import build_pages
    from .runtime import Context, Poller
    from .screen import SIDEBAR_ORDER, Screen

    container = ApplicationContainer.production()
    if container.system_service is None or container.settings_service is None:
        print("The application services could not be built.", file=sys.stderr)
        return 1
    config = {}
    try:
        config = container.settings_service.read_local_config()
    except Exception:  # an unreadable config must not stop the interface
        logging.getLogger(__name__).warning("Could not read the saved settings", exc_info=True)
    set_language(args.lang or config.get("idioma", "auto"))
    ctx = Context(
        service=container.system_service, settings=container.settings_service,
        activity=container.activity_service, platform=container.platform, config=config,
    )
    pages = build_pages()
    poller = Poller(ctx, pages)

    def start(stdscr) -> None:
        screen = Screen(stdscr, ctx, pages, poller, theme=args.theme)
        # Every repository offers its workflows here before any terminal emulator.
        set_embedded_terminal_launcher(screen.launch_workflow)
        ctx.state("ui")["theme"] = args.theme
        if args.page in SIDEBAR_ORDER:
            screen.focus = "content"
            screen._go(screen.order.index(args.page))
        poller.start()
        try:
            screen.loop()
        finally:
            set_embedded_terminal_launcher(None)
            poller.stop()

    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
