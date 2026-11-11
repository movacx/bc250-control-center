"""The main kernel boot options are managed end to end: the helper's list, the
request builder and a row in Additional settings for each of them."""

from bc250cc.infrastructure.system_setup import CU_UNLOCK_OPTION, HIDE_BOOT_MESSAGES_OPTION, KERNEL_OPTIONS
from frontends.desktop.components.dashboard_widgets import PreparationSidebar

MAIN = ("mitigations=off", "nosmt", CU_UNLOCK_OPTION, HIDE_BOOT_MESSAGES_OPTION)


def test_every_managed_option_has_a_row_and_the_rows_add_nothing_unmanaged():
    rows = [option for option, *_ in PreparationSidebar.KERNEL_OPTION_ROWS]
    assert set(rows) == set(KERNEL_OPTIONS)
    assert len(rows) == len(set(rows))


def test_the_main_options_are_among_the_managed_ones():
    assert set(MAIN) <= set(KERNEL_OPTIONS)


def test_each_row_names_what_it_does_and_what_undoes_it():
    for option, title, apply_text, restore_text in PreparationSidebar.KERNEL_OPTION_ROWS:
        assert title.strip() and apply_text.strip() and restore_text.strip(), option
        assert apply_text != restore_text, option


# ------------------------------------------- the BC-250 kernel's amdgpu switches

import pytest

from bc250cc.infrastructure.system_setup import HDMI21_OFF_OPTION, RELINK_OFF_OPTION, SCHED_POLICY_OPTION
from frontends.desktop.pages.additional_settings import AdditionalSettingsPage

OFF = {"managed": False, "configured": False, "active": False, "external": False}
NEW = (SCHED_POLICY_OPTION, HDMI21_OFF_OPTION, RELINK_OFF_OPTION)


def _tools(supported=(), items=None, allowed=None):
    arguments = {option: dict(OFF) for option in KERNEL_OPTIONS}
    arguments.update(items or {})
    state = {
        "available": True, "arguments": arguments,
        "cu_unlock": {"supported": False, "mode": ""},
        "parameters": {option: {"supported": option in supported} for option in (HDMI21_OFF_OPTION, RELINK_OFF_OPTION)},
    }
    if allowed is not None:
        state["allowed"] = allowed
    return {"system_setup": {"helper_available": True, "kernel_options": state}}


def _panel(qtbot):
    page = AdditionalSettingsPage()
    qtbot.addWidget(page)
    page.resize(1200, 900)
    page.show()
    page.panel._page = page
    return page.panel


def test_the_new_options_are_managed_and_drawn_plainly():
    for option in NEW:
        assert option in KERNEL_OPTIONS
        assert option in PreparationSidebar.KERNEL_OPTION_NEUTRAL


def test_the_scheduler_row_is_always_offered_where_the_boot_menu_takes_it(qtbot):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(_tools())
    name, _pill, button = panel.kernel_option_controls[SCHED_POLICY_OPTION]
    assert not name.isHidden() and not button.isHidden()
    assert button.text() == "Use non-HWS scheduling"


@pytest.mark.parametrize("option", [HDMI21_OFF_OPTION, RELINK_OFF_OPTION])
def test_a_bc250_kernel_switch_shows_only_where_the_kernel_has_it(qtbot, option):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(_tools())
    name, _pill, button = panel.kernel_option_controls[option]
    assert name.isHidden() and button.isHidden()
    panel._update_kernel_options_control(_tools(supported=(option,)))
    assert not name.isHidden() and not button.isHidden()


@pytest.mark.parametrize("option", [HDMI21_OFF_OPTION, RELINK_OFF_OPTION])
def test_a_staged_switch_stays_so_it_can_be_taken_back(qtbot, option):
    panel = _panel(qtbot)
    staged = {option: {"managed": True, "configured": True, "active": False, "external": False}}
    panel._update_kernel_options_control(_tools(items=staged))
    _name, _pill, button = panel.kernel_option_controls[option]
    assert not button.isHidden()
    assert button.text() in {"Turn HDMI 2.1 on", "Turn recovery on"}


def test_a_boot_menu_that_does_not_take_them_does_not_show_the_rows(qtbot):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(
        _tools(supported=NEW, allowed=["mitigations=off", "nosmt", "loglevel=0"])
    )
    for option in NEW:
        name, _pill, button = panel.kernel_option_controls[option]
        assert name.isHidden() and button.isHidden(), option


