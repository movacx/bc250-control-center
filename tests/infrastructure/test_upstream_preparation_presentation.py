from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QSizePolicy

from frontends.desktop.components.dashboard_widgets import PreparationSidebar

_APP: QApplication | None = None


def _sidebar() -> PreparationSidebar:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    temporary = TemporaryDirectory()
    settings = QSettings(
        str(Path(temporary.name) / "compatibility.ini"),
        QSettings.Format.IniFormat,
    )
    sidebar = PreparationSidebar(settings=settings)
    sidebar._test_settings_directory = temporary
    return sidebar


def _state(family: str, fsr4: dict) -> SimpleNamespace:
    return SimpleNamespace(
        preparation_tools={
            "os_id": family,
            "os_label": family,
            "os_family": family,
            "masta_bc250_stack_supported": family in {"arch", "cachyos"},
            "prepare_components": {},
            "fsr4": fsr4,
        },
        dependencies_ready=False,
        governor_tool_ready=False,
        cpu_tools_ready=False,
        core_unlock_ready=False,
        umr_ready=False,
        cu_manager_ready=False,
        nct_ready=False,
    )


def test_cachyos_exposes_kernel_mesa_full_routes_and_fsr4():
    sidebar = _sidebar()
    sidebar.set_state(
        _state(
            "cachyos",
            {"precompiled_supported": True, "installed": False, "source_build_required": False},
        )
    )

    assert all(not card.isHidden() for card in sidebar.cachyos_cards)
    assert len(sidebar.cachyos_cards) == 1
    assert all(button.isEnabled() for button in (
        sidebar.cachyos_kernel_button,
        sidebar.cachyos_mesa_button,
        sidebar.cachyos_full_button,
    ))
    assert sidebar.gfx_card.isHidden()
    assert not sidebar.fsr4_card.isHidden()
    assert not sidebar.fsr4_install_button.isHidden()
    assert sidebar.fsr4_remove_button.isHidden()
    assert not sidebar.fsr4_upstream_button.isHidden()


@pytest.mark.parametrize("target", ("steamos", "bazzite", "fedora"))
def test_cachyos_compatibility_filter_shows_gfx1013_for_other_supported_hosts(
    target,
):
    sidebar = _sidebar()
    sidebar.set_state(_state("cachyos", {}))

    sidebar.compatibility_filter.setCurrentIndex(
        sidebar.compatibility_filter.findData(target)
    )

    assert not sidebar.gfx_card.isHidden()
    assert not sidebar.fsr4_card.isHidden()


def test_compatibility_filter_hides_duplicate_gfx1013_for_arch_family():
    sidebar = _sidebar()
    sidebar.set_state(_state("bazzite", {}))

    sidebar.compatibility_filter.setCurrentIndex(
        sidebar.compatibility_filter.findData("arch")
    )

    assert sidebar.gfx_card.isHidden()


def test_bazzite_offers_fsr4_source_build_and_blocks_arch_stack():
    sidebar = _sidebar()
    sidebar.set_state(
        _state(
            "bazzite",
            {
                "precompiled_supported": False,
                "source_build_supported": True,
                "installer_available": True,
                "installed": False,
                "current": False,
                "state": "not-installed",
                "source_build_required": True,
            },
        )
    )
    sidebar.compatibility_filter.setCurrentIndex(
        sidebar.compatibility_filter.findData("all")
    )

    assert all(not card.isHidden() for card in sidebar.cachyos_cards)
    assert all(not button.isEnabled() for button in (
        sidebar.cachyos_kernel_button,
        sidebar.cachyos_mesa_button,
        sidebar.cachyos_full_button,
    ))
    assert not sidebar.fsr4_card.isHidden()
    assert sidebar.fsr4_install_button.isEnabled()
    assert sidebar.fsr4_install_button.text() == "Build and install FSR4"
    assert sidebar.fsr4_card.status.text() == "Source build available"
    assert "rootless Podman" in sidebar.fsr4_card.detail.text()
    assert sidebar.fsr4_remove_button.isHidden()
    assert not sidebar.fsr4_upstream_button.isHidden()


