from bc250cc.application.gpu.diagnostics import (
    compact_diagnostic_path,
    present_gpu_diagnostics,
)
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


def _state(**updates):
    state = {
        "vendor": "0x1002",
        "device": "0x13fe",
        "driver": "amdgpu",
        "gpu_path": "/sys/class/drm/card1/device",
        "config_path": "/etc/cyan-skillfish-governor-smu/config.toml",
        "frequency_range": {"valid": True, "enabled": False},
        "safe_points_voltage_errors": [],
        "safe_points_missing_voltage": [],
        "safe_points_duplicate_frequencies": [],
        "power_state": "active",
        "power_level": "manual",
    }
    state.update(updates)
    return state


def _values(text):
    return dict(text.values)


def test_diagnostic_paths_are_compact_by_default_and_exact_on_demand():
    compact = present_gpu_diagnostics(_state(), detailed=False)
    detailed = present_gpu_diagnostics(_state(), detailed=True)
    assert compact.driver.detail.template == "…/device"
    assert compact.config.detail.template == "…/config.toml"
    assert detailed.driver.detail.template == "/sys/class/drm/card1/device"
    assert detailed.config.detail.template == "/etc/cyan-skillfish-governor-smu/config.toml"
    assert compact_diagnostic_path(None) == "--"


def test_frequency_range_diagnostics_cover_invalid_floor_profile_and_custom():
    invalid = present_gpu_diagnostics(
        _state(frequency_range={"valid": False, "error": "bad range"}),
        detailed=False,
    ).config.value
    assert invalid.template == "invalid: {error}"
    assert _values(invalid) == {"error": "bad range"}

    floor = present_gpu_diagnostics(
        _state(frequency_range={"valid": True, "mode": "floor", "min": "1000"}),
        detailed=False,
    ).config.value
    assert _values(floor) == {"minimum": 1000}

    profile = present_gpu_diagnostics(_state(), detailed=False).config.value
    assert profile.template == "profile mode; section disabled"

    unlimited = present_gpu_diagnostics(
        _state(
            frequency_range={
                "valid": True,
                "enabled": True,
                "min": 500,
                "max": 0,
            }
        ),
        detailed=False,
    ).config.value
    assert _values(unlimited) == {"minimum": 500, "maximum": "unlimited"}
    assert unlimited.translate_values == ("maximum",)


def test_curve_collection_and_power_diagnostics_are_typed_and_robust():
    presentation = present_gpu_diagnostics(
        _state(
            safe_points_voltage_errors=[
                {
                    "previous_frequency": 1500,
                    "previous_voltage": 950,
                    "frequency": 1850,
                    "voltage": 900,
                }
            ],
            safe_points_missing_voltage=[{"frequency": 1850}, 2000],
            safe_points_duplicate_frequencies=[1500, {"frequency": 1850}],
        ),
        detailed=False,
    )
    assert presentation.curve.value.template == "Invalid"
    assert presentation.curve.detail.template == "1500/950 > 1850/900"
    assert presentation.missing.value.template == "2"
    assert presentation.missing.detail.template == "1850, 2000"
    assert presentation.duplicates.detail.template == "1500, 1850"
    assert _values(presentation.power.detail) == {"level": "manual"}


def test_empty_curve_and_collections_have_translation_ready_copy():
    presentation = present_gpu_diagnostics(_state(), detailed=False)
    assert presentation.curve.value.template == "Valid"
    assert presentation.missing.value.template == "None"
    assert presentation.duplicates.value.template == "None"
    assert presentation.power.value.template == "active"
    assert presentation.power.value.literal is True


def test_real_gpu_page_renders_mixed_missing_frequency_entries(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    state = _state(
        safe_points_missing_voltage=[{"frequency": 1850}, 2000],
        frequency_range={"valid": True, "enabled": True, "min": 500, "max": 0},
    )

    page._update_diagnostics(state)

    assert page.missing_line.value.text() == "2"
    assert page.missing_line.detail.text() == "1850, 2000"
    assert page.driver_line.detail.text() == "…/device"
    assert page.config_line.value.text() == "custom 500–unlimited"

    page.current_state = state
    page.set_detailed_diagnostics(True)
    assert page.driver_line.detail.text() == "/sys/class/drm/card1/device"
