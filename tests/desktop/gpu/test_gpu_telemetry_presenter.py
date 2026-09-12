import math
import time

from PyQt6.QtWidgets import QApplication

from bc250cc.application.gpu.telemetry import format_bytes, present_gpu_telemetry
from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


def test_gpu_telemetry_prefers_repository_busy_and_formats_live_counters():
    telemetry = present_gpu_telemetry(
        {
            "gpu_busy": 37,
            "voltaje_actual": 930,
            "vram_total": 16 * 1024**3,
            "vram_usado": 4 * 1024**3,
        },
        {
            "gpu_temp": 61.25,
            "gpu_busy": 99,
            "power_w": 48.2,
            "power_is_total": True,
            "power_label": "Board power",
        },
    )
    assert telemetry.temperature == 61.25
    assert telemetry.utilization == 37
    assert telemetry.voltage_text.template == "930 mV"
    assert telemetry.temperature_text.template == "61.2 °C"
    assert telemetry.utilization_text.template == "37 %"
    assert telemetry.vram_value.template == "25 %"
    assert dict(telemetry.vram_detail.values) == {
        "used": "4.0 GiB", "total": "16.0 GiB"
    }
    assert telemetry.power_text.template == "48 W"
    assert telemetry.power_detail.template == "Dedicated total-board power sensor"


def test_gpu_telemetry_distinguishes_missing_soc_and_total_power_evidence():
    soc = present_gpu_telemetry({}, {"power_scope": "gpu_soc"})
    missing = present_gpu_telemetry({}, {})
    assert soc.power_detail.template == "AMDGPU SoC power sensor; total board power unavailable"
    assert missing.power_detail.template == "No live power sensor exposed"
    assert missing.voltage_text.template == "Not exposed"
    assert missing.temperature_text.template == "Not detected"
    assert missing.utilization is None
    assert missing.vram_detail.template == "VRAM counters unavailable"


def test_gpu_telemetry_marks_an_idle_missing_voltage_as_not_sampled_not_broken():
    telemetry = present_gpu_telemetry({"gpu_busy": 0}, {})
    assert telemetry.voltage_text.template == "Not exposed at idle"


def test_non_finite_telemetry_cannot_generate_nan_or_infinite_ui_values():
    telemetry = present_gpu_telemetry(
        {"vram_total": math.inf, "vram_usado": math.nan},
        {"gpu_temp": math.nan, "power_w": math.inf},
    )
    assert telemetry.temperature == 0
    assert telemetry.vram_value.template == "Not detected"
    assert telemetry.power_text.template == "Not detected"
    assert format_bytes(math.nan) == "--"


def test_production_telemetry_adapter_preserves_existing_dictionary_contract():
    telemetry = GpuGovernorPage._telemetry_copy(
        {"gpu_busy": None, "vram_total": 1024, "vram_usado": 512},
        {"gpu_busy": 20, "gpu_temp": 50},
    )
    assert telemetry["temperature"] == 50
    assert telemetry["utilization"] == 20
    assert telemetry["temperature_text"] == "50.0 °C"
    assert telemetry["utilization_text"] == "20 %"
    assert telemetry["vram_value"] == "50 %"
    assert telemetry["vram_detail"] == "512 B of 1.0 KiB"


def test_new_safe_point_roles_are_translated_in_every_supported_language():
    roles = (
        "Current SCLK", "Active ceiling", "High OC / undervolt lab",
        "High OC safe-point", "Undervolt warning", "OC safe-point", "Safe-point",
    )
    for language in SUPPORTED_LANGUAGES - {"en"}:
        assert all(tr(role, language) != role for role in roles), language


def test_corrupt_and_stale_diagnostics_override_live_tiles(qtbot):
    import json

    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.current_state = {
        "apu_telemetry": {
            "sampled_at_monotonic": time.monotonic(),
            "status": "invalid",
            "metrics": {
                "voltage": {"value": None, "raw": "40058", "status": "invalid"},
                "mclk": {"value": None, "status": "invalid"},
                "fclk": {"value": None, "status": "unverified"},
            },
        },
        "cyan_telemetry": None,
    }

    def refresh():
        page._update_metric_widgets(
            page._telemetry_copy({"voltaje_actual": 40058}, {}),
            frequency=1000, mclk=2, minimum=1000, maximum=1850,
            running=True, active="active", enabled="enabled",
        )

    refresh()
    assert page.voltage_metric.value.text() == tr("Invalid")
    assert page.mclk_metric.value.text() == tr("Invalid")
    assert page.metrics_status.text() == tr("Warning")
    assert "FCLK: " + tr("Not available") in page.memory_clocks_line.text()
    page._copy_apu_diagnostics()
    copied = json.loads(QApplication.clipboard().text())
    assert copied["metrics"]["voltage"]["raw"] == "40058"
    page.current_state["apu_telemetry"]["sampled_at_monotonic"] -= 10
    refresh()
    assert page.voltage_metric.value.text() == tr("Stale")
    assert page.sclk_metric.value.text() == tr("Stale")


def test_diagnostic_actions_are_translated_in_every_supported_language():
    for language in SUPPORTED_LANGUAGES - {"en"}:
        for source in ("Copy diagnostics", "Independent memory clocks require a verified source."):
            assert tr(source, language) != source, language
