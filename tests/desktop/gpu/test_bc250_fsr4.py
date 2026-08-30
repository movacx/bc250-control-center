from __future__ import annotations

from bc250cc.infrastructure import bc250_fsr4


def test_fsr4_state_reports_a_reversible_user_runtime(tmp_path, monkeypatch):
    prefix = tmp_path / "bc250-fsr4" / "v3"
    icd = prefix / "radv-bc250-fsr4-v3.json"
    monkeypatch.setattr(bc250_fsr4, "BC250_FSR4_PREFIX", prefix)
    monkeypatch.setattr(bc250_fsr4, "BC250_FSR4_ICD", icd)

    state = bc250_fsr4.fsr4_runtime_state("cachyos")

    assert state["precompiled_supported"] is True
    assert state["source_build_required"] is False
    assert state["installed"] is False
    assert state["prefix"] == str(prefix)
    (prefix / "libvulkan_radeon.so").parent.mkdir(parents=True)
    (prefix / "libvulkan_radeon.so").touch()
    icd.touch()
    assert bc250_fsr4.fsr4_runtime_state("ubuntu")["installed"] is True
    assert bc250_fsr4.fsr4_runtime_state("ubuntu")["source_build_required"] is True


def test_fsr4_install_command_is_fixed_checksumed_and_never_mutates_system_mesa():
    command = bc250_fsr4.build_fsr4_v3_install_command()

    assert bc250_fsr4.BC250_FSR4_REPOSITORY in command
    assert bc250_fsr4.BC250_FSR4_ASSET in command
    assert bc250_fsr4.BC250_FSR4_SHA256 in command
    assert f"{bc250_fsr4.BC250_FSR4_ASSET}.sha256" not in command
    assert "sha256sum -c" in command
    assert "1002:13fe" in command
    assert "VK_DRIVER_FILES" in command
    assert "sudo" not in command
    assert "pacman" not in command
    assert "/etc/pacman.conf" not in command
    assert "/etc/vulkan" not in command
    assert "curl |" not in command


def test_fsr4_uninstall_only_targets_the_reviewed_user_prefix():
    command = bc250_fsr4.build_fsr4_v3_uninstall_command()

    assert 'case "$bc250_prefix" in "$HOME"/.local/share/bc250-fsr4/v3)' in command
    assert 'rm -rf -- "$bc250_prefix"' in command
