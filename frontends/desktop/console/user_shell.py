"""Which shell F4 opens, and the environment it opens with.

Dolphin opens the user's own shell in its terminal panel; so does this
console. The shell is whatever the user chose, provided it is a real,
executable login shell — a ``SHELL`` pointing at something else is ignored
rather than executed. Nothing the application's launcher added to the
environment leaks into it.
"""

from __future__ import annotations

import os
import pwd
from pathlib import Path

#: Tried in order when neither ``SHELL`` nor the password database names a
#: usable shell. ``sh`` is always present on the systems this runs on.
FALLBACK_SHELLS = ("/bin/bash", "/usr/bin/bash", "/bin/sh")

#: The launcher prepends the application's own ``src`` directory to this so
#: the desktop can import itself. A user's Python in their shell must not.
_LAUNCHER_PATH_VARIABLES = ("PYTHONPATH",)


def _listed_shells(shells_file: Path) -> set[str] | None:
    """The shells ``/etc/shells`` allows, or None when there is no list."""
    try:
        text = shells_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return {
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _usable(candidate: str, allowed: set[str] | None) -> bool:
    if not candidate or not os.path.isabs(candidate):
        return False
    if allowed is not None and candidate not in allowed:
        return False
    path = Path(candidate)
    return path.is_file() and os.access(path, os.X_OK)


def user_shell(
    environment: dict[str, str] | None = None,
    *,
    shells_file: Path = Path("/etc/shells"),
) -> str:
    """The shell to start: ``SHELL``, then the account's, then a fallback."""
    env = os.environ if environment is None else environment
    allowed = _listed_shells(shells_file)
    try:
        account_shell = pwd.getpwuid(os.getuid()).pw_shell
    except (KeyError, OSError):
        account_shell = ""
    for candidate in (env.get("SHELL", ""), account_shell):
        if _usable(candidate, allowed):
            return candidate
    for candidate in FALLBACK_SHELLS:
        if _usable(candidate, None):
            return candidate
    return "/bin/sh"


def shell_environment(
    environment: dict[str, str] | None = None,
    *,
    application_root: Path | None = None,
) -> dict[str, str]:
    """The inherited environment, minus what the launcher put there."""
    env = dict(os.environ if environment is None else environment)
    root = application_root or Path(__file__).resolve().parents[3]
    own_source = str(root / "src")
    for name in _LAUNCHER_PATH_VARIABLES:
        value = env.get(name)
        if value is None:
            continue
        kept = [part for part in value.split(os.pathsep) if part and part != own_source]
        if kept:
            env[name] = os.pathsep.join(kept)
        else:
            env.pop(name)
    return env
