"""The Compatibility tab's hardware video card: one row, what it can do now."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from frontends.desktop.components.dashboard_widgets import PreparationSidebar


def _sidebar() -> PreparationSidebar:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    temporary = TemporaryDirectory()
    settings = QSettings(str(Path(temporary.name) / "vaapi.ini"), QSettings.Format.IniFormat)
    sidebar = PreparationSidebar(settings=settings, standalone=True)
    sidebar._test_settings_directory = temporary
    return sidebar


def _state(vaapi: dict) -> SimpleNamespace:
    return SimpleNamespace(
        preparation_tools={
            "os_id": "bazzite", "os_label": "Bazzite", "os_family": "bazzite",
            "prepare_components": {}, "vaapi_video": vaapi,
        },
        dependencies_ready=False, governor_tool_ready=False, cpu_tools_ready=False,
        core_unlock_ready=False, umr_ready=False, cu_manager_ready=False, nct_ready=False,
    )


def _shown(sidebar) -> list[str]:
    buttons = (sidebar.vaapi_install_button, sidebar.vaapi_test_button, sidebar.vaapi_remove_button)
    return [button.text() for button in buttons if not button.isHidden()]


def test_it_sits_in_compatibility_under_video():
    sidebar = _sidebar()
    groups = dict(sidebar.compatibility_groups)
    assert groups["Video"] == (sidebar.vaapi_card,)
    compatibility = sidebar.stack.widget(sidebar.tab_index("compatibility"))
    assert compatibility.isAncestorOf(sidebar.vaapi_card)


def test_not_installed_offers_the_install():
    sidebar = _sidebar()
    sidebar.set_state(_state({"supported": True, "state": "not-installed", "installed": False}))
    assert sidebar.vaapi_card.status.text() == "Not installed"
    assert _shown(sidebar) == ["Install"] and sidebar.vaapi_install_button.isEnabled()


def test_installed_waits_for_a_new_login_then_tests_and_removes():
    sidebar = _sidebar()
    sidebar.set_state(_state({"supported": True, "state": "relogin-required", "installed": True}))
    assert sidebar.vaapi_card.status.text() == "Log out to apply"
    assert _shown(sidebar) == ["Test", "Remove"]
    sidebar.set_state(_state({"supported": True, "state": "active", "installed": True}))
    assert sidebar.vaapi_card.status.text() == "Active"


def test_an_older_build_is_offered_the_update():
    sidebar = _sidebar()
    sidebar.set_state(_state({"supported": True, "state": "outdated", "installed": True}))
    assert _shown(sidebar) == ["Update", "Test", "Remove"]
    assert sidebar.vaapi_install_button.isEnabled()


def test_another_installer_and_unsupported_systems_cannot_install():
    sidebar = _sidebar()
    sidebar.set_state(_state({"supported": True, "state": "managed-elsewhere", "installed": False}))
    assert sidebar.vaapi_card.status.text() == "Managed externally"
    assert _shown(sidebar) == []
    sidebar.set_state(_state({
        "supported": False, "state": "not-installed", "installed": False,
        "blocked_reason": "The driver needs glibc 2.38 or newer; this system is older.",
    }))
    assert sidebar.vaapi_card.status.text() == "Not compatible"
    assert not sidebar.vaapi_install_button.isEnabled()
    assert "glibc 2.38" in sidebar.vaapi_card.detail.text()


def test_the_buttons_ask_for_the_workflows():
    sidebar = _sidebar()
    sidebar.set_state(_state({"supported": True, "state": "outdated", "installed": True}))
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    for button in (sidebar.vaapi_install_button, sidebar.vaapi_test_button,
                   sidebar.vaapi_remove_button, sidebar.vaapi_upstream_button):
        button.click()
    assert [item["action"] for item in requested] == [
        "vaapi_install", "vaapi_test", "vaapi_uninstall", "vaapi_upstream",
    ]


def test_flatpak_apps_are_offered_access_only_where_they_cannot_reach_the_driver():
    sidebar = _sidebar()
    base = {"supported": True, "state": "active", "installed": True}
    sidebar.set_state(_state({**base, "flatpak": {"available": True, "applied": False}}))
    assert not sidebar.vaapi_flatpak_button.isHidden()
    assert "Flatpak apps such as GPU Screen Recorder" in sidebar.vaapi_card.detail.text()
    sidebar.set_state(_state({**base, "flatpak": {"available": True, "applied": True}}))
    assert sidebar.vaapi_flatpak_button.isHidden()
    sidebar.set_state(_state({**base, "flatpak": {"available": False, "applied": False}}))
    assert sidebar.vaapi_flatpak_button.isHidden(), "no Flatpak on this system: nothing to allow"
    sidebar.set_state(_state({"supported": True, "state": "not-installed", "installed": False,
                              "flatpak": {"available": True, "applied": False}}))
    assert sidebar.vaapi_flatpak_button.isHidden(), "nothing to allow before the driver exists"


def test_flatpak_apps_are_offered_the_alias_even_when_they_were_already_allowed():
    """GPU Screen Recorder clears the driver name: without the alias it lists H.264 as unavailable."""
    sidebar = _sidebar()
    base = {"supported": True, "state": "active", "installed": True, "flatpak": {"available": True, "applied": True}}
    sidebar.set_state(_state({**base, "alias": False}))
    assert not sidebar.vaapi_flatpak_button.isHidden()
    sidebar.set_state(_state({**base, "alias": True}))
    assert sidebar.vaapi_flatpak_button.isHidden()


def test_the_32_bit_driver_is_offered_for_steam_remote_play_and_repaired_after_an_update():
    sidebar = _sidebar()
    base = {"supported": True, "state": "active", "installed": True}
    sidebar.set_state(_state({**base, "driver32": {"state": "not-installed"}}))
    assert not sidebar.vaapi_32_button.isHidden() and sidebar.vaapi_32_button.text() == "Add 32-bit driver"
    assert "Steam Remote Play" in sidebar.vaapi_card.detail.text()
    sidebar.set_state(_state({**base, "driver32": {"state": "needs-libs"}}))
    assert sidebar.vaapi_32_button.text() == "Repair 32-bit driver"
    assert "SteamOS update removed" in sidebar.vaapi_card.detail.text()
    for state in ("installed", "unsupported"):
        sidebar.set_state(_state({**base, "driver32": {"state": state}}))
        assert sidebar.vaapi_32_button.isHidden(), state
    sidebar.set_state(_state({"supported": True, "state": "not-installed", "installed": False,
                              "driver32": {"state": "not-installed"}}))
    assert sidebar.vaapi_32_button.isHidden(), "the 64-bit driver comes first"


def _mesa_state(mesa: dict) -> SimpleNamespace:
    state = _state({"supported": True, "state": "not-installed", "installed": False})
    state.preparation_tools["mesa_desktop"] = mesa
    return state


def test_the_mesa_card_offers_the_ppa_on_ubuntu():
    sidebar = _sidebar()
    sidebar.set_state(_mesa_state({"offered": True, "route": "ppa", "action": "mesa_ppa_install"}))
    assert not sidebar.mesa_card.isHidden()
    assert "kisak-mesa PPA" in sidebar.mesa_card.detail.text()
    assert not sidebar.mesa_button.isHidden() and sidebar.mesa_button.text() == "Update Mesa"
    assert sidebar.mesa_button.request_payload["action"] == "mesa_ppa_install"


def test_the_mesa_card_only_tells_fedora_to_upgrade_the_release():
    sidebar = _sidebar()
    sidebar.set_state(_mesa_state({"offered": True, "route": "release", "action": ""}))
    assert not sidebar.mesa_card.isHidden()
    assert "Fedora 44" in sidebar.mesa_card.detail.text()
    assert sidebar.mesa_button.isHidden(), "there is nothing to run: the release itself carries Mesa 26"


def test_the_mesa_card_reuses_the_debian_backports_action():
    sidebar = _sidebar()
    sidebar.set_state(_mesa_state({"offered": True, "route": "backports", "action": "debian_kernel_install"}))
    assert sidebar.mesa_button.text() == "Install from backports"
    assert sidebar.mesa_button.request_payload["action"] == "debian_kernel_install"
    assert "Debian backports" in sidebar.mesa_card.detail.text()


def test_the_mesa_card_stays_hidden_where_mesa_is_fine():
    sidebar = _sidebar()
    sidebar.set_state(_mesa_state({"offered": False, "route": "", "action": ""}))
    assert sidebar.mesa_card.isHidden()
    sidebar.set_state(_state({"supported": True, "state": "not-installed", "installed": False}))
    assert sidebar.mesa_card.isHidden()


def test_the_mesa_card_is_a_row_of_the_kernel_and_graphics_group_and_the_groups_keep_their_order():
    sidebar = _sidebar()
    sidebar.set_state(_mesa_state({"offered": True, "route": "ppa", "action": "mesa_ppa_install"}))
    assert sidebar.mesa_card.property("listRow") is True
    groups = {heading.text(): cards for heading, _box, cards in sidebar._compatibility_headings}
    assert groups["Kernel and graphics"][0] is sidebar.mesa_card
    layout = sidebar._compatibility_headings[0][0].parentWidget().layout()
    positions = [layout.indexOf(heading) for heading, _box, _cards in sidebar._compatibility_headings]
    assert positions == sorted(positions), "the groups sit on the page in the order they are declared"


def test_the_kernel_and_graphics_group_stays_when_the_mesa_row_is_hidden():
    sidebar = _sidebar()
    sidebar.set_state(_mesa_state({"offered": False, "route": "", "action": ""}))
    headings = {heading.text(): heading for heading, _box, _cards in sidebar._compatibility_headings}
    assert not headings["Kernel and graphics"].isHidden(), "the GFX1013 row is still there"
