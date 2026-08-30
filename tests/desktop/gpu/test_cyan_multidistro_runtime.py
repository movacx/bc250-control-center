import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure.cyan_governor_runtime import CYAN_BC250CC_PATCHER

ROOT = Path(__file__).resolve().parents[3]
INSTALLER = ROOT / "packaging/common/os-scripts/common/install-cyan-upstream-release.sh"


def test_runtime_identity_uses_the_shipped_patcher_not_the_removed_legacy_path():
    assert CYAN_BC250CC_PATCHER.is_file()
    assert CYAN_BC250CC_PATCHER == INSTALLER.with_name("patch-cyan-bc250cc-runtime.py")


@pytest.mark.parametrize("family,manager", (("arch", "pacman -Syu"), ("cachyos", "pacman -Syu"),
    ("manjaro", "pacman -Syu"), ("steamos", "pacman -S"), ("debian", "apt-get install"),
    ("ubuntu", "apt-get install"), ("fedora", "dnf install")))
@pytest.mark.parametrize("toolchain_present", (True, False))
def test_native_build_dependency_routes_without_executing_package_managers(family, manager, toolchain_present):
    source = INSTALLER.read_text()
    function = source.split("prepare_native_build_tools() {", 1)[1].split("\nbuild_bc250cc_runtime()", 1)[0]
    # Execute the actual shell function with harmless command doubles. No root
    # access, package manager, compiler installation, or hardware writes.
    script = f'''
set -eu
target_family={family}
tools_ready={int(toolchain_present)}
have() {{ case "$1" in cc|pkg-config) return 1;; cargo|rustc) test "$tools_ready" = 1;; *) return 0;; esac; }}
as_root() {{ tools_ready=1; printf 'planned: %s\\n' "$*"; }}
rustc() {{ printf 'rustc 1.94.0 (test)\\n'; }}
die() {{ echo "$*"; exit 61; }}
prepare_native_build_tools() {{{function}
prepare_native_build_tools
'''
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert manager in result.stdout
    if not toolchain_present:
        if family == "fedora":
            assert "cargo rust" in result.stdout and "rustc" not in result.stdout
        elif family in {"debian", "ubuntu"}:
            assert "cargo rustc" in result.stdout
        else:
            assert "rust" in result.stdout
    if family == "steamos":
        assert "-Syu" not in result.stdout


def test_all_requested_distros_select_the_patch_and_preserve_source_integrity():
    source = INSTALLER.read_text()
    assert "bazzite|arch|cachyos|manjaro|debian|ubuntu|fedora|steamos) patched_runtime=1" in source
    assert 'cargo build --locked --release' in source
    assert 'cd "$source_copy"' in source
    assert 'git -C "$SOURCE_DIR" archive' in source
    assert 'Run preparation as your desktop user' in source


def test_ubuntu_bootstraps_a_pinned_user_rust_when_apt_rust_is_too_old():
    source = INSTALLER.read_text()
    function = source.split("prepare_native_build_tools() {", 1)[1].split(
        "\nbuild_bc250cc_runtime()", 1
    )[0]
    script = f'''
set -eu
target_family=ubuntu
HOME=/tmp/bc250-rust-test
modern=0
have() {{ case "$1" in cargo|rustc|cc|pkg-config|rustup) return 0;; *) return 1;; esac; }}
pkg-config() {{ return 0; }}
as_root() {{ printf 'planned: %s\\n' "$*"; }}
info() {{ printf 'info: %s\\n' "$*"; }}
die() {{ echo "$*"; exit 61; }}
rustc() {{ if [ "$modern" = 1 ]; then printf 'rustc 1.88.0 (test)\\n'; else printf 'rustc 1.75.0 (test)\\n'; fi; }}
rustup() {{
  [ "$1" = toolchain ] && [ "$2" = install ] && [ "$3" = 1.88.0 ] || return 1
  modern=1
}}
prepare_native_build_tools() {{{function}
prepare_native_build_tools
rustc --version
printf 'selected=%s\\n' "$RUSTUP_TOOLCHAIN"
'''
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "apt-get install -y rustup" in result.stdout
    assert "rustc 1.88.0" in result.stdout
    assert "selected=1.88.0" in result.stdout
