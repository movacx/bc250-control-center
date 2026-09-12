from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import bc250_fsr4
from bc250cc.infrastructure.dependencias_repository import DependenciasRepository


def test_fsr4_launch_options_are_username_independent():
    binary = bc250_fsr4.fsr4_steam_launch_option("")
    source = bc250_fsr4.fsr4_steam_launch_option("debian-podman-source")

    assert binary == 'VK_DRIVER_FILES="$HOME/.local/share/bc250-fsr4/v3/radv-bc250-fsr4-v3.json" %command%'
    assert source.startswith('LD_LIBRARY_PATH="$HOME/.local/share/bc250-fsr4/v3/lib')
    assert '${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}' in source
    assert 'VK_DRIVER_FILES="$HOME/.local/share/bc250-fsr4/v3/' in source
    assert "/home/" not in binary
    assert "/home/" not in source


def test_fsr4_state_reports_a_reversible_user_runtime(tmp_path, monkeypatch):
    prefix = tmp_path / "bc250-fsr4" / "v3"
    icd = prefix / "radv-bc250-fsr4-v3.json"
    monkeypatch.setattr(bc250_fsr4, "BC250_FSR4_PREFIX", prefix)
    monkeypatch.setattr(bc250_fsr4, "BC250_FSR4_ICD", icd)

    state = bc250_fsr4.fsr4_runtime_state(
        "cachyos", "cachyos", compute_kernel_ready=True
    )

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
    (prefix / ".bc250-upstream-revision").write_text(
        bc250_fsr4.BC250_FSR4_REVIEWED_COMMIT, encoding="utf-8"
    )
    icd.write_text(json.dumps({
        "file_format_version": "1.0.0",
        "ICD": {"library_path": str(prefix / "libvulkan_radeon.so"), "api_version": "1.4.0"},
    }))
    installed = bc250_fsr4.fsr4_runtime_state(
        "ubuntu", "ubuntu", compute_kernel_ready=False
    )
    assert installed["installed"] is True
    assert installed["runtime_current"] is True
    assert installed["current"] is False
    assert installed["source_build_required"] is True
    assert installed["source_build_supported"] is False
    assert installed["installer_available"] is False


def test_fsr4_debian_and_ubuntu_wait_for_a_matched_kernel_workflow():
    for family, distro_id in (
        ("debian", "debian"),
        ("ubuntu", "ubuntu"),
        ("ubuntu", "linuxmint"),
    ):
        state = bc250_fsr4.fsr4_runtime_state(family, distro_id)

        assert state["precompiled_supported"] is False
        assert state["experimental_precompiled"] is False
        assert state["source_build_supported"] is False
        assert state["source_build_required"] is True
        assert state["installer_available"] is False


def test_fsr4_manjaro_is_unavailable_even_with_a_compute_kernel():
    state = bc250_fsr4.fsr4_runtime_state(
        "manjaro", "manjaro", compute_kernel_ready=True
    )

    assert state["precompiled_supported"] is False
    assert state["experimental_precompiled"] is False
    assert state["installer_available"] is False
    assert state["source_build_required"] is True


def test_fsr4_bazzite_requires_the_reviewed_ogc_kernel():
    blocked = bc250_fsr4.fsr4_runtime_state("bazzite", "bazzite")
    state = bc250_fsr4.fsr4_runtime_state(
        "bazzite", "bazzite", compute_kernel_ready=True
    )

    assert state["precompiled_supported"] is False
    assert state["experimental_precompiled"] is False
    assert state["source_build_supported"] is True
    assert state["source_build_required"] is True
    assert state["installer_available"] is True
    assert state["build_mode"] == "bazzite-podman-source"
    assert blocked["installer_available"] is False


def test_fsr4_fedora44_requires_the_repaired_gfx1013_boot():
    blocked = bc250_fsr4.fsr4_runtime_state(
        "fedora", "fedora", "44", compute_kernel_ready=False
    )
    ready = bc250_fsr4.fsr4_runtime_state(
        "fedora", "fedora", "44", compute_kernel_ready=True
    )
    unsupported = bc250_fsr4.fsr4_runtime_state(
        "fedora", "fedora", "43", compute_kernel_ready=True
    )

    assert blocked["build_mode"] == "fedora44-podman-source"
    assert blocked["source_build_supported"] is True
    assert blocked["compute_kernel_required"] is True
    assert blocked["installer_available"] is False
    assert ready["installer_available"] is True
    assert unsupported["source_build_supported"] is False
    assert unsupported["installer_available"] is False


def test_fsr4_fedora44_never_marks_private_runtime_ready_on_stock_boot(
    tmp_path, monkeypatch
):
    prefix = tmp_path / "bc250-fsr4" / "v3"
    library = prefix / "libvulkan_radeon.so"
    icd = prefix / "radv-bc250-fsr4-v3.json"
    monkeypatch.setattr(bc250_fsr4, "BC250_FSR4_PREFIX", prefix)
    monkeypatch.setattr(bc250_fsr4, "BC250_FSR4_ICD", icd)
    library.parent.mkdir(parents=True)
    library.touch()
    (prefix / ".bc250-build-kind").write_text(
        "fedora44-podman-source\n", encoding="utf-8"
    )
    (prefix / ".bc250-upstream-revision").write_text(
        bc250_fsr4.BC250_FSR4_REVIEWED_COMMIT, encoding="utf-8"
    )
    runtime_libs = prefix / "lib"
    runtime_libs.mkdir()
    (runtime_libs / "libdrm.so.2").touch()
    (runtime_libs / "libdrm_amdgpu.so.1").touch()
    icd.write_text(
        json.dumps(
            {
                "file_format_version": "1.0.0",
                "ICD": {
                    "library_path": str(library),
                    "api_version": "1.4.0",
                },
            }
        ),
        encoding="utf-8",
    )

    state = bc250_fsr4.fsr4_runtime_state(
        "fedora", "fedora", "44", compute_kernel_ready=False
    )

    assert state["runtime_current"] is True
    assert state["current"] is False
    assert state["state"] == "kernel-required"
    assert state["installer_available"] is False


