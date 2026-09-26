"""Minimal Arch, CachyOS and openSUSE installs may not carry ``cmp``.

Both installers verify protected files byte for byte with ``cmp`` (package
diffutils). Where it was missing, the Decky installer reported that the
installed helper "does not match this build" — a mismatch that did not exist
— and rolled back. Found by running the suite in a clean Arch container.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _path_without_cmp(tmp_path: Path) -> str:
    """A PATH with the basic tools a shell script needs, and no cmp."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("bash", "dirname", "readlink", "realpath", "cat", "env", "sed", "id", "uname"):
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    return str(bin_dir)


def test_decky_installer_names_the_missing_tool_instead_of_a_false_mismatch(tmp_path):
    result = subprocess.run(
        [shutil.which("bash"), str(ROOT / "scripts/install-decky-quick-access.sh")],
        env={"PATH": _path_without_cmp(tmp_path), "HOME": str(tmp_path)},
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 2
    assert "diffutils" in result.stderr
    assert "does not match this build" not in result.stderr


def test_packages_declare_diffutils():
    assert "'diffutils'" in (ROOT / "packaging/arch/aur/PKGBUILD").read_text(encoding="utf-8")
    rpm = (ROOT / "packaging/scripts/build-rpm.sh").read_text(encoding="utf-8")
    assert "diffutils" in next(line for line in rpm.splitlines() if line.startswith("Requires:"))


def test_the_local_installer_only_requires_cmp_when_it_installs_helpers():
    installer = (ROOT / "scripts/install-local.sh").read_text(encoding="utf-8")
    assert '[[ "${BC250_SKIP_PRIVILEGED_HELPER:-0}" != "1" ]] && ! command -v cmp' in installer
    assert os.access(ROOT / "scripts/install-local.sh", os.R_OK)
