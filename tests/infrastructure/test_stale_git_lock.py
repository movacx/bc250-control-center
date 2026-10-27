"""A preparation interrupted mid-fetch left .git/index.lock behind, and every
later run failed on "Unable to create index.lock: File exists"."""

from __future__ import annotations

import shlex
import shutil
import subprocess

import pytest

from bc250cc.infrastructure.source_checkout import _clear_stale_lock


@pytest.mark.skipif(shutil.which("pgrep") is None, reason="pgrep is required")
def test_a_stale_index_lock_is_removed_when_no_git_runs(tmp_path):
    lock = tmp_path / ".git" / "index.lock"
    lock.parent.mkdir()
    lock.write_text("", encoding="utf-8")
    script = _clear_stale_lock(shlex.quote(str(tmp_path))) + "true"
    # A git process elsewhere on this machine keeps the lock: the check is
    # deliberately conservative. Only assert when none is running.
    if subprocess.run(["pgrep", "-x", "git"], capture_output=True).returncode == 0:
        pytest.skip("a git process is running on this machine")
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
    assert not lock.exists()
    assert "stale git lock" in result.stdout
