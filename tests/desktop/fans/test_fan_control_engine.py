import math
from dataclasses import replace

import pytest

from bc250cc.domain.fan.engine import ChannelMemory
from bc250cc.domain.fan.persistence import (
    FanControlMemory,
    normalize_fan_curve,
    normalize_fan_preset,
    select_fan_control_temperature,
)
from bc250cc.domain.fan.persistence import (
    plan_persistent_fan as _plan_persistent_fan,
)
from bc250cc.infrastructure.system_fan_control import build_system_fan_policy


def plan_persistent_fan(metric, config, memory, *, now):
    return _plan_persistent_fan(
        metric, config, memory, now=now, policy=build_system_fan_policy(config),
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


def test_curve_changes_use_engine_asymmetric_steps():
    memory = FanControlMemory(
        last_target=(2, 100, "curve"), last_percent=100,
        last_temperature=80, last_apply=0,
        channel_memory=ChannelMemory(percent=100, source="curve", goal_percent=100,
                                     reference_temperature=80, changed_at=0),
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
            channel_memory=ChannelMemory(percent=40, source="curve", goal_percent=40,
                                         reference_temperature=40, changed_at=0),
        ),
        now=10,
    )
    assert rise.target.percent == 100


def test_string_false_does_not_enable_persistent_hardware_control():
    assert normalize_fan_curve({"enabled": "false"})["enabled"] is False
    assert normalize_fan_preset({
        "enabled": "false", "preset": "maximum"
    })["enabled"] is False


def committed(decision, *, verified_at):
    return FanControlMemory(
        last_target=decision.target.identity, last_percent=decision.target.percent,
        last_apply=verified_at, last_verify=verified_at,
        channel_memory=decision.channel_memory,
        missing_since=decision.missing_since,
        expected_sensors=decision.expected_sensors,
    )


def test_critical_is_100_latched_until_recovery_and_holds_when_sensor_disappears():
    config = curve_config(fan_daemon_failsafe_percent=50)
    critical = plan_persistent_fan({"gpu_temp": 96}, config, FanControlMemory(), now=10)
    assert critical.target.percent == 100
    memory = committed(critical, verified_at=10)
    for metric in ({"gpu_temp": 92}, {"cpu_temp": 40}, {}):
        holding = plan_persistent_fan(metric, config, memory, now=16)
        assert holding.target.percent == 100
        assert holding.target.source == "curve:critical"
    recovered = plan_persistent_fan({"gpu_temp": 89}, config, memory, now=16)
    assert recovered.target.source == "curve"


def test_sensor_loss_failsafe_never_lowers_a_verified_duty():
    config = curve_config(fan_daemon_failsafe_percent=50)
    first = plan_persistent_fan({"gpu_temp": 80}, config, FanControlMemory(), now=10)
    memory = replace(committed(first, verified_at=10), missing_since=11)
    lost = plan_persistent_fan({}, config, memory, now=30)
    assert lost.target.source == "curve:failsafe"
    assert lost.target.percent == 100


def test_explicit_engine_steps_change_at_most_once_per_five_seconds():
    config = {"fan_channels": {"3": {
        "mode": "curve", "source": "gpu", "points": [[40, 40], [80, 100]],
        "max_up_step_percent": 20, "max_down_step_percent": 10,
    }}}
    first = plan_persistent_fan({"gpu_temp": 40}, config, FanControlMemory(), now=10)
    memory = committed(first, verified_at=10)
    too_soon = plan_persistent_fan({"gpu_temp": 80}, config, memory, now=14)
    assert too_soon.target.percent == 40
    rise = plan_persistent_fan({"gpu_temp": 80}, config, memory, now=15)
    assert rise.target.percent == 60
    memory = committed(rise, verified_at=15)
    held = plan_persistent_fan({"gpu_temp": 80}, config, memory, now=19)
    assert held.target.percent == 60
    assert plan_persistent_fan({"gpu_temp": 80}, config, memory, now=20).target.percent == 80


def test_offsets_are_applied_once_and_critical_uses_raw_temperature():
    config = curve_config(fan_daemon_sensor_offsets_c={"gpu": 10})
    decision = plan_persistent_fan({"gpu_temp": 50}, config, FanControlMemory(), now=10)
    assert decision.target.temperature == 60
    assert decision.target.raw_temperature == 50
    assert decision.target.percent == 70
    config["fan_daemon_sensor_offsets_c"] = {"gpu": -30}
    assert plan_persistent_fan(
        {"gpu_temp": 96}, config, FanControlMemory(), now=10,
    ).target.source == "curve:critical"


def test_only_nonfirmware_channels_count_toward_fallback_limit():
    config = {"fan_channels": {
        "2": {"mode": "firmware"}, "3": {"mode": "fixed", "percent": 65},
    }}
    single = plan_persistent_fan({}, config, FanControlMemory(), now=10)
    assert single.target.pwm == 3
    config["fan_channels"]["4"] = {"mode": "fixed", "percent": 70}
    refused = plan_persistent_fan({}, config, FanControlMemory(), now=20)
    assert refused.action == "disabled"
    assert refused.target is None
    assert "Root fan service required" in refused.reason


def test_channel_change_discards_previous_channels_smoothing_baseline():
    memory = FanControlMemory(
        last_target=(2, 100, "curve"),
        channel_memory=ChannelMemory(percent=100, source="critical", changed_at=10),
    )
    config = curve_config()
    config["fan_curve"]["pwm"] = 3
    decision = plan_persistent_fan({"gpu_temp": 40}, config, memory, now=11)
    assert decision.target.pwm == 3
    assert decision.target.percent == 40


@pytest.mark.parametrize("temperature", (30, 40, 45.5, 50, 60, 70, 80))
def test_migrated_curve_preserves_steady_state_interpolation(temperature):
    from bc250cc.domain.fan.persistence import fan_curve_percent_for_temp

    config = curve_config()
    decision = plan_persistent_fan(
        {"gpu_temp": temperature}, config, FanControlMemory(), now=10,
    )
    assert decision.target.percent == fan_curve_percent_for_temp(temperature, config["fan_curve"])
