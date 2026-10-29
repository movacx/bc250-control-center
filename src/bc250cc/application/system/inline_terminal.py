"""Run a workflow in the terminal that is already open.

The desktop repository opens a graphical terminal window for each reviewed
workflow. A terminal interface already is a terminal, so the same command runs
here, with the output and any ``sudo``/Polkit prompt on the user's own screen.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 - the argv is the repository's reviewed workflow
from collections.abc import Callable

from bc250cc.infrastructure.bazzite_deployment import RPM_OSTREE_IDLE_WAIT
from bc250cc.shared.failure_text import describe_failure


def make_runner(
    translate: Callable[[str], str] = str,
    execute: Callable[[str], int] | None = None,
) -> Callable[..., str]:
    """A runner for reviewed workflows.

    ``execute`` runs the command somewhere the interface can show it (an
    in-screen console) and returns its exit status; without it the command
    runs on this process's own terminal.
    """
    def run(command, title="BC250 Control Center"):
        if shutil.which("rpm-ostree"):
            command = f"{RPM_OSTREE_IDLE_WAIT}; {command}"
        if execute is not None:
            status = execute(command)
        else:
            status = subprocess.run(["bash", "-c", command], check=False).returncode  # nosec B603 B607
        if status != 0:
            raise RuntimeError(describe_failure(status, "", "", translate=translate))
        return f"{title}: OK"

    return run


def use_inline_terminal(
    repository, translate: Callable[[str], str] = str, execute: Callable[[str], int] | None = None,
) -> None:
    """Make ``repository`` run its workflows in this terminal instead of a new window."""
    repository._abrir_terminal = make_runner(translate, execute)
