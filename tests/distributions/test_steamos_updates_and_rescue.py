"""SteamOS: updating in place, the read-only switch, and the way back.

SteamOS used to get the release page instead of the in-app update, because
its root is read-only. It also forgot the application entirely on the next
OS update, which replaces the root filesystem. Every flow here runs the real
generated shell against stand-in SteamOS tools.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure.install_source import InstallSource, UpdateChannel
from bc250cc.infrastructure.self_update import (
    ReleaseAsset,
    UpdatePlan,
    install_command,
    parse_release,
    plan_update,
)
from bc250cc.infrastructure.steamos_readonly import (
    build_steamos_readonly_command,
    probe_steamos_readonly,
)
from bc250cc.infrastructure.steamos_rescue import (
    RESCUE_DESKTOP_ID,
    RESCUE_SCRIPT_NAME,
    ensure_steamos_rescue,
    is_steamos,
    rescue_script,
)


def _tool(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
    path.chmod(0o755)


def _steamos(tmp_path: Path, *, readonly: str = "enabled", password: str = "P", pacman_fails: bool = False) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    _tool(bin_dir, "steamos-readonly", f"""
echo "steamos-readonly $*" >> {calls}
[ "$1" = status ] && echo "{readonly}"
exit 0""")
    _tool(bin_dir, "pacman", f'echo "pacman $*" >> {calls}; [ "$1" = -U ] && [ "{int(pacman_fails)}" = 1 ] && exit 1; exit 0')
    _tool(bin_dir, "pacman-key", f'echo "pacman-key $*" >> {calls}')
    _tool(bin_dir, "passwd", f'echo "deck {password} 2026-09-29 -1 -1 -1 -1"')
    # sudo -n fails (a password would be needed); anything else runs as-is.
    _tool(bin_dir, "sudo", f'[ "$1" = -n ] && exit 1; echo "sudo $1" >> {calls}; "$@"')
    _tool(bin_dir, "pkexec", f'echo "pkexec $1" >> {calls}; "$@"')
    return bin_dir, calls


def _run(bin_dir: Path, script: str, *, stdin: str = "") -> subprocess.CompletedProcess:
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    return subprocess.run(["bash", "-c", script], env=env, input=stdin, capture_output=True, text=True, timeout=60)


def _package(tmp_path: Path) -> tuple[Path, UpdatePlan]:
    data = b"pkg bytes"
    package = tmp_path / "bc250-control-center-1.20.4-any.pkg.tar.zst"
    package.write_bytes(data)
    asset = ReleaseAsset(package.name, len(data), "https://x", hashlib.sha256(data).hexdigest())
    return package, UpdatePlan("package", asset=asset, manager="pacman-steamos")


# ------------------------------------------------------------------ the plan


def test_steamos_now_updates_in_place_with_the_arch_package(tmp_path):
    payload = {
        "tag_name": "v1.20.4",
        "assets": [
            {"name": "bc250-control-center-1.20.4-any.pkg.tar.zst", "size": 1,
             "browser_download_url": "https://x/a.pkg.tar.zst", "digest": "sha256:" + "a" * 64},
        ],
    }
    root = tmp_path / "install"
    root.mkdir()
    source = InstallSource(UpdateChannel.PACKAGE, package="bc250-control-center", manager="pacman")
    plan = plan_update(parse_release(payload), source, os_family="steamos", project_root=root)
    assert plan.kind == "package" and plan.manager == "pacman-steamos"
    assert plan.asset.name.endswith(".pkg.tar.zst")
    assert not plan.reboot_required


# ------------------------------------------------------------- the update


def test_the_update_switches_read_only_off_installs_and_switches_it_back(tmp_path):
    package, plan = _package(tmp_path)
    bin_dir, calls = _steamos(tmp_path)
    result = _run(bin_dir, install_command(plan, package))
    assert result.returncode == 0, result.stdout + result.stderr
    log = calls.read_text().splitlines()
    assert log.index("steamos-readonly disable") < log.index(f"pacman -U --noconfirm -- {package}")
    assert log.index(f"pacman -U --noconfirm -- {package}") < log.index("steamos-readonly enable")
    assert log.count("sudo bash") == 1, "one authorization for the whole transaction"


def test_a_failed_install_still_restores_the_protection(tmp_path):
    package, plan = _package(tmp_path)
    bin_dir, calls = _steamos(tmp_path, pacman_fails=True)
    result = _run(bin_dir, install_command(plan, package))
    assert result.returncode != 0
    assert calls.read_text().splitlines()[-1] == "steamos-readonly enable"


def test_an_already_writable_root_is_left_as_it_was(tmp_path):
    package, plan = _package(tmp_path)
    bin_dir, calls = _steamos(tmp_path, readonly="disabled")
    result = _run(bin_dir, install_command(plan, package))
    assert result.returncode == 0
    log = calls.read_text()
    assert "steamos-readonly disable" not in log and "steamos-readonly enable" not in log


@pytest.mark.parametrize("status", ["NP", "L"])
def test_a_deck_account_without_a_password_is_told_before_sudo(tmp_path, status):
    package, plan = _package(tmp_path)
    bin_dir, calls = _steamos(tmp_path, password=status)
    result = _run(bin_dir, install_command(plan, package))
    assert result.returncode == 77
    assert "run passwd" in result.stdout
    assert not calls.exists() or "pacman" not in calls.read_text()


def test_the_graphical_route_uses_one_pkexec_window(tmp_path):
    package, plan = _package(tmp_path)
    bin_dir, calls = _steamos(tmp_path)
    result = _run(bin_dir, install_command(plan, package, graphical=True))
    assert result.returncode == 0
    log = calls.read_text().splitlines()
    assert log.count("pkexec bash") == 1 and "sudo bash" not in log


# ----------------------------------------------------------- the switch


def test_the_read_only_state_is_read_without_root():
    def runner(argv, **_kw):
        return subprocess.CompletedProcess(argv, 0, stdout="disabled\n", stderr="")

    result = probe_steamos_readonly(which=lambda _n: "/usr/bin/steamos-readonly", runner=runner)
    assert {key: result[key] for key in ("available", "state")} == {
        "available": True, "state": "disabled",
    }
    assert probe_steamos_readonly(which=lambda _n: None)["available"] is False


@pytest.mark.parametrize("action", ["disable", "enable"])
def test_the_switch_runs_steamos_readonly_once(tmp_path, action):
    bin_dir, calls = _steamos(tmp_path)
    result = _run(bin_dir, build_steamos_readonly_command(action))
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"steamos-readonly {action}" in calls.read_text().splitlines()


def test_the_switch_refuses_unknown_actions():
    with pytest.raises(ValueError):
        build_steamos_readonly_command("rm -rf /")


# ------------------------------------------------------------ the rescue


def test_the_rescue_files_are_written_only_on_steamos(tmp_path):
    steamos = tmp_path / "os-release-steamos"
    steamos.write_text('NAME="SteamOS"\nID=steamos\nID_LIKE=arch\n')
    arch = tmp_path / "os-release-arch"
    arch.write_text("NAME=\"Arch Linux\"\nID=arch\n")
    assert is_steamos(steamos) and not is_steamos(arch)

    data, apps = tmp_path / "data", tmp_path / "applications"
    package = Path("/usr/share/bc250-control-center/src/bc250cc/infrastructure/steamos_rescue.py")
    common = {"data_dir": data, "applications_dir": apps, "installed_at": package}
    assert ensure_steamos_rescue(os_release=arch, **common) is False
    assert not data.exists()

    assert ensure_steamos_rescue(os_release=steamos, **common) is True
    script = data / "steamos-rescue" / RESCUE_SCRIPT_NAME
    entry = apps / RESCUE_DESKTOP_ID
    assert script.stat().st_mode & 0o111
    assert f'Exec=bash "{script}"' in entry.read_text() and "Terminal=true" in entry.read_text()
    # Unchanged content is not rewritten on every start.
    assert ensure_steamos_rescue(os_release=steamos, **common) is False


def test_a_script_install_on_steamos_gets_no_package_reinstaller(tmp_path):
    """~/.local survives the SteamOS update; the package would be a second copy."""
    steamos = tmp_path / "os-release"
    steamos.write_text("ID=steamos\n")
    data, apps = tmp_path / "data", tmp_path / "applications"
    for script_install in (
        Path("/home/deck/.local/share/bc250-control-center/src/bc250cc/infrastructure/steamos_rescue.py"),
        Path("/usr/local/share/bc250-control-center/src/bc250cc/infrastructure/steamos_rescue.py"),
    ):
        assert ensure_steamos_rescue(
            os_release=steamos, data_dir=data, applications_dir=apps, installed_at=script_install
        ) is False
    assert not data.exists() and not apps.exists()


def _rescue_fixture(tmp_path: Path, *, digest: str | None = None) -> tuple[Path, Path, Path]:
    bin_dir, calls = _steamos(tmp_path)
    data = b"release package"
    served = tmp_path / "served.pkg"
    served.write_bytes(data)
    release = tmp_path / "release.json"
    release.write_text(json.dumps({
        "tag_name": "v1.20.4",
        "assets": [{
            "name": "bc250-control-center-1.20.4-any.pkg.tar.zst",
            "browser_download_url": "https://github.com/x/pkg",
            "digest": "sha256:" + (digest or hashlib.sha256(data).hexdigest()),
        }],
    }))
    # curl stand-in: the API URL answers the release, anything else the package.
    _tool(bin_dir, "curl", f"""
