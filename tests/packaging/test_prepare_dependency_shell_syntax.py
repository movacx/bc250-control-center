import subprocess
from pathlib import Path
from types import SimpleNamespace

import bc250cc.infrastructure.dependencias_repository as dependencies_module
from bc250cc.infrastructure.dependencias_repository import DependenciasRepository
from bc250cc.infrastructure.governor_conflicts import CYAN_GOVERNOR


def _bash_syntax(command: str):
    return subprocess.run(
        ["bash", "-n", "-c", command],
        check=False,
        capture_output=True,
        text=True,
    )


def test_cyan_verification_can_be_followed_by_another_top_level_command():
    verification = DependenciasRepository._cyan_runtime_verification_command()
    command = DependenciasRepository._join_shell_commands(
        [verification, 'echo "next prepare stage"']
    )

    assert "fi;;" not in command
    result = _bash_syntax(command)
    assert result.returncode == 0, result.stderr


def test_prepare_everything_generated_command_is_valid_bash(tmp_path, monkeypatch):
    scripts_root = Path("packaging/common/os-scripts").resolve()

    class FakeOsRepository:
        info = SimpleNamespace(family="fedora", label="Fedora test")

        @staticmethod
        def prepare_dependencies_command(component, cu_manager_script=""):
            suffix = f" {cu_manager_script}" if cu_manager_script else ""
            return f'echo "prepare {component}{suffix}"'

        @staticmethod
        def install_umr_command(cu_manager_script):
            return f'echo "install umr {cu_manager_script}"'

    FakeOsRepository.scripts_root = scripts_root

    captured = {}
    repository = DependenciasRepository()
    repository.estado_herramientas_cache = None
    repository._configured_gpu_governor = lambda _preference=None: {
        "selected": CYAN_GOVERNOR
    }
    repository._os_repository = lambda: FakeOsRepository()
    repository.estado_herramientas_bc250 = lambda: {}
    repository._tool_dir = lambda: tmp_path / "tools"
    repository.config_paths = lambda: {
        "config": str(tmp_path / "config.json"),
        "perfiles": str(tmp_path / "profiles.json"),
        "historial": str(tmp_path / "history.jsonl"),
    }
    repository._governor_config_helper_path = lambda: "/usr/libexec/bc250-control-center/bc250-governor-config-helper"
    repository._comando_preparar_nct6687_control_pwm = lambda: 'echo "prepare pwm"'
    repository._abrir_terminal = lambda command, title: captured.update(
        command=command, title=title
    ) or command

    monkeypatch.setattr(
        dependencies_module,
        "ensure_no_incompatible_governors",
        lambda *args, **kwargs: [],
    )

    command = repository.instalar_dependencias_bc250(
        governor_preference=CYAN_GOVERNOR,
        include_pwm=True,
    )

    assert captured["title"] == "Preparar dependencias BC250"
    assert command == captured["command"]
    assert "fi;;" not in command
    assert ";; echo" not in command
    result = _bash_syntax(command)
    assert result.returncode == 0, result.stderr


def test_install_cyan_generated_command_is_valid_bash(tmp_path, monkeypatch):
    scripts_root = Path("packaging/common/os-scripts").resolve()

    class FakeOsRepository:
        info = SimpleNamespace(family="fedora", label="Fedora test")

        @staticmethod
        def install_governor_command():
            return 'echo "install cyan package"'

    FakeOsRepository.scripts_root = scripts_root

    captured = {}
    repository = DependenciasRepository()
    repository.estado_herramientas_cache = None
    repository._configured_gpu_governor = lambda _preference=None: {
        "selected": CYAN_GOVERNOR
    }
    repository._os_repository = lambda: FakeOsRepository()
    repository._tool_dir = lambda: tmp_path / "tools"
    repository._governor_config_helper_path = lambda: "/usr/libexec/bc250-control-center/bc250-governor-config-helper"
    repository._abrir_terminal = lambda command, title: captured.update(
        command=command, title=title
    ) or command

    monkeypatch.setattr(
        dependencies_module,
        "ensure_no_incompatible_governors",
        lambda *args, **kwargs: [],
    )

    command = repository.instalar_governor(governor_preference=CYAN_GOVERNOR)

    assert "fi;;" not in command
    result = _bash_syntax(command)
    assert result.returncode == 0, result.stderr
