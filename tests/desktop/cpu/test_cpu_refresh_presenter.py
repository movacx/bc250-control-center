import math

from frontends.desktop.core.cpu_refresh_presenter import (
    present_cpu_persistence,
    present_cpu_session_summary,
    present_cpu_telemetry,
    present_cpu_tuning,
)


def test_cpu_telemetry_normalizes_voltage_and_formats_live_values():
    view = present_cpu_telemetry(
        {"cpu_freq": 3487, "cpu_voltage": 1.1, "cpu_temp": 55.2, "power_w": 68}
    )

    assert view.frequency_text.template == "3.49 GHz"
    assert view.voltage_mv == 1100
    assert view.voltage_text.template == "1.100 V"
    assert view.live_frequency_mhz == 3487
    assert view.live_temperature_text == "55 °C"


def test_cpu_telemetry_rejects_non_finite_sensor_values():
    view = present_cpu_telemetry(
        {"cpu_freq": math.nan, "cpu_voltage": math.inf, "cpu_temp": "-inf"}
    )

    assert view.frequency_text.template == "Not detected"
    assert view.voltage_text.template == "Not exposed"
    assert view.temperature_text.template == "Not detected"


def test_persistence_failure_never_claims_enabled_state():
    view = present_cpu_persistence(
        {"enabled": "enabled", "config_exists": True},
        {"persistent": "timed out"},
    )

    assert view.available is False
    assert view.enabled is False
    assert view.service_text.template == "Unavailable"
    assert view.status_value.template == "Unavailable"


def test_valid_boot_config_has_one_consistent_persistence_summary():
    view = present_cpu_persistence(
        {
            "enabled": "enabled",
            "config_exists": True,
            "config_valid": True,
            "config": {
                "exists": True,
                "valid": True,
                "frequency": 3800,
                "scale": -30,
                "max_temperature": 85,
            },
        },
        {},
    )

    assert view.enabled is True
    assert view.status_value.template == "Enabled"
    assert dict(view.status_detail.values) == {
        "frequency": 3800,
        "scale": -30,
        "temperature": 85,
    }


def test_prepared_one_shot_state_is_preserved_over_raw_inactive_state():
    view = present_cpu_persistence(
        {
            "enabled": "enabled",
            "active_state": "inactive",
            "ui_state": "Applied / enabled",
            "ui_detail": "One-shot finished successfully; it will repeat at boot",
            "config_exists": True,
            "config_valid": True,
            "config": {"exists": True, "valid": False},
        },
        {},
    )

    assert view.active_state == "inactive"
    assert view.runtime_text.template == "Applied / enabled"
    assert view.status_detail.template.startswith("One-shot finished")


def test_live_tuning_has_precedence_and_emits_override_safety_copy():
    view = present_cpu_tuning(
        {
            "applied_this_boot": True,
            "config": {"valid": True, "frequency": 3800, "scale": -30},
        },
        {"same_boot": True, "matches_current_config": True, "snapshot": {"scale": -35}},
        {
            "active_in_current_session": True,
            "valid_for_persistence": True,
            "test": {"frequency": 3700, "scale": -28, "temperature": 85, "test_id": "abc"},
        },
        last_applied_frequency=None,
        scale_override_enabled=True,
    )

    assert view.active_source == "live"
    assert view.active_scale == -28
    assert view.live_value.template == "-28"
    assert view.applied_value.template == "{frequency} MHz · scale {scale}"
    assert view.override_status is not None
    assert dict(view.override_status.values)["test_id"] == "abc"


def test_historical_live_test_is_never_presented_as_current():
    view = present_cpu_tuning(
        {},
        {},
        {"matches_detection": True, "active_in_current_session": False, "test": {"scale": -30}},
        last_applied_frequency=3750,
        scale_override_enabled=False,
    )

    assert view.active_source == ""
    assert view.live_value.template == "Not live"
    assert view.applied_value.template == "3750 MHz"


def test_stale_detection_and_absent_tuning_remain_explicit():
    view = present_cpu_tuning(
        {},
        {"recorded": True, "matches_current_config": False},
        {},
        last_applied_frequency=None,
        scale_override_enabled=True,
    )

    assert view.detection_value.template == "Stale"
    assert view.live_value.template == "Unknown"
    assert view.applied_value.template == "None"
    assert view.override_status is None


def test_detection_reference_keeps_requested_and_safe_frequencies_distinct():
    view = present_cpu_tuning(
        {},
        {
            "recorded": True,
            "matches_current_config": True,
            "snapshot": {
                "requested_frequency": 4000,
                "frequency": 3700,
                "scale": -11,
            },
        },
        {},
        last_applied_frequency=None,
        scale_override_enabled=False,
    )

    assert view.detection_value.template == "-11"
    assert view.detection_detail.template.startswith("Requested {requested} MHz → detected {frequency} MHz")
    assert dict(view.detection_detail.values) == {"requested": 4000, "frequency": 3700}


def test_boot_tuning_uses_boot_specific_detail():
    view = present_cpu_tuning(
        {
            "applied_this_boot": True,
            "config": {
                "valid": True,
                "frequency": 3800,
                "scale": -30,
                "max_temperature": 85,
                "estimated_vid": 1050,
            },
        },
        {},
        {},
        last_applied_frequency=None,
        scale_override_enabled=False,
    )

    assert view.active_source == "boot"
    assert view.live_detail.template == "Applied automatically at this boot"
    assert view.applied_detail.template.endswith("applied at boot")


def test_cpu_session_summary_keeps_live_test_and_boot_state_distinct():
    view = present_cpu_session_summary(
        {
            "live_frequency_mhz": 3700,
            "live_temperature_c": 0,
            "detection_matches": True,
            "detection_snapshot": {"frequency": 3800, "scale": -35, "temperature": 85},
            "live_scale_active_this_session": True,
            "live_scale_test": {"frequency": 3700, "scale": -28},
            "service_enabled": True,
            "boot_config": {
                "valid": True,
                "frequency": 3800,
                "scale": -35,
                "max_temperature": 85,
            },
        },
        last_applied_frequency=3700,
    )

    assert dict(view.live_now.values) == {"temperature": 0, "frequency": 3700}
    assert dict(view.manual_live_test.values)["scale"] == -28
    assert dict(view.next_boot.values)["scale"] == -35
    assert view.recommended_next_step.template.startswith("If this exact live scale")


def test_cpu_session_summary_marks_stale_history_without_claiming_live_state():
    view = present_cpu_session_summary(
        {
            "detection_recorded": True,
            "live_scale_test": {"scale": -30},
            "boot_config": {"exists": True},
        },
        last_applied_frequency=None,
    )

    assert view.automatic_detection.template.startswith("A previous detection exists")
    assert view.manual_live_test.template.startswith("A previous manual scale test exists")
    assert view.next_boot.template.startswith("Disabled: a configuration file exists")
    assert view.last_applied.template == "None yet"


def test_direct_manual_session_never_recommends_boot_persistence():
    view = present_cpu_session_summary(
        {
            "live_scale_active_this_session": True,
            "live_scale_test": {
                "frequency": 3700,
                "scale": -34,
                "reference_source": "manual-direct",
            },
        },
        last_applied_frequency=3700,
    )

    assert "direct manual OC" in view.manual_live_test.template
    assert view.recommended_next_step.template.startswith(
        "Keep testing this temporary manual OC"
    )
