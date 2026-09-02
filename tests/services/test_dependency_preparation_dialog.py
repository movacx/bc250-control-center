import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QPushButton, QScrollArea

from frontends.desktop.i18n import tr
from frontends.desktop.pages.gpu_governor import DependencyPreparationDialog


def _tools():
    return {
        "os_id": "linuxmint",
        "os_label": "Linux Mint 22.3",
        "os_family": "debian",
        "os_immutable": False,
        "supported_gpu_governors": {
            "cyan-skillfish-governor-smu": {
                "detected": True,
                "active": True,
                "enabled": True,
            },
            "oberon-governor": {
                "detected": False,
                "active": False,
                "enabled": False,
            },
        },
    }


def _button(dialog, text):
    return next(button for button in dialog.findChildren(QPushButton) if button.text() == text)


def test_dependency_dialog_exposes_automatic_and_both_governors(qtbot):
    dialog = DependencyPreparationDialog(_tools(), "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    assert set(dialog.governor_cards) == {
        "cyan-skillfish-governor-smu",
        "oberon-governor",
    }
    assert _button(dialog, "Prepare selected (2)").isEnabled()
    assert len(dialog.component_switches) == 7
    assert dialog.component_switches["runtime"].isChecked()
    assert not dialog.component_switches["runtime"].isEnabled()
    assert dialog.component_switches["governor"].isChecked()
    assert not dialog.component_switches["umr"].isChecked()
    assert not dialog.component_switches["cu_manager"].isChecked()
    assert "large LLVM toolchain" in dialog.component_switches["umr"].toolTip()
    uninstall_buttons = [
        button for button in dialog.findChildren(QPushButton)
        if button.text() == "Uninstall"
    ]
    assert len(uninstall_buttons) == 2
    assert [button.isEnabled() for button in uninstall_buttons] == [True, False]


def test_dependency_dialog_uses_the_application_frameless_modal_card(qtbot):
    dialog = DependencyPreparationDialog(_tools(), "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert any(
        frame.objectName() == "ControlDialogCard"
        for frame in dialog.findChildren(QFrame)
    )
    assert dialog.findChild(QScrollArea) is not None


