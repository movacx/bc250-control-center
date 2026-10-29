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


def make_runner(translate: Callable[[str], str] = str) -> Callable[..., str]:
    def run(command, title="BC250 Control Center"):
        if shutil.which("rpm-ostree"):
            command = f"{RPM_OSTREE_IDLE_WAIT}; {command}"
        completed = subprocess.run(["bash", "-c", command], check=False)  # nosec B603 B607
        if completed.returncode != 0:
            raise RuntimeError(describe_failure(completed.returncode, "", "", translate=translate))
        return f"{title}: OK"

    return run


def use_inline_terminal(repository, translate: Callable[[str], str] = str) -> None:
    """Make ``repository`` run its workflows in this terminal instead of a new window."""
    repository._abrir_terminal = make_runner(translate)
