from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

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


def test_cachyos_exposes_kernel_mesa_and_full_routes_but_not_fsr4_source_build():
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
    assert not sidebar.fsr4_install_button.isHidden()
    assert sidebar.fsr4_remove_button.isHidden()
    assert not sidebar.fsr4_upstream_button.isHidden()


def test_untested_abi_keeps_masta_actions_visible_but_safely_blocked():
    sidebar = _sidebar()
    sidebar.set_state(
        _state(
            "bazzite",
            {"precompiled_supported": False, "installed": False, "source_build_required": True},
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
    assert sidebar.fsr4_install_button.isHidden()
    assert sidebar.fsr4_remove_button.isHidden()
    assert not sidebar.fsr4_upstream_button.isHidden()


def test_manjaro_exposes_only_the_explicit_abi_gated_fsr4_candidate():
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