out=""; url=""
while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2 ;; -H) shift 2 ;; -*) shift ;; *) url="$1"; shift ;; esac; done
echo "curl $url" >> {calls}
case "$url" in *api.github.com*) cp {release} "$out" ;; *) cp {served} "$out" ;; esac""")
    script = tmp_path / "rescue.sh"
    script.write_text(rescue_script())
    return bin_dir, calls, script


def test_the_rescue_reinstalls_the_verified_latest_package(tmp_path):
    bin_dir, calls, script = _rescue_fixture(tmp_path)
    result = _run(bin_dir, f"bash {script}", stdin="\n")
    assert result.returncode == 0, result.stdout + result.stderr
    log = calls.read_text().splitlines()
    assert "pacman-key --init" in log and "pacman -Syy --noconfirm" in log
    install = [line for line in log if line.startswith("pacman -U --noconfirm -- ")]
    assert len(install) == 1 and install[0].endswith("bc250-control-center-1.20.4-any.pkg.tar.zst")
    assert log.index("steamos-readonly disable") < log.index(install[0]) < log.index("steamos-readonly enable")
    assert "installed again" in result.stdout


def test_the_rescue_refuses_a_package_that_does_not_match(tmp_path):
    bin_dir, calls, script = _rescue_fixture(tmp_path, digest="0" * 64)
    result = _run(bin_dir, f"bash {script}", stdin="\n")
    assert result.returncode != 0
    assert "does not match" in result.stdout
    assert "pacman -U" not in calls.read_text()
