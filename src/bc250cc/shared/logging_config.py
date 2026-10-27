from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from bc250cc.shared.paths import state_root

#: Kept small: a problem report sends its end, not a history.
LOG_MAX_BYTES = 512 * 1024
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def log_path() -> Path:
    """The application's own log, read back by a problem report."""
    return state_root() / "bc250-control-center" / "app.log"


def configure_logging() -> None:
    """Configure one predictable log format for GUI and backend diagnostics.

    Everything still goes to stderr. It also goes to ``log_path()``: without
    it, what the app logged before a failure (a warning, an exception it
    caught) was gone by the time the owner pressed Report.
    """
    debug_enabled = os.environ.get("BC250_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    logging.basicConfig(level=logging.DEBUG if debug_enabled else logging.INFO, format=LOG_FORMAT)
    path = log_path()
    root = logging.getLogger()
    if any(getattr(handler, "baseFilename", "") == str(path) for handler in root.handlers):
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        handler = RotatingFileHandler(path, maxBytes=LOG_MAX_BYTES, backupCount=1, encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    _log_uncaught_exceptions()


def _log_uncaught_exceptions() -> None:
    """Write an exception nobody caught to the log before it ends the app.

    PyQt ends the application on an exception left in a slot only while
    ``sys.excepthook`` is Python's own; replacing it would keep a broken
    window open instead. So after logging, the app still ends as before.
    """
    logger = logging.getLogger("bc250cc.uncaught")
    previous = sys.excepthook

    def hook(kind, value, traceback):
        logger.critical("Uncaught exception", exc_info=(kind, value, traceback))
        previous(kind, value, traceback)
        if "PyQt6.QtCore" in sys.modules and not issubclass(kind, (KeyboardInterrupt, SystemExit)):
            os.abort()

    sys.excepthook = hook
    previous_thread_hook = threading.excepthook

    def thread_hook(arguments):
        logger.critical(
            "Uncaught exception in thread %s", getattr(arguments.thread, "name", "?"),
            exc_info=(arguments.exc_type, arguments.exc_value, arguments.exc_traceback),
        )
        previous_thread_hook(arguments)

    threading.excepthook = thread_hook
