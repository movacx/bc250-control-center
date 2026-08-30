import pytest

from bc250cc.infrastructure.cpu_repository import CORE_UNLOCK_REPOSITORY, CPURepository


class _Repository(CPURepository):
    def __init__(self, tools):
        self.tools = tools

    def _tool_dir(self):
        return self.tools

    def _core_unlock_helper_path(self):
        return "/usr/libexec/bc250-control-center/bc250-core-unlock-helper"

    def _command_path(self, name):
        return "/usr/bin/pkexec" if name == "pkexec" else ""

    def _core_unlock_repository_state(self, _repository):
        return CORE_UNLOCK_REPOSITORY, True, True


def test_existing_mint_umask_clone_is_secured_before_privileged_launch(tmp_path):
    repository = tmp_path / "bc250-core-unlock"
    (repository / ".git").mkdir(parents=True)
    script = repository / "bc250-unlock-cores.py"
    script.write_text("#!/usr/bin/python3\n", encoding="utf-8")
    script.chmod(0o775)

    command = _Repository(tmp_path).comando_desbloquear_nucleos_cpu()

    assert command[-2:] == [str(repository), "--reboot"]
    assert script.stat().st_mode & 0o777 == 0o755


def test_core_unlock_refuses_symlink_even_when_target_is_user_owned(tmp_path):
    repository = tmp_path / "bc250-core-unlock"
    (repository / ".git").mkdir(parents=True)
    target = tmp_path / "payload.py"
    target.write_text("#!/usr/bin/python3\n", encoding="utf-8")
    target.chmod(0o755)
    (repository / "bc250-unlock-cores.py").symlink_to(target)

    with pytest.raises(RuntimeError, match="symbolic link"):
        _Repository(tmp_path).comando_desbloquear_nucleos_cpu()
