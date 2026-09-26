"""Fan profiles travel: to a file and back, and to Decky's presets.

The user asked where the fan profile export was; the GPU and CPU cards had
"Export to Decky" and the Fans page had nothing. A manual speed also used to
vanish at reboot even with the root fan service on.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from bc250cc.domain.fan.persistence import CUSTOM_FAN_PRESET, normalize_fan_preset
from bc250cc.domain.fan.profile_exchange import (
    decky_fan_profiles,
    fan_profiles_document,
    parse_fan_profiles_document,
)
from bc250cc.infrastructure.governor_config_request import plan_governor_config_request
from bc250cc.infrastructure.system_fan_control import build_system_fan_policy

ROOT = Path(__file__).resolve().parents[3]
PROFILES = [
    {"key": "quiet", "name": "Night", "percent": 35},
    {"key": "balanced", "name": "Balanced", "percent": 60},
    {"key": "maximum", "name": "Raid", "percent": 100},
]
CURVE = {
    "enabled": True,
    "pwm": 2,
    "points": [{"temperature": 45, "speed": 40}, {"temperature": 60, "speed": 70}, {"temperature": 72, "speed": 100}],
}


def test_a_document_round_trips_profiles_and_a_switched_off_curve():
    document = json.loads(json.dumps(fan_profiles_document(PROFILES, CURVE)))
    profiles, curve = parse_fan_profiles_document(document)

    assert profiles == PROFILES
    assert curve is not None and curve["enabled"] is False and curve["pwm"] == 2
    assert [(point["temperature"], point["speed"]) for point in curve["points"]] == [(45, 40), (60, 70), (72, 100)]


@pytest.mark.parametrize("document, reason", [
    ({"kind": "something-else", "schema": 1, "profiles": PROFILES}, "not a BC250"),
    ({"kind": "bc250-fan-profiles", "schema": 9, "profiles": PROFILES}, "different version"),
    ({"kind": "bc250-fan-profiles", "schema": 1, "profiles": []}, "no fan profiles"),
    ({"kind": "bc250-fan-profiles", "schema": 1, "profiles": [{"key": "turbo", "name": "x", "percent": 50}]}, "does not have"),
    ({"kind": "bc250-fan-profiles", "schema": 1, "profiles": [{"key": "quiet", "name": "x", "percent": 150}]}, "0 to 100"),
    ({"kind": "bc250-fan-profiles", "schema": 1, "profiles": [{"key": "quiet", "name": "", "percent": 50}]}, "1-24"),
    ({"kind": "bc250-fan-profiles", "schema": 1, "profiles": PROFILES, "curve": {"pwm": 2, "points": [[50, 10], [50, 20], [60, 30]]}}, "increasing"),
])
def test_a_foreign_or_damaged_file_is_refused_whole(document, reason):
    with pytest.raises(ValueError, match=reason):
        parse_fan_profiles_document(document)


def test_decky_gets_its_own_preset_keys_within_its_speed_range():
    published = decky_fan_profiles([{"key": "quiet", "name": "Night", "percent": 10}, *PROFILES[1:]])
    assert published == [
        {"key": "quiet", "name": "Night", "percent": 20},
        {"key": "balanced", "name": "Balanced", "percent": 60},
        {"key": "boost", "name": "Raid", "percent": 100},
    ]
    request = plan_governor_config_request("set-decky-fan-profiles", (published,))
    assert request.action == "set-decky-fan-profiles"
    assert json.loads(request.arguments[0])[2] == {"key": "boost", "name": "Raid", "percent": 100}


@pytest.mark.parametrize("profiles", [
    [{"key": "maximum", "name": "Raid", "percent": 100}],
    [{"key": "boost", "name": "Raid", "percent": 5}],
    [{"key": "quiet", "name": "a"}, {"key": "quiet", "name": "b", "percent": 40}],
])
def test_the_unprivileged_side_refuses_what_the_helper_would(profiles):
    with pytest.raises(ValueError):
        plan_governor_config_request("set-decky-fan-profiles", (profiles,))


def _governor_toml(monkeypatch):
    spec = importlib.util.spec_from_file_location("bc250_governor_toml_test", ROOT / "privileged/lib/governor_toml.py")
    module = importlib.util.module_from_spec(spec)
    # Its dataclasses resolve annotations through sys.modules.
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_the_root_writer_refuses_a_user_owned_place_and_writes_the_schema(tmp_path, monkeypatch):
    module = _governor_toml(monkeypatch)
    target = tmp_path / "etc" / "decky-fan-profiles.json"
    payload = json.dumps(decky_fan_profiles(PROFILES))
    with pytest.raises(module.GovernorTomlError, match="not protected by root"):
        module.write_decky_fan_profiles(payload, target)

    monkeypatch.setattr(module, "_require_root_owned", lambda *_args: None)
    assert module.write_decky_fan_profiles(payload, target).changed is True
    assert json.loads(target.read_text(encoding="utf-8")) == {"schema": 1, "profiles": json.loads(payload)}
    assert module.write_decky_fan_profiles(payload, target).changed is False
    with pytest.raises(module.GovernorTomlError):
        module.write_decky_fan_profiles(json.dumps([{"key": "quiet", "name": "x", "percent": "50"}]), target)


def test_a_manual_speed_is_saved_like_a_tier_and_followed_from_boot_as_fixed():
    preset = normalize_fan_preset({"enabled": True, "preset": CUSTOM_FAN_PRESET, "percent": 55, "pwm": 3})
    assert preset == {"enabled": True, "preset": "custom", "percent": 55, "pwm": 3}

    policy = build_system_fan_policy({"fan_curve": {"enabled": False}, "fan_preset": preset})
    assert policy is not None
    assert (policy["mode"], policy["pwm"], policy["percent"], policy["preset"]) == ("fixed", 3, 55, "")

    named = build_system_fan_policy({"fan_preset": {"enabled": True, "preset": "quiet", "percent": 45, "pwm": 2}})
    assert (named["mode"], named["preset"]) == ("preset", "quiet")
