"""The board has two VRMs, and most boards cannot measure either of them.

`I2C_HEADER1` and `TPMS1` are not connected on a stock BC-250, so the PMIC
that knows the real rail temperatures answers nobody until the owner wires
them together. What the kernel offers instead is a Nuvoton channel labelled
"VRM MOS", which on this board tracks the System sensor.

Presenting that channel as "VRM" is the complaint these tests encode: the
dashboard must name what it is actually showing, and must show the two rails
apart when it really has them.
"""

from __future__ import annotations

import pytest

from frontends.desktop.pages.dashboard import DashboardPage

BASE = {
    "cpu": {"temperature_c": 56},
    "gpu": {"temperature_c": 57},
    "power": {"gpu_w": 41.2},
}

PMBUS = {
    "board_temperature_c": 48,
    "vrm_temperature_c": 48,
    "vrm_source": "pmbus",
    "vrm_cpu_temperature_c": 45,
    "vrm_gpu_temperature_c": 48,
    "vrm_input_voltage_v": 12.22,
    "vrm_total_power_w": 10.0,
    "vrm_cpu_voltage_v": 0.78,
    "vrm_gpu_voltage_v": 0.646,
    "vrm_cpu_current_a": 2.8,
    "vrm_gpu_current_a": 12.0,
    "vrm_alerts": (),
}


@pytest.fixture
def page(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    return page


def _sensors(page, sensors):
    page.apply_state(page.state.with_live_metrics({**BASE, "sensors": sensors}))
    hero = page.gpu_card
    rail = hero.details["rail"]
    return (
        [(rail.label.text(), f"{rail.value.text()} {rail.unit.text()}".strip())],
        page.vrm_strip,
    )


def test_a_stock_board_does_not_call_the_nuvoton_channel_a_vrm_rail(page):
    thermal, vrm_strip = _sensors(
        page,
        {"board_temperature_c": 48, "vrm_temperature_c": 51, "vrm_source": "nct"},
    )

    assert ("VRM MOS", "51.0 °C") in thermal
    # Nothing electrical is known, so the band says so instead of vanishing.
    assert vrm_strip["input"].value.text() == "Not detected"


def test_a_modded_board_shows_both_rails_and_their_electrical_readings(page):
    thermal, vrm_strip = _sensors(page, PMBUS)

    # Each rail is reported by the card for the half of the die it feeds.
    assert ("VRM GPU", "48.0 °C") in thermal
    assert page.cpu_card.details["rail"].value.text() == "45.0"
    assert vrm_strip.isHidden() is False
    assert vrm_strip["input"].value.text() == "12.22"
    assert vrm_strip["cpu_voltage"].value.text() == "0.78"
    assert vrm_strip["gpu_voltage"].value.text() == "0.65"
    assert vrm_strip["total"].value.text() == "10.0"
    assert vrm_strip["gpu_current"].value.text() == "12.0"


def test_the_row_grows_and_shrinks_with_the_sensors_the_board_has(page):
    modded, _strip = _sensors(page, PMBUS)
    stock, _strip = _sensors(
        page,
        {"board_temperature_c": 48, "vrm_temperature_c": 51, "vrm_source": "nct"},
    )

    # One rail cell, named for whatever is measuring it.
    assert modded[0][0] == "VRM GPU"
    assert stock[0][0] == "VRM MOS"


def test_a_raised_status_bit_marks_the_rail_row(page):
    _thermal, vrm_strip = _sensors(
        page, {**PMBUS, "vrm_alerts": ("gpu_temp_warning",)}
    )

    assert page.gpu_card.details["rail"].property("tone") == "warning"
