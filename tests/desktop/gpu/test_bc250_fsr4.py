from __future__ import annotations

import json

from bc250cc.infrastructure import bc250_fsr4


def test_fsr4_state_reports_a_reversible_user_runtime(tmp_path, monkeypatch):
    prefix = tmp_path / "bc250-fsr4" / "v3"
    icd = prefix / "radv-bc250-fsr4-v3.json"
    monkeypatch.setattr(bc250_fsr4, "BC250_FSR4_PREFIX", prefix)
    monkeypatch.setattr(bc250_fsr4, "BC250_FSR4_ICD", icd)

    state = bc250_fsr4.fsr4_runtime_state("cachyos", "cachyos")

    assert state["precompiled_supported"] is True
    assert state["source_build_required"] is False
    assert state["installed"] is False
    assert state["current"] is False
    assert state["state"] == "not-installed"
    assert state["upstream_managed"] is True
    assert state["branch"] == "v3"
    assert state["prefix"] == str(prefix)
    (prefix / "libvulkan_radeon.so").parent.mkdir(parents=True)
    (prefix / "libvulkan_radeon.so").touch()
    icd.write_text(json.dumps({
        "file_format_version": "1.0.0",
        "ICD": {"library_path": str(prefix / "libvulkan_radeon.so"), "api_version": "1.4.0"},
    }))
    installed = bc250_fsr4.fsr4_runtime_state("ubuntu", "ubuntu")
    assert installed["installed"] is True
    assert installed["current"] is True
    assert installed["source_build_required"] is True


def test_fsr4_manjaro_is_explicitly_experimental_and_abi_gated():
    state = bc250_fsr4.fsr4_runtime_state("manjaro", "manjaro")

    assert state["precompiled_supported"] is False
    assert state["experimental_precompiled"] is True
    assert state["installer_available"] is True
    assert state["source_build_required"] is False


def test_fsr4_install_command_invokes_official_v3_and_never_mutates_system_mesa(tmp_path):
    destination = tmp_path / "bc250-fsr4"
    command = bc250_fsr4.build_fsr4_v3_install_command(destination)

    assert bc250_fsr4.BC250_FSR4_REPOSITORY in command
    assert "--branch v3" in command
    assert "remote set-url origin" in command
    assert "checkout -B v3 FETCH_HEAD" in command
    assert f"bash {destination}/install-v3.sh" in command
    assert "bc250-fsr4-v3.patch" in command
    assert "1002:13fe" in command
    assert "previous per-user runtime was restored" in command
    assert ".v3.backup." in command
    assert "manjaro)" in command
    assert "sudo" not in command
    assert "pacman" not in command
    assert "/etc/pacman.conf" not in command
    assert "/etc/vulkan" not in command
    assert "curl |" not in command


def test_fsr4_uninstall_invokes_the_official_v3_script(tmp_path):
    destination = tmp_path / "bc250-fsr4"
    command = bc250_fsr4.build_fsr4_v3_uninstall_command(destination)

    assert bc250_fsr4.BC250_FSR4_REPOSITORY in command
    assert f"bash {destination}/uninstall-v3.sh" in command
    assert 'BC250_FSR4_PREFIX="$HOME/.local/share/bc250-fsr4/v3"' in command
    assert "sudo" not in command
