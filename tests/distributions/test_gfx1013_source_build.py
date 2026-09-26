"""The independent GFX1013 source build and its boot protection.

The fix is built for the running kernel and installed beside the stock amdgpu.
What makes that safe is the boot service: it records an attempt before it
loads the patched module, a timer clears it on a healthy boot, and a boot that
never got that far falls back to the stock module and switches the fix off.
These tests run the real loader against a fake root.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure import gfx1013_source
from bc250cc.infrastructure.gfx1013_source import (
    build_gfx1013_source_command,
    gfx1013_source_state,
    gfx1013_source_supported,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "system" / "bc250-gfx1013-source.sh"
KVER = os.uname().release


def _loader_text() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"<<'LOADER'\n(.*?)\nLOADER\n", text, re.S)
    assert match, "the loader heredoc is missing"
    return match.group(1) + "\n"


def _write(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


@pytest.fixture
def fake_root(tmp_path):
    root = tmp_path / "root"
    log = tmp_path / "calls.log"
    loader = tmp_path / "bc250cc-gfx1013-load"
    _write(loader, _loader_text(), 0o755)
    for tool, body in {
        "modprobe": 'if [ "$1" = "-c" ]; then printf "options amdgpu ppfeaturemask=0xffffffff\\n"; exit 0; fi\n'
                    'echo "modprobe $*" >> "$LOG"',
        "insmod": 'echo "insmod $*" >> "$LOG"; [ -e "$BC250CC_TEST_ROOT/insmod-fails" ] && exit 1\n'
                  'mkdir -p "$BC250CC_TEST_ROOT/sys/module/amdgpu"\n'
                  'cat "$BC250CC_TEST_ROOT/loaded-srcversion" > "$BC250CC_TEST_ROOT/sys/module/amdgpu/srcversion"',
        "modinfo": 'echo "drm_ttm_helper,gpu_sched,drm_buddy"',
    }.items():
        _write(root / "bin" / tool, f"#!/bin/sh\n{body}\n", 0o755)
    _write(root / "proc" / "modules", "nct6687 1 0 - Live\n")
    _write(root / "proc" / "cmdline", "root=UUID=x rw amdgpu.ppfeaturemask=0xfff7bfff quiet\n")
    _write(root / "usr/lib/bc250cc-gfx1013" / KVER / "amdgpu.ko", "module")
    _write(root / "usr/lib/bc250cc-gfx1013" / KVER / "srcversion", "PATCHED123\n")
    _write(root / "loaded-srcversion", "PATCHED123\n")
    _write(root / "etc/bc250cc-gfx1013/enabled", "")

    def run(*args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "BC250CC_TEST_ROOT": str(root), "LOG": str(log)}
        return subprocess.run(["sh", str(loader), *args], env=env, text=True, capture_output=True, check=False)

    def calls() -> str:
        return log.read_text(encoding="utf-8") if log.exists() else ""

    return root, run, calls


def _state(root: Path, *parts: str) -> Path:
    return root.joinpath(*parts)


def test_a_normal_boot_loads_the_patched_module_with_every_option(fake_root):
    root, run, calls = fake_root
    assert run("load").returncode == 0
    assert (root / "run/bc250cc-gfx1013/loaded").read_text().strip() == "patched"
    assert (root / "var/lib/bc250cc-gfx1013/attempt").exists(), "the attempt is recorded before success is known"
    line = next(line for line in calls().splitlines() if line.startswith("insmod"))
    # modprobe.d options, the kernel command line, and upstream's scheduler.
    assert "ppfeaturemask=0xffffffff" in line
    assert "ppfeaturemask=0xfff7bfff" in line
    assert "sched_policy=2" in line
    assert "modprobe drm_ttm_helper" in calls()


def test_a_healthy_boot_clears_the_attempt(fake_root):
    root, run, _calls = fake_root
    run("load")
    assert run("confirm").returncode == 0
    assert not (root / "var/lib/bc250cc-gfx1013/attempt").exists()
    assert (root / "var/lib/bc250cc-gfx1013/last-good").exists()


def test_a_boot_that_never_finished_falls_back_and_switches_the_fix_off(fake_root):
    root, run, calls = fake_root
    run("load")  # this boot hangs: confirm never runs
    assert run("load").returncode == 0
    assert (root / "run/bc250cc-gfx1013/loaded").read_text().strip() == "stock"
    assert not (root / "etc/bc250cc-gfx1013/enabled").exists()
    assert (root / "var/lib/bc250cc-gfx1013/last-fallback").exists()
    assert calls().splitlines()[-1] == "modprobe amdgpu"


def test_the_boot_menu_switch_forces_the_stock_module(fake_root):
    root, run, calls = fake_root
    (root / "proc/cmdline").write_text("root=UUID=x bc250.gfx1013=0\n")
    run("load")
    assert (root / "run/bc250cc-gfx1013/loaded").read_text().strip() == "stock"
    assert "insmod" not in calls()
    assert (root / "etc/bc250cc-gfx1013/enabled").exists(), "a one-boot switch keeps the fix on"


def test_a_kernel_without_a_patched_module_uses_the_stock_one(fake_root):
    root, run, calls = fake_root
    (root / "usr/lib/bc250cc-gfx1013" / KVER / "amdgpu.ko").unlink()
    run("load")
    assert "build the fix again" in (root / "run/bc250cc-gfx1013/reason").read_text()
    assert "insmod" not in calls()


def test_a_refused_module_leaves_no_attempt_behind(fake_root):
    root, run, calls = fake_root
    (root / "insmod-fails").write_text("")
    run("load")
    assert (root / "run/bc250cc-gfx1013/loaded").read_text().strip() == "stock"
    assert not (root / "var/lib/bc250cc-gfx1013/attempt").exists()
    assert calls().splitlines()[-1] == "modprobe amdgpu"


def test_a_driver_already_loaded_is_reported_not_replaced(fake_root):
    root, run, calls = fake_root
    (root / "proc/modules").write_text("amdgpu 1 0 - Live\n")
    run("load")
    assert (root / "run/bc250cc-gfx1013/loaded").read_text().strip() == "early"
    assert calls() == ""


def test_a_foreign_amdgpu_never_unlocks_the_private_radv(fake_root):
    root, run, _calls = fake_root
    (root / "loaded-srcversion").write_text("SOMETHINGELSE\n")
    run("load")
    assert (root / "run/bc250cc-gfx1013/loaded").read_text().strip() == "stock"


def test_the_installed_files_keep_their_safety_rules():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "blacklist amdgpu" in text
    assert "OnBootSec=3min" in text
    # The private RADV follows the loaded module, checked by srcversion.
    assert 'cat $RUN_DIR/srcversion' in text and "/sys/module/amdgpu/srcversion" in text
    # 32-bit games keep a driver.
    assert "radeon_icd.i686.json" in text
    for refused in ("bazzite) die", "steamos) die", "fedora) die", "/run/ostree-booted"):
        assert refused in text
    # Upstream's own Fedora paths are never touched by this build.
    for path in ("/var/lib/bc250-gfx1013", "/etc/bc250-gfx1013", "/opt/bc250-gfx1013/"):
        assert path not in text
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("family, allowed", [
    ("arch", True), ("cachyos", True), ("manjaro", True), ("ubuntu", True),
    ("debian", True), ("opensuse", True),
    ("bazzite", False), ("steamos", False), ("fedora", False), ("gentoo", False),
])
def test_only_the_covered_families_are_offered(family, allowed):
    supported, reason = gfx1013_source_supported(family=family, kernel="7.2.6-1-cachyos")
    assert supported is allowed
    assert bool(reason) is not allowed


def test_mastag_kernels_and_image_systems_are_refused():
    assert gfx1013_source_supported(family="cachyos", kernel="7.2.6-1-cachyos-bc250")[0] is False
    assert gfx1013_source_supported(family="arch", kernel="7.2.6", immutable=True)[0] is False


def test_state_reads_what_the_boot_service_wrote(tmp_path, monkeypatch):
    for name, value in {
        "LIB_DIR": tmp_path / "lib", "CONF_DIR": tmp_path / "conf",
        "STATE_DIR": tmp_path / "state", "RUN_DIR": tmp_path / "run",
    }.items():
        monkeypatch.setattr(gfx1013_source, name, value)
    kwargs = {"family": "cachyos", "kernel": "7.2.6-1-cachyos"}
    assert gfx1013_source_state(**kwargs)["state"] == "not-installed"
    _write(tmp_path / "conf/active.env", f"{gfx1013_source.MARKER}\nVERSION=0.2.0-alpha\nKVER=7.2.6-1-cachyos\n")
    _write(tmp_path / "conf/enabled", "")
    assert gfx1013_source_state(**kwargs)["state"] == "rebuild-needed"
    _write(tmp_path / "lib/7.2.6-1-cachyos/amdgpu.ko", "x")
    assert gfx1013_source_state(**kwargs)["state"] == "reboot-required"
    _write(tmp_path / "run/loaded", "patched\n")
    state = gfx1013_source_state(**kwargs)
    assert state["state"] == "active" and state["version"] == "0.2.0-alpha"


def test_privileged_steps_never_run_a_user_writable_script(tmp_path):
    command = build_gfx1013_source_command("install", tmp_path / "checkout")
    assert "sudo install -m 0755" in command
    assert 'sudo bash "$bc250_root_script" install --stage' in command
    # Building happens as the user.
    assert re.search(r"^bash \S+ build --source", command, re.M)
    assert not re.search(r"^sudo bash \S+bc250-gfx1013-source\.sh", command, re.M)
    rebuild = build_gfx1013_source_command("rebuild", tmp_path / "checkout")
    assert "build --kernel-only" in rebuild and " deps" not in rebuild
    with pytest.raises(ValueError):
        build_gfx1013_source_command("flash", tmp_path)
    for action in ("install", "rebuild", "enable", "disable", "uninstall", "status"):
        result = subprocess.run(
            ["bash", "-n"], input=build_gfx1013_source_command(action, tmp_path / "c"),
            text=True, capture_output=True, check=False,
        )
        assert result.returncode == 0, (action, result.stderr)


def test_the_script_is_executable_in_the_checkout():
    assert SCRIPT.stat().st_mode & stat.S_IXUSR


@pytest.mark.parametrize("kernel, allowed", [
    ("7.2.6-1-cachyos", True),
    ("6.14.0-29-generic", True),          # Ubuntu 24.04 HWE, 25.04
    ("6.16.12+deb13-amd64", True),        # Debian 13 with a backports kernel
    ("6.17.1-1-default", True),           # openSUSE Tumbleweed
    ("6.12.48+deb13-amd64", False),       # Debian 13 default: the patches do not apply
    ("6.8.0-85-generic", False),          # Ubuntu 24.04 before HWE
    ("6.4.0-150600.23-default", False),   # openSUSE Leap 15
])
def test_the_build_is_offered_only_where_the_v33_patches_apply(kernel, allowed):
    family = "debian" if "deb" in kernel or "generic" in kernel else "opensuse" if "default" in kernel else "arch"
    supported, reason = gfx1013_source_supported(family=family, kernel=kernel)
    assert supported is allowed, (kernel, reason)


def test_the_script_refuses_old_kernels_and_reads_debian_release_names():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "kminor < 14" in text and "linux 6.14 or newer" in text
    # 6.16.12+deb13-amd64 is linux-6.16.12 on kernel.org.
    assert 'base="${base%%+*}"' in text


def test_arch_dependencies_are_asked_through_pacman_deptest():
    """CachyOS's zlib-ng-compat provides zlib; naming zlib made pacman stop."""
    text = SCRIPT.read_text(encoding="utf-8")
    arch = text[text.index("        arch)"):text.index("        debian)")]
    assert 'pacman -T "${wanted[@]}"' in arch
    assert 'pacman -S --needed --noconfirm "${missing[@]}"' in arch
    assert not re.search(r"pacman -S [^\n]*\bzlib\b", arch)


def test_the_password_is_asked_once_and_kept_through_the_long_build(tmp_path):
    """The install after a 20-minute build asked for sudo again and timed out."""
    command = build_gfx1013_source_command("install", tmp_path / "checkout")
    lines = command.splitlines()
    ask = lines.index("sudo -v")
    build = next(index for index, line in enumerate(lines) if " build --source " in line)
    assert ask < build
    assert any("sudo -n -v" in line for line in lines[ask:build])
    # Whichever trap is active at the end still stops the keepalive.
    assert "kill" in [line for line in lines if line.startswith("trap ")][-1]


def test_a_finished_build_is_not_repeated_and_download_bars_stay_short():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'say "already built for $KVER: $stage"' in text
    assert "COLUMNS=60 curl" in text
