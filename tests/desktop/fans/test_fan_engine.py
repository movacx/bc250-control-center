"""The shared fan-control engine (docs/FAN_CONTROL_V2.md)."""

from __future__ import annotations

import copy

import pytest

from bc250cc.domain.fan import engine
from bc250cc.domain.fan.engine import ChannelMemory


def _policy(**channels) -> dict:
    raw = {
        "schema": 2,
        "channels": channels or {"2": {"mode": "curve", "points": [[40, 30], [80, 100]]}},
    }
    return engine.validate_policy(raw)


def _run(policy, readings_by_time, *, expected=()):
    """Drive plan() through a list of (now, readings), committing every
    proposal as a successful write would. Returns the decisions per tick."""
    memories: dict[int, ChannelMemory] = {}
    ticks = []
    for now, readings in readings_by_time:
        decisions, memories = engine.plan(policy, readings, memories, now, expected=expected)
        ticks.append(decisions)
    return ticks


# ------------------------------------------------------------------ policy


def test_forum_report_every_channel_has_its_own_policy():
    # PWM 1, 3, 4, 5 on curves, PWM 2 (AIO pump) fixed at 90 %.
    curve = {"mode": "curve", "source": "gpu", "points": [[40, 20], [80, 100]]}
    policy = _policy(**{
        "1": curve, "3": curve, "4": curve, "5": curve,
        "2": {"mode": "fixed", "percent": 90, "role": "pump"},
    })

    decisions, _ = engine.plan(policy, {"gpu": 60.0}, {}, 0.0)

    assert {pwm: d.percent for pwm, d in decisions.items()} == {
        1: 60, 2: 90, 3: 60, 4: 60, 5: 60,
    }
    assert engine.controlled_channels(policy) == [1, 2, 3, 4, 5]


def test_channels_are_sorted_and_defaults_filled():
    policy = _policy(**{
        "5": {"mode": "firmware"},
        "1": {"mode": "curve", "points": [[30, 20], [70, 90]]},
    })

    assert list(policy["channels"]) == ["1", "5"]
    one = policy["channels"]["1"]
    assert one["source"] == "hottest"
    assert one["min_percent"] == 0 and one["max_percent"] == 100
    assert one["max_down_step_percent"] == 10
    assert policy["critical_c"] == engine.DEFAULT_CRITICAL_C
    assert engine.controlled_channels(policy) == [1]


@pytest.mark.parametrize(
    "channels",
    [
        {},
        {"0": {"mode": "fixed", "percent": 50}},
        {"13": {"mode": "fixed", "percent": 50}},
        {"02": {"mode": "fixed", "percent": 50}},
        {"2": {"mode": "auto"}},
        {"2": {"mode": "fixed", "percent": 101}},
        {"2": {"mode": "fixed", "percent": 50, "colour": "red"}},
        {"2": {"mode": "curve", "points": [[40, 30]]}},
        {"2": {"mode": "curve", "points": [[40, 30], [40, 60]]}},
        {"2": {"mode": "curve", "points": [[40, 30], [60, 60]], "source": "ssd"}},
        {"2": {"mode": "mix", "mix": [{"source": "gpu", "points": [[40, 30], [60, 60]]}]}},
        {"2": {"mode": "fixed", "percent": 20, "role": "pump"}},
        {"2": {"mode": "curve", "points": [[40, 0], [60, 60]], "role": "pump", "min_percent": 10}},
        {"2": {"mode": "curve", "points": [[40, 0], [60, 60]], "min_percent": 60, "max_percent": 50}},
        {"2": {"mode": "fixed", "percent": True}},
    ],
)
def test_malformed_policies_are_refused(channels):
    with pytest.raises(ValueError):
        engine.validate_policy({"schema": 2, "channels": channels})


def test_unknown_schema_and_keys_are_refused():
    with pytest.raises(ValueError):
        engine.validate_policy({"schema": 3, "channels": {}})
    with pytest.raises(ValueError):
        engine.validate_policy({
            "schema": 2, "channels": {"2": {"mode": "firmware"}}, "extra": 1,
        })


def test_a_pump_on_a_curve_defaults_to_a_safe_floor():
    policy = _policy(**{"2": {"mode": "curve", "role": "pump", "points": [[30, 0], [80, 100]]}})

    decisions, _ = engine.plan(policy, {"cpu": 20.0}, {}, 0.0)

    assert decisions[2].percent == engine.PUMP_DEFAULT_MIN_PERCENT


