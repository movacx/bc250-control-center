from bc250cc.infrastructure.governor_health_policy import (
    classify_cyan_health,
    classify_oberon_health,
)


def cyan(**updates):
    values = {
        "migration": {},
        "frequency_range": {"valid": True, "mode": "profile"},
        "safe_points": ({"frequency": 1000},),
        "telemetry": {"valid": True, "fix_metrics": True, "fix_frequency": True},
        "runtime": {"supports_frequency_fix": True},
        "needs_frequency_fix": True,
    }
    values.update(updates)
    return classify_cyan_health(**values)


def test_cyan_legacy_and_invalid_range_have_deterministic_repairs():
    legacy = cyan(migration={"needed": True, "reason": "legacy"})
    invalid = cyan(frequency_range={"valid": False, "error": "overlap"})

    assert legacy.repair_action == "migrate-legacy-frequency-range"
    assert invalid.repair_action == "clear-frequency-range"


def test_cyan_runtime_fix_precedes_telemetry_repair():
    decision = cyan(
        runtime={"supports_frequency_fix": False},
        telemetry={"valid": False},
    )

    assert decision.title == "Governor runtime"
    assert decision.repair_action == "update-cyan-runtime"


def test_cyan_healthy_requires_points_metrics_and_frequency_fix():
    assert cyan().status == "healthy"
    assert cyan(safe_points=()).status == "error"
    assert cyan(
        telemetry={"valid": True, "fix_metrics": True, "fix_frequency": False},
        needs_frequency_fix=False,
    ).status == "healthy"
    # The metrics overlay is optional upstream. A known incompatible kernel
    # must not force it back on merely to satisfy a configuration check.
    assert cyan(telemetry={"valid": True, "fix_metrics": False, "fix_frequency": True}).status == "healthy"


def test_cyan_metrics_overlay_failure_requires_explicit_compatibility_review():
    decision = cyan(runtime={
        "supports_frequency_fix": True,
        "metrics_fix_runtime_error": True,
    })

    assert decision.status == "warning"
    assert decision.repair_action == "review-cyan-compatibility"
    assert "frequency reporting remains independent" in decision.detail
    assert "four Cyan compatibility controls" in decision.recommendation


def test_oberon_voltage_floor_is_backend_specific():
    safe = classify_oberon_health(
        {"safe_voltage": True, "frequency_min": 500, "frequency_max": 2000, "voltage_min": 700, "voltage_max": 1000},
        voltage_floor_mv=650,
    )
    unsafe = classify_oberon_health({"safe_voltage": False}, voltage_floor_mv=650)

    assert safe.status == "healthy"
    assert unsafe.status == "error"
    assert "650 mV" in unsafe.detail