def test_ubuntu_offers_fsr4_source_build_with_state_intact():
    sidebar = _sidebar()
    sidebar.set_state(
        _state(
            "ubuntu",
            {
                "precompiled_supported": False,
                "source_build_supported": True,
                "installer_available": True,
                "installed": False,
                "current": False,
                "state": "not-installed",
                "source_build_required": True,
                "build_mode": "debian-podman-source",
            },
        )
    )

    assert not sidebar.fsr4_card.isHidden()
    assert sidebar.fsr4_install_button.isEnabled()
    assert sidebar.fsr4_install_button.text() == "Build and install FSR4"
    assert sidebar.fsr4_card.status.text() == "Source build available"
    assert sidebar.fsr4_card.scope.text() == "Debian/Ubuntu · Official Podman source build"
    assert "installed with APT" in sidebar.fsr4_card.detail.text()
    assert "private per-game user runtime" in sidebar.fsr4_card.detail.text()
    assert sidebar.fsr4_launch_row.isHidden()


def test_fedora44_fsr4_waits_for_repaired_gfx1013_boot():
    sidebar = _sidebar()
    sidebar.set_state(
        _state(
            "fedora",
            {
                "precompiled_supported": False,
                "source_build_supported": True,
                "installer_available": False,
                "installed": False,
                "current": False,
                "state": "not-installed",
                "source_build_required": True,
                "build_mode": "fedora44-podman-source",
                "compute_kernel_required": True,
                "compute_kernel_ready": False,
            },
        )
    )

    assert sidebar.fsr4_card.scope.text() == "Fedora 44 · GFX1013 · Podman"
    assert sidebar.fsr4_card.status.text() == "Kernel repair required"
    assert "repaired GFX1013 boot must be active first" in sidebar.fsr4_card.detail.text()
    assert sidebar.fsr4_install_button.isHidden()


def test_fedora44_fsr4_source_build_is_offered_after_repaired_boot():
    sidebar = _sidebar()
    sidebar.set_state(
        _state(
            "fedora",
            {
                "precompiled_supported": False,
                "source_build_supported": True,
                "installer_available": True,
                "installed": False,
                "current": False,
                "state": "not-installed",
                "source_build_required": True,
                "build_mode": "fedora44-podman-source",
                "compute_kernel_required": True,
                "compute_kernel_ready": True,
            },
        )
    )

    assert sidebar.fsr4_card.status.text() == "Source build available"
    assert not sidebar.fsr4_card.isHidden()
    assert sidebar.fsr4_install_button.isEnabled()
    assert sidebar.fsr4_install_button.text() == "Build and install FSR4"


def test_ready_fsr4_runtime_is_offered_while_the_backend_remains_available():
    sidebar = _sidebar()
    option = (
        'LD_LIBRARY_PATH="$HOME/.local/share/bc250-fsr4/v3/lib'
        '${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" '
        'VK_DRIVER_FILES="$HOME/.local/share/bc250-fsr4/v3/radv-bc250-fsr4-v3.json" %command%'
    )
    sidebar.set_state(
        _state(
            "ubuntu",
            {
                "precompiled_supported": False,
                "source_build_supported": True,
                "installer_available": True,
                "installed": True,
                "current": True,
                "state": "ready",
                "source_build_required": True,
                "build_mode": "debian-podman-source",
                "steam_launch_option": option,
            },
        )
    )

    assert not sidebar.fsr4_card.isHidden()
    assert not sidebar.fsr4_launch_row.isHidden()
    assert sidebar.fsr4_copy_button.width() == 30
    assert sidebar.fsr4_copy_button.height() == 30
    assert sidebar._fsr4_launch_option == option


