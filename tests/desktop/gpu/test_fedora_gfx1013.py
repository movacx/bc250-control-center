from pathlib import Path

import pytest

from bc250cc.infrastructure.fedora_gfx1013 import build_fedora_gfx1013_command
from bc250cc.infrastructure.gfx1013_compute_policy import (
    GFX1013_REVIEWED_COMMIT,
    GFX1013_TESTED_KERNEL,
)


def test_fedora_workflow_is_pinned_gated_and_installs_both_required_halves(tmp_path):
    command = build_fedora_gfx1013_command("install", tmp_path / "gfx")

    assert GFX1013_REVIEWED_COMMIT in command
    assert GFX1013_TESTED_KERNEL in command
    assert 'test "${ID:-}" = fedora' in command
    assert 'test "${VERSION_ID:-}" = 43' in command
    assert "rpm-ostree" in command
    assert "1002" in command and "13fe" in command
    assert "install.sh deps" in command
    assert "install.sh build" in command
    assert "install.sh install" in command
    assert "0001-gfx1013-compute-queue-fix.patch" in command
    assert "0002" in command and "0003" in command
    assert "selected for the next boot only" in command


def test_fedora_workflow_exposes_reviewed_status_and_rollback(tmp_path):
    status = build_fedora_gfx1013_command("status", tmp_path / "gfx")
    uninstall = build_fedora_gfx1013_command("uninstall", tmp_path / "gfx")

    assert "install.sh status" in status
    assert "install.sh uninstall" in uninstall
    assert "install.sh build" not in uninstall
    assert GFX1013_TESTED_KERNEL not in uninstall
    assert 'test "${VERSION_ID:-}" = 43' not in uninstall
    assert "rpm-ostree" in uninstall


def test_fedora_workflow_rejects_unknown_actions(tmp_path):
    with pytest.raises(ValueError, match="Unsupported Fedora GFX1013 action"):
        build_fedora_gfx1013_command("kernel-only", Path(tmp_path) / "gfx")
