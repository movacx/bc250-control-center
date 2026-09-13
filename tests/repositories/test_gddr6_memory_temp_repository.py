from pathlib import Path

import pytest

from bc250cc.infrastructure.gddr6_memory_temp_repository import (
    GDDR6_MEMORY_TEMP_DIRECTORY,
    GDDR6_MEMORY_TEMP_REPOSITORY,
    Gddr6MemoryTempRepository,
)
from bc250cc.infrastructure.gddr6_memory_temp_trust import REVIEWED_REVISION


class FakeRepository(Gddr6MemoryTempRepository):
    def __init__(self, tool_dir, *, responses=None, helper_path="", pkexec_path="/usr/bin/pkexec"):
        self._tool_dir_value = tool_dir
        self.responses = responses or {}
        self._helper_path_value = helper_path
        self._pkexec_path = pkexec_path

    def _tool_dir(self):
        return self._tool_dir_value

    def _ejecutar(self, comando, timeout=2):
        key = tuple(comando)
        return self.responses.get(key, (1, "", "unavailable"))

    def _command_path(self, name):
        return self._pkexec_path if name == "pkexec" else ""

    def _gddr6_temp_helper_path(self):
        return self._helper_path_value

    def _hardware_source_checkout_command(self, repository_url, destination, os_repository=None):
        return f"clone {repository_url} into {destination}"

    def _abrir_terminal(self, command, title):
        return (command, title)


def _clean_repo_responses(repository: Path, *, revision=REVIEWED_REVISION, dirty=False):
    git = ["git", "-C", str(repository)]
    return {
        tuple(git + ["remote", "get-url", "origin"]): (0, GDDR6_MEMORY_TEMP_REPOSITORY, ""),
        tuple(git + ["status", "--porcelain", "--untracked-files=all"]): (
            0, ("?? stray\n" if dirty else ""), "",
        ),
        tuple(git + ["rev-parse", "HEAD"]): (0, revision, ""),
    }


def test_status_reports_not_ready_when_repository_is_absent(tmp_path):
    repository = FakeRepository(tmp_path)

    status = repository.estado_gddr6_memory_temp()

    assert status["repository_ready"] is False
    assert status["reference_url"] == GDDR6_MEMORY_TEMP_REPOSITORY
    assert status["reviewed_revision"] == REVIEWED_REVISION


def test_status_reports_ready_for_a_clean_reviewed_checkout(tmp_path):
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    (destination / "SMUPayload.bin").write_bytes(b"\x00")
    repository = FakeRepository(tmp_path, responses=_clean_repo_responses(destination))

    status = repository.estado_gddr6_memory_temp()

    assert status["repository_ready"] is True
    assert status["payload_present"] is True


def test_status_rejects_a_checkout_at_the_wrong_revision(tmp_path):
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    repository = FakeRepository(
        tmp_path, responses=_clean_repo_responses(destination, revision="0" * 40)
    )

    status = repository.estado_gddr6_memory_temp()

    assert status["repository_ready"] is False


def test_read_command_refuses_when_helper_is_not_installed(tmp_path):
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    repository = FakeRepository(
        tmp_path, responses=_clean_repo_responses(destination), helper_path=""
    )

    with pytest.raises(RuntimeError, match="helper is not installed"):
        repository.comando_leer_temperatura_vram()


def test_apply_command_refuses_a_dirty_checkout(tmp_path):
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    repository = FakeRepository(
        tmp_path,
        responses=_clean_repo_responses(destination, dirty=True),
        helper_path="/usr/libexec/bc250-control-center/bc250-gddr6-temp-helper",
    )

    with pytest.raises(RuntimeError, match="origin, revision, and integrity validation"):
        repository.comando_aplicar_parche_vram()


def test_read_command_builds_the_exact_pkexec_argv(tmp_path):
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    helper = "/usr/libexec/bc250-control-center/bc250-gddr6-temp-helper"
    repository = FakeRepository(
        tmp_path, responses=_clean_repo_responses(destination), helper_path=helper
    )

    argv = repository.comando_leer_temperatura_vram()

    assert argv == [
        "pkexec", "--disable-internal-agent", helper, "--repo", str(destination), "--action", "read",
    ]


def test_apply_command_builds_the_exact_pkexec_argv(tmp_path):
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    helper = "/usr/libexec/bc250-control-center/bc250-gddr6-temp-helper"
    repository = FakeRepository(
        tmp_path, responses=_clean_repo_responses(destination), helper_path=helper
    )

    argv = repository.comando_aplicar_parche_vram()

    assert argv[-2:] == ["--action", "apply"]


def test_prepare_command_delegates_to_the_shared_checkout_orchestrator(tmp_path):
    repository = FakeRepository(tmp_path)

    command, title = repository.comando_preparar_gddr6_memory_temp()

    assert GDDR6_MEMORY_TEMP_REPOSITORY in command
    assert GDDR6_MEMORY_TEMP_DIRECTORY in command
    assert title == "BC250 GDDR6 memory temperature"
