"""Three dashboard answers the user asked for by name.

* Cooling names the installed BIOS under Swap: P2/P3/P5, and for P3.00 which
  image, as far as the running system can tell.
* Power delivery can be forced on from Settings while the I2C mod is being
  wired, showing what BC250-Telemetry reports even when it says invalid.
* With manual GDDR6 monitoring on, a P2.00 board said "BC250-Telemetry
  stopped updating" under a grey button. The real reason is the firmware.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from frontends.desktop.core.state import DashboardState
from frontends.desktop.pages.dashboard import DashboardPage

READY_STATUS = {
    "hardware_detected": True,
    "repository_ready": True,
    "reader_ready": True,
    "helper_ready": True,
    "payload_present": True,
}


@pytest.fixture
def page(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    return page


def _bios(page, version, variant="", evidence="how it was told"):
    page.apply_state(replace(DashboardState(), bios_version=version, bios_variant=variant, bios_evidence=evidence))
    row = page.fan_card.details["bios"]
    return row.value.text(), row.detail.text() if row.detail.isVisibleTo(page) else "", row.toolTip()


def test_the_bios_sits_in_its_own_group_right_under_swap(page):
    details = page.fan_card.details
    assert details.group_of("bios") == "BIOS"
    assert details.group_of("swap") == "M.2 drive"


@pytest.mark.parametrize("version, variant, shown", [
    ("P2.00", "ASRock", ("P2.00", "ASRock stock")),
    ("P5.00", "ASRock", ("P5.00", "ASRock stock")),
    ("P3.00", "Chipset Menu", ("P3.00", "Chipset Menu")),
    ("P3.00", "MeiMeiDXE v3", ("P3.00", "MeiMeiDXE v3")),
    # DMI's P3.00 is shared by two images nothing here separates: say both.
    ("P3.00", "", ("P3.00", "Stock or Chipset Menu")),
])
def test_the_row_names_the_image_and_keeps_the_evidence_a_hover_away(page, version, variant, shown):
    value, detail, tooltip = _bios(page, version, variant)
    assert (value, detail) == shown
    assert tooltip == "how it was told"


def test_no_version_reads_not_detected(page):
    value, detail, _tooltip = _bios(page, "", evidence="")
    assert value == "Not detected" and detail == ""


PROBE_INVALID = {
    "daemon": "running",
    "age_s": 0.4,
    "rails": {
        "cpu": {"valid": False, "vin": 0.0, "vout": 0.0, "iout": 0.0, "pout": 0.0, "temp": 0.0},
        "gpu": {"valid": False, "vin": 0.0, "vout": 0.0, "iout": 0.0, "pout": 0.0, "temp": 0.0},
    },
    "total_power_w": 0.0,
    "total_power_valid": False,
}


def test_power_delivery_stays_folded_until_manual_mode_is_on(page):
    page.apply_state(replace(DashboardState(), vrm_probe=PROBE_INVALID))
    strip = page.vrm_strip
    assert strip.readings_visible is False
    assert strip.note.text() == "Requires the I2C modification"

    page.set_vrm_manual(True)

    assert strip.readings_visible is True
    # Nothing filtered: the daemon's zeros are shown as zeros and marked.
    assert (strip["input"].value.text(), strip["input"].unit.text()) == ("0.00", "V")
    assert strip["cpu_voltage"].property("tone") == "warning"
    assert "no valid answer from the PMIC" in strip.note.text()

    page.set_vrm_manual(False)
    assert strip.readings_visible is False
    assert strip["cpu_voltage"].property("tone") == ""


@pytest.mark.parametrize("probe, note", [
    ({"daemon": "missing"}, "not publishing"),
    ({"daemon": "stale", "age_s": 42.0, "rails": {}}, "42 s old"),
])
def test_manual_mode_says_why_there_is_nothing_to_read(page, probe, note):
    page.set_vrm_manual(True)
    page.apply_state(replace(DashboardState(), vrm_probe=probe))
    assert note in page.vrm_strip.note.text()
    assert page.vrm_strip["input"].value.text() == "Not detected"


def test_a_real_pmbus_reading_wins_over_the_manual_view(page):
    page.set_vrm_manual(True)
    page.apply_state(replace(
        DashboardState(), vrm_source="pmbus", vrm_input_voltage_v=12.2,
        vrm_cpu_temperature_c=45.0, vrm_probe=PROBE_INVALID,
    ))
    strip = page.vrm_strip
    assert strip["input"].value.text() == "12.20"
    assert "Manual mode" not in strip.note.text()


def test_manual_gddr6_on_a_p2_board_names_the_firmware_not_the_collector(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    monitor = page.memory_monitor
    monitor._state.status = dict(
        READY_STATUS, firmware_supported=False, bios_version="P2.00",
        external={"state": "stale", "status": "stale", "chips": []},
    )
    monitor.set_manual_override(True)
    monitor._rebuild()

    summary = page.memory_summary
    assert not summary.live_button.isEnabled()
    assert "P2.00" in summary.blocker.text()
    assert "P3.00" in summary.blocker.text()
    assert "stopped updating" not in summary.blocker.text()

    # Without the override the channel check still speaks first.
    monitor.set_manual_override(False)
    monitor._rebuild()
    assert "SMU" in summary.blocker.text()


def test_a_marked_reading_is_actually_painted_in_its_tone(qtbot):
    """The tone lives on the frame and the colour on the number: repolishing
    only the frame left warm, hot and invalid readings in the plain colour."""
    from PyQt6.QtWidgets import QVBoxLayout, QWidget

    from frontends.desktop import theme
    from frontends.desktop.components.dashboard_instruments import Reading

    host = QWidget()
    host.setStyleSheet(theme.application_stylesheet())
    reading = Reading("CPU rail voltage")
    QVBoxLayout(host).addWidget(reading)
    qtbot.addWidget(host)
    host.show()
    reading.set_value("0.00 V")

    def colour():
        return reading.value.palette().color(reading.value.foregroundRole()).name().upper()

    plain = colour()
    reading.set_tone("warning")
    assert colour() == theme.COLORS["orange"].upper()
    reading.set_tone("danger")
    assert colour() == theme.COLORS["red"].upper()
    reading.set_tone("")
    assert colour() == plain