@pytest.mark.parametrize(
    ("legacy", "expected_channel"),
    [
        (
            {"mode": "curve", "pwm": 3, "points": [[50, 70], [65, 100], [70, 100]],
             "hysteresis_c": 2.0, "deadband_percent": 3, "max_down_step_percent": 5},
            {"mode": "curve", "source": "hottest", "points": [[50, 70], [65, 100], [70, 100]],
             "hysteresis_c": 2.0, "deadband_percent": 3, "max_down_step_percent": 5},
        ),
        (
            {"mode": "preset", "pwm": 2, "percent": 45, "preset": "quiet"},
            {"mode": "fixed", "percent": 45, "preset": "quiet"},
        ),
        (
            {"mode": "fixed", "pwm": 4, "percent": 80, "preset": ""},
            {"mode": "fixed", "percent": 80, "preset": ""},
        ),
    ],
)
def test_schema_1_policies_migrate_to_one_channel(legacy, expected_channel):
    legacy = {"schema": 1, "failsafe_percent": 90, "offsets_c": {"gpu": -3}, **legacy}

    policy = engine.validate_policy(legacy)

    assert policy["schema"] == 2
    assert list(policy["channels"]) == [str(legacy["pwm"])]
    channel = policy["channels"][str(legacy["pwm"])]
    for key, value in expected_channel.items():
        assert channel[key] == value
    assert policy["failsafe_percent"] == 90
    assert policy["offsets_c"]["gpu"] == -3.0


def test_schema_1_still_needs_three_points():
    with pytest.raises(ValueError):
        engine.validate_policy({"schema": 1, "mode": "curve", "pwm": 2, "points": [[40, 30], [60, 60]]})


def test_validation_is_idempotent():
    policy = _policy(**{
        "2": {"mode": "mix", "mix": [
            {"source": "gpu", "points": [[50, 30], [80, 100]]},
            {"source": "vrm", "points": [[70, 30], [95, 100]]},
        ]},
    })
    assert engine.validate_policy(copy.deepcopy(policy)) == policy


# --------------------------------------------------------------- planning


def test_interpolation_matches_v1_rounding():
    points = [[50, 70], [65, 100], [70, 100]]
    assert engine.interpolate(points, 20) == 70
    assert engine.interpolate(points, 57.5) == 85
    assert engine.interpolate(points, 51) == 72
    assert engine.interpolate(points, 99) == 100


def test_a_curve_follows_its_own_sensor_not_the_hottest():
    policy = _policy(**{
        "1": {"mode": "curve", "source": "cpu", "points": [[40, 20], [80, 100]]},
        "3": {"mode": "curve", "source": "gpu", "points": [[40, 20], [80, 100]]},
    })

    decisions, _ = engine.plan(policy, {"cpu": 40.0, "gpu": 80.0}, {}, 0.0)

    assert (decisions[1].percent, decisions[1].sensor) == (20, "cpu")
    assert (decisions[3].percent, decisions[3].sensor) == (100, "gpu")


def test_a_mix_takes_the_highest_member():
    policy = _policy(**{
        "2": {"mode": "mix", "mix": [
            {"source": "gpu", "points": [[50, 30], [80, 100]]},
            {"source": "vrm", "points": [[70, 30], [95, 100]]},
        ]},
    })

    decisions, _ = engine.plan(policy, {"gpu": 55.0, "vrm": 95.0}, {}, 0.0)

    assert (decisions[2].percent, decisions[2].sensor) == (100, "vrm")


def test_offsets_move_the_curve_but_not_the_critical_limit():
    policy = engine.validate_policy({
        "schema": 2, "offsets_c": {"gpu": -20},
        "channels": {"2": {"mode": "curve", "source": "gpu", "points": [[40, 20], [80, 100]]}},
    })

    decisions, _ = engine.plan(policy, {"gpu": 80.0}, {}, 0.0)
    assert decisions[2].percent == 60
    decisions, _ = engine.plan(policy, {"gpu": 96.0}, {}, 0.0)
    assert decisions[2].source == "critical"


