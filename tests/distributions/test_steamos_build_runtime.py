"""keyboardspecialist v0.40 builds the AMDGPU module with the installed SteamOS channel.

Up to the v0.30 pin Control Center ran adapted copies of fetch-sources.sh and
build.sh, because the toolkit took Python from rolling ``core-main`` and its
``math`` module needs GLIBC_2.44 (SteamOS 3.9.5 has glibc 2.43). Since v0.38
upstream's fetch-build-deps.sh reads ``pacman-conf --repo-list`` (extra-3.9 and
core-3.9 here), checks package SHA-256s and that the cache runs before using
it. These tests pin that the upstream scripts now run unchanged, that the old
copies are removed and that a dependency runtime failure keeps BUILD-001.
"""
import os
import shlex
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure.dependencias_constants import (
    STEAMOS_FIX_DIRECTORY,
    STEAMOS_FIX_SUBDIRECTORY,
)
from bc250cc.infrastructure.dependencias_steamos import SteamosDependenciesMixin
from bc250cc.infrastructure.steamos_amdgpu import (
    LEGACY_BUILD_ADAPTER_FILES,
    SUPPORTED_KERNEL_BASES,
    UPSTREAM_DEPENDENCY_RUNTIME_FAILURE,
    build_dependencies_command,
    retire_build_adapter_command,
)
from bc250cc.infrastructure.steamos_amdgpu_backend import STEAMOS_AMDGPU_AUDIO_FIX_ROOT
from bc250cc.infrastructure.terminal_plan import workflow_wrapper
from bc250cc.shared.error_catalog import for_marker

#: /etc/os-release and ``uname -r`` of the BC-250 this update was checked on.
REAL_OS_RELEASE = Path("tests/fixtures/steamos_amdgpu/os-release-steamos-3.9.5")
REAL_KERNEL = "7.2.7-valve2-2-neptune-72-g31504582a073"
#: Upstream v0.40's own lines when Python from the wrong channel cannot load.
UPSTREAM_RUNTIME_FAILURE_OUTPUT = (
    "Build dependency repositories: extra-main core-main\n"
    "ImportError: /usr/lib/libm.so.6: version `GLIBC_2.44' not found\n"
    "FATAL: Python build modules are incompatible; run fetch-build-deps.sh to repair the cache\n"
    "FATAL: Downloaded dependencies do not run on this host; the previous cache was preserved\n"
)


class Repository(SteamosDependenciesMixin):
    def __init__(self, root):
        self.root = root

    def _tool_dir(self):
        return self.root

    def _clone_or_update_commit_command(self, *args):
        return ":"


def _audio(tmp_path):
    return tmp_path / STEAMOS_FIX_DIRECTORY / STEAMOS_FIX_SUBDIRECTORY


