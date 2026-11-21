"""R-f193b192: a damaged download is deleted and fetched again, without asking."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from bc250cc.infrastructure.cachyos_bc250_kernel import (
    build_cachyos_bc250_kernel_command,
)
from bc250cc.shared import error_catalog
from frontends.desktop.core.error_diagnostics import diagnose_error

DAMAGED = (
    ":: File {cache}/linux-cachyos-bc250-7.3.4-1.425-x86_64.pkg.tar.zst is corrupted "
    "(invalid or corrupted package (checksum)).\n"
    "error: failed to commit transaction (invalid or corrupted package)"
)


def _install_step() -> str:
    script = build_cachyos_bc250_kernel_command("kernel")
    start = script.index("bc250_cache_dirs=")
    end = script.index('for bc250_target in "${bc250_packages[@]}"; do\n  bc250_name=')
    return script[start:end]


def _run(tmp_path: Path, failures: int):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "linux-cachyos-bc250-7.3.4-1.425-x86_64.pkg.tar.zst").write_text("damaged")
    (cache / "linux-cachyos-bc250-headers-7.3.4-1.425-x86_64.pkg.tar.zst").write_text("damaged")
    count = tmp_path / "count"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    message = DAMAGED.format(cache=cache).replace("\n", "\\n")
    (bin_dir / "pacman").write_text(
        "#!/bin/bash\n"
        f'if [ "$1" = -Syy ]; then echo synced >> {tmp_path}/synced; exit 0; fi\n'
        f"n=$(($(cat {count} 2>/dev/null || echo 0) + 1)); echo $n > {count}\n"
        f'if [ $n -le {failures} ]; then printf "{message}\\n"; exit 1; fi\n'
        "echo installed\n"
    )
    (bin_dir / "pacman-conf").write_text(f"#!/bin/bash\necho {cache}\n")
    (bin_dir / "sudo").write_text('#!/bin/bash\nexec "$@"\n')
    for path in bin_dir.iterdir():
        path.chmod(0o755)
    head = "set -euo pipefail\nbc250_scope_guard=()\nbc250_packages=(bc250-cachyos/linux-cachyos-bc250 bc250-cachyos/linux-cachyos-bc250-headers)\n"
    result = subprocess.run(["/usr/bin/bash", "-c", head + _install_step()], capture_output=True, text=True,
                            timeout=30, check=False, env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"})
    return result, cache, tmp_path


def test_a_damaged_download_is_deleted_and_downloaded_again(tmp_path):
    result, cache, root = _run(tmp_path, failures=1)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "downloading them again" in result.stdout
    assert not list(cache.glob("*.pkg.tar.zst"))
    assert (root / "synced").exists()


def test_a_repository_that_keeps_serving_a_damaged_file_stops_with_a_clear_reason(tmp_path):
    result, _cache, _root = _run(tmp_path, failures=5)
    assert result.returncode == 75
    assert "BC-250 repository is serving a damaged package" in result.stdout


def test_a_damaged_package_is_not_called_a_signature_problem():
    text = DAMAGED.format(cache="/var/cache/pacman/pkg")
    assert diagnose_error(text).code == "BC250-PKG-006"
    assert error_catalog.BY_CODE["BC250-PKG-006"].summary == "A downloaded package was damaged."


def test_a_repository_defined_twice_is_named_as_such_on_both_surfaces():
    """R-d0e4fa7c: paru stopped with pacman's "database already registered"."""
    text = "error: database already registered"
    diagnosis = diagnose_error(text)
    assert diagnosis.code == "BC250-PKG-007"
    assert "pacman-conf --repo-list | sort | uniq -d" in diagnosis.action
    assert error_catalog.for_marker(text).code == "BC250-PKG-007"
