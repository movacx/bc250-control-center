"""SteamOS' /var is about 230 MB: the guard asks only for what the work needs,
says what takes the room and how to get it back, and Control Center can clear
the caches itself (issue #34, report R-51d26e02)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from bc250cc.infrastructure.steamos_readonly import (
    STEAMOS_PACMAN_INSTALL,
    STEAMOS_VAR_SPACE_GUARD,
    build_steamos_readonly_command,
    probe_steamos_readonly,
)

ROOT_SCRIPT = Path("packaging/common/os-scripts/common/steamos-root.sh").resolve()
PREPARE = Path("packaging/common/os-scripts/steamos/prepare-dependencies.sh").resolve()


def _guard(tmp_path: Path, need: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "BC250_STEAMOS_VAR_DIR": str(tmp_path), "BC250_STEAMOS_MIN_VAR_MB": need}
    return subprocess.run(
        ["bash", "-c", f'source "{ROOT_SCRIPT}"; bc250_steamos_require_var_space'],
        env=env, text=True, capture_output=True, check=False,
    )


def test_eighty_megabytes_free_is_enough_for_the_default_need():
    # The report had 83 MB free; downloads no longer land in /var.
    assert 'BC250_STEAMOS_MIN_VAR_MB:-40}' in ROOT_SCRIPT.read_text(encoding="utf-8")
    assert 'bc250_need="${1:-40}"' in STEAMOS_VAR_SPACE_GUARD


def test_a_full_var_names_each_cache_with_its_command_and_keeps_umr(tmp_path):
    (tmp_path / "cache" / "fwupd").mkdir(parents=True)
    (tmp_path / "cache" / "fwupd" / "metadata").write_bytes(b"\0" * 3 * 1024 * 1024)
    (tmp_path / "cache" / "pacman").mkdir()
    (tmp_path / "cache" / "pacman" / "pkg.tar.zst").write_bytes(b"\0" * 3 * 1024 * 1024)
    (tmp_path / "lib" / "umr").mkdir(parents=True)
    (tmp_path / "lib" / "umr" / "data").write_bytes(b"\0" * 12 * 1024 * 1024)
    result = _guard(tmp_path, "999999999")
    assert result.returncode == 75
    assert "sudo rm -rf /var/cache/fwupd/*" in result.stderr
    assert "sudo pacman -Scc" in result.stderr
    assert "/var/lib/umr" in result.stderr and "keep it" in result.stderr
    assert "Free /var space" in result.stderr
    assert "journalctl --vacuum-size=50M, pacman -Sc" not in result.stderr


def test_a_var_with_nothing_to_name_still_offers_a_command(tmp_path):
    result = _guard(tmp_path, "999999999")
    assert result.returncode == 75
    assert "journalctl --vacuum-size=20M" in result.stderr


def test_the_temporary_pacman_cache_is_made_once_and_dropped(tmp_path):
    script = (
        f'source "{ROOT_SCRIPT}"; '
        'bc250_steamos_pacman_cache >/dev/null; first="$BC250_STEAMOS_PACMAN_CACHE"; '
        'bc250_steamos_pacman_cache >/dev/null; [ "$first" = "$BC250_STEAMOS_PACMAN_CACHE" ] || exit 9; '
        '[ -d "$first" ] || exit 8; bc250_steamos_drop_pacman_cache; [ ! -e "$first" ] || exit 7'
    )
    result = subprocess.run(["bash", "-c", script], env={**os.environ, "TMPDIR": str(tmp_path)},
                            text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


def test_steamos_dependency_installs_download_outside_var():
    source = PREPARE.read_text(encoding="utf-8")
    assert 'pacman --cachedir "$BC250_STEAMOS_PACMAN_CACHE"' in source
    assert "as_root pacman -S" not in source
    assert "bc250_steamos_drop_pacman_cache" in source
    assert 'pacman --cachedir "$bc250_cache" -S' in STEAMOS_PACMAN_INSTALL


def test_free_var_clears_caches_only_and_keeps_umr():
    command = build_steamos_readonly_command("free-var")
    assert "find /var/cache/pacman/pkg -mindepth 1 -delete" in command
    assert "find /var/cache/fwupd -mindepth 1 -delete" in command
    assert "journalctl --vacuum-size=20M" in command
    assert "bc250_require_password" in command
    assert "umr" not in command.split("OK:")[0].replace("/var/lib/umr", "")
    assert "steamos-readonly disable" not in command


def test_the_probe_reports_free_space_on_var():
    class _Stats:
        f_bavail = 83 * 256
        f_frsize = 4096

    result = probe_steamos_readonly(
        which=lambda _name: "/usr/bin/steamos-readonly",
        runner=lambda *a, **k: subprocess.CompletedProcess(a, 0, "enabled\n", ""),
        statvfs=lambda _path: _Stats(),
    )
    assert result == {"available": True, "state": "enabled", "var_free_mb": 83}