def test_fsr4_install_command_invokes_official_v3_and_never_mutates_system_mesa(tmp_path):
    destination = tmp_path / "bc250-fsr4"
    command = bc250_fsr4.build_fsr4_v3_install_command(destination)

    assert bc250_fsr4.BC250_FSR4_REPOSITORY in command
    assert bc250_fsr4.BC250_FSR4_REVIEWED_COMMIT in command
    assert "remote set-url origin" in command
    assert "checkout --detach --force FETCH_HEAD" in command
    assert f"bash {destination}/install-v3.sh" in command
    assert "bc250-fsr4-v3.patch" in command
    assert "1002:13fe" in command
    assert "previous per-user runtime was restored" in command
    assert ".v3.backup." in command
    assert "manjaro)" not in command
    assert 'case "$(uname -r)"' in command
    assert "sudo" not in command
    assert "pacman" not in command
    assert "/etc/pacman.conf" not in command
    assert "/etc/vulkan" not in command
    assert "curl |" not in command
    assert 'VK_DRIVER_FILES="$HOME/.local/share/bc250-fsr4/v3/' in command


def test_fsr4_bazzite_command_builds_official_source_and_rolls_back(tmp_path):
    destination = tmp_path / "bc250-fsr4"
    command = bc250_fsr4.build_fsr4_v3_bazzite_install_command(destination)

    assert bc250_fsr4.BC250_FSR4_REPOSITORY in command
    assert bc250_fsr4.BC250_FSR4_REVIEWED_COMMIT in command
    assert 'test "${ID:-}" = "bazzite"' in command
    assert "1002:13fe" in command
    assert "podman info" in command
    assert "podman build" in command
    assert "podman run --rm" in command
    assert "Dockerfile" in command
    assert "build-bc250.sh" in command
    assert "bc250-fsr4-v3.patch" in command
    assert "mesa-commit.txt" in command
    assert "Fedora 44" in command
    assert 'VK_DRIVER_FILES="$bc250_icd" vulkaninfo --summary' in command
    assert "bazzite-podman-source" in command
    assert "previous per-user runtime was restored" in command
    assert "sudo" not in command
    assert "rpm-ostree" not in command
    assert "/etc/vulkan" not in command
    assert "command -v docker" not in command

    result = subprocess.run(
        ["bash", "-n"],
        input=command,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_fsr4_debian_command_refuses_without_a_matched_kernel(tmp_path):
    with pytest.raises(RuntimeError, match="matching repaired GFX1013 kernel"):
        bc250_fsr4.build_fsr4_v3_debian_install_command(
            tmp_path / "bc250-fsr4"
        )


def test_fsr4_fedora44_command_bootstraps_dnf_and_requires_patched_boot(tmp_path):
    destination = tmp_path / "bc250-fsr4"
    command = bc250_fsr4.build_fsr4_v3_fedora44_install_command(destination)

    assert 'test "${ID:-}" = "fedora"' in command
    assert 'test "${VERSION_ID:-}" = "44"' in command
    assert "rpm-ostree" in command
    assert "sudo dnf install -y" in command
    assert "bc250.gfx1013_v33=1" in command
    assert "/var/lib/bc250-gfx1013/active.env" in command
    assert "podman build" in command
    assert "podman run --rm" in command
    assert "fedora44-podman-source" in command
    assert "/etc/vulkan" not in command
    assert "install-v3.sh" not in command

    result = subprocess.run(
        ["bash", "-n"],
        input=command,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_repository_blocks_ubuntu_until_a_matched_kernel_exists(tmp_path):
    repository = DependenciasRepository()
    repository._os_repository = lambda: SimpleNamespace(
        info=SimpleNamespace(family="ubuntu", distro_id="ubuntu")
    )
    repository._tool_dir = lambda: tmp_path
    repository._abrir_terminal = lambda command, _title: command

    with pytest.raises(RuntimeError, match="verified matching GFX1013 kernel"):
        repository.gestionar_fsr4_bc250("install")


def test_repository_routes_ready_fedora44_to_gated_source_build(tmp_path):
    repository = DependenciasRepository()
    os_repository = SimpleNamespace(
        info=SimpleNamespace(
            family="fedora",
            distro_id="fedora",
            version_id="44",
            immutable=False,
        )
    )
    repository._os_repository = lambda: os_repository
    repository._gfx1013_compute_state = lambda _os: {
        "dryhopped_ready": True
    }
    repository._tool_dir = lambda: tmp_path
    repository._abrir_terminal = lambda command, _title: command

    command = repository.gestionar_fsr4_bc250("install")

    assert "official V3 source build for Fedora 44" in command
    assert "bc250.gfx1013_v33=1" in command
    assert "sudo dnf install -y" in command
    assert "install-v3.sh" not in command


def test_fsr4_uninstall_invokes_the_official_v3_script(tmp_path):
    destination = tmp_path / "bc250-fsr4"
    command = bc250_fsr4.build_fsr4_v3_uninstall_command(destination)

    assert bc250_fsr4.BC250_FSR4_REPOSITORY in command
    assert f"bash {destination}/uninstall-v3.sh" in command
    assert 'BC250_FSR4_PREFIX="$HOME/.local/share/bc250-fsr4/v3"' in command
    assert "sudo" not in command
