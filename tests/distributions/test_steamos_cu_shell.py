import subprocess

from bc250cc.infrastructure.dependencias_repository import DependenciasRepository
from bc250cc.infrastructure.steamos_cu_shell import service_backend_update_command


def test_delegated_steamos_cu_fragments_are_valid_bash(tmp_path):
    repository = DependenciasRepository()
    repository._tool_dir = lambda: tmp_path / "tools"
    script = tmp_path / "manager with spaces"
    fragments = (
        repository._steamos_cu_env_shell(),
        repository._steamos_umr_database_repair_command(),
        repository._steamos_umr_database_repair_command(check_only=True),
        repository._steamos_cu_service_backend_update_command(script),
        repository._steamos_cu_status_probe_command(script),
    )
    for fragment in fragments:
        completed = subprocess.run(
            ["bash", "-n", "-c", fragment], check=False, capture_output=True, text=True
        )
        assert completed.returncode == 0, completed.stderr


def test_service_update_allows_only_owned_exec_paths(tmp_path):
    command = service_backend_update_command(tmp_path / "manager")
    assert "/usr/local/bin/bc250-cu-live-manager" in command
    assert "/var/lib/bc250-cu-live-manager/umr/bc250-cu-live-manager" in command
    assert 'sudo install -m 0755' in command
    assert 'outside the allowed BC250 paths' in command


def test_status_probe_uses_private_unique_temporary_file(tmp_path):
    repository = DependenciasRepository()
    repository._tool_dir = lambda: tmp_path / "tools"
    command = repository._steamos_cu_status_probe_command(tmp_path / "manager")
    assert "mktemp" in command
    assert "chmod 0600" in command
    assert "/tmp/bc250-cu-steamos-status.last" not in command
    assert 'rm -f "$bc250_cu_status_file"' in command


def test_status_probe_validates_the_protected_backend_not_user_checkout(tmp_path):
    repository = DependenciasRepository()
    repository._tool_dir = lambda: tmp_path / "tools"
    user_checkout = tmp_path / "bc250-cu-live-manager-bc250.sh"

    command = repository._steamos_cu_status_probe_command(user_checkout)

    assert "/usr/libexec/bc250-control-center/bc250-cu-live-manager status" in command
    assert str(user_checkout) not in command


def test_protected_stage_normalizes_and_verifies_promoted_executable(tmp_path):
    repository = DependenciasRepository()
    repository._tool_dir = lambda: tmp_path / "tools"
    command = repository._steamos_cu_privileged_backend_stage_command(
        tmp_path / "bc250-cu-live-manager-bc250.sh"
    )

    target = "/usr/libexec/bc250-control-center/bc250-cu-live-manager"
    assert f"sudo chown root:root {target}" in command
    assert f"sudo chmod 0755 {target}" in command
    assert f"sudo stat -c %u {target}" in command
    assert f"sudo stat -c %a {target}" in command


def test_strict_uid_zero_repair_is_not_added_to_generic_bazzite_stage(tmp_path):
    repository = DependenciasRepository()
    command = repository._generic_cu_privileged_backend_stage_command(
        tmp_path / "bc250-cu-live-manager.sh"
    )

    assert "sudo stat -c %u" not in command
    assert "sudo chown root:root" not in command
