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
    page.cu_card.primary_button.click()
    assert actions == ["cpu_configuration", "cpu_overview", "fans_manual", "fans_curve", "repositories"]
    assert modules == ["cu"]
    assert page.cu_card.status.isHidden()
    assert page.readiness.status.isHidden()
    assert page.gpu_card.governor_metric.parent() is page.gpu_card.evidence
    assert page.gpu_card.load_metric.parent() is page.gpu_card.evidence
    assert page.gpu_card.gpu_voltage_metric.parent() is page.gpu_card.evidence
    assert page.gpu_card.thermal_strip.parent() is page.gpu_card.metrics_host
    assert page.gpu_card.technical_strip.parent() is page.gpu_card.metrics_host


def test_gpu_configuration_shows_the_live_gpu_voltage_sensor(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(DashboardState(cpu_voltage_mv=1206, gpu_voltage_mv=799))
    page.resize(1180, 900)
    page.show()
    qtbot.wait(50)
    assert page.gpu_card.gpu_voltage_metric.label.text() == tr("GPU voltage")
    assert page.gpu_card.gpu_voltage_metric.value.text() == "0.799 V"
    assert page.gpu_card.gpu_voltage_metric.y() == page.gpu_card.load_metric.y()
    assert page.gpu_card.gpu_voltage_metric.x() > page.gpu_card.load_metric.x()


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

    assert page.gpu_card.thermal_strip.values[0].text() == tr("Invalid")
    assert page.gpu_card.gpu_voltage_metric.value.text() == tr("Invalid")
    assert page.gpu_card.technical_strip.values[1].text() == tr("Invalid")
    assert page.gpu_card.status.text() == "running"
    assert page.gpu_card.gpu_voltage_metric.toolTip() == tr(
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

    assert not page.gpu_card.telemetry_repair_button.isHidden()
    assert page.gpu_card.telemetry_repair_button.isEnabled()
    assert page.gpu_card.telemetry_repair_button.text() == tr("Repair BC250 telemetry")


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

    assert not page.gpu_card.telemetry_repair_button.isHidden()
    assert not page.gpu_card.telemetry_repair_button.isEnabled()
    assert page.gpu_card.telemetry_repair_button.text() == tr(
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

    page.gpu_card.telemetry_repair_button.click()

    assert calls == [True]


def test_gpu_technical_strip_sits_below_temperatures_without_expanding_evidence(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(
        DashboardState(
            gpu_power_w=41.2,
            gpu_memory_frequency_mhz=450,
            gpu_gtt_used_bytes=249_376_768,
            gpu_gtt_total_bytes=5_587_288_064,
            gpu_dpm_force_level="auto",
            gpu_dpm_state="performance",
            nvme_temperature_c=43.85,
            nvme_hotspot_temperature_c=68.85,
        )
    )
    page.resize(1180, 900)
    page.show()
    qtbot.wait(50)

    assert page.gpu_card.thermal_strip.y() < page.gpu_card.technical_strip.y()
    assert [label.text() for label in page.gpu_card.technical_strip.labels] == [
        tr("GPU power"),
        tr("MCLK"),
        tr("Hotspot"),
        tr("GTT"),
        tr("DPM mode"),
    ]
    assert [value.text() for value in page.gpu_card.technical_strip.values] == [
        "41 W",
        "450 MHz",
        "68.8 °C",
        "238 MB / 5.2 GB",
        "auto",
    ]
    assert page.gpu_card.technical_strip.values[4].toolTip() == (
        "Power state: performance"
    )
    assert page.gpu_card.thermal_strip.values[2].text() == "43.9 °C"


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
        for button, key in zip(page.cpu_card.action_buttons, ("Configure CPU", "Unlock cores"), strict=True):
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
