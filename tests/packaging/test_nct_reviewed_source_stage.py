"""The NCT build source must come from a pinned archive, not ResourceTools."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "packaging/common/os-scripts/common/common.sh"


def _git(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["/usr/bin/git", *command], cwd=cwd, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def test_reviewed_nct_stage_preserves_worktree_edits_and_archives_the_pinned_commit(tmp_path):
    source = tmp_path / "nct-source"
    source.mkdir()
    (source / "Makefile").write_text("committed makefile\n", encoding="utf-8")
    (source / "nct6687.c").write_text("committed source\n", encoding="utf-8")
    _git(["init"], source)
    _git(["config", "user.email", "bc250-tests@example.invalid"], source)
    _git(["config", "user.name", "BC250 tests"], source)
    _git(["add", "."], source)
    _git(["commit", "-m", "reviewed nct"], source)
    revision = _git(["rev-parse", "HEAD"], source)
    (source / "nct6687.c").write_text("mutable worktree source\n", encoding="utf-8")

    command = (
        f'source "{COMMON}"; '
        f'bc250_stage_reviewed_git_tree "{source}" "{source}" "{revision}" STAGED; '
        'printf "%s\\n" "$STAGED"; '
        'cat "$STAGED/nct6687.c"; '
        'rm -rf -- "$STAGED"'
    )
    result = subprocess.run(
        ["/usr/bin/bash", "-o", "pipefail", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {"TMPDIR": str(tmp_path)},
    )

    assert result.returncode == 0, result.stderr
    assert "committed source" in result.stdout
    assert "mutable worktree source" not in result.stdout
    # The helper fetches/archive the object but never checks it out, so the
    # user's local edit remains available for inspection.
    assert (source / "nct6687.c").read_text(encoding="utf-8") == "mutable worktree source\n"
    assert _git(["status", "--porcelain"], source) == "M nct6687.c"


def test_all_nct_build_scripts_clean_the_temporary_reviewed_source_stage():
    scripts = ROOT / "packaging/common/os-scripts"
    for family in ("arch", "bazzite", "debian", "fedora", "steamos"):
        source = (scripts / family / "prepare-fan-pwm.sh").read_text(encoding="utf-8")
        assert "NCT_SOURCE_STAGE" in source, family
        assert 'rm -rf -- "$NCT_SOURCE_STAGE"' in source, family
        assert 'cd "$NCT_SOURCE_STAGE"' in source or 'BUILD_WORK="$NCT_SOURCE_STAGE' in source, family


def test_dkms_wrappers_clean_root_owned_staging_with_matching_authority():
    scripts = ROOT / "packaging/common/os-scripts"
    for family in ("arch", "debian", "fedora"):
        source = (scripts / family / "prepare-fan-pwm.sh").read_text(encoding="utf-8")
        assert 'as_root rm -rf -- "$NCT_SOURCE_STAGE"' in source, family
