"""A supported web runtime installed for the logged-in user, never system pip."""
from __future__ import annotations

import fcntl
import os
import re
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from bc250cc.shared.errors import ActionNeeded


def require_supported_version() -> None:
    """Reject an old distro server before opening any listening socket."""
    try:
        installed = version('cheroot')
    except PackageNotFoundError:
        installed = ''
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:\.post\d+)?(?:\+[a-zA-Z0-9.]+)?', installed)
    release = tuple(map(int, match.groups())) if match else ()
    if not release or not (11, 1, 2) <= release < (12, 0, 0):
        raise ActionNeeded('The web server dependencies are unavailable: Cheroot >=11.1.2,<12 is required. '
                           'Start web access from the desktop to prepare its isolated runtime.')


def prepare(root: Path, destination: Path) -> Path:
    """Called only when starting/enabling web access and no valid runtime exists."""
    if os.geteuid() == 0:
        raise ActionNeeded('Prepare the web server runtime from the ordinary Linux user session, not as root.')
    requirements = root / 'requirements-web.txt'
    if not requirements.is_file():
        raise ActionNeeded('The web server requirements file is missing. Reinstall BC250 Control Center.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination.parent / 'web-runtime.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ActionNeeded('Another web runtime preparation is still in progress. Retry after it finishes.') from error
        interpreter = destination / 'bin/python'
        # Refresh the interpreter after a distro Python update without clearing
        # the directory. Never follow a replaced runtime or use system pip's target.
        if destination.is_symlink() or (destination / 'pyvenv.cfg').is_symlink():
            raise ActionNeeded('The web server runtime path is a symbolic link. Reinstall its isolated environment.')
        argv = [sys.executable, '-I', '-m', 'venv', '--system-site-packages', '--without-pip']
        if (destination / 'pyvenv.cfg').is_file():
            argv.append('--upgrade')
        _run([*argv, str(destination)], timeout=60)
        _run([sys.executable, '-I', '-m', 'pip', '--isolated', '--python', str(interpreter),
              'install', '--disable-pip-version-check', '--no-input', '--timeout', '20', '--retries', '1',
              '--index-url', 'https://pypi.org/simple', '-r', str(requirements)], timeout=240)
    return interpreter


def _run(argv: list[str], *, timeout: int) -> None:
    try:
        subprocess.run(argv, check=True, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as error:
        detail = str(getattr(error, 'stderr', '') or error)[-1500:]
        raise ActionNeeded('The web server runtime could not be prepared. Check internet access and '
                           'the distribution Python pip/venv packages, then retry. ' + detail) from error
