"""Every generated workflow must be syntactically valid shell.

A presentation edit once left Python source text ("+ script_presentation..."
) inside a generated script. It compiled fine as Python and only failed when
bash tried to run it, which is the worst place to find out.
"""

from __future__ import annotations

import subprocess

import pytest

from bc250cc.infrastructure.bazzite_async_compute import (
    build_bazzite_async_compute_command,
)
from bc250cc.infrastructure.cachyos_bc250_kernel import (
    build_cachyos_bc250_kernel_command,
)


def _assert_valid_shell(script: str, label: str) -> None:
    assert script.strip(), f"{label} produced an empty script"
    result = subprocess.run(
        ["bash", "-n", "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"{label} is not valid shell: {result.stderr.strip()}"
    # Python source that leaked into the template would appear verbatim here.
    for leak in ("script_presentation.", "+ script_presentation", "f'BC-250"):
        assert leak not in script, f"{label} contains Python source: {leak!r}"


@pytest.mark.parametrize("action", ("kernel", "mesa", "full"))
def test_cachyos_workflows_are_valid_shell(action: str) -> None:
    _assert_valid_shell(build_cachyos_bc250_kernel_command(action), f"cachyos/{action}")


@pytest.mark.parametrize("action", ("install", "uninstall"))
def test_bazzite_async_compute_workflow_is_valid_shell(action: str) -> None:
    _assert_valid_shell(
        build_bazzite_async_compute_command(action), f"bazzite-async/{action}"
    )
