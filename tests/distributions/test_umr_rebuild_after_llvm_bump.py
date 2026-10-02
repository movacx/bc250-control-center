"""A umr that exists but no longer starts must be rebuilt, not kept.

CachyOS moved to LLVM 23. umr links against LLVM, so a copy built earlier stays
in PATH and fails on launch with a missing libLLVM. Preparing Compute Units
used to look for the file only, call that "already installed", and leave it
broken; and ``--needed`` would have skipped a rebuild of the same version
anyway. The fix is to ask whether the program can start, and to build it again
when it cannot.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure.dependencias_repository import DependenciasRepository

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "packaging/common/os-scripts"
COMMON = SCRIPTS / "common/common.sh"
AUR = SCRIPTS / "common/aur.sh"
ARCH = SCRIPTS / "arch/prepare-dependencies.sh"


def _function(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(name)}\(\) \{{\n.*?^\}}\n", text, re.S | re.M)
    assert match, f"{name} is missing from {path.name}"
    return match.group(0)


def _bash(script: str, *, env_path: str | None = None):
    env = {"PATH": env_path} if env_path else None
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False, env=env)


# ------------------------------------------------------------------ binary_runs

@pytest.fixture
def fake_bin(tmp_path):
    """A PATH holding a fake ``umr`` and an ``ldd`` whose verdict the test picks."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    umr = bin_dir / "umr"
    umr.write_text("#!/bin/bash\nexit 0\n")
    umr.chmod(0o755)

    def ldd(output: str):
        script = bin_dir / "ldd"
        script.write_text(f"#!/bin/bash\ncat <<'EOF'\n{output}\nEOF\n")
        script.chmod(0o755)

    return bin_dir, ldd


def _runs(bin_dir) -> bool:
    script = f'have() {{ command -v "$1" >/dev/null 2>&1; }}\n{_function(COMMON, "binary_runs")}\nbinary_runs umr'
    return _bash(script, env_path=f"{bin_dir}:/usr/bin:/bin").returncode == 0


def test_a_program_whose_libraries_are_all_there_runs(fake_bin):
    bin_dir, ldd = fake_bin
    ldd("\tlibc.so.6 => /usr/lib/libc.so.6 (0x1)\n\tlibLLVM.so.23.1 => /usr/lib/libLLVM.so.23.1 (0x2)")
    assert _runs(bin_dir)


def test_a_program_linked_against_a_replaced_library_does_not(fake_bin):
    bin_dir, ldd = fake_bin
    ldd("\tlibc.so.6 => /usr/lib/libc.so.6 (0x1)\n\tlibLLVM.so.22.1 => not found")
    assert not _runs(bin_dir)


def test_a_static_program_is_fine(fake_bin):
    bin_dir, ldd = fake_bin
    ldd("\tnot a dynamic executable")
    assert _runs(bin_dir)


