"""A preparation interrupted mid-fetch left .git/index.lock behind, and every
later run failed on "Unable to create index.lock: File exists"."""

from __future__ import annotations

import os
import shlex
import subprocess

import pytest

from bc250cc.infrastructure.source_checkout import _clear_stale_lock


@pytest.mark.parametrize("status", [0, 1, 2])
def test_only_top_level_locks_are_removed_when_git_is_idle(tmp_path, status):
    git = tmp_path / ".git"
    (git / "refs").mkdir(parents=True)
    locks = [git / name for name in ("index.lock", "shallow.lock", "config.lock", "HEAD.lock", "packed-refs.lock")]
    keep = [git / "HEAD", git / "refs" / "branch.lock"]
    for path in locks + keep:
        path.touch()
    pgrep = tmp_path / "pgrep"
    pgrep.write_text(f"#!/bin/sh\nexit {status}\n")
    pgrep.chmod(0o755)
    script = _clear_stale_lock(shlex.quote(str(tmp_path))) + "true"
    subprocess.run(["bash", "-c", script], check=True, env={"PATH": f"{tmp_path}:{os.defpath}"})
    assert all(path.exists() == (status != 1) for path in locks)
    assert all(path.exists() for path in keep)
