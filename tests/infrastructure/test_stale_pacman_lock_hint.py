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


def _run(tmp_path, *, status=1, evidence=EVIDENCE, lock=True, running=False, front_end=False,
         previous_boot=False):
    lock_file = tmp_path / "db.lck"
    if lock:
        lock_file.touch()
        if previous_boot:
            os.utime(lock_file, (1000, 1000))
    (tmp_path / "stat").write_text("cpu 1 2 3\nbtime 2000\n" if previous_boot else "btime 1\n")
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    # pgrep -x pacman answers for pacman itself; any other pattern is the front-ends.
    (fake / "pgrep").write_text(
        "#!/bin/sh\n"
        f'if [ "$2" = pacman ]; then exit {0 if running else 1}; fi\n'
        f"exit {0 if front_end else 1}\n"
    )
    (fake / "pgrep").chmod(0o755)
    script = f'status={status}; evidence="$1"; ' + _stale_pacman_lock_shell(lambda text: text)
    env = {**os.environ, "BC250_PACMAN_LOCK": str(lock_file), "BC250_PROC_STAT": str(tmp_path / "stat"),
           "PATH": f"{fake}:{os.environ['PATH']}"}
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


def test_an_idle_packagekit_does_not_hide_a_lock_from_before_the_reboot(tmp_path):
    """R-40f0868d / R-1c81b064: the same lock, nine hours and a reboot apart."""
    result = _run(tmp_path, front_end=True, previous_boot=True)
    assert STALE_PACMAN_LOCK_MESSAGE in result.stdout


def test_a_front_end_with_a_lock_from_this_boot_may_be_working(tmp_path):
    assert _run(tmp_path, front_end=True).stdout == ""


def test_pacman_itself_running_is_never_a_leftover(tmp_path):
    assert _run(tmp_path, running=True, previous_boot=True).stdout == ""
