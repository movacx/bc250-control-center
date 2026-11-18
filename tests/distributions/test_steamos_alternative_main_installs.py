"""Installations made by Control Center 1.22.x (branch ``main``) keep working.

That release staged keyboardspecialist v0.30.0 (``e1563f2``) in the protected
backend, built the module with its markers and installed Mesa 26.2.2 RADV with
profile ``production-fsr4-v4``. After the pin moved to v0.40.0, Check and
Restore must still accept that copy; Install / update and Remove stage v0.40.0
first. Upstream code never runs here: the staged scripts are stand-ins that
print the v0.30.0 texts.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest

import bc250cc.infrastructure.steamos_amdgpu_backend as backend
import bc250cc.infrastructure.steamos_graphics_runtime as graphics
from bc250cc.infrastructure.dependencias_constants import STEAMOS_FIX_REVIEWED_COMMIT
from bc250cc.infrastructure.dependencias_steamos import SteamosDependenciesMixin
from bc250cc.infrastructure.steamos_amdgpu import build_steamos_compatibility_command

MAIN_REVISION = "e1563f2051727702a000b6ff6f6c524e2792aa21"
REAL_KERNEL = "7.2.7-valve2-2-neptune-72-g31504582a073"
OS_RELEASE = Path("tests/fixtures/steamos_amdgpu/os-release-steamos-3.9.5")
#: The members Control Center 1.22.x required in its protected copy.
MAIN_EXECUTABLES = tuple(name for name in backend.BACKEND_REQUIRED_EXECUTABLES
                         if name != "bc250-audio-fix/fetch-build-deps.sh")
MAIN_REGULARS = ("bc250-audio-fix/build-env.sh",)


def _main_stage(root: Path, *, revision: str = MAIN_REVISION, status_lines=(), status_json=None):
    root.mkdir(parents=True)
    for name in MAIN_EXECUTABLES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/usr/bin/bash\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    for name in MAIN_REGULARS:
        (root / name).write_text("# v0.30.0 build environment\n", encoding="utf-8")
    (root / "bc250-audio-fix" / "patch-driver.sh").write_text(
        "#!/usr/bin/bash\n[ \"${1:-}\" = status ] || exit 2\n"
        + "".join(f"echo {shlex.quote(line)}\n" for line in status_lines),
        encoding="utf-8",
    )
    if status_json is not None:
        (root / "bc250-mesh-shader.sh").write_text(
            "#!/usr/bin/bash\n[ \"${1:-}\" = status-json ] || exit 2\n"
            f"printf '%s\\n' {shlex.quote(json.dumps(status_json))}\n",
            encoding="utf-8",
        )
    (root / ".bc250-control-center-reviewed-revision").write_text(revision + "\n", encoding="utf-8")


def _read_only_sudo(tmp_path: Path) -> dict[str, str]:
    """A sudo that only answers the guard's read-only probes, as the desktop user."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    (fake_bin / "sudo").write_text(
        "#!/usr/bin/bash\n"
        "case \"${1:-}\" in stat) echo 0; exit 0 ;; find) exit 0 ;; test|tr) exec \"$@\" ;; esac\n"
        "echo \"sudo refused in this test: $*\" >&2; exit 99\n",
        encoding="utf-8",
    )
    (fake_bin / "sudo").chmod(0o755)
    return os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}", "XDG_RUNTIME_DIR": str(tmp_path)}


def _read_only_guard(root: Path) -> str:
    return (f"{{ {backend.existing_backend_guard(STEAMOS_FIX_REVIEWED_COMMIT, root)}; }} && "
            f"{{ {backend.legacy_stage_note(root)}; }}")


V030_READY = (
    f"[bc250-amdgpu] {REAL_KERNEL}: installed, metrics and compute aware "
    f"(/usr/lib/modules/{REAL_KERNEL}/updates/amdgpu.ko.zst)",
    "[bc250-amdgpu] scheduler policy: configured and active (amdgpu.sched_policy=2)",
    "[bc250-amdgpu] state: installed",
)
V030_DEFERRED = (
    V030_READY[0],
    "[bc250-amdgpu] scheduler policy: deferred until Mesa / RADV setup",
    "[bc250-amdgpu] state: installed",
)


