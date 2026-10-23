"""Prepare dependencies must leave a working board alone.

Reported on CachyOS (2026-09-28): the runtime step ran ``pacman -Syu`` although
every package was installed, upgraded 22 packages including the kernel, and
removed the running kernel's modules and headers. The fan PWM step right after
it then tried to rebuild nct6687 — which was loaded and working — and failed
on headers for a kernel that no longer existed. Four Arch users on Reddit saw
the same: "can't detect already active services".

These tests run the real scripts against stand-in package managers.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "packaging" / "common" / "os-scripts"
RELEASE = "7.2.7-1-cachyos"


def _tool(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
    path.chmod(0o755)


def _fake_bin(tmp_path: Path, *, missing: str = "", sync_fails: bool = False) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    _tool(bin_dir, "sudo", '"$@"')
    _tool(bin_dir, "pacman", f"""
echo "pacman $*" >> {calls}
case "$1" in
  -T) [ -n "{missing}" ] && {{ printf '%s\\n' {missing}; exit 127; }}; exit 0 ;;
  -S) [ "{int(sync_fails)}" = 1 ] && exit 1; exit 0 ;;
  *) exit 0 ;;
esac""")
    for name in ("makepkg", "fakeroot", "jq", "lspci", "pkexec"):
        _tool(bin_dir, name, "exit 0")
    return bin_dir, calls


def _env(bin_dir: Path, tmp_path: Path, **extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        PATH=f"{bin_dir}:{env['PATH']}",
        HOME=str(tmp_path / "home"),
        BC250_TOOLS_DIR=str(tmp_path / "tools"),
        BC250_KERNEL_RELEASE_OVERRIDE=RELEASE,
    )
    env.update(extra)
    return env


def _runtime(tmp_path: Path, **fake) -> tuple[subprocess.CompletedProcess, list[str]]:
    bin_dir, calls = _fake_bin(tmp_path, **fake)
    modules = tmp_path / "modules"
    modules.mkdir()
    if not fake.get("kernel_replaced"):
        (modules / RELEASE).mkdir()
    result = subprocess.run(
        ["bash", str(SCRIPTS / "arch" / "prepare-dependencies.sh"), "--component", "runtime"],
        env=_env(bin_dir, tmp_path, BC250_MODULE_ROOTS=str(modules)),
        capture_output=True, text=True, timeout=60,
    )
    return result, calls.read_text().splitlines() if calls.exists() else []


def test_an_installed_runtime_does_not_touch_the_system(tmp_path):
    result, calls = _runtime(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "already installed; the system was not updated" in result.stdout
    assert [call for call in calls if not call.startswith("pacman -T")] == []


def test_only_the_missing_package_is_installed(tmp_path):
    result, calls = _runtime(tmp_path, missing="jq")
    assert result.returncode == 0, result.stderr
    installs = [call for call in calls if not call.startswith("pacman -T")]
    assert installs == ["pacman -S --needed --noconfirm jq"]


def test_a_stale_database_falls_back_to_a_full_update_for_the_missing_package(tmp_path):
    bin_dir, calls = _fake_bin(tmp_path, missing="jq", sync_fails=True)
    modules = tmp_path / "modules"
    modules.mkdir()  # the update removed the running kernel's tree
    result = subprocess.run(
        ["bash", str(SCRIPTS / "arch" / "prepare-dependencies.sh"), "--component", "runtime"],
        env=_env(bin_dir, tmp_path, BC250_MODULE_ROOTS=str(modules)),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    installs = [call for call in calls.read_text().splitlines() if not call.startswith("pacman -T")]
    assert installs == ["pacman -S --needed --noconfirm jq", "pacman -Syu --needed --noconfirm jq"]
    assert f"replaced the running kernel ({RELEASE})" in result.stderr
    assert "Reboot before preparing kernel modules" in result.stderr


# ------------------------------------------------------------------ fan PWM


def _usable(tmp_path: Path, *, loaded: bool, replaced: bool, module_file: bool = False, dkms: bool = False):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    modules = tmp_path / "modules"
    modules.mkdir()
    if not replaced:
        (modules / RELEASE).mkdir()
    ko = tmp_path / "nct6687.ko.zst"
    if module_file:
        ko.write_bytes(b"ko")
    _tool(bin_dir, "modinfo", f'[ "{int(module_file)}" = 1 ] && echo {ko}; exit 0')
    _tool(bin_dir, "dkms", f'[ "{int(dkms)}" = 1 ] && echo "nct6687d/1, 7.2.8-1-cachyos, x86_64: installed"; exit 0')
    proc = tmp_path / "proc_modules"
    proc.write_text("nct6687 69632 0 - Live 0x0000000000000000\n" if loaded else "amdgpu 1 0 - Live\n")
    # common.sh runs under ``set -e``; the scripts call this inside ``if``.
    script = (
        f'source {SCRIPTS / "common" / "common.sh"}; '
        f'if bc250_nct6687_already_usable {RELEASE}; then echo "rc=0"; else echo "rc=1"; fi'
    )
    return subprocess.run(
        ["bash", "-c", script],
        env=_env(bin_dir, tmp_path, BC250_MODULE_ROOTS=str(modules), BC250_PROC_MODULES=str(proc)),
        capture_output=True, text=True, timeout=30,
    )


def test_a_module_the_running_kernel_already_has_is_not_rebuilt(tmp_path):
    result = _usable(tmp_path, loaded=False, replaced=False, module_file=True)
    assert "rc=0" in result.stdout and "already installed" in result.stdout


def test_a_loaded_driver_is_not_rebuilt(tmp_path):
    result = _usable(tmp_path, loaded=True, replaced=False)
    assert "rc=0" in result.stdout and "loaded and working" in result.stdout


def test_a_loaded_driver_after_a_kernel_update_waits_for_the_reboot(tmp_path):
    """The user's exact case: working in this session, kernel upgraded under it."""
    result = _usable(tmp_path, loaded=True, replaced=True, dkms=True)
    assert "rc=0" in result.stdout
    assert "DKMS already builds nct6687" in result.stdout
    assert "nothing needs to be compiled now" in result.stdout