def test_steamos_ready_fsr4_is_offered_on_the_graphics_card():
    sidebar = _sidebar()
    option = (
        '"$HOME/.local/share/bc250-mesh-shader/fsr4/bc250-fsr4-run" %command%'
    )
    state = _state("steamos", {})
    state.preparation_tools["gfx1013_compute"] = {
        "reason_key": "steamos-dedicated-backend",
        "steamos_kernel_ready": True,
        "steamos_external_radv_state": "ready",
        "steamos_external_radv_current": True,
        "steamos_external_fsr4_state": "ready",
        "steamos_external_fsr4_current": True,
        "steamos_external_fsr4_launch_option": option,
    }

    sidebar.set_state(state)

    assert not sidebar.gfx_card.isHidden()
    # FSR4 is installed and current here, so its launch option is shown
    # instead of being hidden behind a developer flag.
    assert not sidebar.steamos_fsr4_launch_row.isHidden()
    assert not sidebar.gfx_tertiary_button.isHidden()
    assert sidebar.steamos_fsr4_copy_button.width() == 30
    assert sidebar.steamos_fsr4_copy_button.height() == 30
    sidebar.steamos_fsr4_copy_button.click()
    assert QApplication.clipboard().text() == option
    assert "$HOME" in QApplication.clipboard().text()


def test_steamos_fsr4_copy_stays_hidden_until_the_profile_is_current():
    sidebar = _sidebar()
    state = _state("steamos", {})
    state.preparation_tools["gfx1013_compute"] = {
        "reason_key": "steamos-dedicated-backend",
        "steamos_kernel_ready": True,
        "steamos_external_radv_state": "ready",
        "steamos_external_radv_current": True,
        "steamos_external_fsr4_state": "invalid",
        "steamos_external_fsr4_current": False,
        "steamos_external_fsr4_launch_option": "",
    }

    sidebar.set_state(state)

    assert sidebar.steamos_fsr4_launch_row.isHidden()


def test_bazzite_async_compute_card_explains_old_kernel_gate():
    sidebar = _sidebar()
    state = _state(
        "bazzite",
        {"source_build_supported": True, "installer_available": True},
    )
    state.preparation_tools["gfx1013_compute"] = {
        "reason_key": "bazzite-release-kernel-unsupported",
        "direct_installer_allowed": False,
        "kernel": "6.19.14-ogc5.1.fc44.x86_64",
    }
    sidebar.set_state(state)

    assert sidebar.gfx_card.scope.text() == "Bazzite 44 · Compatible kernel required"
    assert sidebar.gfx_card.status.text() == "Blocked"
    assert "7.2.0-ogc4.1" in sidebar.gfx_card.detail.text()
    assert sidebar.gfx_primary_button.text() == "Install / update"
    assert not sidebar.gfx_primary_button.isEnabled()
    assert sidebar.gfx_secondary_button.text() == "Open upstream project"


@pytest.mark.parametrize("version_id", ("43", "44"))
def test_fedora_gfx1013_card_stays_visible(version_id):
    sidebar = _sidebar()
    state = _state("fedora", {})
    state.preparation_tools["version_id"] = version_id
    state.preparation_tools["gfx1013_compute"] = {
        "reason_key": "fedora-upstream-managed",
        "version_id": version_id,
    }

    sidebar.set_state(state)

    assert not sidebar.gfx_card.isHidden()
    assert not sidebar.fsr4_card.isHidden()


def test_bazzite_async_compute_card_exposes_reviewed_release_action():
    sidebar = _sidebar()
    state = _state(
        "bazzite",
        {"source_build_supported": True, "installer_available": True},
    )
    state.preparation_tools["gfx1013_compute"] = {
        "reason_key": "bazzite-release-managed",
        "direct_installer_allowed": True,
        "bazzite_async_installed": False,
    }
    sidebar.set_state(state)

    assert sidebar.gfx_card.scope.text() == "Bazzite 44 · Reviewed v0.2.4 release"
    assert sidebar.gfx_card.status.text() == "Bazzite release available"
    assert sidebar.gfx_primary_button.isEnabled()
    assert sidebar.gfx_primary_button.request_payload["action"] == "gfx1013_bazzite_install"


