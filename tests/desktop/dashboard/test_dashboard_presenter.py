import math

from frontends.desktop.core.dashboard_presenter import (
    present_activities,
    present_cu_labels,
    present_dashboard_fan,
)


def test_dashboard_cu_labels_distinguish_unverified_and_saved_states():
    assert present_cu_labels({}) == ("Not verified", "Not detected")
    assert present_cu_labels({"mode_key": "full", "boot_sync_key": "saved"}) == (
        "full dispatch",
        "Saved",
    )


def test_dashboard_prefers_pump_row_and_normalizes_label_and_pwm():
    view = present_dashboard_fan(
        {
            "driver_control": True,
            "sensores": {
                "fans": [
                    {"label": "CPU Fan", "rpm": 900},
                    {"label": "Pump Fan / J4003", "rpm": 1700, "pwm": 128},
                ]
            },
        },
        performance_rpm=800,
    )

    assert view.rpm == 1700
    assert view.duty_percent == 50
    assert view.label == "Pump Fan · J4003"
    assert view.pwm_ready is True


def test_dashboard_fallback_marks_fan_available_without_claiming_pwm_write():
    view = present_dashboard_fan({}, performance_rpm=0).with_fallback(1650, "Pump Fan J4003")

    assert view.available is True
    assert view.rpm == 1650
    assert view.mode == "read only"
    assert view.pwm_ready is False


def test_dashboard_fan_rejects_nonfinite_rpm_pwm_and_fallback():
    view = present_dashboard_fan(
        {"sensores": {"fans": [{"label": "Pump Fan", "rpm": math.inf, "pwm": math.nan}]}},
        performance_rpm=math.inf,
    ).with_fallback(math.nan, "fallback")

    assert view.rpm == 0
    assert view.duty_percent == 0
    assert view.label == "fallback"


def test_dashboard_activity_normalization_ignores_invalid_rows_and_truncates():
    events = [
        None,
        {"titulo": "A" * 100, "fecha": "2026-08-13 12:34:56", "nivel": "warning"},
        {"detail": "ignored key"},
    ]
    result = present_activities(events)

    assert len(result) == 2
    assert result[0] == ("A" * 78, "12:34:56", "warning")
    assert result[1][0] == "System event"
