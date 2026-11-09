"""Per-channel config, labels and modes (domain + application service)."""

from __future__ import annotations

import pytest

from bc250cc.application.fan.channels import FanChannelsService
from bc250cc.domain.fan import channels as model
from bc250cc.infrastructure.system_fan_control import (
    build_system_fan_policy,
    downgrade_policy_to_v1,
    normalized_policy_digest,
    policy_digest,
)

LEGACY_CURVE = {
    "fan_curve": {"enabled": True, "pwm": 2, "points": [[45, 40], [60, 70], [75, 100]]},
    "fan_preset": {"enabled": False},
}


class Settings:
    def __init__(self, config=None):
        self.config = dict(config or {})

    def read_local_config(self):
        return dict(self.config)

    def save_local_config(self, values):
        self.config.update(values)
        return self.config


def _curve(points=((40, 30), (80, 100)), **extra):
    return {"mode": "curve", "points": [list(p) for p in points], **extra}


def test_the_forum_layout_becomes_one_policy_with_every_channel():
    service = FanChannelsService(Settings())
    for pwm in (1, 3, 4, 5):
        service.set_channel(pwm, _curve(source="gpu"))
    board = service.set_channel(2, {"mode": "fixed", "percent": 90, "role": "pump"})

    assert board.controlled == [1, 2, 3, 4, 5]
    assert board.needs_root_service
    assert board.policy["channels"]["2"] == {
        "mode": "fixed", "role": "pump", "percent": 90, "preset": "", "stall_detect": True,
    }


def test_editing_a_channel_migrates_the_legacy_curve_instead_of_losing_it():
    settings = Settings(LEGACY_CURVE)
    board = FanChannelsService(settings).set_channel(3, _curve())

    assert board.controlled == [2, 3]
    assert board.channels["2"]["points"] == [[45, 40], [60, 70], [75, 100]]
    assert settings.config["fan_curve"]["enabled"] is False


def test_firmware_hands_a_channel_back_and_invalid_entries_are_refused():
    service = FanChannelsService(Settings())
    service.set_channel(3, _curve())
    with pytest.raises(ValueError):
        service.set_channel(3, {"mode": "fixed", "percent": 140})
    board = service.set_channel(3, {"mode": "firmware"})

    assert board.channels == {} and board.policy is None


def test_a_broken_saved_entry_only_drops_itself():
    channels = model.normalize_fan_channels({
        "1": _curve(), "3": {"mode": "fixed", "percent": "x"}, "99": _curve(), "a": _curve(),
    })
    assert list(channels) == ["1"]


def test_labels_are_trimmed_and_never_change_the_channel():
    service = FanChannelsService(Settings())
    service.set_channel(1, _curve())
    board = service.set_label(1, "   Front   intake  " + "x" * 80)

    assert board.labels["1"].startswith("Front intake x")
    assert len(board.labels["1"]) == model.LABEL_MAX_LENGTH
    assert board.controlled == [1]
    assert service.set_label(1, "  ").labels == {}


def test_a_mode_replaces_the_active_set():
    service = FanChannelsService(Settings())
    service.set_channel(1, _curve())
    service.save_mode("Gaming")
    service.set_channel(4, {"mode": "fixed", "percent": 50})
    assert service.board().controlled == [1, 4]

    board = service.apply_mode("gaming")

    assert board.controlled == [1]  # pwm4 is not in the mode: back to firmware
    assert board.active_mode == "Gaming"


def test_builtin_modes_never_slow_a_pump():
    service = FanChannelsService(Settings())
    service.set_channel(2, {"mode": "fixed", "percent": 90, "role": "pump"})
    service.set_channel(3, _curve())

    board = service.apply_mode("Quiet")

    assert board.channels["2"]["percent"] == 90
    assert board.channels["3"]["points"] == model.BUILTIN_MODE_CURVES["quiet"]
    with pytest.raises(ValueError):
        service.apply_mode("Turbo")


def test_modes_are_unique_by_name_and_deletable():
    service = FanChannelsService(Settings())
    service.set_channel(1, _curve())
    service.save_mode("Night")
    service.save_mode("night")
    assert [m["name"] for m in service.board().modes] == ["night"]
    assert service.delete_mode("night").modes == []
    with pytest.raises(ValueError):
        FanChannelsService(Settings()).save_mode("Empty")


# ----------------------------------------------- old root helper negotiation


def test_a_single_legacy_curve_downgrades_without_loss():
    policy = build_system_fan_policy(LEGACY_CURVE)
    legacy = downgrade_policy_to_v1(policy)

    assert legacy["schema"] == 1 and legacy["pwm"] == 2 and legacy["mode"] == "curve"
    assert normalized_policy_digest(legacy) == policy_digest(policy)


@pytest.mark.parametrize("channels", [
    {"1": _curve(), "3": _curve()},
    {"2": _curve(source="gpu", points=((40, 30), (60, 50), (80, 100)))},
    {"2": {"mode": "fixed", "percent": 90, "role": "pump"}},
    {"2": _curve(points=((40, 30), (80, 100)))},  # two points: v1 needs three
])
def test_what_an_old_helper_cannot_follow_is_refused(channels):
    policy = build_system_fan_policy({"fan_channels": channels})
    assert downgrade_policy_to_v1(policy) is None


# ------------------------------------------- reported 2026-11-08: empty profile


def test_a_builtin_profile_with_every_channel_on_firmware_drives_the_given_headers():
    """Every header on Firmware, apply Balanced: it used to raise "This fan
    mode has no valid channel" (shown as hardware error BC250-FAN-001)."""
    service = FanChannelsService(Settings())

    board = service.apply_mode("Balanced", targets=[2, 1])

    assert board.controlled == [1, 2]
    assert board.channels["2"]["points"] == model.BUILTIN_MODE_CURVES["balanced"]
    assert board.channels["2"]["role"] == "fan"
    assert board.active_mode == "Balanced"


def test_a_builtin_profile_with_nothing_to_drive_is_still_refused():
    with pytest.raises(ValueError):
        FanChannelsService(Settings()).apply_mode("Quiet")


def test_configured_channels_win_over_targets_and_pumps_are_kept():
    service = FanChannelsService(Settings())
    service.set_channel(2, {"mode": "fixed", "percent": 90, "role": "pump"})

    board = service.apply_mode("Performance", targets=[3, 4])

    assert board.controlled == [2]
    assert board.channels["2"]["percent"] == 90
