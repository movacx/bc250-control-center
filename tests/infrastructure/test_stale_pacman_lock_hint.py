"""A pacman lock left by an interrupted update is named, with the command that
clears it; a lock held by a running package manager is not (R-1bf75324, R-d8d8dc3d)."""

from __future__ import annotations

import os
import subprocess

from bc250cc.infrastructure.terminal_plan import (
    STALE_PACMAN_LOCK_MESSAGE,
    _stale_pacman_lock_shell,
)

EVIDENCE = "error: failed to init transaction (unable to lock database)\nerror: could not lock database: File exists"


def _run(tmp_path, *, status=1, evidence=EVIDENCE, lock=True, running=False):
    lock_file = tmp_path / "db.lck"
    if lock:
        lock_file.touch()
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "pgrep").write_text(f"#!/bin/sh\nexit {0 if running else 1}\n")
    (fake / "pgrep").chmod(0o755)
    script = f'status={status}; evidence="$1"; ' + _stale_pacman_lock_shell(lambda text: text)
    env = {**os.environ, "BC250_PACMAN_LOCK": str(lock_file), "PATH": f"{fake}:{os.environ['PATH']}"}
    return subprocess.run(["bash", "-c", script, "bash", evidence], env=env, text=True, capture_output=True, check=False)


def test_a_leftover_lock_is_named_with_its_command(tmp_path):
    result = _run(tmp_path)
    assert STALE_PACMAN_LOCK_MESSAGE in result.stdout
    assert "sudo rm /var/lib/pacman/db.lck" in result.stdout


def test_a_running_package_manager_gets_no_hint(tmp_path):
    assert _run(tmp_path, running=True).stdout == ""


def test_no_lock_file_or_another_failure_gets_no_hint(tmp_path):
    assert _run(tmp_path, lock=False).stdout == ""
    assert _run(tmp_path, evidence="error: target not found: foo").stdout == ""


def test_a_cancelled_or_successful_run_gets_no_hint(tmp_path):
    assert _run(tmp_path, status=0).stdout == ""
