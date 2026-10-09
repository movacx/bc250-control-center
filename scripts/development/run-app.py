#!/usr/bin/env python3
"""Launch the whole desktop application from a source checkout.

Works from any folder and on any system with PyQt6 and psutil, Windows
included (``run.sh`` is bash only):

    python scripts/development/run-app.py

It only puts the checkout on the import path and starts the same entry
point as ``./run.sh``; nothing is installed or written to the repository.
The application is built for Linux and the BC250. Where the Linux-only
modules (fcntl, pwd, termios, ...) are missing they are stubbed, so the pages
open but hardware readings, the terminal and root actions are unavailable.
``--force-stubs`` stubs them even on Linux, to try that path.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]


#: Modules only POSIX systems have. The application imports them at the top of
#: several files; stubbing them lets the pages open elsewhere (Windows).
_POSIX_ONLY = ("fcntl", "pwd", "grp", "pty", "termios", "tty", "resource")


class _PosixStub(types.ModuleType):
    """Stands in for a POSIX-only module: constants read as 0, calls fail."""

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        if name.isupper():
            return 0

        def unavailable(*_args, **_kwargs):
            raise OSError(f"{self.__name__}.{name} is not available on this system")

        return unavailable


def _stub_posix_modules(force: bool) -> list[str]:
    """Install stubs for the POSIX-only modules this system lacks."""
    stubbed = []
    for name in _POSIX_ONLY:
        if not force:
            try:
                __import__(name)
                continue
            except Exception:  # absent, or present but broken (tty on Windows)
                sys.modules.pop(name, None)
        sys.modules[name] = _PosixStub(name)
        stubbed.append(name)
    for name in ("geteuid", "getuid", "getgid"):
        if not hasattr(os, name):
            setattr(os, name, lambda: 1000)
    return stubbed


def _missing_dependencies() -> list[str]:
    missing = []
    for module, package in (("PyQt6.QtWidgets", "PyQt6"), ("psutil", "psutil")):
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    return missing


def main() -> int:
    missing = _missing_dependencies()
    if missing:
        print(f"Missing: {', '.join(missing)}.", file=sys.stderr)
        print(f"Install with:  {sys.executable} -m pip install {' '.join(missing)}", file=sys.stderr)
        return 127
    stubbed = _stub_posix_modules(force="--force-stubs" in sys.argv)
    if stubbed:
        sys.argv.remove("--force-stubs") if "--force-stubs" in sys.argv else None
        print(f"Note: no {', '.join(stubbed)} here; Linux-only features are disabled.", file=sys.stderr)
    from frontends.desktop.main import main as run_application

    return run_application()


if __name__ == "__main__":
    raise SystemExit(main())