def test_critical_drives_every_controlled_channel_and_never_lowers():
    policy = engine.validate_policy({
        "schema": 2, "failsafe_percent": 40,
        "channels": {
            "1": {"mode": "fixed", "percent": 30},
            "2": {"mode": "fixed", "percent": 90, "role": "pump"},
            "5": {"mode": "firmware"},
        },
    })

    decisions, _ = engine.plan(policy, {"vrm": 106.0}, {}, 0.0)

    assert decisions[1].percent == 100 and decisions[1].source == "critical"
    assert decisions[2].percent == 100
    assert decisions[5].action == "release"


def test_critical_latches_until_there_is_margin():
    policy = _policy()
    ticks = _run(policy, [
        (0.0, {"gpu": 96.0}),
        (2.0, {"gpu": 93.0}),   # under 95 but inside the 5 C recovery margin
        (4.0, {"gpu": 70.0}),   # far enough: back to the curve (83 %)...
        (8.0, {"gpu": 70.0}),   # ...stepping down one change at a time
        (13.0, {"gpu": 70.0}),
    ])

    assert [t[2].source for t in ticks] == ["critical", "critical", "curve", "curve", "curve"]
    assert [t[2].percent for t in ticks] == [100, 100, 100, 90, 83]


def test_a_missing_sensor_waits_then_fails_safe():
    policy = _policy(**{"2": {"mode": "curve", "source": "gpu", "points": [[40, 20], [80, 100]]}})
    ticks = _run(policy, [
        (0.0, {"gpu": 50.0}),
        (2.0, {"cpu": 50.0}),
        (17.0, {"cpu": 50.0}),
        (19.0, {"cpu": 50.0}),
    ])

    assert ticks[0][2].percent == 40
    assert ticks[1][2].action == "hold" and ticks[1][2].source == "waiting-sensor"
    assert ticks[2][2].source == "failsafe" and ticks[2][2].percent == 100
    assert ticks[3][2].percent == 100


def test_hottest_does_not_hide_a_lost_sensor():
    # VRM answered before; now it is gone and only a cool GPU answers.
    policy = _policy(**{"2": {"mode": "curve", "points": [[40, 20], [80, 100]]}})
    ticks = _run(
        policy,
        [(0.0, {"gpu": 45.0, "vrm": 80.0}), (6.0, {"gpu": 45.0}), (21.0, {"gpu": 45.0})],
        expected={"gpu", "vrm"},
    )

    assert ticks[0][2].percent == 100
    assert ticks[1][2].percent == 100  # grace period: never down while incomplete
    assert ticks[2][2].source == "failsafe"


def test_a_mix_member_lost_never_lowers_the_duty_during_grace():
    policy = _policy(**{
        "2": {"mode": "mix", "mix": [
            {"source": "gpu", "points": [[40, 20], [80, 100]]},
            {"source": "vrm", "points": [[40, 20], [80, 100]]},
        ]},
    })
    ticks = _run(policy, [(0.0, {"gpu": 45.0, "vrm": 80.0}), (6.0, {"gpu": 45.0})])

    assert ticks[1][2].percent == 100


def test_step_limits_and_change_interval():
    policy = _policy(**{"2": {
        "mode": "curve", "source": "gpu", "points": [[40, 0], [80, 100]],
        "max_up_step_percent": 20, "max_down_step_percent": 10,
    }})
    ticks = _run(policy, [
        (0.0, {"gpu": 40.0}),
        (2.0, {"gpu": 80.0}),   # inside the change interval: hold
        (5.0, {"gpu": 80.0}),
        (10.0, {"gpu": 80.0}),
        (15.0, {"gpu": 40.0}),
    ])

    assert [t[2].percent for t in ticks] == [0, 0, 20, 40, 30]


def test_hysteresis_and_deadband_hold_small_changes():
    policy = _policy(**{"2": {
        "mode": "curve", "source": "gpu", "points": [[40, 0], [80, 100]],
        "hysteresis_c": 2.0, "deadband_percent": 2,
    }})
    ticks = _run(policy, [
        (0.0, {"gpu": 60.0}),
        (10.0, {"gpu": 61.5}),  # under 2 C of hysteresis
        (20.0, {"gpu": 62.5}),  # past it: 56 %
    ])

    assert [t[2].percent for t in ticks] == [50, 50, 56]