def test_manjaro_shows_the_abi_gated_fsr4_candidate():
    sidebar = _sidebar()
    sidebar.set_state(
        _state(
            "manjaro",
            {
                "precompiled_supported": False,
                "experimental_precompiled": True,
                "installer_available": True,
                "installed": False,
                "current": False,
                "state": "not-installed",
                "source_build_required": False,
            },
        )
    )

    assert all(
        not button.isEnabled()
        for button in (
            sidebar.cachyos_kernel_button,
            sidebar.cachyos_mesa_button,
            sidebar.cachyos_full_button,
        )
    )
    assert not sidebar.fsr4_card.isHidden()
    assert sidebar.fsr4_install_button.isEnabled()
    assert sidebar.fsr4_card.status.text() == "Experimental ABI check"


def test_installed_stack_changes_badges_and_buttons_to_repair_actions():
    sidebar = _sidebar()
    state = _state(
        "cachyos",
        {"precompiled_supported": True, "installed": True, "source_build_required": False},
    )
    state.preparation_tools["masta_bc250_stack"] = {
        "supported": True,
        "kernel_installed": True,
        "kernel_active": True,
        "mesa_installed": True,
    }
    state.preparation_tools["gfx1013_compute"] = {
        "reason_key": "arch-family-manual-untested",
        "masta_async_compute_ready": True,
    }
    sidebar.set_state(state)

    assert sidebar.cachyos_stack_card.status.text() == "Full stack installed"
    assert sidebar.cachyos_kernel_status.text() == "Active"
    assert sidebar.cachyos_mesa_status.text() == "Patched installed"
    assert "repair kernel" in sidebar.cachyos_kernel_button.text()
    assert "repair Mesa" in sidebar.cachyos_mesa_button.text()
    assert sidebar.gfx_card.status.text() == "Installed via MastaG"
    assert "No separate DryhoppedIPA installation" in sidebar.gfx_card.detail.text()
    assert sidebar.gfx_primary_button.text() == "View original GFX1013 project"
    assert sidebar.fsr4_remove_button.isVisibleTo(sidebar.fsr4_card)


def test_distribution_filter_defaults_to_detected_and_persists_last_choice():
    temporary = TemporaryDirectory()
    settings = QSettings(
        str(Path(temporary.name) / "compatibility.ini"),
        QSettings.Format.IniFormat,
    )
    first = PreparationSidebar(settings=settings)
    assert first.compatibility_filter.currentData() == "detected"
    assert not hasattr(first, "compatibility_detected_badge")
    assert first.compatibility_filter.sizePolicy().horizontalPolicy() == (
        QSizePolicy.Policy.Expanding
    )
    first.compatibility_filter.setCurrentIndex(
        first.compatibility_filter.findData("steamos")
    )

    second = PreparationSidebar(settings=settings)
    assert second.compatibility_filter.currentData() == "steamos"
    temporary.cleanup()


def test_cross_distribution_preview_never_enables_foreign_installers():
    sidebar = _sidebar()
    sidebar.set_state(
        _state(
            "bazzite",
            {"precompiled_supported": False, "installed": False, "source_build_required": True},
        )
    )
    sidebar.compatibility_filter.setCurrentIndex(
        sidebar.compatibility_filter.findData("steamos")
    )

    assert not sidebar.gfx_card.isHidden()
    assert sidebar.gfx_card.status.text() == "Preview only"
    assert not sidebar.gfx_primary_button.isEnabled()
    assert not sidebar.gfx_secondary_button.isEnabled()
    assert not sidebar.gfx_tertiary_button.isEnabled()
    assert sidebar.gfx_quaternary_button.isEnabled()
    assert sidebar.gfx_quaternary_button.text() == "Open upstream project"
