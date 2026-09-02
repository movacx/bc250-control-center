import time

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QLabel

from frontends.desktop.components.dashboard_widgets import DashboardCoreSummary
from frontends.desktop.components.sidebar import Sidebar
from frontends.desktop.core.state import DashboardState
from frontends.desktop.i18n import (
    SUPPORTED_LANGUAGES,
    localize_widget_tree,
    set_language,
    tr,
    tr_format,
)
from frontends.desktop.pages.dashboard import DashboardPage
from frontends.desktop.theme import application_stylesheet


def test_dashboard_telemetry_headings_reuse_existing_icons(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)

    for card in (page.gpu_card, page.cpu_card, page.cu_card, page.fan_card):
        assert not card.heading_icon.pixmap().isNull()
        assert card.heading_icon.width() == 24


@pytest.mark.parametrize("width", (390, 700, 1100, 1400))
def test_prepare_button_stays_directly_below_core_unlock(qtbot, width):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    panel = page.readiness
    panel._reflow(width)
    qtbot.wait(10)
    grid = panel.components_grid
    core_index = grid.indexOf(panel.component_cards["core_unlock"])
    footer_index = grid.indexOf(panel.prepare_footer)
    core_row, core_column, _rowspan, _colspan = grid.getItemPosition(core_index)
    footer_row, footer_column, _rowspan, _colspan = grid.getItemPosition(footer_index)
    assert footer_column == core_column
    assert footer_row == core_row + 1


def test_dashboard_displays_physical_clock_and_core_counts_without_duplicate_rows(
    qtbot,
):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(DashboardState(governor_min_mhz=1000, governor_max_mhz=1850))
    page._apply_live_sample(
        (
            time.monotonic(),
            {
                "cpu": {
                    "physical_cores": 6,
                    "logical_cores": 12,
                    "temperature_c": 56,
                    "per_core_frequency_mhz": [3470],
                    "per_core_percent": [1],
                },
                "gpu": {"frequency_mhz": 1000, "temperature_c": 57, "usage_percent": 0},
            },
        )
    )
    hero = page.gpu_card
    assert hero.frequency_value.text() == "1000"
    assert hero.accepted_row.value.text() == "1850 MHz"
    assert len(hero.evidence_rows) == 2
    assert not hasattr(hero, "power_summary")
    assert hero.cores_summary.value.text() == "6 cores / 12 threads"
    assert hero.cores_summary.detail.isHidden()
    assert len(page.cu_card.metric_rows) == 2  # Mode is already in the CU badge.
    assert page.cpu_card.status.isHidden()
    assert not hasattr(hero, "uptime_metric")
    page._apply_live_sample(
        (
            time.monotonic(),
            {
                "gpu": {
                    "temperature_c": 57,
                    "memory_frequency_mhz": 450,
                    "gtt_used": 249_376_768,
                    "gtt_total": 5_587_288_064,
                    "dpm_force_level": "auto",
                    "dpm_state": "performance",
                },
                "power": {"gpu_w": 41.2},
                "sensors": {
                    "nvme_temperature_c": 46.85,
                    "nvme_hotspot_temperature_c": 68.85,
                    "board_temperature_c": 48,
                    "vrm_temperature_c": 49,
                },
            },
        )
    )
    assert [item.text() for item in hero.thermal_strip.labels] == [
        tr("GPU"),
        tr("CPU"),
        tr("M.2"),
        tr("Board"),
        tr("VRM"),
    ]
    assert [item.text() for item in hero.thermal_strip.values] == [
        "57 °C",
        "56.0 °C",
        "46.9 °C",
        "48.0 °C",
        "49.0 °C",
    ]
    assert [item.text() for item in hero.technical_strip.values] == [
        "41 W",
        "450 MHz",
        "68.8 °C",
        "238 MB / 5.2 GB",
        "auto",
    ]
    assert hero.cores_summary.core_labels[0].text() == "N1"
    assert hero.cores_summary.core_frequency_labels[0].text() == "3.47 GHz"
    assert hero.cores_summary.core_usage_labels[0].text() == "1%"
    assert len([cell for cell in hero.cores_summary.core_cells if not cell.isHidden()]) == 8
    assert hero.cores_summary.core_frequency_labels[6].text() == tr("Hidden / offline")
    page._apply_live_sample(
        (time.monotonic() - 5, {"cpu": {"physical_cores": 8, "logical_cores": 16}})
    )
    assert hero.frequency_value.text() == "--"
    assert hero.cores_summary.value.text() == tr("Not detected")
    assert hero.cores_summary.detail.isHidden()


