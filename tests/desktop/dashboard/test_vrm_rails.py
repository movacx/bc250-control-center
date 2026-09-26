"""The board has two VRMs, and most boards cannot measure either of them.

`I2C_HEADER1` and `TPMS1` are not connected on a stock BC-250, so the PMIC
that knows the real rail temperatures answers nobody until the owner wires
them together. What the kernel offers instead is a Nuvoton channel labelled
"VRM MOS", which on this board tracks the System sensor.

Presenting that channel as "VRM" is the complaint these tests encode: the
dashboard must name what it is actually showing, and must show the two rails
apart when it really has them. The graphics card therefore keeps two fixed
rows -- "VRM MOS", which every board has, and "VRM GPU" under it, which
reads only with the I2C link.
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
    rows = [hero.details["mos"], hero.details["rail"]]
    return (
        [(row.label.text(), f"{row.value.text()} {row.unit.text()}".strip()) for row in rows],
        page.vrm_strip,
    )


def test_a_stock_board_does_not_call_the_nuvoton_channel_a_vrm_rail(page):
    thermal, vrm_strip = _sensors(
        page,
        {"board_temperature_c": 48, "vrm_temperature_c": 51, "vrm_source": "nct",
         "vrm_mos_temperature_c": 51},
    )

    assert ("VRM MOS", "51.0 °C") in thermal
    assert ("VRM GPU", "Not detected") in thermal
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


def test_the_mosfet_sensor_and_the_graphics_rail_are_two_rows(page):
    modded, _strip = _sensors(page, {**PMBUS, "vrm_mos_temperature_c": 47})
    stock, _strip = _sensors(
        page,
        {"board_temperature_c": 48, "vrm_temperature_c": 51, "vrm_source": "nct",
         "vrm_mos_temperature_c": 51},
    )

    # The same two rows either way; the I2C link only fills the second.
    assert modded == [("VRM MOS", "47.0 °C"), ("VRM GPU", "48.0 °C")]
    assert stock == [("VRM MOS", "51.0 °C"), ("VRM GPU", "Not detected")]


def test_a_raised_status_bit_marks_the_rail_row(page):
    _thermal, vrm_strip = _sensors(
        page, {**PMBUS, "vrm_alerts": ("gpu_temp_warning",)}
    )

    assert page.gpu_card.details["rail"].property("tone") == "warning"


@pytest.mark.parametrize("system, pwm_enable, curve, preset, expected", [
    (True, 1, True, False, "system"),
    (False, 2, True, False, "firmware"),
    (False, 1, True, False, "daemon"),
    (False, 1, False, True, "daemon"),
    (False, 1, False, False, "manual"),
])
def test_the_fan_row_says_who_drives_the_fan(system, pwm_enable, curve, preset, expected):
    from frontends.desktop.core.dashboard_presenter import dashboard_fan_owner

    fan = {"sensores": {"fans": [{"label": "Pump Fan / J4003 Fan 1", "pwm_enable": pwm_enable}]}}
    config = {"fan_curve": {"enabled": curve}, "fan_preset": {"enabled": preset}}
    assert dashboard_fan_owner(fan, system_owned=system, config=config) == expected


def test_the_dashboard_shows_the_owner_instead_of_the_raw_mode(page):
    from dataclasses import replace

    page.apply_state(replace(page.state, fan_state_available=True, fan_mode="manual", fan_owner="system"))
    assert page.fan_card.details["mode"].value.text() == "System service"
