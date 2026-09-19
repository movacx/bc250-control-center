import time

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QLabel

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

    for card in (page.gpu_card, page.cpu_card, page.fan_card):
        # Every panel names itself in the same heading style.
        assert card.heading_icon.text() == card.heading_icon.text().upper()


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
    assert hero.headline.items["clock"][0].text() == "1000"
    assert hero.details["range"].detail.text() == "Accepted 1850 MHz"
    assert not hasattr(hero, "power_summary")
    assert page.cores_summary.shape.text() == "6 cores / 12 threads"
    # Compute Units are reported by the panel that owns the die. This state
    # carries no CU evidence, so the reading says so rather than assuming 40.
    assert page.gpu_card.details["cu"].value.text() == tr("Not detected")
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
    # Graphics only: the processor reports its own temperature, and the drive
    # and the board are reported next to the fan that moves their heat.
    assert hero.details["temperature"].value.text() == "57"
    assert hero.details["rail"].label.text() == tr("VRM")
    assert hero.details["rail"].value.text() == "49.0"
    assert page.cpu_card.details["temperature"].value.text() == "56.0"
    assert page.fan_card.details["board"].value.text() == "48.0"
    assert page.fan_card.details["nvme"].value.text() == "46.9"
    assert page.fan_card.details["hotspot"].value.text() == "68.8"
    assert hero.details["power"].value.text() == "41"
    assert hero.details["mclk"].value.text() == "450"
    rows = page.cores_summary.grid.rows
    assert rows[0].name.text() == "N1"
    assert rows[0].frequency.text() == "3.47 GHz"
    assert rows[0].usage.text() == "1 %"
    assert len([row for row in rows if not row.isHidden()]) == 8
    assert rows[6].frequency.text() == tr("Hidden")
    page._apply_live_sample(
        (time.monotonic() - 5, {"cpu": {"physical_cores": 8, "logical_cores": 16}})
    )
    assert hero.headline.items["clock"][0].text() == "--"
    assert page.cores_summary.shape.text() == tr("Not detected")


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

    assert page.cores_summary.shape.text() == "6 cores / 12 threads"
    # A registered overclock is a reading of the processor, reported with the
    # rest of them rather than as a caption on the core strip.
    assert page.cpu_card.details["oc"].value.text() == "3500"
    assert page.cpu_card.details["oc"].unit.text() == "MHz"
    assert page.cpu_card.details["oc"].detail.text() == "Scale -20"

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
    assert page.cpu_card.details["oc"].value.text() == tr("Not detected")


def test_a_medium_dashboard_stacks_the_three_panels(qtbot):
    """Three peers side by side, or one column. Never two and an orphan."""
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.resize(920, 800)
    page.show()
    qtbot.wait(30)

    columns = {page.modules_grid.getItemPosition(index)[1] for index in range(3)}
    assert columns == {0}


def test_the_core_grid_belongs_to_the_processor_card_and_keeps_even_cells(qtbot):
    """The eight core positions moved out of the graphics card.

    They describe the processor, so they are reported by the processor. The
    card is half the page rather than its full width, so the grid folds to two
    rows of four instead of one row of eight — the cells must still measure
    the same, or a core looks busier than its neighbour for no reason.
    """
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.resize(1500, 900)
    page.show()
    qtbot.wait(30)

    cores = page.cores_summary
    assert not page.gpu_card.isAncestorOf(cores)
    assert page.cpu_card.isAncestorOf(cores)
    # Two columns of four in a third of the page.
    assert cores.grid._columns == 2
    widths = [row.width() for row in cores.grid.rows if row.isVisible()]
    assert len(widths) == 8
    assert max(widths) - min(widths) <= 1


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
    assert page.cores_summary.shape.text() == tr("Not detected")


@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_core_tile_translates_without_losing_live_counts(qtbot, language):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    try:
        set_language(language)
        localize_widget_tree(page, language)
        page.apply_state(DashboardState(cpu_physical_cores=8, cpu_logical_cores=16))
        tile = page.cores_summary
        assert tile.title.text() == tr("Live core monitor").upper()
        assert "8" in tile.shape.text() and "16" in tile.shape.text()
        if language != "en" and tr("Live core monitor") != "Live core monitor":
            assert tile.title.text() != "LIVE CORE MONITOR"

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
        # The registered overclock is a reading of the processor now, so it
        # is translated with the rest of them rather than as a caption here.
        overclock = page.cpu_card.details["oc"]
        # The unit is translated as well, and some languages join it to the
        # number, so the assertion is on the reading rather than the split.
        assert "3850" in overclock.value.text()
        assert overclock.detail.text() == tr_format("Scale {scale}", scale=-35)
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
    # The hero now carries every graphics reading in two boards instead of
    # two strips, so its ceiling rose with the content it owns.
    assert page.gpu_card.height() < 520
    # Each panel is as tall as its own content; they share a top edge, not a
    # bottom one, so no panel ends in a quarter-height void.
    assert len({card.y() for card in page.instruments}) == 1
    assert len({card.y() for card in page.instruments}) == 1
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

    dialog.deleteLater()
    qtbot.waitUntil(lambda: preparation._decky_screenshot_dialog is None)
    preparation.select_tab(2)
    preparation.decky_preview_button.click()
    replacement = preparation._decky_screenshot_dialog
    assert replacement is not dialog
    assert replacement.isVisible()
    replacement.close()
