"""Acquire the child PTY after setsid, then replace this process with the command.

Running this small child avoids preexec_fn in the multithreaded TUI process.
"""
from __future__ import annotations

import fcntl
import os
import sys
import termios


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(2)
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    os.execvpe(argv[0], argv, os.environ)


if __name__ == "__main__":
    main()
