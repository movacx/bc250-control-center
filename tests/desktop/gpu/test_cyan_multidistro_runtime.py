import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
INSTALLER = ROOT / "packaging/common/os-scripts/common/install-cyan-upstream-release.sh"
PATCHER = INSTALLER.with_name("patch-cyan-bc250cc-runtime.py")


def test_cyan_is_installed_as_upstream_publishes_it():
    """No Control Center patch: the official release, or its commit built as is."""
    source = INSTALLER.read_text()
    assert not PATCHER.exists()
    assert "BC250CC_RUNTIME_REVISION" not in source and "patched_runtime" not in source
    assert 'REVIEWED_RELEASE_TAG="v0.4.14"' in source
    assert 'REVIEWED_COMMIT="7b08fdcf542d1edd82f3a9077c902038019c9842"' in source
    assert 'REVIEWED_ARCHIVE_SHA256="57fda5438d5f1856e9638300a60ba8c54c39f356ada749381275b836e8b1c787"' in source
    main = source.split('target_family="${BC250_CYAN_TARGET_FAMILY:-unknown}"', 1)[1]
    assert main.index("elif release_runs_here; then") < main.index("install_release")
    assert main.index("install_release") < main.index("build_upstream_source")


@pytest.mark.parametrize("glibc,expected", (("2.41", 0), ("2.39", 0), ("2.36", 1), ("2.35", 1)))
def test_the_official_binary_is_used_from_glibc_2_39(glibc, expected):
    source = INSTALLER.read_text()
    function = source.split("release_runs_here() {", 1)[1].split("\n}\n", 1)[0]
    script = f'''
RELEASE_MIN_GLIBC=2.39
getconf() {{ echo "glibc {glibc}"; }}
release_runs_here() {{{function}
}}
release_runs_here
'''
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == expected, result.stderr


def test_the_source_build_changes_nothing_in_the_source():
    source = INSTALLER.read_text()
    build = source.split("build_upstream_source() (", 1)[1].split("\n)\n", 1)[0]
    assert 'git -C "$SOURCE_DIR" archive --format=tar "$REVIEWED_COMMIT"' in build
    assert 'CYAN_SKILLFISH_GOVERNOR_VERSION="$REVIEWED_RELEASE_TAG"' in build
    assert "cargo build --locked --release" in build
    assert "python3" not in build and "sed " not in build and "patch" not in build.lower()
    assert "Run preparation as your desktop user" in build


def test_a_patched_runtime_from_an_older_release_is_replaced_and_forgotten():
    source = INSTALLER.read_text()
    assert "LEGACY_STATE_FILES=(runtime-revision upstream-commit patcher-sha256 binary-sha256)" in source
    fast_path = source.split("if supports_frequency_fix \"$MANAGED_BINARY\"", 2)[-1].split("elif", 1)[0]
    assert '[[ "$legacy_runtime" -eq 0 ]]' in fast_path
    stage = source.split("stage_managed_binary() (", 1)[1].split("\n)\n", 1)[0]
    assert "forget_legacy_runtime" in stage


@pytest.mark.parametrize("family,manager", (("arch", "pacman -S"), ("cachyos", "pacman -S"),
    ("manjaro", "pacman -S"), ("steamos", "pacman -S"), ("debian", "apt-get install"),
    ("ubuntu", "apt-get install"), ("fedora", "dnf install")))
@pytest.mark.parametrize("toolchain_present", (True, False))
def test_native_build_dependency_routes_without_executing_package_managers(family, manager, toolchain_present):
    source = INSTALLER.read_text()
    function = source.split("prepare_native_build_tools() {", 1)[1].split("\nbuild_upstream_source()", 1)[0]
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
    if family in {"arch", "cachyos", "manjaro", "steamos"}:
        # A full system update can replace the running kernel; the stubbed
        # package manager succeeds, so it must never be the first attempt.
        assert "-Syu" not in result.stdout


def test_ubuntu_bootstraps_a_pinned_user_rust_when_apt_rust_is_too_old():
    source = INSTALLER.read_text()
    function = source.split("prepare_native_build_tools() {", 1)[1].split(
        "\nbuild_upstream_source()", 1
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


def test_cachyos_rustup_shim_without_default_toolchain_gets_pinned_user_rust():
    source = INSTALLER.read_text()
    function = source.split("prepare_native_build_tools() {", 1)[1].split(
        "\nbuild_upstream_source()", 1
    )[0]
    script = f'''
set -eu
target_family=cachyos
HOME=/tmp/bc250-rust-test
modern=0
have() {{ case "$1" in cargo|rustc|cc|pkg-config|rustup) return 0;; *) return 1;; esac; }}
pkg-config() {{ return 0; }}
as_root() {{ printf 'planned: %s\\n' "$*"; }}
info() {{ printf 'info: %s\\n' "$*"; }}
die() {{ echo "$*"; exit 61; }}
rustc() {{
  [ "$modern" = 1 ] || {{ echo "error: rustup could not choose a version of rustc" >&2; return 1; }}
  printf 'rustc 1.88.0 (test)\\n'
}}
rustup() {{
  [ "$1" = toolchain ] && [ "$2" = install ] && [ "$3" = 1.88.0 ] || return 1
  modern=1
}}
cyan_rust_is_supported() {{
  have rustc || return 1
  local v; v="$(rustc --version 2>/dev/null)" || return 1
  [ -n "$v" ]
}}
prepare_native_build_tools() {{{function}
prepare_native_build_tools
printf 'selected=%s\\n' "$RUSTUP_TOOLCHAIN"
'''
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "apt-get" not in result.stdout
    assert "selected=1.88.0" in result.stdout
