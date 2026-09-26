"""Layout contract for the Compute Units workspace.

The page reads like the CPU and GPU workspaces: no title rows, no badges. The
WGP table spans the page, large enough to read and press. Underneath, the
controls that act on it (the target, the live actions and boot persistence)
sit beside the telemetry that says what the routing costs: the GPU's clock,
load, power and heat, the VRM's heat and the fan, next to the CU service and
its persistence.

``persistence_card`` still exists, hidden, purely so the ``persistence_status``
calls scattered through the page keep working. It is not part of the visible
layout, so nothing here measures it — these tests assert against what actually
renders. The matching "Recent CU actions" card has been removed outright.
"""

import pytest
from PyQt6.QtCore import QPoint

from frontends.desktop.components.widgets import IconBadge
from frontends.desktop.i18n import localize_widget_tree, set_language, tr
from frontends.desktop.pages.compute_units import ComputeUnitsPage
from frontends.desktop.theme import application_stylesheet


def _bottom(widget, parent):
    return widget.mapTo(parent, widget.rect().bottomLeft()).y()


def _host_card(widget):
    """The SectionCard a widget is rendered inside, or None."""
    host = widget.parent()
    while host is not None and not hasattr(host, "body"):
        host = host.parent()
    return host


@pytest.mark.parametrize("width", (1200, 1440, 1920))
@pytest.mark.parametrize("language", ("en", "es", "de"))
def test_the_table_spans_the_page_and_the_row_under_it_ends_together(qtbot, width, language):
    """The controls and the telemetry finish on the same line, in every language.

    The grid stretches both to the row's height and each card's trailing
    stretch absorbs the slack, so a card that forgets that stretch shows up
    here as one of them floating short.
    """
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    try:
        set_language(language)
        localize_widget_tree(page, language)
        page.setStyleSheet(application_stylesheet("dark", scale=100))
        page.resize(width, 1000)
        page.show()
        qtbot.wait(100)
        assert page._workspace_columns == 2
        for expanded in (False, True, False):
            page.register_panel.set_expanded(expanded)
            # Register details animate; check the final layout, not an interim frame.
            qtbot.wait(350)
            table = page.topology_card.geometry()
            controls = page.controls_card.geometry()
            side = page.side_column.mapTo(page.content, QPoint())
            # The table above, across both cards below it.
            assert controls.top() > table.bottom() and side.y() > table.bottom()
            assert controls.left() == table.left()
            assert side.x() + page.side_column.width() - 1 == table.right()
            # The two cards below start and end together.
            assert side.y() == controls.top()
            assert abs(_bottom(page.controls_card, page.content)
                       - _bottom(page.side_column, page.content)) <= 1
            for button in page.persistence_action_buttons:
                assert button.isVisible()
                card = _host_card(button)
                assert card is page.controls_card, button.text()
                assert card.rect().contains(
                    button.mapTo(card, button.rect().bottomRight())
                ), button.text()
    finally:
        set_language("en")


def test_the_telemetry_says_what_the_routing_costs_and_whether_it_lasts(qtbot):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    strip = page.summary_strip
    assert strip.items == [
        strip.service_item, strip.persistence_item,
        strip.gpu_freq_item, strip.gpu_load_item,
        strip.gpu_power_item, strip.gpu_temp_item,
        strip.vrm_temp_item, strip.fan_item,
    ]
    # CPU readings belong to the CPU page.
    assert not hasattr(strip, "cpu_freq_item") and not hasattr(strip, "mclk_item")

    page._apply_gpu_telemetry({
        "gpu": {"sclk_actual": 1850, "gpu_busy": 97},
        "performance": {
            "gpu_power": 88.4, "power_label": "SoC package power", "vrm_source": "nct",
            "vrm_mos_temp": 63.5, "fan_rpm": 3120, "gpu_temp": 71.0,
        },
    })
    assert strip.gpu_freq_item.value.text() == "1850 MHz"
    assert strip.gpu_power_item.value.text() == "88.4 W"
    assert strip.gpu_power_item.detail.text() == tr("SoC package power")
    assert strip.vrm_temp_item.value.text() == "63.5 °C"
    assert strip.vrm_temp_item.detail.text() == tr("VRM MOS")
    assert strip.fan_item.value.text() == "3120 RPM"


def test_the_vrm_rail_over_i2c_is_preferred_when_the_board_has_it(qtbot):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    strip = page.summary_strip
    page._apply_gpu_telemetry({
        "gpu": {},
        "performance": {
            "gpu_power": 88.4, "vrm_source": "pmbus", "vrm_mos_temp": 63.5,
            "vrm_gpu_power_w": 95.2, "vrm_gpu_current_a": 101.3, "vrm_temp_gpu": 58.0,
        },
    })
    assert strip.gpu_power_item.value.text() == "95.2 W"
    assert "PMBus" in strip.gpu_power_item.detail.text()
    assert "101.3 A" in strip.gpu_power_item.detail.text()
    assert strip.vrm_temp_item.value.text() == "58.0 °C"
    assert "PMBus" in strip.vrm_temp_item.detail.text()

    # Nothing read at all: said, not left as a stale number.
    page._apply_gpu_telemetry({"gpu": {}, "performance": {}})
    for item in (strip.gpu_power_item, strip.vrm_temp_item, strip.fan_item):
        assert item.value.text() == tr("Not detected")


def test_no_title_rows_badges_or_decorative_icons(qtbot):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    for card in (page.topology_card, page.controls_card, page.profiles_card, page.persistence_card):
        assert card.status is None
    for card in (page.topology_card, page.controls_card, page.profiles_card):
        assert card.findChildren(IconBadge) == []
    # Text-only actions; the register toggle keeps the arrow that says it opens.
    for button in page.persistence_action_buttons + [page.apply_live_button]:
        assert button.icon().isNull() == (button is not page.register_toggle), button.text()
    assert any(button.text() == tr("Raw status") for button in page.persistence_action_buttons)

    page._apply_state({})
    page._set_busy(True, "Working")
    assert not page.topology_table.isEnabled()
    page._set_busy(False, "")
    assert page.topology_table.isEnabled()


def test_the_merged_cards_stay_out_of_the_visible_layout(qtbot):
    """They are kept alive for their state hooks, not to be shown again."""
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    page.resize(1440, 900)
    page.show()
    qtbot.wait(50)
    assert not page.persistence_card.isVisible()
    # The activity card is gone entirely, not merely hidden.
    assert not hasattr(page, "activity_card")
    assert not hasattr(page, "activity_body")


@pytest.mark.parametrize("width", (360, 720, 1440, 720))
def test_cu_workspace_reflows_without_overflowing_sideways(qtbot, width):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    page.resize(1440, 900)
    page.show()
    qtbot.wait(50)
    page.resize(width, 900)
    qtbot.wait(100)
    assert page.scroll.horizontalScrollBar().maximum() == 0
    assert page.content.width() == page.scroll.viewport().width()
    table = page.topology_card.geometry()
    assert page.controls_card.y() > table.bottom()
    if page._workspace_columns == 1:
        # One column: table, controls, telemetry.
        assert page.side_column.y() > page.controls_card.geometry().bottom()
    else:
        # Two columns under the table: beside each other, never overlapping.
        assert page.side_column.x() > page.controls_card.geometry().right()
