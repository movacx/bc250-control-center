"""The root writers refuse what the request check refuses.

The governor-config helper can be run directly (and through the SteamOS
game helper), so the /etc export must not rely on the app having checked
the payload first.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

GPU = {"key": "balanced", "name": "Balanced", "min": 1000, "max": 1850}
CPU = {"key": "mid_point", "name": "Mid", "frequency": 3850, "vid": 1150, "temperature": 85}
FAN = {"key": "quiet", "name": "Quiet", "percent": 40}


def _governor_toml(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "bc250_governor_toml_writer_test", ROOT / "privileged/lib/governor_toml.py"
    )
    module = importlib.util.module_from_spec(spec)
    # Its dataclasses resolve annotations through sys.modules.
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_require_root_owned", lambda *_args: None)
    return module


def _bad_variants(good: dict) -> list[list[dict]]:
    return [
        [{**good, "extra": 1}],
        [{**good, "key": "unknown"}],
        [good, dict(good)],
        [{**good, "name": ""}],
        [{**good, "name": "   "}],
        [{**good, "name": "x" * 41}],
        [],
        [good, good, good, good],
    ]


@pytest.mark.parametrize(
    ("writer", "good"),
    [
        ("write_decky_gpu_profiles", GPU),
        ("write_decky_cpu_profiles", CPU),
        ("write_decky_fan_profiles", FAN),
    ],
)
def test_a_malformed_payload_is_refused_and_nothing_is_written(tmp_path, monkeypatch, writer, good):
    module = _governor_toml(monkeypatch)
    target = tmp_path / "decky-profiles.json"
    for profiles in _bad_variants(good):
        with pytest.raises(module.GovernorTomlError):
            getattr(module, writer)(json.dumps(profiles), target)
        assert not target.exists()

    assert getattr(module, writer)(json.dumps([good]), target).changed is True


@pytest.mark.parametrize("percent", [19, 101, 0])
def test_the_fan_writer_keeps_the_twenty_to_hundred_range(tmp_path, monkeypatch, percent):
    module = _governor_toml(monkeypatch)
    target = tmp_path / "decky-fan-profiles.json"
    with pytest.raises(module.GovernorTomlError, match="20-100"):
        module.write_decky_fan_profiles(json.dumps([{**FAN, "percent": percent}]), target)
    assert not target.exists()


def test_a_cpu_export_from_before_the_cap_still_publishes(tmp_path, monkeypatch):
    module = _governor_toml(monkeypatch)
    target = tmp_path / "decky-cpu-profiles.json"
    legacy = {key: value for key, value in CPU.items() if key != "temperature"}
    assert module.write_decky_cpu_profiles(json.dumps([legacy]), target).changed is True
    stored = json.loads(target.read_text(encoding="utf-8"))["profiles"]
    assert stored == [{**legacy, "temperature": 90}]
