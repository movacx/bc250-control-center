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
    # Not the preset this host's panel applied last.
    module.SYSTEM_FAN_LAST_PRESET = Path("/nonexistent/fan-last-preset.json")
    return module


def test_the_panel_localizes_names_the_desktop_left_at_their_default():
    """Exported names are no longer translated; the panel must know the defaults."""
    from frontends.desktop.pages.cpu_control_view import DEFAULT_CPU_PROFILES
    from frontends.desktop.pages.fans_widgets import DEFAULT_FAN_PROFILES
    from frontends.desktop.pages.gpu_governor_view import DEFAULT_PROFILES

    panel = (ROOT / "integrations/decky/bc250-quick-access/src/index.tsx").read_text(encoding="utf-8")
    decky_key = {"quiet": "quiet", "balanced": "balanced", "maximum": "boost"}
    fan_names = ", ".join(f'{decky_key[p.key]}: "{p.name}"' for p in DEFAULT_FAN_PROFILES)
    cpu_names = ", ".join(f'{p.key}: "{p.name}"' for p in DEFAULT_CPU_PROFILES)
    assert f"const SHIPPED_FAN_NAMES: Record<string, string> = {{ {fan_names} }};" in panel
    assert f"const SHIPPED_CPU_NAMES: Record<string, string> = {{ {cpu_names} }};" in panel
    gpu_names = "Balanced: () => text.profileBalanced, Gaming: () => text.profileGaming, Benchmark: () => text.profileBenchmark"
    assert [p.name for p in DEFAULT_PROFILES] == ["Balanced", "Gaming", "Benchmark"] and gpu_names in panel


def test_the_panel_says_which_fans_its_presets_drive():
    panel = (ROOT / "integrations/decky/bc250-quick-access/src/index.tsx").read_text(encoding="utf-8")
    assert "{text.fanPresetsHint}" in panel
    for path in (ROOT / "integrations/decky/bc250-quick-access/locales").glob("*.json"):
        hint = json.loads(path.read_text(encoding="utf-8"))["fanPresetsHint"]
        assert "PWM3–PWM8" in hint and "PWM2" in hint and "20 %" in hint, path.name


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


def test_the_protocol_is_the_one_the_plugin_and_contract_expect(helper):
    contract = (ROOT / "privileged/lib/bc250_contract.py").read_text(encoding="utf-8")
    plugin = (ROOT / "integrations/decky/bc250-quick-access/main.py").read_text(encoding="utf-8")
    assert helper.HELPER_PROTOCOL == 21
    assert "QUICK_ACCESS_PROTOCOL = 21" in contract
    assert "HELPER_PROTOCOL = 21" in plugin
