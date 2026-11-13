"""The pacman lock row, MastaG's newer switches and packages, and the Cyan preset.

R-48d27e43 failed with "unable to lock database". MastaG's repository added
opt-in display fixes (CH7218 quirk and VRR, forced DSC, re-detect at boot),
bc250-dual-audio, linux-cachyos-bc250-meta and two more kernels; its README
recommends kernel-side Cyan settings on that kernel.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from frontends.desktop.components import (
    dashboard_widgets,  # noqa: F401 - import order of the mixins
    preparation_pages,
)


@pytest.fixture
def lock(monkeypatch):
    state = {"value": {"state": "free", "path": "/var/lib/pacman/db.lck", "holders": (), "from_previous_boot": False}}
    monkeypatch.setattr(preparation_pages, "PACMAN_LOCK_PROBE", lambda: state["value"])
    return state


def _page(qtbot):
    from frontends.desktop.pages.additional_settings import AdditionalSettingsPage

    page = AdditionalSettingsPage()
    qtbot.addWidget(page)
    return page


def test_the_row_sits_under_system_after_acpi(qtbot, lock):
    page = _page(qtbot)
    groups = dict(page.panel.compatibility_groups)
    assert groups["System"] == (page.panel.acpi_card, page.panel.pacman_lock_card)


@pytest.mark.parametrize("kind, status, release_visible", [
    ("stale", "Stuck", True),
    ("in-use", "In use", False),
    ("free", "Not locked", False),
])
def test_each_state_reads_as_it_should(qtbot, lock, kind, status, release_visible):
    page = _page(qtbot)
    lock["value"] = {"state": kind, "path": "/var/lib/pacman/db.lck",
                     "holders": ("pamac-daemon",) if kind == "in-use" else (), "from_previous_boot": False}
    page.panel.refresh_pacman_lock()
    card = page.panel.pacman_lock_card
    assert card.status.text() == status
    assert page.panel.pacman_unlock_button.isHidden() is (not release_visible)
    assert page.panel.pacman_lock_holders.isHidden() is (kind != "in-use")


def test_a_system_without_pacman_shows_no_row(qtbot, lock):
    page = _page(qtbot)
    lock["value"] = {"state": "not-applicable"}
    page.panel.refresh_pacman_lock()
    assert page.panel.pacman_lock_card.isHidden()


def test_opening_compatibility_while_locked_says_so(qtbot, lock, monkeypatch):
    from frontends.desktop.pages import additional_settings

    shown = []
    monkeypatch.setattr(additional_settings, "show_toast", lambda _anchor, title, message, tone: shown.append((title, tone)))
    page = _page(qtbot)
    lock["value"] = {"state": "stale", "path": "/var/lib/pacman/db.lck", "holders": (), "from_previous_boot": True}
    page.show()
    page.panel.select_tab(page.panel.TAB_KEYS.index("compatibility"))
    assert ("pacman is locked", "orange") in shown
    shown.clear()
    lock["value"] = {"state": "free", "path": "/var/lib/pacman/db.lck", "holders": (), "from_previous_boot": False}
    page.panel.select_tab(page.panel.TAB_KEYS.index("compatibility"))
    assert shown == []


def test_check_again_is_answered_in_place_and_release_goes_to_the_terminal(qtbot, lock):
    page = _page(qtbot)
    forwarded = []
    page.panel.dependency_action_requested.connect(forwarded.append)
    page.panel.pacman_check_button.click()
    assert forwarded == []
    lock["value"] = {"state": "stale", "path": "/var/lib/pacman/db.lck", "holders": (), "from_previous_boot": True}
    page.panel.refresh_pacman_lock()
    page.panel.pacman_unlock_button.click()
    assert forwarded and forwarded[-1]["action"] == "pacman-unlock"


def test_the_new_kernel_switches_are_offered_as_rows():
    from bc250cc.infrastructure import system_setup
    from frontends.desktop.components.dashboard_widgets import PreparationSidebar

    rows = {option for option, *_ in PreparationSidebar.KERNEL_OPTION_ROWS}
    for option in (system_setup.CH7218_QUIRK_OPTION, system_setup.CH7218_VRR_OPTION,
                   system_setup.PCON_FORCE_DSC_OPTION, system_setup.RELINK_AT_BOOT_OPTION):
        assert option in rows and option in system_setup.KERNEL_OPTIONS
        # Offered only where the running kernel has the parameter.
        assert option in PreparationSidebar.KERNEL_PARAMETER_OPTIONS


def test_the_helper_accepts_exactly_the_same_switches():
    import importlib.util
    import sys
    from pathlib import Path

    lib = Path("privileged/lib")
    sys.path.insert(0, str(lib))
    try:
        spec = importlib.util.spec_from_file_location("kernel_args_under_test", lib / "system_setup_kernel_args.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(lib))
    from bc250cc.infrastructure.system_setup import KERNEL_OPTIONS

    assert set(module.ARGUMENTS) == set(KERNEL_OPTIONS)
    assert module.KERNEL_PARAMETERS["amdgpu.bc250_ch7218_quirk=1"] == "bc250_ch7218_quirk"
    assert module.KERNEL_PARAMETERS["amdgpu.cs_relink_at_boot=1"] == "cs_relink_at_boot"


def test_masta_dual_audio_waits_for_the_apps_own_5_1_output(qtbot, lock):
    page = _page(qtbot)
    tools = {
        "masta_bc250_stack": {"supported": True, "extras_installed": {}, "variants_installed": {}},
        "accessories": {"hdmi_ac3": {"state": "active"}},
    }
    page.panel.set_state(SimpleNamespace(preparation_tools=tools))
    assert not page.panel.cachyos_dual_audio_button.isEnabled()
    tools["accessories"] = {"hdmi_ac3": {"state": "not-installed"}}
    page.panel.set_state(SimpleNamespace(preparation_tools=tools))
    assert page.panel.cachyos_dual_audio_button.isEnabled()


def test_the_apps_5_1_output_and_tv_control_step_aside_for_mastag_packages(tmp_path, monkeypatch):
    from bc250cc.infrastructure.accessories import hdmi_ac3, hdmi_cec

    assert any("bc250-dual-audio" in str(path) for path in hdmi_ac3.FOREIGN_SYSTEM)
    conf = tmp_path / "bc250-cec.conf"
    monkeypatch.setattr(hdmi_cec, "FOREIGN_CEC", (conf,))
    assert hdmi_cec.foreign_cec() is False
    conf.write_text("")
    assert hdmi_cec.foreign_cec() is True


def test_the_bc250_kernel_preset_stages_upstreams_cyan_settings(qtbot, monkeypatch):
    from frontends.desktop.pages import gpu_governor_view as view_module

    monkeypatch.setattr(view_module, "_running_bc250_kernel", lambda: True)
    view = view_module.GpuGovernorView()
    qtbot.addWidget(view)
    state = view_module.GpuViewState(bc250_kernel=True, set_method="smu", usage_method="busy-flag",
                                     fix_metrics=True, fix_frequency=False, temp_read="drm")
    view._sync_compatibility(state)
    assert not view._bc250_kernel_row.isHidden()
    view._stage_bc250_kernel_settings()
    options = view.compatibility_options()
    assert options["set_method"] == "kernel" and options["usage_method"] == "kernel"
    assert options["metrics"] is False and options["frequencies"] is False
    assert options["temp_read"] in {"sysfs", None}