def test_no_driver_and_a_replaced_kernel_asks_for_the_reboot(tmp_path):
    result = _usable(tmp_path, loaded=False, replaced=True)
    assert result.returncode == 20
    assert "rc=" not in result.stdout
    assert "Reboot into the updated kernel" in result.stderr


def test_a_board_without_the_driver_still_builds_it(tmp_path):
    result = _usable(tmp_path, loaded=False, replaced=False)
    assert "rc=1" in result.stdout


def test_the_arch_pwm_step_stops_before_any_package_or_build_work(tmp_path):
    bin_dir, calls = _fake_bin(tmp_path)
    modules = tmp_path / "modules"
    (modules / RELEASE).mkdir(parents=True)
    proc = tmp_path / "proc_modules"
    proc.write_text("nct6687 69632 0 - Live 0x0\n")
    _tool(bin_dir, "modinfo", "exit 0")
    result = subprocess.run(
        ["bash", str(SCRIPTS / "arch" / "prepare-fan-pwm.sh")],
        env=_env(bin_dir, tmp_path, BC250_MODULE_ROOTS=str(modules), BC250_PROC_MODULES=str(proc)),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "loaded and working" in result.stdout
    assert not calls.exists(), "no pacman call, no headers, no build"


def test_the_terminal_says_up_front_what_is_already_there():
    from bc250cc.infrastructure.preparation_workflow import _presence_notes

    notes = _presence_notes(
        frozenset({"governor", "umr", "cpu_oc"}), frozenset({"governor", "umr", "fan_pwm"})
    )
    assert notes == [
        'echo "    Already present (checked and kept): governor, umr";',
        'echo "    To prepare now: cpu_oc";',
    ]
    assert _presence_notes(frozenset({"umr"}), frozenset()) == ['echo "    To prepare now: umr";']