def test_dependency_dialog_returns_only_selected_components(qtbot):
    dialog = DependencyPreparationDialog(_tools(), "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    dialog.component_switches["cpu_oc"].setChecked(True)
    dialog.component_switches["umr"].setChecked(True)
    _button(dialog, "Prepare selected (4)").click()

    assert dialog.action == "prepare"
    assert dialog.selected_components == {"runtime", "governor", "cpu_oc", "umr"}
    assert any(
        button.objectName() == "DialogClose"
        for button in dialog.findChildren(QPushButton)
    )


def test_dependency_dialog_separates_components_from_advanced_tools(qtbot):
    dialog = DependencyPreparationDialog(_tools(), "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    assert dialog.section_stack.currentIndex() == 0
    _button(dialog, "Compatibility and governors").click()
    assert dialog.section_stack.currentIndex() == 1
    assert dialog.section_buttons[1].isChecked()


def test_dependency_dialog_places_drivers_in_its_own_tab(qtbot):
    dialog = DependencyPreparationDialog(_tools(), "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    _button(dialog, "Drivers").click()

    assert dialog.section_keys[-1] == "drivers"
    assert dialog.section_stack.currentIndex() == len(dialog.section_keys) - 1


def test_dependency_dialog_places_memory_policy_in_components_and_ttm_in_gpu(qtbot):
    tools = _tools()
    tools["memory_runtime"] = {
        "zram_active": True,
        "zram_total_bytes": 8 * 1024 ** 3,
        "zswap_enabled": False,
        "backing_swap_active": False,
        "ttm_limit_bytes": 12 * 1024 ** 3,
    }
    dialog = DependencyPreparationDialog(tools, "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    assert [dialog.memory_policy_combo.itemData(index) for index in range(4)] == [
        "preserve", "swap-16", "swap-32", "zram",
    ]
    assert dialog.ttm_limit_combo.currentData() == 12
    assert [dialog.ttm_limit_combo.itemData(index) for index in range(5)] == [0, -1, 8, 10, 12]
    assert dialog.action == ""


@pytest.mark.parametrize("family,label", [("steamos", "SteamOS"), ("bazzite", "Bazzite"), ("cachyos", "CachyOS")])
def test_dependency_dialog_shows_optional_quick_access_on_game_mode_families(qtbot, family, label):
    tools = _tools()
    tools.update({
        "os_family": family,
        "os_label": label,
        "quick_access": {"supported": True, "decky_detected": False, "ready": False},
    })
    dialog = DependencyPreparationDialog(tools, "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    _button(dialog, "Decky Loader").click()

    assert dialog.section_stack.currentIndex() == 2
    _button(dialog, "Install Decky + Quick Access (Beta)").click()
    assert dialog.action == "quick_access_install_decky"


def test_dependency_dialog_offers_explicit_decky_install_on_generic_systemd(qtbot):
    tools = _tools()
    tools["quick_access"] = {
        "supported": True,
        "init_system": "systemd",
        "decky_detected": False,
        "ready": False,
    }
    dialog = DependencyPreparationDialog(tools, "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    _button(dialog, "Decky Loader").click()
    _button(dialog, "Install Decky + Quick Access (Beta)").click()

    assert dialog.action == "quick_access_install_decky"


def test_dependency_dialog_updates_decky_when_the_detected_frontend_is_incompatible(
    qtbot,
):
    tools = _tools()
    tools.update({
        "os_family": "steamos",
        "os_label": "SteamOS",
        "quick_access": {
            "supported": True,
            "decky_detected": True,
            "decky_frontend_compatible": False,
            "ready": False,
        },
    })
    dialog = DependencyPreparationDialog(tools, "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    _button(dialog, "Decky Loader").click()
    _button(dialog, "Install Decky + Quick Access (Beta)").click()

    assert dialog.action == "quick_access_install_decky"


def test_dependency_dialog_exposes_cachyos_kernel_as_an_explicit_action(qtbot):
    tools = _tools()
    tools.update({
        "os_id": "cachyos",
        "os_family": "cachyos",
        "os_label": "CachyOS",
        "masta_bc250_stack_supported": True,
    })
    dialog = DependencyPreparationDialog(tools, "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    _button(dialog, "Compatibility and governors").click()
    _button(dialog, "Install BC-250 kernel").click()

    assert dialog.action == "cachyos_bc250_kernel"


@pytest.mark.parametrize(
    ("os_id", "family"),
    (("manjaro", "manjaro"), ("endeavouros", "arch"), ("artix", "arch"), ("fedora", "fedora")),
)
def test_dependency_dialog_blocks_masta_kernel_on_unqualified_hosts(
    qtbot, os_id, family
):
    tools = _tools()
    tools.update({
        "os_id": os_id,
        "os_family": family,
        "os_label": os_id,
        "masta_bc250_stack_supported": False,
    })
    dialog = DependencyPreparationDialog(tools, "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    button = _button(dialog, "Install BC-250 kernel")
    assert not button.isEnabled()
    assert "Arch Linux or CachyOS" in button.toolTip()


def test_40cu_selection_keeps_umr_dependency_consistent(qtbot):
    dialog = DependencyPreparationDialog(_tools(), "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    dialog.component_switches["umr"].setChecked(False)
    assert not dialog.component_switches["cu_manager"].isChecked()

    dialog.component_switches["cu_manager"].setChecked(True)
    assert dialog.component_switches["umr"].isChecked()


def test_gfx1013_card_routes_only_explicit_steamos_actions(qtbot):
    tools = _tools()
    tools["gfx1013_compute"] = {
        "reason_key": "steamos-dedicated-backend",
        "steamos_kernel_ready": False,
    }
    dialog = DependencyPreparationDialog(tools, "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    _button(dialog, "1 · Install SteamOS kernel").click()

    assert dialog.action == "steamos_compat"


def test_gfx1013_card_enables_radv_only_when_kernel_is_ready(qtbot):
    tools = _tools()
    tools["gfx1013_compute"] = {
        "reason_key": "steamos-dedicated-backend",
        "steamos_kernel_ready": True,
    }
    dialog = DependencyPreparationDialog(tools, "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    assert _button(dialog, "Update / repair SteamOS kernel").isEnabled()
    assert _button(dialog, "2 · Install / repair Mesa RADV").isEnabled()


def test_gfx1013_card_exposes_combined_official_upstream_install_on_fedora(qtbot):
    tools = _tools()
    tools["gfx1013_compute"] = {
        "reason_key": "fedora-upstream-managed",
        "exact_upstream_validated_host": True,
        "dryhopped_installed": False,
    }
    dialog = DependencyPreparationDialog(tools, "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    install_buttons = [
        button for button in dialog.findChildren(QPushButton)
        if button.text() == "Install / update"
        and bool(button.property("dependencyGfxPrimary"))
    ]
    assert len(install_buttons) == 1
    install_buttons[0].click()

    assert dialog.action == "gfx1013_fedora_install"


def test_gfx1013_card_keeps_bazzite_install_disabled_on_old_kernel(qtbot):
    tools = _tools()
    tools["gfx1013_compute"] = {
        "reason_key": "bazzite-release-kernel-unsupported",
        "direct_installer_allowed": False,
    }
    dialog = DependencyPreparationDialog(tools, "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    gfx_install = [
        button for button in dialog.findChildren(QPushButton)
        if button.text() == "Install / update"
        and bool(button.property("dependencyGfxPrimary"))
    ]
    assert len(gfx_install) == 1
    assert not gfx_install[0].isEnabled()


def test_gfx1013_card_routes_reviewed_bazzite_release(qtbot):
    tools = _tools()
    tools["gfx1013_compute"] = {
        "reason_key": "bazzite-release-managed",
        "direct_installer_allowed": True,
        "bazzite_async_installed": False,
    }
    dialog = DependencyPreparationDialog(tools, "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    install = next(
        button for button in dialog.findChildren(QPushButton)
        if button.text() == "Install / update"
        and bool(button.property("dependencyGfxPrimary"))
    )
    assert install.isEnabled()
    install.click()
    assert dialog.action == "gfx1013_bazzite_install"


def present_gfx_install_buttons(dialog):
    return sum(
        button.text() == "Install / update"
        for button in dialog.findChildren(QPushButton)
    )


def test_dependency_dialog_returns_explicit_oberon_choice(qtbot):
    dialog = DependencyPreparationDialog(_tools(), "cyan-skillfish-governor-smu")
    qtbot.addWidget(dialog)

    install_buttons = [
        button for button in dialog.findChildren(QPushButton)
        if button.text() == "Install / update"
    ]
    install_buttons[1].click()

    assert dialog.action == "prepare"
    assert dialog.governor == "oberon-governor"


def test_dependency_menu_copy_is_translated_in_every_supported_language():
    copy = (
        "Prepare BC250 system",
        "Install what you need and choose the features you want to use.",
        "Detected system: {distribution}",
        "Choose automatic setup or manage one supported GPU governor.",
        "Automatic setup",
        "Components",
        "Compatibility and governors",
        "Game Mode Quick Access (Beta)",
        "Optional Game Mode controls for safe live GPU, CU, system-fan and saved CPU-profile actions.",
        "Decky detected",
        "Decky not installed",
        "Install Decky + Quick Access (Beta)",
        "Install / repair BC250 Quick Access",
        "Could not prepare Game Mode Quick Access",
        "Beta boundary: after your explicit confirmation in this dialog, this workflow downloads the official Decky stable installer, displays its SHA-256 in the terminal, then installs the local BC250 panel. It never changes GPU voltage, custom clocks, services, boot settings or hardware state.",
        "Decky Loader is an external third-party root-plugin service. This Beta workflow downloads its official stable installer to a temporary file and displays its SHA-256 in the terminal before it runs. Your confirmation in this dialog authorizes that explicit action. BC250 then installs only its local Quick Access panel. Continue?",
        "Bazzite installs Decky through its native ujust setup-decky install workflow. BC250 then installs only its local Quick Access panel. Continue?",
        "Opened the explicit Game Mode Quick Access Beta workflow. Review the terminal output, then restart Game Mode after the official Decky installer and local BC250 panel finish successfully.",
        "Open native SteamOS diagnostics",
        "Kernel partial",
        "D-Bus · BC250 telemetry",
        "YAML · alternative backend",
        "Check SteamOS compatibility",
        "Prepare SteamOS compatibility",
        "Open upstream project",
        "A reboot may be required.",
        "Unavailable on the detected system.",
        "Already prepared; selecting it checks for updates and repairs missing files.",
        "{component} · Ready",
        "Prepare selected",
        "Install / update",
        "Uninstall",
        "Only one GPU governor can be enabled at a time. Preparing another governor will ask before stopping the active one.",
    )
    for language in ("es", "pt", "ru", "uk", "de", "pl"):
        assert all(tr(text, language) != text for text in copy), language


def test_memory_policy_preview_copy_is_translated_in_every_supported_language():
    copy = (
        "Memory and swap",
        "Preview only",
        "Keep current configuration",
        "ZRAM (compressed RAM)",
        "ZSWAP + 16 GiB swapfile",
        "ZSWAP + 32 GiB swapfile",
        "Review requirements",
        "Memory configuration preview",
        "No swap, boot or kernel setting will be changed.",
        "GPU memory limit (TTM)",
        "TTM limits managed GPU pages; it is not a guaranteed VRAM reservation.",
        "GPU memory limit preview",
    )
    for language in ("es", "pt", "ru", "uk", "de", "pl"):
        assert all(tr(text, language) != text for text in copy), language


def test_bazzite_memory_card_copy_is_translated_in_every_supported_language():
    copy = (
        "Memory & Swap",
        "Swap and compression",
        "Keep Bazzite default (ZRAM)",
        "Recommended · ZSWAP + 16 GiB swapfile",
        "Keep current TTM limit",
        "Dynamic GPU Memory Limit (TTM)",
        "Apply Swap",
        "Apply TTM",
        "Open safe memory setup",
    )
    for language in ("es", "pt", "ru", "uk", "de", "pl"):
        assert all(tr(text, language) != text for text in copy), language
