"""Upstream's "already installed" refusal gets its own code, not GENERAL-001."""

from __future__ import annotations

import os
import subprocess

from bc250cc.infrastructure.terminal_plan import exit_explanation_shell


def _diagnose(tail: str, status: int = 1) -> str:
    script = f'status={status}; evidence="$EVIDENCE"; {exit_explanation_shell()}\necho "CODE=$diagnostic"'
    result = subprocess.run(
        ["bash", "-c", script], env={**os.environ, "EVIDENCE": tail},
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip().splitlines()[-1].removeprefix("CODE=")


def test_an_installed_release_refusal_is_named():
    tail = (
        "warning: Fedora 44; validated on Fedora 43 only\n"
        "error: a release is already installed; uninstall it first"
    )
    assert _diagnose(tail) == "BC250-GFX-001"
