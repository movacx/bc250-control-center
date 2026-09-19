from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from frontends.desktop.app import ControlCenterWindow
from frontends.desktop.components.sidebar import Sidebar
from frontends.desktop.core.state import DashboardState
from frontends.desktop.i18n import (
    SUPPORTED_LANGUAGES,
    localize_widget_tree,
    set_language,
    tr,
)
from frontends.desktop.pages.cpu_smu import CpuSmuPage
from frontends.desktop.pages.dashboard import DashboardPage
from frontends.desktop.pages.fans import FansPage
from frontends.desktop.theme import application_stylesheet


def test_dashboard_buttons_emit_navigation_not_hardware_operations(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    actions = []
    modules = []
    page.action_requested.connect(actions.append)
    page.module_requested.connect(modules.append)
    for card in (page.cpu_card, page.fan_card):
        for button in card.action_buttons:
            button.click()
    page.footer.repositories_button.click()
    page.gpu_card.action_buttons[1].click()
    # The CPU module is one workspace now, so it offers one way in.
    assert actions == ["cpu_configuration", "fans_manual", "fans_curve", "repositories"]
    assert modules == ["cu"]
    # No panel wears a state badge: the readings underneath carry it, and the
    # board's own state is in the header.
    assert page.cpu_card.status.isHidden()
    assert page.readiness.status.isHidden()
    assert page.gpu_card.details["governor"].label.text() != ""
    # Live readings belong to the sensor boards; the evidence panel keeps the
    # configuration the user asked for.
    # Every live reading is in the panel that owns the hardware.
    assert page.gpu_card.isAncestorOf(page.gpu_card.details)
    assert page.gpu_card.isAncestorOf(page.gpu_card.headline)


def test_gpu_configuration_shows_the_live_gpu_voltage_sensor(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(DashboardState(cpu_voltage_mv=1206, gpu_voltage_mv=799))
    page.resize(1180, 900)
    page.show()
    qtbot.wait(50)
    voltage = page.gpu_card.details["voltage"]
    assert voltage.label.text() == tr("GPU voltage")
    assert voltage.value.text() == "0.799"
    assert voltage.unit.text() == "V"


def test_dashboard_labels_corrupt_eight_core_telemetry_as_invalid(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(
        DashboardState(
            gpu_state_available=True,
            governor_running=True,
            governor_frequency_mhz=1000,
            gpu_telemetry_invalid=True,
            gpu_metrics_layout_mismatch=True,
        )
    )

    assert page.gpu_card.details["temperature"].value.text() == tr("Invalid")
    assert page.gpu_card.details["voltage"].value.text() == tr("Invalid")
    assert page.gpu_card.details["mclk"].value.text() == tr("Invalid")
    assert page.gpu_card.status.text() == "running"
    assert page.gpu_card.details["voltage"].toolTip() == tr(
        "Advanced GPU diagnostics"
    )


def test_eight_core_layout_mismatch_exposes_the_boot_repair(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(
        DashboardState(
            gpu_state_available=True,
            governor_running=True,
            gpu_metrics_layout_mismatch=True,
            gpu_telemetry_repair_available=True,
            gpu_telemetry_repair_pending=False,
        )
    )

    assert not page.telemetry_repair_button.isHidden()
    assert page.telemetry_repair_button.isEnabled()
    assert page.telemetry_repair_button.text() == tr("Repair BC250 telemetry")


def test_eight_core_telemetry_repair_pending_reboot_disables_the_button(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(
        DashboardState(
            gpu_state_available=True,
            governor_running=True,
            gpu_metrics_layout_mismatch=False,
            gpu_telemetry_repair_pending=True,
        )
    )

    assert not page.telemetry_repair_button.isHidden()
    assert not page.telemetry_repair_button.isEnabled()
    assert page.telemetry_repair_button.text() == tr(
        "Restart to finish telemetry repair"
    )


def test_eight_core_telemetry_button_click_requests_repair_without_a_dialog(qtbot):
    # A bare object() cannot take attributes, so the double needs a __dict__.
    class _Controller:
        pass

    page = DashboardPage(_Controller())
    qtbot.addWidget(page)
    page.apply_state(DashboardState(gpu_metrics_layout_mismatch=True))
    calls = []
    page.controller.reparar_telemetria_8core = lambda: calls.append(True)

    page.telemetry_repair_button.click()

    assert calls == [True]


def test_the_graphics_panel_lists_its_clock_domains(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(
        DashboardState(
            gpu_power_w=41.2,
            gpu_memory_frequency_mhz=450,
            gpu_gtt_used_bytes=249_376_768,
            gpu_gtt_total_bytes=5_587_288_064,
            nvme_temperature_c=43.85,
            nvme_hotspot_temperature_c=68.85,
        )
    )
    page.resize(1180, 900)
    page.show()
    qtbot.wait(50)

    details = page.gpu_card.details
    assert details["mclk"].value.text() == "450"
    assert details["mclk"].unit.text() == "MHz"
    # This payload carries neither of the other two clock domains.
    assert details["socclk"].value.text() == tr("Not detected")
    assert details["fclk"].value.text() == tr("Not detected")
    assert details["gtt"].value.text() == "238"
    assert details["gtt"].unit.text() == "MB"
    assert details["gtt"].detail.text() == "/ 5.2 GB"
    assert "dpm" not in details.readings
    assert details["power"].value.text() == "41"
    assert page.gpu_card.headline.y() < details.y()
    # The drive is reported by the cooling card, not by the graphics row.
    assert page.fan_card.details["nvme"].value.text() == "43.9"


def test_shortcuts_select_the_requested_tab_even_after_visiting_the_other(qtbot):
    cpu, fans = CpuSmuPage(object()), FansPage(object())
    qtbot.addWidget(cpu)
    qtbot.addWidget(fans)
    visited = []
    window = SimpleNamespace(cpu_page=cpu, fans_page=fans, navigate=visited.append)
    for action in ("cpu_overview", "cpu_configuration", "fans_curve", "fans_manual"):
        ControlCenterWindow._dashboard_action(window, action)
    assert visited == ["cpu", "cpu", "fans", "fans"]
    assert cpu.workspace_tab_buttons["configuration"].isChecked()
    assert fans.manual_mode_button.isChecked()


@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_new_shortcuts_translate_when_language_changes(qtbot, language):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    try:
        set_language(language)
        localize_widget_tree(page, language)
        for button, key in zip(page.cpu_card.action_buttons, ("Configure CPU",), strict=True):
            assert button.text() == tr(key)
            if language != "en":
                assert button.text() != key
    finally:
        set_language("en")


@pytest.mark.parametrize("width,height", ((1024, 720), (1920, 1080)))
def test_icons_fit_existing_sidebar_without_reserving_dashboard_space(qtbot, width, height):
    shell = QWidget()
    qtbot.addWidget(shell)
    shell.setStyleSheet(application_stylesheet("dark", scale=100))
    layout = QHBoxLayout(shell)
    sidebar, page = Sidebar(), DashboardPage(object())
    sidebar.set_collapsed(True)
    layout.addWidget(sidebar)
    layout.addWidget(page, 1)
    shell.resize(width, height)
    shell.show()
    qtbot.wait(100)
    assert shell.width() == width and shell.height() == height
    assert page.scroll.viewportMargins().right() == 0
    assert page.readiness.system_bar.isAncestorOf(page.footer)
    assert page.footer.isVisible()
    assert page.footer.geometry().right() < page.readiness.system_bar.width()
    assert page.footer.x() > page.readiness.system_label.geometry().right()
    assert page.content.width() == page.scroll.viewport().width()