@pytest.mark.parametrize(("status_lines", "cmdline", "decision"), [
    # Control Center 1.22.x wrote the policy back right after the module.
    (V030_READY, "quiet amdgpu.sched_policy=2", "READY: module and scheduler policy are installed"),
    # The v0.30 installer itself defers the policy until RADV setup.
    (V030_DEFERRED, "quiet", "READY FOR MESA / RADV"),
])
def test_kernel_check_accepts_the_copy_main_staged(tmp_path, status_lines, cmdline, decision):
    root = tmp_path / "steamos-amdgpu-backend"
    _main_stage(root, status_lines=status_lines)
    (tmp_path / "cmdline").write_text(cmdline + "\n", encoding="utf-8")
    command = build_steamos_compatibility_command(
        script=root / "bc250-audio-fix" / "patch-driver.sh",
        boot_config=root / "bc250-audio-fix" / "boot-config.sh",
        checkout_command=":", install=False,
        cmdline_path=tmp_path / "cmdline",
        backend_guard=_read_only_guard(root),
    )
    script = f"uname() {{ echo {REAL_KERNEL}; }}; " + command
    result = subprocess.run(["bash", "-Eeuo", "pipefail", "-c", script],
                            capture_output=True, text=True, env=_read_only_sudo(tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr
    assert decision in result.stdout
    assert "earlier Control Center release (toolkit v0.30.0)" in result.stdout
    assert "unavailable or untrusted" not in result.stdout


def test_a_current_stage_prints_no_legacy_note(tmp_path):
    root = tmp_path / "steamos-amdgpu-backend"
    _main_stage(root, revision=STEAMOS_FIX_REVIEWED_COMMIT)
    for name in backend.BACKEND_REQUIRED_EXECUTABLES + backend.BACKEND_REQUIRED_REGULARS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("#!/usr/bin/bash\n", encoding="utf-8")
            path.chmod(0o755)
    result = subprocess.run(["bash", "-c", _read_only_guard(root)],
                            capture_output=True, text=True, env=_read_only_sudo(tmp_path))
    assert result.returncode == 0 and result.stdout == ""


@pytest.mark.parametrize("damage", ["unknown-revision", "missing-member", "tracking-hook"])
def test_only_a_complete_known_copy_is_accepted(tmp_path, damage):
    root = tmp_path / "steamos-amdgpu-backend"
    _main_stage(root, revision="c" * 40 if damage == "unknown-revision" else MAIN_REVISION)
    if damage == "missing-member":
        (root / "bc250-audio-fix" / "rollback.sh").unlink()
    if damage == "tracking-hook":
        (root / "scripts").mkdir()
        (root / "scripts" / "feature-tracking.sh").write_text("echo TRACKED\n", encoding="utf-8")
    env = _read_only_sudo(tmp_path)
    assert subprocess.run(["bash", "-c", _read_only_guard(root)], env=env).returncode != 0
    if damage != "missing-member":
        assert subprocess.run(
            ["bash", "-c", backend.rollback_backend_guard(STEAMOS_FIX_REVIEWED_COMMIT, root)], env=env
        ).returncode != 0


def test_stock_module_restore_accepts_the_copy_main_staged(tmp_path):
    root = tmp_path / "steamos-amdgpu-backend"
    _main_stage(root)
    env = _read_only_sudo(tmp_path)
    guard = backend.rollback_backend_guard(STEAMOS_FIX_REVIEWED_COMMIT, root)
    assert subprocess.run(["bash", "-c", guard], env=env).returncode == 0
    # A change never runs from it: the strict guard wants the current stage.
    strict = backend.protected_backend_guard(root, reviewed_revision=STEAMOS_FIX_REVIEWED_COMMIT)
    assert subprocess.run(["bash", "-c", strict], env=env).returncode != 0


def test_mesa_check_accepts_the_copy_main_staged(tmp_path):
    root = tmp_path / "steamos-amdgpu-backend"
    _main_stage(root, status_json={
        "scriptAvailable": True, "runtimeState": "ready", "mesaVersion": "mesa-26.2.2",
        "configValid": True, "kernelReady": True, "schedulerConfigured": True,
        "schedulerActive": True, "globalEnabled": True, "restartRequired": False,
        "fsr4State": "not-installed", "games": [], "error": None,
    })
    command = graphics.build_steamos_graphics_command(
        "status", backend_guard=_read_only_guard(root), script=root / "bc250-mesh-shader.sh",
    ).replace("/etc/os-release", shlex.quote(str(OS_RELEASE)))
    result = subprocess.run(["bash", "-Eeuo", "pipefail", "-c", command],
                            capture_output=True, text=True, env=_read_only_sudo(tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "earlier Control Center release (toolkit v0.30.0)" in result.stdout
    assert f"BC250_UPSTREAM SteamOS-toolkit {MAIN_REVISION}" in result.stdout
    assert "Graphics runtime       Ready" in result.stdout
    assert "Mesa version           mesa-26.2.2" in result.stdout


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _main_radv(tmp_path: Path, monkeypatch, *, tamper=False):
    """Mesa 26.2.2 RADV as v0.30.0 recorded it: six-field manifest, profile v4."""
    home = tmp_path / "home"
    driver = tmp_path / "usr/lib/libvulkan_radeon_driconf.so"
    generator = tmp_path / "usr/lib/systemd/user-environment-generators/60-bc250-gfx1013"
    icd = home / "radeon_driconf_icd.x86_64.json"
    for path, payload in ((driver, b"radv-26.2.2"), (generator, b"#!/bin/sh\n"),
                          (icd, b'{"ICD": {"library_path": "/usr/lib/libvulkan_radeon_driconf.so"}}')):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    manifest = home / ".local/share/bc250-mesh-shader/install.conf"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        f"{_sha(driver)} {_sha(icd)} mesa-26.2.2 {graphics.CURRENT_UPSTREAM_COMMIT} "
        f"production-fsr4-v4 {_sha(generator)}\n", encoding="utf-8",
    )
    if tamper:
        driver.write_bytes(b"changed")
    monkeypatch.setattr(graphics, "RADV_DRIVER", driver)
    monkeypatch.setattr(graphics, "RADV_GENERATOR", generator)
    return home, driver, icd, generator


def _v040_report(tmp_path, home, icd):
    """What v0.40's status-json says about a v0.30 install: owned, not current."""
    status = tmp_path / "status-json.sh"
    status.write_text(
        "#!/usr/bin/bash\nprintf '%s\\n' " + shlex.quote(json.dumps({
            "scriptAvailable": True, "runtimeState": "invalid", "mesaVersion": "mesa-26.2.2",
            "directMeshVersion": None, "icdPath": str(icd), "configValid": True,
            "kernelReady": True, "schedulerConfigured": True, "schedulerActive": True,
            "globalEnabled": False, "restartRequired": False, "fsr4State": "not-installed",
            "games": [], "error": None,
        })) + "\n", encoding="utf-8",
    )
    status.chmod(0o755)
    return subprocess.run(
        ["bash", "-c", graphics._graphics_status_report_command(status, system_helper=None)],
        capture_output=True, text=True, env=os.environ | {"HOME": str(home)},
    )


def test_after_updating_the_stage_a_main_radv_is_shown_as_an_earlier_release(tmp_path, monkeypatch):
    home, _driver, icd, _generator = _main_radv(tmp_path, monkeypatch)
    result = _v040_report(tmp_path, home, icd)
    assert result.returncode == 0, result.stderr
    assert "Graphics runtime       Installed (earlier release)" in result.stdout
    assert "Mesa / RADV mesa-26.2.2 (production-fsr4-v4) was installed by an earlier" in result.stdout
    assert "replaces it with mesa-26.3.0" in result.stdout
    assert "RADV GFX1013 compute-queue fix (earlier release)" in result.stdout
    assert "Invalid" not in result.stdout


def test_a_changed_main_radv_is_still_reported_invalid(tmp_path, monkeypatch):
    home, _driver, icd, _generator = _main_radv(tmp_path, monkeypatch, tamper=True)
    result = _v040_report(tmp_path, home, icd)
    assert "Graphics runtime       Invalid" in result.stdout
    assert "earlier release" not in result.stdout


def test_the_dashboard_probe_shows_a_main_radv_as_installed_with_an_update(tmp_path, monkeypatch):
    home, driver, icd, generator = _main_radv(tmp_path, monkeypatch)
    state = graphics.probe_steamos_graphics_runtime(
        home=home, driver_path=driver, icd_path=icd, generator_path=generator)
    assert state["radv"]["state"] == "ready"  # shown "Installed", never "Incomplete"
    assert state["radv"]["current"] is False  # Install / update offers v0.40.0
    assert state["incomplete"] is False


class _Repository(SteamosDependenciesMixin):
    def __init__(self, root):
        self.root = root

    def _tool_dir(self):
        return self.root

    def _clone_or_update_commit_command(self, *args):
        return "echo CLONE_REVIEWED_COMMIT"


def test_update_and_removal_stage_v040_before_running_anything(tmp_path):
    repository = _Repository(tmp_path)
    kernel = repository._steamos_compatibility_stage_command(install=True)
    removal = graphics.build_steamos_graphics_command(
        "uninstall",
        checkout_command=repository._steamos_alternative_stage_command(tmp_path / "bc250-steamos"),
        backend_guard=repository._steamos_alternative_backend_guard(read_only=False),
    )
    for command, first_run in ((kernel, "patch-driver.sh status"), (removal, " uninstall")):
        clone = command.index("CLONE_REVIEWED_COMMIT")
        retire = command.index("Removed the build adapter of an earlier Control Center release")
        stage = command.index("Staging protected SteamOS AMDGPU backend")
        assert clone < retire < stage < command.index(first_run)
        strict = command[stage:command.index(first_run)]
        assert MAIN_REVISION not in strict  # the old copy is never trusted for a change
        assert STEAMOS_FIX_REVIEWED_COMMIT in strict


def test_proton_install_waits_for_the_current_mesa_stage(tmp_path):
    from bc250cc.infrastructure.steamos_proton import build_steamos_proton_command

    command = build_steamos_proton_command(
        "install", tmp_path / "bc250-steamos-proton",
        backend_guard=backend.protected_backend_guard(reviewed_revision=STEAMOS_FIX_REVIEWED_COMMIT),
    )
    assert MAIN_REVISION not in command
    assert "Prepare the SteamOS kernel and Mesa/RADV backend first." in command
