"""Every reading on the dashboard belongs to one physical domain.

The screen used to put the processor's temperature, the drive's hotspot and
the board sensor inside the graphics card, because that card happened to be
the widest thing on the page. These tests pin the grouping itself: which
panel owns which reading, and that a panel reports its own domain and nothing
else.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from frontends.desktop.core.state import DashboardState
from frontends.desktop.i18n import tr
from frontends.desktop.pages.dashboard import DashboardPage


@pytest.fixture
def page(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    return page


def test_the_graphics_panel_reports_the_graphics_die_and_nothing_else(page):
    keys = set(page.gpu_card.details.readings)

    assert {"temperature", "voltage", "power", "rail"} <= keys
    assert {"mclk", "socclk", "fclk", "load"} <= keys
    assert {"vram", "gtt", "governor", "range", "cu"} <= keys
    # The DPM mode is a tuning control, not a reading; it left this panel.
    assert "dpm" not in keys
    # The processor, the drive and the board are not graphics readings.
    assert not keys & {"nvme", "hotspot", "board", "cores"}


def test_the_processor_panel_owns_its_cores(page):
    assert set(page.cpu_card.details.readings) == {
        "temperature", "rail", "load", "voltage", "oc",
    }
    assert page.cpu_card.isAncestorOf(page.cores_summary)
    assert not page.gpu_card.isAncestorOf(page.cores_summary)


def test_the_cooling_panel_owns_the_board_and_the_drive(page):
    keys = set(page.fan_card.details.readings)

    assert {"duty", "mode", "controller", "board", "nvme", "hotspot"} <= keys


def test_every_panel_is_built_the_same_way(page):
    for panel in page.instruments:
        assert panel.headline.items, panel.key
        assert panel.details.readings, panel.key
        assert panel.action_buttons, panel.key
        assert panel.status is not None, panel.key


def test_a_headline_never_carries_a_sentence(page):
    """"Not detected" at 30 px is wider than the panel that holds it."""
    page.apply_state(DashboardState())

    for panel in page.instruments:
        for key in panel.headline.items:
            value, _unit, _caption = panel.headline.items[key]
            assert value.text() == "--", (panel.key, key)


def test_the_header_says_what_the_machine_is(page):
    page.apply_state(
        DashboardState(
            cpu_physical_cores=6,
            cpu_logical_cores=12,
            cu_state_available=True,
            active_cus=40,
            total_cus=40,
            vram_total_bytes=268_435_456,
        )
    )

    specification = page.board_header.spec.text()

    assert "6" in specification and "12" in specification
    assert "40 / 40" in specification
    assert "256 MB" in specification


def test_the_header_reports_the_hottest_reading_as_the_board_state(page):
    page.apply_state(DashboardState(cpu_temperature_c=57, gpu_temperature_c=55))
    assert page.board_header.status.text() != ""

    page.apply_state(DashboardState(cpu_temperature_c=57, gpu_temperature_c=92))
    hot = page.board_header.status.text()

    page.apply_state(DashboardState(cpu_temperature_c=57, gpu_temperature_c=55))
    assert page.board_header.status.text() != hot


def test_the_power_band_says_a_stock_board_cannot_report_its_rails(page):
    """It stays on screen without the mod, because that is worth knowing.

    Reading these rails needs two wires soldered between ``I2C_HEADER1`` and
    ``TPMS1``; it is the only sensor group on this page a user can go and add,
    so the band says what is missing rather than disappearing.
    """
    page.apply_state(DashboardState())
    assert page.vrm_strip.isHidden() is False
    assert page.vrm_strip["input"].value.text() == tr("Not detected")
    assert page.vrm_strip.note.text() != ""

    page.apply_state(
        page.state.with_live_metrics(
            {
                "cpu": {"temperature_c": 56},
                "sensors": {
                    "vrm_source": "pmbus",
                    "vrm_cpu_temperature_c": 45,
                    "vrm_gpu_temperature_c": 48,
                    "vrm_input_voltage_v": 12.22,
                    "vrm_total_power_w": 10.0,
                    "vrm_cpu_voltage_v": 0.78,
                    "vrm_gpu_voltage_v": 0.646,
                    "vrm_cpu_current_a": 2.8,
                    "vrm_gpu_current_a": 12.0,
                },
            }
        )
    )

    assert page.vrm_strip.note.text() == ""
    assert page.vrm_strip["input"].value.text() == "12.22"
    assert page.vrm_strip["cpu_current"].value.text() == "2.8"
    assert page.vrm_strip["cpu_temperature"].value.text() == "45.0"


def test_each_panel_groups_readings_by_what_they_are(page):
    """Power beside heat, memory with memory, the drive's rows together."""
    gpu = page.gpu_card.details
    assert gpu.group_of("power") == gpu.group_of("voltage") == "Power"
    assert gpu.group_of("ram") == gpu.group_of("vram") == "Memory"
    fans = page.fan_card.details
    assert {fans.group_of(key) for key in ("nvme", "hotspot", "storage", "swap")} == {"M.2 drive"}
    assert "ram" not in fans.readings


def test_power_delivery_labels_are_unique_and_fold_without_the_link(page):
    labels = [reading.label.text() for reading in page.vrm_strip.readings.values()]
    assert len(labels) == len(set(labels))
    page._update_vrm_strip(SimpleNamespace(vrm_source=""))
    assert page.vrm_strip.readings_visible is False
    assert all(reading.isHidden() for reading in page.vrm_strip.readings.values())
    assert page.vrm_strip.note.text() != ""
