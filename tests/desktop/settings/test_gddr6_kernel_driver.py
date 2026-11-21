"""The bc250_memory driver: one boot option, offered in Settings and in Compatibility."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from bc250cc.infrastructure.system_setup import KERNEL_OPTIONS, MEMORY_SENSOR_OPTION
from frontends.desktop.components.dashboard_widgets import PreparationSidebar
from frontends.desktop.i18n import tr
from frontends.desktop.pages.settings import SettingsPage


class _Service:
    def read_local_config(self):
        return {"gpu_governor": "auto"}


class _Activity:
    def clear(self):
        return True


def _settings(qtbot, tmp_path):
    page = SettingsPage(object(), settings_service=_Service(), activity_service=_Activity(),
                        app_settings=QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(page)
    page._ensure_section("telemetry")
    return page


def _setup(*, supported=True, managed=False, active=False, loaded=False):
    return {
        "helper_available": True,
        "kernel_options": {
            "available": True,
            "allowed": list(KERNEL_OPTIONS),
            "arguments": {MEMORY_SENSOR_OPTION: {"managed": managed, "active": active,
                                                 "configured": managed, "external": False}},
            "parameters": {MEMORY_SENSOR_OPTION: {"supported": supported, "loaded": loaded}},
        },
    }


def test_the_option_is_a_managed_kernel_boot_option():
    assert MEMORY_SENSOR_OPTION == "modules-load=bc250_memory" and MEMORY_SENSOR_OPTION in KERNEL_OPTIONS


def test_settings_says_where_the_driver_stands_and_offers_the_switch(qtbot, tmp_path):
    page = _settings(qtbot, tmp_path)
    page._apply_gddr6_kernel_driver(_setup())
    assert page.gddr6_kernel_state.text() == tr("Off") and page.gddr6_kernel_button.isEnabled()
    page._apply_gddr6_kernel_driver(_setup(managed=True))
    assert page.gddr6_kernel_state.text() == tr("Loads at the next boot")
    assert page.gddr6_kernel_button.text() == tr("Stop loading at boot")
    page._apply_gddr6_kernel_driver(_setup(managed=True, active=True))
    assert page.gddr6_kernel_state.text() == tr("Loads at every boot")
    page._apply_gddr6_kernel_driver(_setup(supported=False))
    assert not page.gddr6_kernel_button.isEnabled()
    requested = []
    page.kernel_option_requested.connect(requested.append)
    page._apply_gddr6_kernel_driver(_setup())
    page.gddr6_kernel_button.click()
    assert requested == [MEMORY_SENSOR_OPTION]


def test_compatibility_lists_it_only_where_the_kernel_ships_it(qtbot):
    sidebar = PreparationSidebar()
    qtbot.addWidget(sidebar)
    name, _pill, button = sidebar.kernel_option_controls[MEMORY_SENSOR_OPTION]
    sidebar._update_kernel_options_control({"system_setup": _setup(supported=False)})
    assert name.isHidden()
    sidebar._update_kernel_options_control({"system_setup": _setup(supported=True)})
    assert not name.isHidden() and button.text() == tr("Load at boot")
