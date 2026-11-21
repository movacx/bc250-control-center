"""R-b6d54432: a manual CPU scale test on a board whose bc250_smu_oc clone is
missing fetched nothing and stopped with "Use Prepare dependencies first".

The clone is now fetched at its reviewed revision, as the desktop user, and the
same pkexec test runs right after it, writing to the same overclock.conf.
"""

from __future__ import annotations

import subprocess

from bc250cc.infrastructure import cpu_repository
from bc250cc.infrastructure.cpu_repository import CPURepository

HELPER = "/usr/libexec/bc250-control-center/bc250-cpu-smu-helper"


def _repository(tmp_path, *, smu_oc_exists):
    repository = object.__new__(CPURepository)
    tools = {
        "stress": True,
        "smu_oc_exists": smu_oc_exists,
        "smu_oc_path": str(tmp_path / "bc250_smu_oc"),
    }
    fetched = []
    stubs = {
        "evaluar_aplicacion_manual_cpu": lambda *_a: {"frequency": 3850, "scale": -38, "temperature": 90},
        "_usar_steamos_game_helper": lambda: False,
        "_command_path": lambda name: f"/usr/bin/{name}",
        "estado_herramientas_bc250": lambda: tools,
        "_cpu_smu_helper_path": lambda: HELPER,
        "_tool_dir": lambda: tmp_path,
        "_hardware_source_checkout_command": lambda url, destination, _os: fetched.append((url, destination))
        or f"echo checkout {destination}",
    }
    for name, stub in stubs.items():
        setattr(repository, name, stub)
    return repository, fetched


def test_a_present_clone_runs_the_test_directly(tmp_path, monkeypatch):
    monkeypatch.setattr(cpu_repository, "pkexec_prefix", lambda name: [name])
    repository, fetched = _repository(tmp_path, smu_oc_exists=True)
    command = repository.comando_cpu_oc_manual_verificado_embebido(3850, -38, 90, True)
    assert command[0] == "pkexec" and command[-5:] == [
        "verify-scale", "3850", "-38", "90", str(tmp_path / "bc250_smu_oc" / "overclock.conf"),
    ]
    assert fetched == []


def test_a_missing_clone_is_fetched_then_the_same_test_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(cpu_repository, "pkexec_prefix", lambda name: [name])
    repository, fetched = _repository(tmp_path, smu_oc_exists=False)
    command = repository.comando_cpu_oc_manual_verificado_embebido(3850, -38, 90, True)
    assert command[:2] == ["/bin/bash", "-c"]
    script = command[2]
    assert fetched == [(cpu_repository.EXTERNAL_TOOLS["cpu_smu_oc"].upstream, tmp_path / "bc250_smu_oc")]
    assert script.index("echo checkout") < script.index("exec pkexec")
    assert f"verify-scale 3850 -38 90 {tmp_path / 'bc250_smu_oc' / 'overclock.conf'}" in script
    assert "bc250_detect.py is missing" in script
    result = subprocess.run(["bash", "-n", "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
