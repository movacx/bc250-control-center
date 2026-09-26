"""The Game Mode voltage laboratory (Decky protocol 18).

Quick Access may choose the governor curve or +10/+20/+30 mV above 2000 MHz,
and nudge single points in 5 mV steps between the governor value and 60 mV
above it. Everything else is refused before the governor-config helper runs.
"""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "privileged" / "helpers" / "bc250-quick-access-helper"

CURVE = """[[safe-points]]
frequency = 1850
voltage = 930

[[safe-points]]
frequency = 2000
voltage = 970

[[safe-points]]
frequency = 2050
voltage = 990

[[safe-points]]
frequency = 2100
voltage = 1010
"""


class _Completed:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


@pytest.fixture
def helper(tmp_path, monkeypatch):
    module = runpy.run_path(str(HELPER))
    g = module["gpu_voltage_custom"].__globals__
    config = tmp_path / "config.toml"
    config.write_text(CURVE, encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setitem(g, "CYAN_CONFIG", config)
    monkeypatch.setitem(g, "trusted_directory", lambda _path: True)
    monkeypatch.setitem(g, "trusted_file", lambda *_a, **_k: True)
    monkeypatch.setitem(g, "active_gpu_governor", lambda: "cyan")
    monkeypatch.setitem(g, "service_active", lambda _unit: True)
    monkeypatch.setitem(g, "cyan_range", lambda: (1000, 1850))
    monkeypatch.setitem(g, "wait_for_cyan_range", lambda requested, **_k: requested)
    monkeypatch.setitem(g, "run", lambda argv, **_k: calls.append(list(argv)) or _Completed())
    # cyan_voltage_points reads the fixture through the default argument.
    monkeypatch.setitem(g, "cyan_voltage_points", lambda config=config: module["cyan_voltage_points"](config))
    return module, g, calls


def test_the_curve_reports_levels_the_way_the_desktop_names_them(helper):
    module, _g, _calls = helper
    points = module["cyan_voltage_points"](_g["CYAN_CONFIG"])
    assert [point["default"] for point in points] == [930, 960, 980, 1000]
    # +10 mV on 2000 MHz and up, the governor value below: level 1.
    assert module["detected_voltage_level"](points) == 1


def test_a_point_of_its_own_makes_the_curve_custom_as_on_the_desktop(helper):
    """voltage_lab_state._applied_level calls this curve custom; so must Game Mode."""
    module, _g, _calls = helper
    points = list(module["cyan_voltage_points"](_g["CYAN_CONFIG"]))
    assert module["detected_voltage_level"](points) == 1
    points.append({"frequency": 1925, "voltage": 950, "default": 0})
    assert module["detected_voltage_level"](points) is None


def test_the_level_ladder_is_the_desktops(helper):
    from bc250cc.application.gpu.voltage_lab_state import build_voltage_lab_state

    module, _g, _calls = helper
    points = module["cyan_voltage_points"](_g["CYAN_CONFIG"])
    desktop = build_voltage_lab_state({
        "safe_points_with_voltage": [
            {"frequency": point["frequency"], "voltage": point["voltage"]} for point in points
        ]
    })
    assert desktop.applied_level == module["detected_voltage_level"](points)


def test_a_level_goes_through_the_governor_helper_and_keeps_the_range(helper, capsys):
    module, _g, calls = helper
    assert module["gpu_voltage_level"]("2") == 0
    assert calls[0][1:] == ["set-cyan-voltage-level", "2"]
    assert ["/usr/bin/systemctl", "restart", "cyan-skillfish-governor-smu.service"] in calls
    assert any("SetRange" in call and call[-2:] == ["1000", "1850"] for call in calls)
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["ok"] is True


@pytest.mark.parametrize("level", ["4", "6", "-1", "x", ""])
def test_levels_above_the_ladder_are_refused(helper, level):
    module, _g, calls = helper
    assert module["gpu_voltage_level"](level) != 0
    assert calls == []


def test_a_point_nudge_is_written_alone(helper):
    module, _g, calls = helper
    assert module["gpu_voltage_custom"](["2050=995"]) == 0
    assert calls[0][1:] == ["set-cyan-custom-voltages", "2050=995"]


@pytest.mark.parametrize("pair, reason", [
    ("2050=975", "below the governor value"),
    ("2050=1045", "more than 60 mV above it"),
    ("2050=993", "not a 5 mV step"),
    ("2075=1000", "not an active point"),
    ("2050=abc", "malformed"),
    ("2000=1015", "above the next point"),
])
def test_out_of_bounds_points_never_reach_the_governor_helper(helper, pair, reason):
    module, _g, calls = helper
    assert module["gpu_voltage_custom"]([pair]) != 0, reason
    assert calls == []


def test_oberon_and_a_stopped_governor_are_refused(helper, monkeypatch):
    module, g, calls = helper
    monkeypatch.setitem(g, "active_gpu_governor", lambda: "oberon")
    assert module["gpu_voltage_level"]("1") != 0
    monkeypatch.setitem(g, "active_gpu_governor", lambda: "cyan")
    monkeypatch.setitem(g, "service_active", lambda _unit: False)
    assert module["gpu_voltage_custom"](["2050=995"]) != 0
    assert calls == []


def test_a_quick_access_fan_change_is_recorded_for_the_system_service(tmp_path, monkeypatch):
    module = runpy.run_path(str(HELPER))
    g = module["note_fan_takeover"].__globals__
    policy = tmp_path / "fan-policy.json"
    override = tmp_path / "run" / "fan-override.json"
    monkeypatch.setitem(g, "SYSTEM_FAN_POLICY", policy)
    monkeypatch.setitem(g, "SYSTEM_FAN_OVERRIDE", override)

    module["note_fan_takeover"]([2])
    assert not override.exists(), "no policy, no system service to tell"

    policy.write_text("{}", encoding="utf-8")
    module["note_fan_takeover"](["2", 99, "x"])
    module["note_fan_takeover"]([3])
    assert json.loads(override.read_text())["channels"] == [2, 3]
