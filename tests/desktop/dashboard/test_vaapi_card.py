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
