"""pacman's lock: detection for the System row and the checked release.

R-1bf75324, R-d8d8dc3d and R-48d27e43 failed with "unable to lock database".
Nothing here reads this machine's real pacman: the lock, /proc and the
commands are all stand-ins.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path

import pytest

from bc250cc.infrastructure import pacman_lock


def _proc(tmp_path: Path, *names: str, boot: float) -> Path:
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "stat").write_text(f"cpu 1 2 3\nbtime {int(boot)}\n")
    for pid, name in enumerate(names, start=100):
        (proc / str(pid)).mkdir()
        (proc / str(pid) / "comm").write_text(name + "\n")
    (proc / "self").mkdir()
    return proc


def _lock(tmp_path: Path, *, age: float = 0) -> Path:
    lock = tmp_path / "db.lck"
    lock.write_text("")
    if age:
        stamp = time.time() - age
        os.utime(lock, (stamp, stamp))
    return lock


def test_no_lock_file_is_free(tmp_path):
    state = pacman_lock.lock_state(tmp_path / "db.lck", proc=_proc(tmp_path, boot=time.time() - 60),
                                   pacman_present=True)
    assert state["state"] == pacman_lock.FREE


def test_a_lock_with_nothing_running_is_stale(tmp_path):
    state = pacman_lock.lock_state(_lock(tmp_path), proc=_proc(tmp_path, "bash", boot=time.time() - 60),
                                   pacman_present=True)
    assert state["state"] == pacman_lock.STALE and state["holders"] == ()


def test_a_running_pacman_is_in_use_even_with_an_old_lock(tmp_path):
    state = pacman_lock.lock_state(_lock(tmp_path, age=7200), proc=_proc(tmp_path, "pacman", boot=time.time() - 60),
                                   pacman_present=True)
    assert state["state"] == pacman_lock.IN_USE and state["holders"] == ("pacman",)


def test_an_open_front_end_counts_only_for_a_lock_from_this_boot(tmp_path):
    proc = _proc(tmp_path, "pamac-daemon", boot=time.time() - 600)
    fresh = pacman_lock.lock_state(_lock(tmp_path), proc=proc, pacman_present=True)
    assert fresh["state"] == pacman_lock.IN_USE and fresh["holders"] == ("pamac-daemon",)
    old = pacman_lock.lock_state(_lock(tmp_path, age=7200), proc=proc, pacman_present=True)
    assert old["state"] == pacman_lock.STALE and old["from_previous_boot"] is True


def test_a_system_without_pacman_shows_nothing(tmp_path):
    state = pacman_lock.lock_state(_lock(tmp_path), proc=_proc(tmp_path, boot=0), pacman_present=False)
    assert state["state"] == pacman_lock.NOT_APPLICABLE


@pytest.mark.parametrize("path", ["relative/db.lck", "/var/lib/pacman/other.lck"])
def test_the_release_refuses_an_unexpected_path(path):
    with pytest.raises(ValueError):
        pacman_lock.release_command(Path(path))


def _release(tmp_path: Path, lock: Path, running: str = "", *, with_pgrep: bool = True):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    if with_pgrep:
        (bin_dir / "pgrep").write_text(
            "#!/bin/bash\n"
            'names="$RUNNING"\n'
            '[ -z "$names" ] && exit 1\n'
            'if [ "$2" = pacman ]; then case " $names " in *" pacman "*) exit 0;; *) exit 1;; esac; fi\n'
            'i=1; for n in $names; do echo "$i $n"; i=$((i+1)); done\n'
        )
    (bin_dir / "sudo").write_text('#!/bin/bash\nexec "$@"\n')
    for tool in bin_dir.iterdir():
        tool.chmod(0o755)
    path = f"{bin_dir}:/usr/bin:/bin" if with_pgrep else f"{bin_dir}:/nonexistent"
    if not with_pgrep:
        for tool in ("awk", "stat", "rm", "sort", "tr"):
            target = Path("/usr/bin") / tool
            (bin_dir / tool).symlink_to(target)
    return subprocess.run(
        ["/bin/bash", "-c", pacman_lock.release_command(lock)],
        env={"PATH": path, "RUNNING": running}, capture_output=True, text=True, timeout=30,
    )


def test_a_stale_lock_is_removed(tmp_path):
    lock = _lock(tmp_path)
    result = _release(tmp_path, lock)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not lock.exists()
    assert "sudo pacman -Syu" in result.stdout


def test_nothing_is_removed_while_pacman_runs(tmp_path):
    lock = _lock(tmp_path, age=7200)
    result = _release(tmp_path, lock, running="pacman")
    assert result.returncode == 1 and lock.exists()
    assert "so pacman is busy" in result.stdout


def test_an_open_front_end_blocks_a_lock_from_this_boot_only(tmp_path):
    fresh = _lock(tmp_path)
    assert _release(tmp_path, fresh, running="octopi").returncode == 1 and fresh.exists()
    old = _lock(tmp_path, age=10 ** 7)
    result = _release(tmp_path, old, running="octopi")
    assert result.returncode == 0 and not old.exists()
    assert "older than this boot" in result.stdout


def test_without_pgrep_the_lock_stays(tmp_path):
    lock = _lock(tmp_path)
    result = _release(tmp_path, lock, with_pgrep=False)
    assert result.returncode == 1 and lock.exists()


def test_the_refusal_is_diagnosed_as_a_busy_package_manager(tmp_path):
    from bc250cc.infrastructure.terminal_plan import workflow_wrapper
    from bc250cc.shared import error_catalog

    refusal = ("ERROR: A package manager is still running (pacman ), so pacman is busy. "
               "Nothing was removed: let it finish or close it, then check again.")
    assert error_catalog.for_marker(refusal).code == "BC250-PKG-001"
    wrapped = workflow_wrapper(f"printf '%s\\n' {shlex.quote(refusal)}; exit 1",
                               tmp_path / "status", tmp_path / "log", hold=False)
    shown = subprocess.run(["bash", "-c", wrapped], input="", text=True, capture_output=True,
                           timeout=30, check=False).stdout
    assert "Diagnostic code: BC250-PKG-001" in shown
