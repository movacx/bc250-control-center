"""A damaged copy of DirectMesh's source is removed before the installer reuses it (R-576f65ba)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure import directmesh
from bc250cc.infrastructure.directmesh import _damaged_source_check

TAG = "directmesh-v1.4"
GOOD_WRAP = "[wrap-git]\ndirectory = DirectX-Headers-1.0\nurl = https://example.invalid/x.git\n"


def _source(cache: Path) -> Path:
    source = cache / "directmesh-build" / f"src-{TAG}"
    (source / "subprojects").mkdir(parents=True)
    (source / "meson.build").write_text("project('mesa')\n", encoding="utf-8")
    (source / "subprojects" / "DirectX-Headers.wrap").write_text(GOOD_WRAP, encoding="utf-8")
    return source


def _run(cache: Path, tail: str = "") -> subprocess.CompletedProcess[str]:
    script = "set -Eeuo pipefail\n" + _damaged_source_check(TAG) + "\n" + tail
    return subprocess.run(["bash", "-c", script], env={**os.environ, "XDG_CACHE_HOME": str(cache)},
                          text=True, capture_output=True, check=False)


def test_a_healthy_copy_is_kept(tmp_path):
    source = _source(tmp_path)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert source.is_dir() and "damaged" not in result.stdout


@pytest.mark.parametrize("damage", ["empty", "missing", "no_section", "no_subprojects", "no_meson"])
def test_a_damaged_copy_is_removed(tmp_path, damage):
    source = _source(tmp_path)
    wrap = source / "subprojects" / "DirectX-Headers.wrap"
    if damage == "empty":
        wrap.write_text("", encoding="utf-8")
    elif damage == "missing":
        wrap.unlink()
        wrap.symlink_to(source / "gone")
    elif damage == "no_section":
        wrap.write_text("directory = x\n", encoding="utf-8")
    elif damage == "no_subprojects":
        for child in (source / "subprojects").iterdir():
            child.unlink()
        (source / "subprojects").rmdir()
    else:
        (source / "meson.build").unlink()
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert not source.exists()
    assert "damaged" in result.stdout


def test_no_copy_yet_changes_nothing(tmp_path):
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_a_failure_naming_a_damaged_wrap_removes_the_copy(tmp_path):
    source = _source(tmp_path)
    (tmp_path / "directmesh-build" / "setup.log").write_text(
        f"ERROR: Missing sections in {source}/subprojects/DirectX-Headers.wrap\n", encoding="utf-8")
    result = _run(tmp_path, "bc250_forget_damaged_source")
    assert not source.exists()
    assert "Press Install again" in result.stdout


def test_the_install_checks_the_copy_before_running_the_installer(monkeypatch):
    monkeypatch.setattr(directmesh, "directmesh_release", lambda: {
        "tag": TAG, "installer_sha256": "531c4960d769f36c8b59b392fb927cbeb240baeb6f956efd400e9d19bba5b00f",
        "reviewed": True})
    command = directmesh.build_directmesh_install_command(family="arch", distro_id="cachyos")
    assert command.index("bc250_source_damaged; then") < command.index('bash "$bc250_installer"')
    assert "bc250_forget_damaged_source" in command.split("bc250_finish() {", 1)[1].split("}", 1)[0]
