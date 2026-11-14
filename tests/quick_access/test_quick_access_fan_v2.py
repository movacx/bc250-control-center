"""Decky follows the desktop's fan control v2: it shows each header's mode,
role and service state, never drives a pump from a group preset, and never
runs a pump under the engine's floor."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from bc250cc.domain.fan import engine

ROOT = Path(__file__).resolve().parents[2]
HELPER_SOURCE = ROOT / "privileged/helpers/bc250-quick-access-helper"
BACKEND = ROOT / "integrations/decky/bc250-quick-access/main.py"


def _backend_module(monkeypatch):
    decky = types.ModuleType("decky")
    decky.logger = types.SimpleNamespace(info=lambda *_args, **_kwargs: None)
    decky.DECKY_PLUGIN_SETTINGS_DIR = tempfile.mkdtemp(prefix="bc250-qam-settings-")
    monkeypatch.setitem(sys.modules, "decky", decky)
    spec = importlib.util.spec_from_file_location("bc250_quick_access_backend_fan_v2", BACKEND)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def helper(tmp_path, monkeypatch):
    loader = SourceFileLoader("bc250_quick_access_fan_v2_test", str(HELPER_SOURCE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SYSTEM_FAN_POLICY = tmp_path / "fan-policy.json"
    module.SYSTEM_FAN_STATUS = tmp_path / "fan-control.json"
    module.SYSTEM_FAN_LAST_PRESET = tmp_path / "fan-last-preset.json"
    # The test runs as an ordinary user: its files stand in for root's.
    monkeypatch.setattr(module, "_root_json", lambda path, limit=65536: _plain_json(path))
    return module


def _plain_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return document if isinstance(document, dict) else {}


def _sensor(tmp_path: Path, duties: dict[int, int]) -> Path:
    sensor = tmp_path / "hwmon0"
    sensor.mkdir()
    for channel, duty in duties.items():
        (sensor / f"pwm{channel}").write_text(f"{duty}\n", encoding="ascii")
        (sensor / f"pwm{channel}_enable").write_text("1\n", encoding="ascii")
        (sensor / f"fan{channel}_input").write_text("900\n", encoding="ascii")
    return sensor


def test_the_pump_floor_is_the_engines():
    source = HELPER_SOURCE.read_text(encoding="utf-8")
    assert f"PUMP_FLOOR_PERCENT = {engine.PUMP_FLOOR_PERCENT}" in source


def test_group_presets_leave_a_pump_alone(helper, tmp_path):
    sensor = _sensor(tmp_path, {1: 100, 2: 200, 3: 100, 4: 100, 5: 100})
    assert helper.system_fan_channels(sensor) == [1, 3, 4, 5]
    helper.SYSTEM_FAN_POLICY.write_text(json.dumps({"schema": 2, "channels": {
        "3": {"mode": "fixed", "percent": 90, "role": "pump"}, "4": {"mode": "curve", "points": [[40, 30], [80, 100]]}}}))
    assert helper.system_fan_channels(sensor) == [1, 4, 5]


def test_a_pump_never_runs_under_its_floor_from_quick_access(helper, tmp_path, capsys):
    helper.SYSTEM_FAN_POLICY.write_text(json.dumps({"schema": 2, "channels": {
        "2": {"mode": "fixed", "percent": 90, "role": "pump"}}}))
    helper.nct_sensor = lambda: pytest.fail("refused before any hardware access")
    assert helper.fan_channel_control("2", "20") == 40
    captured = capsys.readouterr()
    assert "pump" in (captured.out + captured.err).lower()


def test_each_channel_carries_the_desktops_mode_role_and_service_state(helper, tmp_path):
    sensor = _sensor(tmp_path, {1: 0, 2: 230, 3: 150, 4: 0, 5: 140})
    helper.SYSTEM_FAN_POLICY.write_text(json.dumps({"schema": 2, "channels": {
        "2": {"mode": "fixed", "percent": 90, "role": "pump"}, "3": {"mode": "curve", "points": [[40, 30], [80, 100]]}}}))
    helper.SYSTEM_FAN_STATUS.write_text(json.dumps({"channels": {
        "2": {"state": "active", "percent": 90}, "3": {"state": "active", "percent": 64, "fault": "stalled"}}}))
    rows = {row["channel"]: row for row in helper.qam_fan_channel_state(sensor)}
    assert rows[2]["role"] == "pump" and rows[2]["policy_mode"] == "fixed" and rows[2]["bios_fan"] == 1
    assert rows[3]["policy_mode"] == "curve" and rows[3]["service_fault"] == "stalled" and rows[3]["service_percent"] == 64
    assert rows[1]["policy_mode"] == "firmware" and rows[1]["role"] == "fan" and rows[1]["header"] == "J4003 Fan 5"


def test_a_policy_or_status_file_that_root_did_not_write_is_ignored(tmp_path):
    loader = SourceFileLoader("bc250_quick_access_fan_v2_trust", str(HELPER_SOURCE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "fan-policy.json"
    path.write_text(json.dumps({"schema": 2, "channels": {"3": {"mode": "fixed", "percent": 90, "role": "pump"}}}))
    module.SYSTEM_FAN_POLICY = path
    if os.geteuid() != 0:
        assert module.fan_policy_channels() == {}  # not root's file
    link = tmp_path / "link.json"
    link.symlink_to(path)
    assert module._root_json(link) == {}


def test_the_panel_resumes_the_desktops_fan_service(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    calls: list[tuple[str, ...]] = []

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(plugin, "_run_verified", lambda *args, **_kwargs: calls.append(args) or {"ok": True, "resumed": True})
    assert asyncio.run(plugin.resume_fan_service())["ok"] is True
    assert calls == [("fan-resume",)]


def test_the_panel_shows_v2_modes_and_keeps_pumps_over_their_floor():
    panel = (ROOT / "integrations/decky/bc250-quick-access/src/index.tsx").read_text(encoding="utf-8")
    assert f"const PUMP_FLOOR_PERCENT = {engine.PUMP_FLOOR_PERCENT};" in panel
    assert "fanPump ? PUMP_FLOOR_PERCENT : 0" in panel
    assert "applyFanChannel(fanChannel, Math.max(fanMin, fanDuty))" in panel
    assert 'callable<[], Result>("resume_fan_service")' in panel
