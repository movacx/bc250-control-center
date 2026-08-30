from pathlib import Path

import pytest

from bc250cc.infrastructure.cu_repository import CURepository

ROOT = Path(__file__).resolve().parents[3]


class Repository(CURepository):
    def __init__(self, script: Path):
        self.script = script
        self.commands = []

    def estado_herramientas_bc250(self):
        return {
            "cu_manager": str(self.script),
            "cu_manager_exists": True,
            "cu_manager_backend": "steamos",
            "is_steamos": True,
        }

    def _command_path(self, name):
        return "/usr/bin/bash" if name == "bash" else ""

    def _ejecutar(self, command, timeout=0):
        self.commands.append((command, timeout))
        return 1, "", "umr register access requires root"

    def _exportar_env_cu(self, _tools):
        return ""

    def _leer_dashboard_cu_cache(self):
        return ""


def _backend(tmp_path):
    script = tmp_path / "bc250-cu-live-manager-bc250.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    return Repository(script)


def test_status_never_executes_self_elevating_user_owned_backend(tmp_path):
    repository = _backend(tmp_path)
    with pytest.raises(RuntimeError, match="self-elevate through sudo"):
        repository.obtener_dashboard_cu()
    assert repository.commands == []


@pytest.mark.parametrize(
    "arguments",
    (["--yes", "enable", "all"], ["--yes", "stock-dispatch"], ["--yes", "install-service"]),
)
def test_typed_actions_fail_before_any_privileged_process(tmp_path, arguments):
    repository = _backend(tmp_path)
    with pytest.raises(RuntimeError, match="CU_BACKEND_UNTRUSTED"):
        repository._ejecutar_cu_accion_pkexec(arguments)
    assert repository.commands == []


def test_graphical_table_and_menu_fail_before_privilege(tmp_path):
    repository = _backend(tmp_path)
    with pytest.raises(RuntimeError, match="CU_BACKEND_UNTRUSTED"):
        repository._ejecutar_tabla_cu([0x07, 0x07, 0x07, 0x07], save_boot=True)
    with pytest.raises(RuntimeError, match="CU_BACKEND_UNTRUSTED"):
        repository.ejecutar_cu_manager("menu")
    assert repository.commands == []


def test_passwordless_game_helper_never_executes_resource_tools_cu_script():
    helper = (
        ROOT / "privileged" / "helpers" / "bc250-steamos-game-helper"
    ).read_text(encoding="utf-8")
    section = helper[helper.index("def cu_status"):helper.index("def cu_table_commands")]
    assert "run_cu_capture" not in section
    assert "CU_BACKEND_UNTRUSTED" in section
