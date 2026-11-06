from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import steamos_proton
from bc250cc.infrastructure.dependencias_steamos import SteamosDependenciesMixin
from bc250cc.infrastructure.external_tools.catalog import EXTERNAL_TOOLS
from bc250cc.shared.error_catalog import for_marker


def _run(tmp_path, monkeypatch, action, *, result=0, guard="true"):
    destination = tmp_path / "upstream proton"
    destination.mkdir()
    script = destination / "bc250-proton.sh"
    script.write_text(
        'printf "UPSTREAM_ACTION=%s\\nMESH=%s\\n" "$1" "$BC250_MESH_TOOL"\n'
        f'exit {result}\n'
    )
    monkeypatch.setattr(steamos_proton, "clone_or_update_branch", lambda *_args: 'echo FETCH_UPSTREAM')
    release = tmp_path / "os-release"
    release.write_text('ID=steamos\n')
    command = steamos_proton.build_steamos_proton_command(
        action, destination, backend_guard=guard,
    ).replace('. /etc/os-release;', f'. "{release}";')
    return subprocess.run(['bash', '-c', command], text=True, capture_output=True, timeout=10)


@pytest.mark.parametrize("action", ["install", "update", "uninstall", "status"])
def test_runs_upstream_action_with_existing_protected_radv(tmp_path, monkeypatch, action):
    result = _run(tmp_path, monkeypatch, action)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"UPSTREAM_ACTION={action}" in result.stdout
    assert f"MESH={steamos_proton.STEAMOS_GRAPHICS_BACKEND}" in result.stdout
    assert ("FETCH_UPSTREAM" in result.stdout) == (action != "status")


@pytest.mark.parametrize("action", ["install", "update"])
def test_install_requires_existing_protected_backend_before_invoking_upstream(tmp_path, monkeypatch, action):
    result = _run(tmp_path, monkeypatch, action, guard="false")
    assert result.returncode == 38
    assert "STEAMOS_PROTON_FAILED" in result.stdout
    assert "UPSTREAM_ACTION=" not in result.stdout


def test_uninstall_does_not_require_radv_to_still_be_installed(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch, "uninstall", guard="false")
    assert result.returncode == 0
    assert "UPSTREAM_ACTION=uninstall" in result.stdout


@pytest.mark.parametrize("result", [1, 2])
def test_upstream_status_absent_or_incomplete_is_an_inspection_result(tmp_path, monkeypatch, result):
    process = _run(tmp_path, monkeypatch, "status", result=result, guard="false")
    assert process.returncode == 0
    assert "STEAMOS_PROTON_FAILED" not in process.stdout
    assert "install or repair" in process.stdout


def test_failed_upstream_action_keeps_error_and_gets_proton_diagnostic(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch, "update", result=2)
    assert result.returncode == 2
    assert for_marker(result.stdout).code == "BC250-PROTON-001"


def test_only_proton_checkout_tracks_upstream_master(tmp_path):
    spec = EXTERNAL_TOOLS["steamos_proton"]
    assert spec.validation_issues() == ()
    assert spec.update_strategy == "upstream-branch"
    command = steamos_proton.build_steamos_proton_command(
        "install", tmp_path / "bc250-steamos-proton", backend_guard="true",
    )
    assert "--branch master" in command
    assert spec.upstream in command
    assert "sudo pacman" not in command
    assert " setup" not in command
    assert "bc250-proton.sh install" in command
    assert EXTERNAL_TOOLS["steamos_amdgpu"].reviewed_revision == "e1563f2051727702a000b6ff6f6c524e2792aa21"
    subprocess.run(['bash', '-n'], input=command, text=True, check=True)


@pytest.mark.parametrize("action", ["shell", "install; touch /tmp/injected", ""])
def test_unknown_actions_are_rejected(tmp_path, action):
    with pytest.raises(ValueError):
        steamos_proton.build_steamos_proton_command(action, tmp_path, backend_guard="true")


def test_repository_rejects_other_distributions_without_opening_terminal():
    repository = SimpleNamespace(_os_repository=lambda: SimpleNamespace(info=SimpleNamespace(family="cachyos")))
    with pytest.raises(RuntimeError, match="only on SteamOS"):
        SteamosDependenciesMixin.gestionar_proton_steamos(repository, "install")


def test_service_opens_the_finite_steamos_workflow_in_the_app_terminal(tmp_path):
    from bc250cc.infrastructure.system_service import SistemaService

    repository = SimpleNamespace(
        _os_repository=lambda: SimpleNamespace(info=SimpleNamespace(family="steamos")),
        _tool_dir=lambda: tmp_path,
        _abrir_terminal=lambda command, title: (command, title),
    )
    repository.gestionar_proton_steamos = lambda action: SteamosDependenciesMixin.gestionar_proton_steamos(repository, action)
    service = SimpleNamespace(repo=repository)
    command, title = SistemaService.gestionar_proton_steamos(service, "update")
    assert "bc250-steamos-proton/bc250-proton.sh update" in command
    assert title == "SteamOS · BC-250 GE-Proton"
    assert repository.estado_herramientas_cache is None
