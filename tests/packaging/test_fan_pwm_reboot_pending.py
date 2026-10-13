"""A system update without a reboot must not fail the PWM preparation.

Reported on Manjaro (2026-10-09): the kernel on disk was newer than the running
one, ``nct6687`` had nothing to build against and the whole "Prepare
dependencies" run ended as failed. That state only asks for a reboot.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

from bc250cc.infrastructure.fan_repository import FanRepository


class _Repo(FanRepository):
    def __init__(self, installer: str, family: str = "arch"):
        self.installer = installer
        self.family = family

    def _nct_service_commands(self):
        return {"restart": "echo SERVICE", "status": "true", "logs": "true", "remove": "true", "reload": "true"}

    def _os_repository(self):
        return SimpleNamespace(
            info=SimpleNamespace(family=self.family),
            install_fan_pwm_command=lambda _tools: self.installer,
            install_fan_persistence_command=lambda _tools: "echo PERSIST",
        )

    def _tool_dir(self):
        from pathlib import Path

        return Path("/nonexistent")


def _run(repo: _Repo, tmp_path) -> subprocess.CompletedProcess:
    command = repo._comando_preparar_nct6687_control_pwm()
    # Keep the test away from the real system: sudo and tee become no-ops.
    script = "sudo() { :; }\nBC250_REBOOT_REQUIRED=0\n" + command + '\necho "PWM_DEFERRED=$BC250_PWM_DEFERRED"\n'
    return subprocess.run(
        ["bash", "-c", "set -Eeuo pipefail\n" + script],
        capture_output=True, text=True, timeout=30, cwd=tmp_path,
    )


def test_a_replaced_kernel_defers_the_build_instead_of_failing(tmp_path):
    result = _run(_Repo("(exit 20)"), tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Reboot into the updated kernel" in result.stdout
    assert "PWM_DEFERRED=1" in result.stdout
    assert "Configuring module preference" not in result.stdout
    assert "SERVICE" not in result.stdout


def test_any_other_installer_failure_still_fails(tmp_path):
    result = _run(_Repo("(exit 21)"), tmp_path)
    assert result.returncode == 21


def test_a_successful_installer_continues_with_the_module_setup(tmp_path):
    result = _run(_Repo("true"), tmp_path)
    assert "Configuring module preference" in result.stdout
    assert "PWM_DEFERRED=0" in result.stdout or "PWM_DEFERRED" not in result.stdout
