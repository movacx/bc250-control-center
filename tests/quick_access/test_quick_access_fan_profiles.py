"""Decky's fan presets take the Desktop's names and speeds (protocol 19)."""

from __future__ import annotations

import importlib.util
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER_SOURCE = ROOT / "privileged/helpers/bc250-quick-access-helper"


@pytest.fixture()
def helper():
    loader = SourceFileLoader("bc250_quick_access_fan_profiles_test", str(HELPER_SOURCE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exported_speeds_become_the_preset_duties(helper, monkeypatch):
    monkeypatch.setattr(helper, "_load_fan_profile_overrides", lambda path=None: {
        "quiet": {"name": "Night", "percent": 30},
        "boost": {"name": "Raid", "percent": 100},
    })

    presets = helper.effective_fan_presets()
    assert presets["quiet"] == round(30 * 255 / 100)
    assert presets["balanced"] == helper.FAN_SYSTEM_PRESETS["balanced"]
    assert presets["boost"] == 255 and presets["automatic"] is None
    assert helper.fan_profiles_payload() == [
        {"key": "quiet", "name": "Night", "percent": 30},
        {"key": "balanced", "name": "", "percent": 60},
        {"key": "boost", "name": "Raid", "percent": 100},
    ]


def test_a_file_the_system_does_not_own_is_ignored(helper, tmp_path):
    path = tmp_path / "decky-fan-profiles.json"
    path.write_text(json.dumps({"schema": 1, "profiles": [{"key": "quiet", "name": "x", "percent": 30}]}), encoding="utf-8")
    # Owned by the test user, not root: exactly what a planted file looks like.
    assert helper._load_fan_profile_overrides(path) == {}


def test_resume_releases_only_a_takeover_decky_recorded(helper, tmp_path, monkeypatch, capsys):
    override = tmp_path / "fan-override.json"
    monkeypatch.setattr(helper, "SYSTEM_FAN_OVERRIDE", override)
    monkeypatch.setattr(helper, "SYSTEM_FAN_POLICY", tmp_path / "fan-policy.json")

    override.write_text(json.dumps({"channels": [3, 4], "source": "session"}), encoding="utf-8")
    assert helper.fan_resume() == 0
    assert json.loads(capsys.readouterr().out)["resumed"] is False
    assert override.exists()  # a change made on the Desktop keeps pausing the service

    override.write_text(json.dumps({"channels": [3, 4], "source": "decky"}), encoding="utf-8")
    assert helper.fan_resume() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["resumed"] is True and not override.exists()
    assert payload["system_fan_override"] is False


def test_protocol_19_is_the_one_the_plugin_and_contract_expect(helper):
    contract = (ROOT / "privileged/lib/bc250_contract.py").read_text(encoding="utf-8")
    plugin = (ROOT / "integrations/decky/bc250-quick-access/main.py").read_text(encoding="utf-8")
    assert helper.HELPER_PROTOCOL == 19
    assert "QUICK_ACCESS_PROTOCOL = 19" in contract
    assert "HELPER_PROTOCOL = 19" in plugin
