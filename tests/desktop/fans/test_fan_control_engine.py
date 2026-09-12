import math

import pytest

from bc250cc.domain.fan.persistence import (
    FanControlMemory,
    normalize_fan_curve,
    normalize_fan_preset,
    plan_persistent_fan,
    select_fan_control_temperature,
)


def curve_config(**overrides):
    config = {
        "fan_curve": {
            "enabled": True, "pwm": 2,
            "points": [(40, 40), (60, 70), (80, 100)],
        },
        "fan_preset": {"enabled": False},
    }
    config.update(overrides)
    return config


def test_disabled_configuration_has_no_target():
    decision = plan_persistent_fan({}, {}, FanControlMemory(), now=10)
    assert decision.action == "disabled"
    assert decision.target is None


def test_sensor_loss_transitions_wait_then_failsafe():
    first = plan_persistent_fan(
        {"gpu_temp": None}, curve_config(), FanControlMemory(), now=10
    )
    assert first.action == "sensor-missing"
    assert first.missing_since == 10

    waiting = plan_persistent_fan(
        {"gpu_temp": None}, curve_config(),
        FanControlMemory(missing_since=10), now=20,
    )
    assert waiting.action == "sensor-wait"

    failsafe = plan_persistent_fan(
        {"gpu_temp": None}, curve_config(),
        FanControlMemory(missing_since=10), now=30,
    )
    assert failsafe.action == "apply"
    assert failsafe.target.source == "curve:failsafe"
    assert failsafe.target.percent == 100
    assert failsafe.target.raw == 255


def test_curve_uses_the_hottest_available_apu_temperature():
    decision = plan_persistent_fan(
        {"gpu_temp": 55, "cpu_temp": 80},
        curve_config(),
        FanControlMemory(),
        now=10,
    )

    assert decision.target.temperature == 80
    assert decision.target.temperature_sensor == "cpu"
    assert decision.target.percent == 100


def test_curve_falls_back_to_either_valid_temperature_sensor():
    assert select_fan_control_temperature(
        {"gpu_temp": None, "cpu_temp": 62}
    ) == (62.0, "cpu")
    assert select_fan_control_temperature(
        {"gpu_temp": 64, "cpu_temp": math.nan}
    ) == (64.0, "gpu")


def test_curve_includes_vrm_and_board_sensors_with_offsets():
    metric = {
        "gpu_temp": 70,
        "cpu_temp": 72,
        "vrm_temp": 78,
        "board_temp": 60,
    }
    assert select_fan_control_temperature(metric) == (78.0, "vrm")
    assert select_fan_control_temperature(
        metric, {"fan_daemon_sensor_offsets_c": {"cpu": 10}}
    ) == (82.0, "cpu")


def test_stale_sensor_is_excluded_from_fan_control():
    metric = {
        "gpu_temp": 70,
        "vrm_temp": 100,
        "temperature_sensor_times": {"gpu": 99, "vrm": 80},
    }
    assert select_fan_control_temperature(metric, now=100) == (70.0, "gpu")

    del metric["temperature_sensor_times"]["vrm"]
    assert select_fan_control_temperature(metric, now=100) == (70.0, "gpu")
    metric["temperature_sensor_times"].clear()
    assert select_fan_control_temperature(metric, now=100) == (None, None)


def test_critical_sensor_forces_immediate_failsafe():
    decision = plan_persistent_fan(
        {"gpu_temp": 70, "vrm_temp": 108},
        curve_config(),
        FanControlMemory(last_apply=9, last_percent=40),
        now=10,
    )
    assert decision.action == "apply"
    assert decision.target.source == "curve:critical"
    assert decision.target.temperature_sensor == "vrm"
    assert decision.target.raw_temperature == 108
    assert decision.target.percent == 100


@pytest.mark.parametrize("temperature", (None, math.nan, math.inf, "invalid"))
def test_nonfinite_or_invalid_temperature_never_enters_normal_curve(temperature):
    decision = plan_persistent_fan(
        {"gpu_temp": temperature}, curve_config(), FanControlMemory(), now=10
    )
    assert decision.action == "sensor-missing"


def test_same_target_skips_then_requests_periodic_verification():
    target = (2, 70, "preset:cooling")
    config = {
        "fan_curve": {"enabled": False},
        "fan_preset": {
            "enabled": True, "preset": "cooling", "percent": 70, "pwm": 2,
        },
    }
    recent = plan_persistent_fan(
        {}, config,
        FanControlMemory(last_target=target, last_apply=10, last_verify=10), now=20,
    )
    assert recent.action == "skip"
    due = plan_persistent_fan(
        {}, config,
        FanControlMemory(last_target=target, last_apply=10, last_verify=10), now=45,
    )
    assert due.action == "verify"


def test_downward_curve_change_is_bounded_but_rise_is_immediate():
    memory = FanControlMemory(
        last_target=(2, 100, "curve"), last_percent=100,
        last_temperature=80, last_apply=0,
    )
    down = plan_persistent_fan(
        {"gpu_temp": 40}, curve_config(), memory, now=10
    )
    assert down.target.percent == 90
    rise = plan_persistent_fan(
        {"gpu_temp": 80}, curve_config(),
        FanControlMemory(
            last_target=(2, 40, "curve"), last_percent=40,
            last_temperature=40, last_apply=0,
        ),
        now=10,
    )
    assert rise.target.percent == 100


def test_string_false_does_not_enable_persistent_hardware_control():
    assert normalize_fan_curve({"enabled": "false"})["enabled"] is False
    assert normalize_fan_preset({
        "enabled": "false", "preset": "maximum"
    })["enabled"] is False