def test_a_missing_program_does_not_run(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    script = f'have() {{ command -v "$1" >/dev/null 2>&1; }}\n{_function(COMMON, "binary_runs")}\nbinary_runs umr'
    assert _bash(script, env_path=f"{empty}:/usr/bin:/bin").returncode != 0


# --------------------------------------------------------------- the Arch script

def _install_umr(*, runs: list[int], umr_git: bool, force: str = "0"):
    """Run the real install_umr/rebuild_broken_umr with the system replaced by stubs."""
    script = f"""
set -u
calls=()
BC250_FORCE_UMR_FALLBACK={force}
BC250_CU_MANAGER_SCRIPT=
runs=({' '.join(map(str, runs))})
have() {{ return 0; }}
info() {{ :; }}
warn() {{ echo "warn: $*"; }}
error() {{ echo "error: $*"; }}
verify_command() {{ return 0; }}
as_root() {{ echo "as_root $*"; }}
hash() {{ :; }}
command() {{ if [ "${{1:-}}" = "-v" ]; then echo /usr/bin/umr; else builtin command "$@"; fi; }}
ldd() {{ :; }}
binary_runs() {{
  local verdict="${{runs[0]:-0}}"
  runs=("${{runs[@]:1}}")
  return "$verdict"
}}
pacman() {{
  if [ "$1" = "-Qq" ] && [ "$2" = "umr-git" ]; then return {0 if umr_git else 1}; fi
  return 1
}}
install_aur_package() {{ echo "install_aur_package $*"; }}
{_function(ARCH, "rebuild_broken_umr")}
{_function(ARCH, "install_umr")}
install_umr
echo "status=$?"
"""
    return _bash(script)


def test_a_healthy_umr_is_left_alone():
    result = _install_umr(runs=[0], umr_git=False)
    assert "install_aur_package" not in result.stdout
    assert "status=0" in result.stdout


def test_a_broken_umr_is_rebuilt_from_the_aur_package_it_came_from():
    result = _install_umr(runs=[1, 0], umr_git=False)
    assert "install_aur_package umr rebuild" in result.stdout
    assert "does not start" in result.stdout
    assert "status=0" in result.stdout


def test_the_git_flavour_is_rebuilt_as_the_git_flavour():
    result = _install_umr(runs=[1, 0], umr_git=True)
    assert "install_aur_package umr-git rebuild" in result.stdout


def test_a_rebuild_that_still_does_not_start_fails_and_says_so():
    result = _install_umr(runs=[1, 1], umr_git=False)
    assert "still does not start" in result.stdout
    assert "status=1" in result.stdout


# ----------------------------------------------------------------- the AUR helper

def _aur_args(helper: str, rebuild: str) -> str:
    script = f"""
set -u
AUR_HELPER=/usr/bin/{helper}
ensure_aur_helper() {{ :; }}
export_parallel_build_env() {{ :; }}
bold() {{ :; }}
warn() {{ :; }}
run() {{ echo "run $*"; }}
install_aur_package_direct() {{ echo "direct $*"; }}
{_function(AUR, "install_aur_package")}
[ -x "$AUR_HELPER" ] || {{ mkdir -p /tmp/aur-stub; AUR_HELPER=/bin/true; }}
install_aur_package umr {rebuild}
"""
    return _bash(script).stdout


def test_a_rebuild_never_asks_the_helper_to_skip_an_installed_version():
    out = _aur_args("true", "rebuild")  # /usr/bin/true stands in for the helper binary
    assert "-S --rebuild --noconfirm" in out
    assert "--needed" not in out


def test_an_ordinary_install_still_skips_what_is_already_installed():
    out = _aur_args("true", "")
    assert "-S --needed --noconfirm" in out
    assert "--rebuild" not in out


def test_the_makepkg_fallback_does_not_skip_a_rebuild():
    text = AUR.read_text(encoding="utf-8")
    direct = _function(AUR, "install_aur_package_direct")
    assert 'if [[ "$rebuild" == "rebuild" ]]' in direct
    assert re.search(r"--install --noconfirm\n", direct)
    assert "--install --needed --noconfirm" in direct
    assert 'install_aur_package_direct "$package" "$rebuild"' in text


# ------------------------------------------------------------ the Python inventory

class _Inventory(DependenciasRepository):
    def __init__(self, umr_path, broken):
        self._umr = umr_path
        self._broken = broken

    def _command_path(self, name):
        return self._umr if name == "umr" else ""

    def _has_unresolved_libraries(self, path, **_kw):
        return self._broken

    def _system_dbus_ready(self, *_a, **_kw):
        return False


def test_the_inventory_flags_a_umr_that_will_not_start():
    broken = _Inventory("/usr/bin/umr", True)._probe_runtime_inventory()
    assert broken["umr"] == "/usr/bin/umr" and broken["umr_broken"] is True
    assert _Inventory("/usr/bin/umr", False)._probe_runtime_inventory()["umr_broken"] is False
    assert _Inventory("", True)._probe_runtime_inventory()["umr_broken"] is False


def test_only_evidence_of_a_missing_library_marks_a_program_as_broken(monkeypatch):
    class Result:
        def __init__(self, stdout):
            self.stdout = stdout

    check = DependenciasRepository._has_unresolved_libraries
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ldd")
    assert check("/usr/bin/umr", runner=lambda *a, **k: Result("\tlibLLVM.so.22.1 => not found\n")) is True
    assert check("/usr/bin/umr", runner=lambda *a, **k: Result("\tlibc.so.6 => /usr/lib/libc.so.6\n")) is False
    assert check("/usr/bin/umr", runner=lambda *a, **k: Result("\tnot a dynamic executable\n")) is False

    def boom(*_a, **_k):
        raise OSError("no ldd")

    assert check("/usr/bin/umr", runner=boom) is False
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert check("/usr/bin/umr", runner=lambda *a, **k: Result("not found")) is False
