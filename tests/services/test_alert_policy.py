import math

from frontends.desktop.core.alert_policy import (
    AlertEvent,
    classify_alerts,
    evaluate_alert_cooldown,
)


def keys(result):
    return {event.key for event in result.events}


def test_nonfinite_values_never_trigger_temperature_or_load_alerts():
    result = classify_alerts(
        {"cpu": {"temperature_c": math.inf}, "gpu": {"temperature_c": math.nan, "usage_percent": math.inf}},
        {"current_max": 2200},
        gpu_history=(),
        now=10,
    )

    assert not keys(result)
    assert result.gpu_history == ()


def test_critical_thresholds_and_high_oc_can_coexist():
    result = classify_alerts(
        {"cpu": {"temperature_c": 91}, "gpu": {"temperature_c": 86, "usage_percent": 90}, "memory": {"usage_percent": 95}},
        {"current_max": 2100, "service_active": "active", "dbus_ok": True},
        gpu_history=(),
        now=10,
    )

    assert keys(result) == {"cpu-temp-critical", "gpu-temp-critical", "memory-critical", "gpu-high-oc-load"}


def test_history_is_pruned_and_rapid_rise_requires_four_samples():
    result = classify_alerts(
        {"gpu": {"temperature_c": 72}},
        {},
        gpu_history=((0, 30), (50, 62), (55, 63)),
        now=61,
    )

    assert "gpu-temp-rise" not in keys(result)
    assert result.gpu_history == ((50, 62), (55, 63), (61.0, 72.0))
    raised = classify_alerts(
        {"gpu": {"temperature_c": 72}}, {},
        gpu_history=((45, 60), (50, 62), (55, 63)), now=60,
    )
    assert "gpu-temp-rise" in keys(raised)


def test_inactive_governor_has_precedence_over_dbus_alert():
    result = classify_alerts({}, {"service_active": "failed", "dbus_ok": False}, gpu_history=(), now=1)

    assert keys(result) == {"governor-inactive"}


def test_warning_thresholds_are_distinct_from_critical_thresholds():
    result = classify_alerts(
        {
            "cpu": {"temperature_c": 82},
            "gpu": {"temperature_c": 78},
            "memory": {"usage_percent": 85, "swap_percent": 0},
        },
        {"service_active": "running", "dbus_ok": True},
        gpu_history=(),
        now=1,
    )

    assert keys(result) == {"cpu-temp-high", "gpu-temp-high", "memory-warning"}


def test_active_governor_with_failed_dbus_emits_only_dbus_alert():
    result = classify_alerts(
        {},
        {"service_active": "active", "dbus_ok": False},
        gpu_history=(),
        now=1,
    )

    assert keys(result) == {"governor-dbus"}


def test_first_alert_is_not_suppressed_early_after_boot():
    event = AlertEvent("thermal", "title", "message", cooldown_seconds=300)

    decision = evaluate_alert_cooldown(event, last_alerts={}, now=10)

    assert decision.accepted is True
    assert decision.reason == "first-event"


def test_repeated_alert_obeys_cooldown_and_accepts_after_elapsed_time():
    event = AlertEvent("thermal", "title", "message", cooldown_seconds=300)

    blocked = evaluate_alert_cooldown(event, last_alerts={"thermal": 100}, now=200)
    accepted = evaluate_alert_cooldown(event, last_alerts={"thermal": 100}, now=401)

    assert (blocked.accepted, blocked.reason) == (False, "cooldown")
    assert (accepted.accepted, accepted.reason) == (True, "elapsed")


def test_monotonic_clock_reset_never_suppresses_safety_alert():
    event = AlertEvent("thermal", "title", "message", cooldown_seconds=300)

    decision = evaluate_alert_cooldown(event, last_alerts={"thermal": 500}, now=5)

    assert decision.accepted is True
    assert decision.reason == "clock-reset"
