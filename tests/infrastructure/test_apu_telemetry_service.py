"""The BC250-Telemetry installer: closed workflow, honest state, nothing it does not own."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure import apu_telemetry_service as service
from bc250cc.infrastructure.apu_telemetry_service import (
    APU_TELEMETRY_DIRECTORY,
    APU_TELEMETRY_REVIEWED_COMMIT,
    APU_TELEMETRY_UPSTREAM,
    MARKER,
    apu_telemetry_state,
    apu_telemetry_supported,
    build_apu_telemetry_command,
)
from bc250cc.infrastructure.dependencias_repository import DependenciasRepository
from bc250cc.infrastructure.external_tools.catalog import (
    EXTERNAL_TOOL_DIRECTORIES,
    EXTERNAL_TOOL_LIFECYCLES,
    EXTERNAL_TOOLS,
    LifecycleAction,
)


@pytest.mark.parametrize("family", ["arch", "cachyos", "manjaro", "debian", "ubuntu", "fedora", "gentoo"])
def test_mutable_systemd_families_are_offered_the_install(family):
    assert apu_telemetry_supported(family=family) == (True, "")


def test_image_based_and_non_systemd_systems_keep_their_own_route():
    supported, reason = apu_telemetry_supported(family="alpine")
    assert supported is False and reason
    assert apu_telemetry_supported(family="arch", immutable=True)[0] is False
    assert apu_telemetry_supported(family="unsupported", immutable=True)[0] is False


def test_rpm_ostree_images_are_offered_the_install():
    # /etc and /usr/local (-> /var/usrlocal) are writable and survive updates.
    assert apu_telemetry_supported(family="bazzite", distro_id="bazzite", immutable=True) == (True, "")


def test_steamos_is_offered_the_install():
    # The unit is on SteamOS' default keep list and /var is its own partition.
    assert apu_telemetry_supported(family="steamos", distro_id="steamos", immutable=True) == (True, "")


def test_steamos_builds_static_in_the_pinned_container_and_installs_to_var(tmp_path):
    command = build_apu_telemetry_command("install", tmp_path / "bc250-telemetry", family="steamos")
    # The image strips the C headers, so the host compiler is never used.
    assert not any(line.startswith("g++ ") for line in command.splitlines())
    assert "command -v g++" not in command
    build = next(line for line in command.splitlines() if line.startswith("podman run "))
    assert service.STEAMOS_BUILD_IMAGE in build and "@sha256:" in service.STEAMOS_BUILD_IMAGE
    assert "-static" in build and "--network=none" in build and ":/src:ro" in build
    # /usr/local is wiped by the next update; the binary goes to /var.
    assert str(service.STEAMOS_BINARY_PATH) in command
    assert str(service.BINARY_PATH) not in command
    assert f"s|TELEMETRY_BIN_PATH|{service.STEAMOS_BINARY_PATH}|g" in command
    # Nothing here needs the read-only root unlocked.
    assert "steamos-readonly" not in command
    # The deck account without a password is caught before sudo asks.
    assert command.index("bc250_require_password\n") < command.index("sudo -v")
    assert command.index("== Building the daemon ==") < command.index("sudo install")


def test_steamos_only_removes_the_compiler_image_it_pulled(tmp_path):
    lines = build_apu_telemetry_command("install", tmp_path / "x", family="steamos").splitlines()
    probe = next(i for i, line in enumerate(lines) if "bc250_had_image=1" in line)
    pull = next(i for i, line in enumerate(lines) if "podman pull" in line)
    remove = next(i for i, line in enumerate(lines) if "podman rmi" in line)
    assert probe < pull < remove
    assert lines[remove].startswith('[ "$bc250_had_image" = 1 ] ||')


def test_the_state_looks_for_the_binary_where_the_family_installs_it(tmp_path):
    unit = tmp_path / "unit"
    unit.write_text(f"{MARKER}\n", encoding="utf-8")
    state = apu_telemetry_state(family="steamos", unit=unit, snapshot=tmp_path / "none")
    assert state["binary_present"] == service.STEAMOS_BINARY_PATH.is_file()
    assert service.binary_path_for("steamos") == service.STEAMOS_BINARY_PATH
    assert service.binary_path_for("bazzite") == service.BINARY_PATH


def test_the_static_attempt_is_quiet_and_the_dynamic_build_reports(tmp_path):
    script = build_apu_telemetry_command("install", tmp_path)
    build = next(line for line in script.splitlines() if line.startswith("g++ "))
    static, dynamic = build.split(" || ")[:2]
    assert "-static" in static and static.endswith("2>/dev/null")
    assert "-static" not in dynamic and "2>/dev/null" not in dynamic


def _state(tmp_path, *, unit=None, binary=False, snapshot=False):
    unit_path, binary_path, snapshot_path = (tmp_path / n for n in ("unit", "bin", "run.json"))
    if unit is not None:
        unit_path.write_text(unit, encoding="utf-8")
    if binary:
        binary_path.write_text("x", encoding="utf-8")
    if snapshot:
        snapshot_path.write_text("{}", encoding="utf-8")
    return apu_telemetry_state(
        family="cachyos", unit=unit_path, binary=binary_path, snapshot=snapshot_path
    )


def test_the_state_follows_the_files(tmp_path):
    assert _state(tmp_path)["state"] == "not-installed"
    assert _state(tmp_path, unit="[Unit]\n")["state"] == "external"
    assert _state(tmp_path, unit=f"{MARKER}\n[Unit]\n")["state"] == "invalid"
    assert _state(tmp_path, unit=f"{MARKER}\n", binary=True)["state"] == "installed"
    published = _state(tmp_path, unit=f"{MARKER}\n", binary=True, snapshot=True)
    assert published["state"] == "publishing" and published["managed"] is True


def test_a_unit_from_upstreams_own_installer_is_never_called_ours(tmp_path):
    state = _state(tmp_path, unit="[Unit]\nDescription=APU\n", binary=True, snapshot=True)
    assert state["managed"] is False and state["state"] == "external"


def test_the_install_builds_the_pinned_commit_and_installs_only_the_daemon(tmp_path):
    command = build_apu_telemetry_command("install", tmp_path / "bc250-telemetry")
    assert APU_TELEMETRY_REVIEWED_COMMIT in command and APU_TELEMETRY_UPSTREAM in command
    assert "g++" in command and "sudo -v" in command
    assert MARKER in command
    # What upstream's install.sh would add and this must not.
    for left_out in ("bc250-web", "8090", "nct6683", "modules-load.d", "bc250-memory", "install.sh"):
        assert left_out not in command
    # Nothing is written to the system before the daemon has built.
    assert command.index("== Building the daemon ==") < command.index("sudo install")


def test_other_actions_never_touch_the_build_and_status_needs_no_root(tmp_path):
    checkout = tmp_path / "bc250-telemetry"
    status = build_apu_telemetry_command("status", checkout)
    assert "sudo" not in status and "g++" not in status
    uninstall = build_apu_telemetry_command("uninstall", checkout)
    assert "g++" not in uninstall and "git " not in uninstall
    with pytest.raises(ValueError):
        build_apu_telemetry_command("rm -rf /", checkout)


@pytest.mark.parametrize("action", ["install", "uninstall", "status"])
def test_every_workflow_is_valid_shell(tmp_path, action):
    command = build_apu_telemetry_command(action, tmp_path / "bc250-telemetry")
    result = subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


def _run_with_stubs(tmp_path, command, *, unit, binary_path_in_script=None):
    """Run a workflow with the system paths moved under tmp_path and root commands stubbed."""
    bin_dir = tmp_path / "stubs"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    for name in ("systemctl", "journalctl", "modprobe", "restorecon"):
        stub = bin_dir / name
        stub.write_text(f'#!/bin/bash\necho "{name} $*" >> {log}\n', encoding="utf-8")
        stub.chmod(0o755)
    # sudo runs its command as the test user, so the removal really happens.
    sudo = bin_dir / "sudo"
    sudo.write_text('#!/bin/bash\n[ "$1" = -n ] && shift\n[ "$1" = -v ] && exit 0\nexec "$@"\n', encoding="utf-8")
    sudo.chmod(0o755)
    unit_path, binary_path, snapshot_path = (tmp_path / n for n in ("etc-unit", "usr-bin", "run.json"))
    if unit is not None:
        unit_path.write_text(unit, encoding="utf-8")
    binary_path.write_text("daemon", encoding="utf-8")
    command = (
        command.replace(str(service.UNIT_PATH), str(unit_path))
        .replace(str(binary_path_in_script or service.BINARY_PATH), str(binary_path))
        .replace(str(service.SNAPSHOT_PATH), str(snapshot_path))
    )
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    result = subprocess.run(["bash", "-c", command], env=env, text=True, capture_output=True, check=False)
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    return result, calls, unit_path, binary_path


def test_uninstall_removes_what_it_installed(tmp_path):
    command = build_apu_telemetry_command("uninstall", tmp_path / "x")
    result, calls, unit, binary = _run_with_stubs(tmp_path, command, unit=f"{MARKER}\n[Unit]\n")
    assert result.returncode == 0, result.stderr
    assert not unit.exists() and not binary.exists()
    assert "systemctl disable --now apu-telemetry.service" in calls


def test_steamos_uninstall_removes_the_binary_from_var(tmp_path):
    command = build_apu_telemetry_command("uninstall", tmp_path / "x", family="steamos")
    assert str(service.STEAMOS_BINARY_PATH) in command and "bc250_require_password" in command
    result, calls, unit, binary = _run_with_stubs(
        tmp_path, command, unit=f"{MARKER}\n[Unit]\n", binary_path_in_script=service.STEAMOS_BINARY_PATH
    )
    assert result.returncode == 0, result.stderr
    assert not unit.exists() and not binary.exists()
    assert "systemctl disable --now apu-telemetry.service" in calls


def test_uninstall_leaves_a_service_it_did_not_install(tmp_path):
    command = build_apu_telemetry_command("uninstall", tmp_path / "x")
    result, calls, unit, binary = _run_with_stubs(tmp_path, command, unit="[Unit]\nDescription=upstream\n")
    assert result.returncode == 0
    assert unit.exists() and binary.exists()
    assert "systemctl" not in calls and "left untouched" in result.stdout


def test_install_leaves_a_service_it_did_not_install(tmp_path):
    command = build_apu_telemetry_command("install", tmp_path / "x")
    result, calls, unit, _binary = _run_with_stubs(tmp_path, command, unit="[Unit]\nDescription=upstream\n")
    assert result.returncode == 0
    assert unit.read_text(encoding="utf-8") == "[Unit]\nDescription=upstream\n"
    assert "left untouched" in result.stdout
    assert "enable" not in calls and "restart" not in calls


def test_the_manifest_declares_the_root_daemon_and_agrees_with_the_module():
    spec = EXTERNAL_TOOLS["apu_telemetry"]
    assert spec.upstream == APU_TELEMETRY_UPSTREAM
    assert spec.reviewed_revision == APU_TELEMETRY_REVIEWED_COMMIT
    assert spec.privilege_class != "userspace" and spec.hardware_writes is True
    assert spec.adoption_ready is True and spec.redistribution_ready is True
    lifecycle = EXTERNAL_TOOL_LIFECYCLES["apu_telemetry"]
    assert lifecycle.validation_issues() == ()
    assert LifecycleAction.UNINSTALL in lifecycle.actions
    assert EXTERNAL_TOOL_DIRECTORIES["apu_telemetry"] == APU_TELEMETRY_DIRECTORY


class _Repository(DependenciasRepository):
    def __init__(self, family, immutable=False):
        self.opened = []
        info = type("Info", (), {"family": family, "distro_id": family, "immutable": immutable})()
        self._info = info

    def _os_repository(self):
        return type("OS", (), {"info": self._info})()

    def _tool_dir(self):
        return Path("/tmp/bc250-tools")

    def _abrir_terminal(self, command, title="BC250 Control Center"):
        self.opened.append((command, title))
        return "opened"


def test_the_repository_opens_the_workflow_in_the_terminal():
    repository = _Repository("cachyos")
    assert repository.gestionar_apu_telemetry("install") == "opened"
    command, title = repository.opened[0]
    assert APU_TELEMETRY_REVIEWED_COMMIT in command and "BC250-Telemetry" in title
    assert str(Path("/tmp/bc250-tools") / APU_TELEMETRY_DIRECTORY) in command


def test_the_repository_passes_the_family_to_the_workflow():
    repository = _Repository("steamos", immutable=True)
    assert repository.gestionar_apu_telemetry("install") == "opened"
    command, _title = repository.opened[0]
    assert "podman run " in command and str(service.STEAMOS_BINARY_PATH) in command


def test_the_repository_refuses_to_install_where_it_is_not_offered():
    repository = _Repository("alpine")
    with pytest.raises(RuntimeError):
        repository.gestionar_apu_telemetry("install")
    assert repository.opened == []
    # Checking or removing is still allowed: it only touches what the app installed.
    repository.gestionar_apu_telemetry("status")
    with pytest.raises(ValueError):
        repository.gestionar_apu_telemetry("explode")