def test_dashboard_shows_only_registered_boot_cpu_oc_and_scale(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)

    page.apply_state(
        DashboardState(
            cpu_physical_cores=6,
            cpu_logical_cores=12,
            cpu_oc_active=True,
            cpu_oc_frequency_mhz=3500,
            cpu_oc_scale=-20,
            cpu_oc_source="boot",
        )
    )

    assert page.gpu_card.cores_summary.value.text() == "6 cores / 12 threads"
    assert page.gpu_card.cores_summary.detail.text() == (
        "Registered OC: 3500 MHz · Scale -20"
    )

    page.apply_state(
        DashboardState(
            cpu_physical_cores=6,
            cpu_logical_cores=12,
            cpu_oc_active=False,
            cpu_oc_frequency_mhz=3850,
            cpu_oc_scale=-35,
            cpu_oc_source="live",
        )
    )
    assert page.gpu_card.cores_summary.detail.isHidden()


def test_medium_dashboard_width_gives_the_core_grid_the_full_hero_width(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.resize(920, 800)
    page.show()
    qtbot.wait(30)

    hero = page.gpu_card
    assert not hero._wide
    assert hero.root.indexOf(hero.evidence) >= 0
    evidence_row, evidence_column, _rowspan, _colspan = hero.root.getItemPosition(
        hero.root.indexOf(hero.evidence)
    )
    assert (evidence_row, evidence_column) == (1, 0)
    assert hero.cores_summary._columns == 4


def test_wide_core_strip_keeps_all_eight_cells_the_same_width(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.resize(1500, 800)
    page.show()
    qtbot.wait(30)

    cores = page.gpu_card.cores_summary
    assert cores._columns == 8
    widths = [cell.width() for cell in cores.core_cells if cell.isVisible()]
    assert len(widths) == 8
    assert max(widths) - min(widths) <= 1


@pytest.mark.parametrize("scale", (100, 150))
def test_compact_core_strip_grows_to_keep_every_reading_visible(qtbot, scale):
    tile = DashboardCoreSummary()
    qtbot.addWidget(tile)
    tile.setStyleSheet(application_stylesheet("dark", scale=scale))
    tile.set_value("6 cores / 12 threads")
    tile.set_detail("Registered OC: 3850 MHz · Scale -35")
    tile.set_core_metrics(
        [3190, 1400, 2300, 3190, 1390, 1400],
        [7, 9, 5, 3, 4, 9],
    )
    tile.setFixedWidth(560)
    tile.show()
    tile.adjustSize()
    qtbot.wait(20)

    assert tile._columns == 2
    assert tile.height() >= tile.minimumSizeHint().height()
    for label in tile.core_labels + tile.core_frequency_labels:
        if not label.isHidden():
            assert label.height() >= label.fontMetrics().height()


@pytest.mark.parametrize(
    "cpu",
    (
        {},
        {"physical_cores": None, "logical_cores": 12},
        {"physical_cores": -2, "logical_cores": 12},
        {"physical_cores": 16, "logical_cores": 8},
    ),
)
def test_core_tile_never_invents_an_unlocked_or_healthy_state(qtbot, cpu):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(DashboardState().with_live_metrics({"cpu": cpu}))
    assert page.gpu_card.cores_summary.value.text() == tr("Not detected")
    assert page.gpu_card.cores_summary.detail.isHidden()


@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_core_tile_translates_without_losing_live_counts(qtbot, language):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    try:
        set_language(language)
        localize_widget_tree(page, language)
        page.apply_state(DashboardState(cpu_physical_cores=8, cpu_logical_cores=16))
        tile = page.gpu_card.cores_summary
        assert tile.label.text() == tr("Available CPU cores")
        assert tile.detail.isHidden()
        assert "8" in tile.value.text() and "16" in tile.value.text()
        if language != "en":
            assert tile.label.text() != "Available CPU cores"

        page.apply_state(
            DashboardState(
                cpu_physical_cores=8,
                cpu_logical_cores=16,
                cpu_oc_active=True,
                cpu_oc_frequency_mhz=3850,
                cpu_oc_scale=-35,
                cpu_oc_source="boot",
            )
        )
        expected = tr_format(
            "Registered OC: {frequency} MHz · Scale {scale}",
            frequency=3850,
            scale=-35,
        )
        assert tile.detail.text() == expected
        assert not tile.detail.isHidden()
        if language != "en":
            assert tile.detail.text() != "Registered OC: 3850 MHz · Scale -35"
    finally:
        set_language("en")


@pytest.mark.parametrize("mode", ("light", "dark"))
@pytest.mark.parametrize("scale", (70, 100, 150))
def test_scrollbar_remains_outside_fixed_icons_when_resizing_and_changing_tabs(
    qtbot, mode, scale
):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.setStyleSheet(application_stylesheet(mode, scale=scale))
    page.show()
    try:
        for width, height in ((1440, 900), (360, 800), (1440, 2400), (1440, 900)):
            page.resize(width, height)
            qtbot.wait(80)
            assert page.scroll.height() == page.height()
            assert page.scroll.horizontalScrollBar().maximum() == 0
            assert page.content.width() == page.scroll.viewport().width()
            assert page.scroll.viewportMargins().right() == 0
            margins = page.layout.contentsMargins()
            assert margins.left() == margins.right()
            scrollbar = page.scroll.verticalScrollBar()
            if scrollbar.isVisible():
                assert (
                    page.scroll.viewport().geometry().right()
                    < scrollbar.mapTo(page.scroll, QPoint()).x()
                )
            for button in (page.support_button, page.contact_button):
                assert page.readiness.system_bar.rect().contains(
                    button.mapTo(page.readiness.system_bar, button.rect().bottomRight())
                )
        for tab in (1, 2, 3, 0):
            page.readiness.select_tab(tab)
            qtbot.wait(80)
            assert page.readiness.prepare_footer.isVisible() == (tab == 0)
            assert page.footer.isVisible()
            # Tabs may change header width slightly, but links remain contained.
            assert page.readiness.system_bar.rect().contains(
                page.support_button.mapTo(
                    page.readiness.system_bar,
                    page.support_button.rect().bottomRight(),
                )
            )
    finally:
        application_stylesheet("light", scale=100)


def test_dashboard_compact_cards_and_preparation_grid_keep_equal_edges(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.setStyleSheet(application_stylesheet("dark", scale=100))
    page.resize(1600, 1000)
    page.show()
    qtbot.wait(150)
    assert page.gpu_card.height() < 420
    assert len({card.height() for card in page.module_cards}) == 1
    assert len({card.y() for card in page.module_cards}) == 1
    assert page.readiness._component_columns == 4
    assert len({card.height() for card in page.readiness.rows}) == 1
    assert (
        page.readiness.memory_controls.itemAtPosition(1, 0).widget()
        is page.readiness.memory_policy_combo
    )
    assert (
        page.readiness.memory_controls.itemAtPosition(1, 2).widget()
        is page.readiness.ttm_limit_combo
    )


def test_sidebar_no_longer_claims_system_protection(qtbot):
    sidebar = Sidebar()
    qtbot.addWidget(sidebar)
    for collapsed in (False, True, False):
        sidebar.set_collapsed(collapsed)
        sidebar.retranslate()
        assert not hasattr(sidebar, "status_card")
        assert not any(
            label.text() in {tr("System protected"), tr("BC250 services ready")}
            for label in sidebar.findChildren(QLabel)
        )
    assert len(sidebar.buttons) == 8


def test_compatibility_filter_ignores_incidental_mouse_wheel(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    filter_box = page.readiness.compatibility_filter
    filter_box.setCurrentIndex(0)
    event = QWheelEvent(
        QPointF(8, 8),
        QPointF(8, 8),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )

    QApplication.sendEvent(filter_box, event)

    assert filter_box.currentData() == "detected"


def test_bazzite_swap_choices_remain_selectable(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    panel = page.readiness
    # Reproduce the stale partial refresh from the reported screen: it first
    # shows the generic, disabled choices and only later has the Bazzite label.
    panel._update_memory_controls(
        {"os_family": "unsupported", "system_setup": {"memory": {}}}
    )
    assert panel.memory_policy_combo.currentData() == "preserve"
    panel.set_state(
        DashboardState(
            preparation_tools={
                # This is the partial inventory shown in the reported UI:
                # the label says Bazzite while the family is not yet ready.
                "os_family": "unsupported",
                "os_label": "Bazzite Deck",
                "memory_runtime": {},
            }
        )
    )

    panel.memory_policy_combo.setCurrentIndex(
        panel.memory_policy_combo.findData("zswap-16")
    )

    assert panel.memory_policy_combo.isEnabled()
    assert panel.memory_policy_combo.currentData() == "zswap-16"
    assert panel.memory_swap_apply_button.isEnabled()


def test_decky_screenshot_preview_opens_without_losing_component_selection(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.setStyleSheet(application_stylesheet("dark", scale=100))
    page.resize(1440, 900)
    page.show()
    qtbot.wait(100)
    preparation = page.readiness
    components_height = preparation.height()
    preparation.component_cards["cpu_oc"].checkbox.setChecked(False)
    selected = preparation.selected_components
    preparation.select_tab(2)
    qtbot.wait(100)
    assert preparation.decky_preview_button.isVisibleTo(preparation)
    assert not preparation.prepare_button.isVisible()
    preparation.decky_preview_button.click()
    qtbot.wait(50)
    dialog = preparation._decky_screenshot_dialog
    assert dialog.isVisible()
    assert not dialog.image.pixmap().isNull()
    assert not hasattr(preparation, "_decky_preview_overlay")
    dialog.close()
    preparation.select_tab(0)
    qtbot.wait(100)
    assert preparation.selected_components == selected
    assert abs(preparation.height() - components_height) <= 1
