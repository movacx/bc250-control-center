import pytest

from bc250cc.application.fan.policy import request_from_percent, validate_pwm
from bc250cc.application.health.aggregator import aggregate_findings
from bc250cc.domain.fan.models import FanChannel, FanMode
from bc250cc.domain.health.models import HealthFinding, HealthStatus


def test_fan_request_is_bounded_and_converts_to_hwmon_range():
    channel = FanChannel("hwmon2:pwm3", 3, True, FanMode.MANUAL)
    request = request_from_percent(channel, 60)
    assert request.raw_pwm == 153


def test_fan_request_rejects_non_writable_and_coerced_inputs():
    with pytest.raises(ValueError):
        request_from_percent(FanChannel("hwmon2:pwm3", 3, False, FanMode.MANUAL), 60)
    with pytest.raises(ValueError):
        request_from_percent(FanChannel("hwmon2:pwm3", 3, True, FanMode.MANUAL), 60.5)


def test_pwm_policy_rejects_invalid_values_without_hardware_access():
    assert validate_pwm(2, 255) == (2, 255)
    try:
        validate_pwm(2, 256)
    except ValueError as error:
        assert "between 0 and 255" in str(error)
    else:
        raise AssertionError("invalid PWM request was accepted")


def test_pwm_policy_rejects_decimal_values_instead_of_truncating_them():
    with pytest.raises(ValueError):
        validate_pwm(2.9, 120)
    with pytest.raises(ValueError):
        validate_pwm(2, 120.9)


def test_health_aggregation_is_deterministic_and_preserves_provenance():
    snapshot = aggregate_findings([
        HealthFinding("z", HealthStatus.WARNING, "Z", "z detail"),
        HealthFinding("a", HealthStatus.HEALTHY, "A", "a detail"),
    ])
    assert [item.identifier for item in snapshot.findings] == ["a", "z"]
    assert snapshot.status is HealthStatus.WARNING


def test_health_domain_rejects_untyped_or_empty_findings():
    with pytest.raises(ValueError):
        HealthFinding("", HealthStatus.ERROR, "Error", "detail")
    with pytest.raises(ValueError):
        HealthFinding("gpu", "error", "Error", "detail")


def test_fan_channel_constructor_rejects_untyped_mode_and_index():
    with pytest.raises(ValueError):
        FanChannel("hwmon2:pwm3", 3.5, True, FanMode.MANUAL)
    with pytest.raises(ValueError):
        FanChannel("hwmon2:pwm3", 3, True, "manual")