def _fake_upstream_step(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def test_upstream_build_scripts_run_unchanged_and_in_order(tmp_path):
    command = Repository(tmp_path)._steamos_compatibility_stage_command(install=True)
    audio = _audio(tmp_path)
    protected = STEAMOS_AMDGPU_AUDIO_FIX_ROOT

    order = [
        command.index(f"sudo /usr/bin/bash {protected}/ensure-build-prereqs.sh"),
        command.index(f"/usr/bin/bash {audio}/fetch-build-deps.sh"),
        command.index(f"/usr/bin/bash {audio}/fetch-sources.sh"),
        command.index(f"/usr/bin/bash {audio}/build.sh"),
        command.index(f"sudo /usr/bin/bash {protected}/install.sh"),
    ]
    assert order == sorted(order)
    # Upstream picks the channel from pacman-conf; nothing overrides it.
    assert "DEP_REPOS" not in command
    assert "prepare-steamos-build-runtime" not in command
    for name in LEGACY_BUILD_ADAPTER_FILES:
        assert f"/usr/bin/bash {audio}/{name}" not in command
    assert not Path("scripts/system/prepare-steamos-build-runtime.py").exists()
    subprocess.run(["bash", "-n"], input=command, text=True, check=True)


def test_adapter_of_earlier_releases_is_removed_without_following_links(tmp_path):
    audio = tmp_path / "audio"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("kept", encoding="utf-8")
    for name in LEGACY_BUILD_ADAPTER_FILES:
        _fake_upstream_step(audio / name, "exit 0\n")
    _fake_upstream_step(audio / "deps-bc250cc-3.9/usr/bin/python3", "exit 0\n")
    (audio / "deps-bc250cc-3.8").symlink_to(outside, target_is_directory=True)
    for name in ("fetch-sources.sh", "build.sh", "build-env.sh"):
        (audio / name).write_text("# upstream\n", encoding="utf-8")
    (audio / "deps").mkdir()

    script = retire_build_adapter_command(audio)
    result = subprocess.run(["bash", "-Eeuo", "pipefail", "-c", script],
                            capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert "Removed the build adapter of an earlier Control Center release" in result.stdout
    assert sorted(path.name for path in audio.iterdir()) == [
        "build-env.sh", "build.sh", "deps", "fetch-sources.sh",
    ]
    assert (outside / "keep").read_text(encoding="utf-8") == "kept"
    again = subprocess.run(["bash", "-Eeuo", "pipefail", "-c", script],
                           capture_output=True, text=True)
    assert again.returncode == 0 and again.stdout == ""


def _run_dependencies(tmp_path, body):
    audio = tmp_path / "audio"
    _fake_upstream_step(audio / "fetch-build-deps.sh", body)
    return subprocess.run(
        ["bash", "-Eeuo", "pipefail", "-c", build_dependencies_command(audio) + "; echo NEXT_STEP"],
        capture_output=True, text=True, env=os.environ | {"XDG_RUNTIME_DIR": str(tmp_path)},
    )


def test_dependency_runtime_failure_stops_before_the_kernel_download(tmp_path):
    assert UPSTREAM_DEPENDENCY_RUNTIME_FAILURE in UPSTREAM_RUNTIME_FAILURE_OUTPUT
    body = f"printf %s {shlex.quote(UPSTREAM_RUNTIME_FAILURE_OUTPUT)} >&2\nexit 1\n"
    result = _run_dependencies(tmp_path, body)

    assert result.returncode == 1
    assert "NEXT_STEP" not in result.stdout
    assert "GLIBC_2.44" in result.stdout  # upstream's own explanation is kept
    marker = next(line for line in result.stdout.splitlines()
                  if "STEAMOS_BUILD_RUNTIME_INCOMPATIBLE" in line)
    assert for_marker(marker).code == "BC250-BUILD-001"
    assert not list(tmp_path.glob("bc250-build-deps.*"))


def test_the_whole_failure_log_is_diagnosed_as_the_steamos_build_runtime(tmp_path):
    body = f"printf %s {shlex.quote(UPSTREAM_RUNTIME_FAILURE_OUTPUT)} >&2\nexit 1\n"
    audio = tmp_path / "audio"
    _fake_upstream_step(audio / "fetch-build-deps.sh", body)
    command = build_dependencies_command(audio)
    result = subprocess.run(
        ["bash", "-c", workflow_wrapper(command, tmp_path / "status", tmp_path / "log", hold=False)],
        capture_output=True, text=True, timeout=30,
        env=os.environ | {"XDG_RUNTIME_DIR": str(tmp_path)},
    )
    assert result.returncode == 1
    assert "BC250-BUILD-001" in result.stdout


@pytest.mark.parametrize("body", [
    # Offline: upstream dies before any runtime check.
    "echo 'FATAL: Could not fetch package database for extra-3.9' >&2\nexit 1\n",
    # A stale cache fails its check, the rebuild then fails to download.
    "echo 'FATAL: Python build modules are incompatible; run fetch-build-deps.sh to repair the cache' >&2\n"
    "echo 'FATAL: Download failed: python-3.14.2-1-x86_64.pkg.tar.zst' >&2\nexit 1\n",
])
def test_other_dependency_failures_keep_their_status_without_the_runtime_claim(tmp_path, body):
    result = _run_dependencies(tmp_path, body)
    assert result.returncode == 1
    assert "NEXT_STEP" not in result.stdout
    assert "STEAMOS_BUILD_RUNTIME_INCOMPATIBLE" not in result.stdout


def test_matching_dependencies_continue_and_leave_no_log(tmp_path):
    result = _run_dependencies(
        tmp_path, "echo 'Build dependencies already match 3.9 and pass runtime checks'\n")
    assert result.returncode == 0, result.stderr
    assert "already match 3.9" in result.stdout
    assert "NEXT_STEP" in result.stdout
    assert not list(tmp_path.glob("bc250-build-deps.*"))


def _real_os_release():
    values = {}
    for line in REAL_OS_RELEASE.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value.strip('"')
    return values


def test_this_steamos_3_9_5_host_is_steamos_for_every_alternative_check(tmp_path):
    from bc250cc.infrastructure.steamos_graphics_runtime import (
        build_steamos_graphics_command,
    )

    info = _real_os_release()
    assert info["VERSION_ID"] == "3.9.5" and info["ID"] == "steamos"
    assert SteamosDependenciesMixin._es_steamos(None, info)
    command = build_steamos_graphics_command("status", backend_guard="true")
    start = command.index("grep -Eiq")
    check = command[start:command.index(" ||", start)]
    assert check.endswith("/etc/os-release")
    check = check.replace("/etc/os-release", shlex.quote(str(REAL_OS_RELEASE)))
    assert subprocess.run(["bash", "-c", check]).returncode == 0


@pytest.mark.parametrize(("release", "accepted"), [
    (REAL_KERNEL, True),
    ("6.18.53-valve1-1-neptune-618", True),
    ("7.3.4-1.425-cachyos-bc250", False),
])
def test_the_kernel_gate_accepts_this_host_and_refuses_unpatched_bases(tmp_path, release, accepted):
    assert "7.2" in SUPPORTED_KERNEL_BASES
    command = Repository(tmp_path)._steamos_compatibility_stage_command(install=True)
    start = command.index('running_release="$(uname -r)"')
    end = command.index("esac", start) + len("esac")
    gate = f"uname() {{ echo {shlex.quote(release)}; }}; " + command[start:end] + "; echo GATE_PASSED"
    result = subprocess.run(["bash", "-c", gate], capture_output=True, text=True)
    if accepted:
        assert result.returncode == 0 and "GATE_PASSED" in result.stdout
    else:
        assert result.returncode == 38
        assert "No system changes were made." in result.stdout
