from pathlib import Path

import pytest

from bc250cc.infrastructure.gddr6_memory_temp_repository import (
    GDDR6_MEMORY_TEMP_DIRECTORY,
    GDDR6_MEMORY_TEMP_REPOSITORY,
    Gddr6MemoryTempRepository,
)
from bc250cc.infrastructure.gddr6_memory_temp_trust import REVIEWED_REVISION

HELPER = "/usr/libexec/bc250-control-center/bc250-gddr6-temp-helper"
READER = "/usr/libexec/bc250-control-center/bc250-gddr6-temp-reader"


class FakeRepository(Gddr6MemoryTempRepository):
    def __init__(
        self,
        tool_dir,
        *,
        responses=None,
        helper_path="",
        reader_path="",
        pkexec_path="/usr/bin/pkexec",
        bios_version="P3.00",
    ):
        self._tool_dir_value = tool_dir
        self.responses = responses or {}
        self._helper_path_value = helper_path
        self._reader_path_value = reader_path
        self._pkexec_path = pkexec_path
        self._bios_version_value = bios_version

    def _tool_dir(self):
        return self._tool_dir_value

    def _ejecutar(self, comando, timeout=2):
        key = tuple(comando)
        return self.responses.get(key, (1, "", "unavailable"))

    def _command_path(self, name):
        return self._pkexec_path if name == "pkexec" else ""

    def _board_bios_version(self):
        return self._bios_version_value

    def _gddr6_temp_helper_path(self):
        return self._helper_path_value

    def _gddr6_temp_reader_path(self):
        return self._reader_path_value

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


def test_read_command_refuses_when_reader_is_not_installed(tmp_path):
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    repository = FakeRepository(
        tmp_path, responses=_clean_repo_responses(destination), reader_path=""
    )

    with pytest.raises(RuntimeError, match="helper is not installed"):
        repository.comando_leer_temperatura_vram()


def test_apply_command_refuses_a_dirty_checkout(tmp_path):
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    repository = FakeRepository(
        tmp_path,
        responses=_clean_repo_responses(destination, dirty=True),
        helper_path=HELPER,
    )

    with pytest.raises(RuntimeError, match="origin, revision, and integrity validation"):
        repository.comando_aplicar_parche_vram()


def test_read_command_builds_the_exact_pkexec_argv(tmp_path):
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    repository = FakeRepository(
        tmp_path, responses=_clean_repo_responses(destination), reader_path=READER
    )

    argv = repository.comando_leer_temperatura_vram()

    assert argv == [
        "pkexec", "--disable-internal-agent", READER, "--repo", str(destination), "--action", "read",
    ]


def test_status_command_uses_the_reader_not_the_patcher(tmp_path):
    """The read-only path must never reach the binary that can write SMU memory."""
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    repository = FakeRepository(
        tmp_path,
        responses=_clean_repo_responses(destination),
        reader_path=READER,
        helper_path=HELPER,
    )

    argv = repository.comando_estado_smu_vram()

    assert READER in argv
    assert HELPER not in argv
    assert argv[-2:] == ["--action", "status"]


def test_apply_command_builds_the_exact_pkexec_argv(tmp_path):
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    repository = FakeRepository(
        tmp_path, responses=_clean_repo_responses(destination), helper_path=HELPER
    )

    argv = repository.comando_aplicar_parche_vram()

    assert argv[-2:] == ["--action", "apply"]


def test_apply_command_refuses_an_unverified_board_firmware(tmp_path):
    """The reviewed payload writes fixed SMU addresses built for P3.0 only."""
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    repository = FakeRepository(
        tmp_path,
        responses=_clean_repo_responses(destination),
        helper_path=HELPER,
        bios_version="P4.10",
    )

    with pytest.raises(RuntimeError, match="GDDR6_FIRMWARE_UNSUPPORTED"):
        repository.comando_aplicar_parche_vram()


def test_status_reports_whether_the_payload_matches_this_firmware(tmp_path):
    ready = FakeRepository(tmp_path, bios_version="P3.00").estado_gddr6_memory_temp()
    other = FakeRepository(tmp_path, bios_version="P4.10").estado_gddr6_memory_temp()

    assert ready["firmware_supported"] is True
    assert ready["bios_version"] == "P3.00"
    assert other["firmware_supported"] is False


def test_reading_parses_the_reader_snapshot(tmp_path):
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    responses = _clean_repo_responses(destination)
    argv = [
        "pkexec", "--disable-internal-agent", READER,
        "--repo", str(destination), "--action", "read",
    ]
    responses[tuple(argv)] = (
        0,
        '{"patch_active": true, "chips": [{"chip": 0, "raw": 9766, "code": 38,'
        ' "temperature_c": 36}], "average_c": 36.0, "hotspot_c": 36, "hotspot_chip": 0}',
        "",
    )
    repository = FakeRepository(tmp_path, responses=responses, reader_path=READER)

    snapshot = repository.leer_temperatura_vram()

    assert snapshot["available"] is True
    assert snapshot["patch_active"] is True
    assert snapshot["chips"][0]["temperature_c"] == 36


def test_reading_reports_an_inactive_patch_as_state_not_failure(tmp_path):
    """An unpatched board is the normal case after a power cycle."""
    destination = tmp_path / GDDR6_MEMORY_TEMP_DIRECTORY
    (destination / ".git").mkdir(parents=True)
    responses = _clean_repo_responses(destination)
    argv = [
        "pkexec", "--disable-internal-agent", READER,
        "--repo", str(destination), "--action", "read",
    ]
    responses[tuple(argv)] = (
        0, '{"patch_active": false, "blocked_reason": "GDDR6_PATCH_INACTIVE", "chips": []}', "",
    )
    repository = FakeRepository(tmp_path, responses=responses, reader_path=READER)

    snapshot = repository.leer_temperatura_vram()

    assert snapshot["available"] is True
    assert snapshot["patch_active"] is False
    assert snapshot["blocked_reason"] == "GDDR6_PATCH_INACTIVE"


def test_reading_never_raises_when_the_reader_is_missing(tmp_path):
    snapshot = FakeRepository(tmp_path).leer_temperatura_vram()

    assert snapshot["available"] is False
    assert snapshot["chips"] == []
    assert snapshot["error"]


def test_prepare_command_delegates_to_the_shared_checkout_orchestrator(tmp_path):
    repository = FakeRepository(tmp_path)

    command, title = repository.comando_preparar_gddr6_memory_temp()

    assert GDDR6_MEMORY_TEMP_REPOSITORY in command
    assert GDDR6_MEMORY_TEMP_DIRECTORY in command
    assert title == "BC250 GDDR6 memory temperature"
