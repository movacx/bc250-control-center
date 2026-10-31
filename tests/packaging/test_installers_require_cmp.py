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


def _fake_package_manager(tmp_path: Path, *, installs: bool) -> tuple[str, Path]:
    """A PATH without cmp whose pacman installs it, or fails, and logs each call.

    Any other pacman call (the GUI dependencies that follow) stops the
    installer with 42, before it copies a single file.
    """
    path = str(tmp_path / "host-bin")
    Path(path).mkdir()
    # Every host tool except cmp, the package managers and python3: without
    # python3 the GUI dependencies are always the next pacman call.
    hidden = {"cmp", "sudo", "pacman", "apt-get", "dnf", "zypper", "apk", "rpm-ostree"}
    for tool in Path("/usr/bin").iterdir():
        if tool.name not in hidden and not tool.name.startswith("python") and not (Path(path) / tool.name).exists():
            (Path(path) / tool.name).symlink_to(tool)
    log = tmp_path / "calls.log"
    cmp = shutil.which("cmp")
    (Path(path) / "sudo").write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
    (Path(path) / "pacman").write_text(
        "#!/bin/sh\n"
        f'echo "pacman $*" >> "{log}"\n'
        'case "$*" in *diffutils*) ;; *) exit 42 ;; esac\n'
        + (f'ln -s "{cmp}" "{path}/cmp"\n' if installs else "exit 1\n"),
        encoding="utf-8",
    )
    for fake in ("sudo", "pacman"):
        (Path(path) / fake).chmod(0o755)
    return path, log


def _run_local_installer(tmp_path: Path, path: str, **extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [shutil.which("bash"), str(ROOT / "scripts/install-local.sh")],
        env={"PATH": path, "HOME": str(tmp_path), **extra},
        capture_output=True, text=True, timeout=60, check=False,
    )


def test_the_local_installer_installs_diffutils_instead_of_stopping(tmp_path):
    if Path("/run/ostree-booted").exists() or shutil.which("cmp") is None:
        import pytest

        pytest.skip("needs a package-based host with cmp to link to")
    path, log = _fake_package_manager(tmp_path, installs=True)
    result = _run_local_installer(tmp_path, path)
    calls = log.read_text(encoding="utf-8").splitlines()
    assert calls[0] == "pacman -S --needed --noconfirm diffutils"
    # It went on to the GUI dependencies, which the fake refuses.
    assert result.returncode == 42 and len(calls) == 2
    assert "cmp command" not in result.stderr


def test_the_local_installer_stops_when_diffutils_cannot_be_installed(tmp_path):
    if Path("/run/ostree-booted").exists():
        import pytest

        pytest.skip("image-based hosts are not asked to layer diffutils")
    path, log = _fake_package_manager(tmp_path, installs=False)
    result = _run_local_installer(tmp_path, path)
    assert log.read_text(encoding="utf-8").splitlines() == ["pacman -S --needed --noconfirm diffutils"]
    assert result.returncode == 2 and "diffutils" in result.stderr


def test_the_local_installer_leaves_packages_alone_when_asked(tmp_path):
    path, log = _fake_package_manager(tmp_path, installs=True)
    result = _run_local_installer(tmp_path, path, BC250_SKIP_DEPENDENCY_INSTALL="1")
    assert not log.exists()
    assert result.returncode == 2 and "diffutils" in result.stderr


def test_gentoo_runtime_plan_is_not_misplaced_in_diffutils_bootstrap(tmp_path):
    path, log = _fake_package_manager(tmp_path, installs=True)
    # cmp already works, but Python/Git preparation must still use Portage.
    # The fake manager stops before any application files are installed.
    bin_dir = Path(path)
    (bin_dir / "cmp").symlink_to(shutil.which("cmp"))
    manager = bin_dir / "pacman"
    manager.rename(bin_dir / "emerge")
    emerge = bin_dir / "emerge"
    emerge.write_text(emerge.read_text().replace('echo "pacman ', 'echo "emerge '))
    result = _run_local_installer(
        tmp_path, path, BC250_INSTALL_PROFILE="tui",
        BC250_SKIP_PRIVILEGED_HELPER="1", PREFIX=str(tmp_path / "install"),
    )
    assert result.returncode == 42, result.stdout + result.stderr
    assert log.read_text().splitlines() == [
        "emerge --ask=n --getbinpkg dev-lang/python dev-python/psutil dev-vcs/git"
    ]