def test_choosing_a_row_asks_for_that_option_and_taking_it_back_asks_for_none(qtbot):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(_tools(supported=NEW))
    requests = []
    panel.dependency_action_requested.connect(requests.append)
    panel.kernel_option_controls[SCHED_POLICY_OPTION][2].click()
    assert requests[-1]["kernel_options"] == [SCHED_POLICY_OPTION]
    assert requests[-1]["kernel_option_changed"] == SCHED_POLICY_OPTION
    panel._update_kernel_options_control(_tools(
        supported=NEW,
        items={SCHED_POLICY_OPTION: {"managed": True, "configured": True, "active": False, "external": False}},
    ))
    panel.kernel_option_controls[SCHED_POLICY_OPTION][2].click()
    assert requests[-1]["kernel_options"] == []


# ------------------------------------------------ MastaG's optional extras


def _stack_state(extras):
    from types import SimpleNamespace

    return SimpleNamespace(
        preparation_tools={
            "os_id": "cachyos", "os_label": "CachyOS", "os_family": "arch", "prepare_components": {},
            "masta_bc250_stack": {
                "supported": True, "repository_configured": True, "kernel_release": "7.3.3-cachyos-bc250",
                "kernel_is_bc250": True, "kernel_fallbacks": [], "proton_installed": {},
                "extras_installed": extras, "kernel_installed": True, "kernel_active": True,
                "kernel_variant": "stable", "mesa_installed": True,
            },
        },
        dependencies_ready=False, governor_tool_ready=False, cpu_tools_ready=False,
        core_unlock_ready=False, umr_ready=False, cu_manager_ready=False, nct_ready=False,
    )


def _sidebar(qtbot):
    from PyQt6.QtCore import QSettings
    from tempfile import TemporaryDirectory
    from pathlib import Path

    temporary = TemporaryDirectory()
    _KEEP.append(temporary)
    sidebar = PreparationSidebar(
        settings=QSettings(str(Path(temporary.name) / "s.ini"), QSettings.Format.IniFormat), standalone=True
    )
    qtbot.addWidget(sidebar)
    sidebar.resize(1200, 900)
    sidebar.show()
    return sidebar


_KEEP = []


def test_an_extra_that_is_not_installed_offers_its_install_and_hides_its_removal(qtbot):
    sidebar = _sidebar(qtbot)
    sidebar.set_state(_stack_state({"fixes": False, "paccache": False}))
    assert not sidebar.cachyos_fixes_button.isHidden() and sidebar.cachyos_fixes_remove_button.isHidden()
    assert not sidebar.cachyos_paccache_button.isHidden() and sidebar.cachyos_paccache_remove_button.isHidden()
    assert sidebar.cachyos_fixes_button.request_payload["action"] == "cachyos_bc250_extra-fixes"
    assert sidebar.cachyos_paccache_button.request_payload["action"] == "cachyos_bc250_extra-paccache"


def test_an_installed_extra_offers_its_removal_instead(qtbot):
    sidebar = _sidebar(qtbot)
    sidebar.set_state(_stack_state({"fixes": True, "paccache": False}))
    assert sidebar.cachyos_fixes_button.isHidden() and not sidebar.cachyos_fixes_remove_button.isHidden()
    assert sidebar.cachyos_fixes_remove_button.request_payload["action"] == "cachyos_bc250_remove-extra-fixes"
    assert not sidebar.cachyos_paccache_button.isHidden()


def test_the_adapter_firmware_files_are_offered_and_flashing_is_not(qtbot):
    sidebar = _sidebar(qtbot)
    sidebar.set_state(_stack_state({"fixes": False, "paccache": False, "ch7218": False}))
    button = sidebar.cachyos_ch7218_button
    assert not button.isHidden() and sidebar.cachyos_ch7218_remove_button.isHidden()
    assert button.request_payload["action"] == "cachyos_bc250_extra-ch7218"
    from bc250cc.infrastructure.cachyos_bc250_kernel import build_cachyos_bc250_kernel_command

    script = build_cachyos_bc250_kernel_command("extra-ch7218")
    assert "bc250-cachyos/bc250-ch7218-fw" in script
    assert "flash" not in script.lower().replace("bc250-ch7218-fw", "")
