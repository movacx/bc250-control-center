import subprocess
from pathlib import Path

import pytest

from bc250cc.platform.packages.strategies.base_repository import BaseOSRepository
from bc250cc.platform.packages.strategies.detector import OSInfo
from bc250cc.shared.operation_contract import parse_result_line

SCRIPTS = tuple(
    Path("packaging/common/os-scripts", family, "prepare-dependencies.sh")
    for family in ("arch", "debian", "fedora", "bazzite", "steamos")
)


@pytest.mark.parametrize("script", SCRIPTS)
def test_plan_mode_is_read_only_and_structured(script):
    completed = subprocess.run(
        ["bash", str(script), "--component", "runtime", "--mode", "plan"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "PLAN component=runtime" in completed.stdout
    assert "BC250_RESULT status=ok component=runtime" in completed.stdout
    assert "no changes made" in completed.stdout
    assert "sudo " not in completed.stdout


@pytest.mark.parametrize("script", SCRIPTS)
def test_runtime_plan_does_not_pull_optional_components(script):
    completed = subprocess.run(
        ["bash", str(script), "--component", "runtime", "--mode", "plan"],
        check=True,
        capture_output=True,
        text=True,
    )
    plan = next(line for line in completed.stdout.splitlines() if line.startswith("PLAN "))
    assert "lm_sensors" not in plan
    assert "lm-sensors" not in plan
    assert "stress" not in plan
    assert "umr" not in plan
    if "debian/prepare-dependencies.sh" in str(script):
        assert "build-essential" not in plan
        assert "dkms" not in plan
        assert "linux-headers" not in plan


def test_unknown_mode_and_component_fail_before_an_operation():
    script = str(SCRIPTS[0])
    bad_mode = subprocess.run(
        ["bash", script, "--component", "runtime", "--mode", "remove"],
        check=False,
        capture_output=True,
        text=True,
    )
    bad_component = subprocess.run(
        ["bash", script, "--component", "unknown", "--mode", "plan"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bad_mode.returncode == 2
    assert bad_component.returncode == 2


def test_repository_rejects_unknown_mode_before_building_command(tmp_path):
    class Host:
        def _command_path(self, _name):
            return ""

        def _tool_dir(self):
            return tmp_path

    repository = BaseOSRepository(
        Host(), OSInfo("test", (), "Test", "Test", "", "arch", False)
    )
    with pytest.raises(ValueError, match="Unsupported dependency operation mode"):
        repository.prepare_dependencies_command("runtime", mode="remove")


def test_failed_component_emits_structured_error_with_real_exit_code():
    common = Path("packaging/common/os-scripts/common/common.sh").resolve()
    command = (
        f'source "{common}"; BC250_COMPONENT=runtime; BC250_MODE=check; '
        'apply_fn(){ return 0; }; check_fn(){ return 17; }; plan_fn(){ return 0; }; '
        'component_action runtime apply_fn check_fn plan_fn'
    )
    completed = subprocess.run(
        ["bash", "-c", command], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 17
    event = next(
        parse_result_line(line)
        for line in completed.stdout.splitlines()
        if line.startswith("BC250_RESULT")
    )
    assert event is not None
    assert event.status == "error"
    assert event.component == "runtime"
    assert event.code == 17