def test_response_delay_needs_a_change_to_persist():
    policy = _policy(**{"2": {
        "mode": "curve", "source": "gpu", "points": [[40, 0], [80, 100]],
        "response_delay_seconds": 6, "hysteresis_c": 0,
    }})
    ticks = _run(policy, [
        (0.0, {"gpu": 40.0}),
        (10.0, {"gpu": 60.0}),
        (12.0, {"gpu": 40.0}),  # a spike that went away
        (14.0, {"gpu": 60.0}),
        (18.0, {"gpu": 61.0}),
        (20.0, {"gpu": 61.0}),  # rising for 6 s now
    ])

    assert [t[2].percent for t in ticks] == [0, 0, 0, 0, 0, 53]


def test_min_max_and_start_kick():
    policy = _policy(**{"2": {
        "mode": "curve", "source": "gpu", "points": [[40, 0], [80, 100]],
        "min_percent": 0, "max_percent": 80, "start_percent": 45,
    }})
    ticks = _run(policy, [
        (0.0, {"gpu": 40.0}),
        (5.0, {"gpu": 50.0}),   # 25 % from a stop: kick at 45 % first
        (7.0, {"gpu": 50.0}),
        (9.0, {"gpu": 50.0}),   # kick over
        (20.0, {"gpu": 90.0}),
        (30.0, {"gpu": 90.0}),
    ])

    assert [t[2].percent for t in ticks] == [0, 45, 45, 25, 80, 80]


def test_fixed_and_firmware_need_no_sensor():
    policy = _policy(**{"1": {"mode": "fixed", "percent": 35}, "2": {"mode": "firmware"}})

    decisions, _ = engine.plan(policy, {}, {}, 0.0)

    assert (decisions[1].action, decisions[1].percent) == ("set", 35)
    assert decisions[2].action == "release" and decisions[2].raw is None


def test_implausible_readings_are_ignored():
    assert engine.clean_readings(
        {"gpu": 0, "cpu": float("nan"), "vrm": 140.0, "board": True, "ssd": 40}
    ) == {}


# ------------------------------------------------------------------ stall


def test_stall_needs_a_tach_that_spun_and_a_grace_period():
    channel = _policy()["channels"]["2"]
    memory = ChannelMemory()

    fault, memory = engine.assess_stall(channel, memory, 60, 0, 0.0)
    assert fault == ""  # never seen spinning: maybe no tach wire
    fault, memory = engine.assess_stall(channel, memory, 60, 1200, 1.0)
    fault, memory = engine.assess_stall(channel, memory, 60, 0, 2.0)
    assert fault == ""
    fault, memory = engine.assess_stall(channel, memory, 60, 0, 12.5)
    assert fault == "stalled"
    fault, memory = engine.assess_stall(channel, memory, 60, 900, 13.0)
    assert fault == "" and memory.stalled_since is None


def test_a_stopped_pump_is_its_own_fault_and_low_duty_is_not_a_stall():
    pump = engine.validate_policy({
        "schema": 2, "channels": {"2": {"mode": "fixed", "percent": 90, "role": "pump"}},
    })["channels"]["2"]
    memory = ChannelMemory(seen_spinning=True)

    _, memory = engine.assess_stall(pump, memory, 90, 0, 0.0)
    fault, _ = engine.assess_stall(pump, memory, 90, 0, 11.0)
    assert fault == "pump-stalled"

    fan = _policy()["channels"]["2"]
    fault, _ = engine.assess_stall(fan, ChannelMemory(seen_spinning=True, stalled_since=0.0), 10, 0, 60.0)
    assert fault == ""
    fault, _ = engine.assess_stall(fan, ChannelMemory(seen_spinning=True), 60, None, 60.0)
    assert fault == ""


def test_an_emergency_holds_while_the_hot_sensor_is_missing():
    # Codex review: GPU 96 C, then the GPU disappears and only a cool CPU
    # answers. That is not evidence the emergency is over.
    policy = _policy()
    ticks = _run(
        policy,
        [(0.0, {"gpu": 96.0, "cpu": 40.0}), (6.0, {"cpu": 40.0}), (12.0, {"cpu": 40.0})],
        expected={"gpu", "cpu"},
    )

    assert [t[2].source for t in ticks] == ["critical", "critical", "critical"]
    assert [t[2].percent for t in ticks] == [100, 100, 100]
    assert ticks[1][2].sensor == "gpu" and ticks[1][2].temperature is None
