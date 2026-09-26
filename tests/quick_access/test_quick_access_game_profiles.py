"""Per-game profiles and the live async-compute row of the Decky panel.

A game's saved GPU profile and fan preset are applied when Steam reports it
running and the previous state comes back when it ends — the player no
longer has to remember to switch by hand. Only names the panel already
offers are stored, and the root helper validates each one again.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "integrations" / "decky" / "bc250-quick-access" / "main.py"


def _module(monkeypatch):
    decky = types.ModuleType("decky")
    decky.logger = types.SimpleNamespace(info=lambda *_args, **_kwargs: None)
    monkeypatch.setitem(sys.modules, "decky", decky)
    spec = importlib.util.spec_from_file_location("bc250_quick_access_games_test", BACKEND)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Helper:
    """The root helper as the backend sees it: a status and named actions."""

    def __init__(self, module, *, gpu_range, fan_preset, fan_policy=False):
        self.module = module
        self.calls: list[tuple[str, ...]] = []
        self.status = {
            "ok": True,
            "protocol": module.HELPER_PROTOCOL,
            "gpu_governor": "cyan",
            "gpu_allowed_range": [500, 2000],
            "gpu_range": list(gpu_range),
            "gpu_safe_point_ceilings": [{"frequency": 2100, "voltage": 1000}],
            "system_fan_preset": fan_preset,
            "system_fan_policy": fan_policy,
        }

    def run(self, *args, timeout=0):
        self.calls.append(args)
        if args == ("status",):
            return dict(self.status)
        return {"ok": True}


def _plugin(module, tmp_path, helper, monkeypatch):
    plugin = module.Plugin()
    plugin._settings_dir = tmp_path / "settings"
    monkeypatch.setattr(plugin, "_run", helper.run)
    return plugin


def _profile(module, key):
    return next(p for p in module.profiles_payload(500, 2000, governor="cyan") if p["key"] == key)


def test_the_store_keeps_only_names_the_panel_offers(monkeypatch, tmp_path):
    module = _module(monkeypatch)
    path = tmp_path / "game-profiles.json"
    path.write_text(json.dumps({
        "schema": 1,
        "enabled": True,
        "games": {
            "1091500": {"name": "Cyberpunk 2077", "gpu": "gaming", "fan": "boost"},
            "42": {"name": "Indie", "gpu": "2400-mhz-please", "fan": "quiet"},
            "not-an-id": {"name": "x", "gpu": "gaming"},
            "7": {"name": "Nothing chosen", "gpu": None, "fan": None},
        },
        "session": {"app_id": "abc"},
    }), encoding="utf-8")

    store = module._load_game_store(path)

    assert store["games"] == {
        "1091500": {"name": "Cyberpunk 2077", "gpu": "gaming", "fan": "boost"},
        "42": {"name": "Indie", "gpu": None, "fan": "quiet"},
    }
    assert store["session"] is None
    assert module._app_id(True) is None and module._app_id("0") is None
    assert module._app_id(2 ** 64) is None and module._app_id("3141592653") == "3141592653"


def test_a_game_start_applies_its_profile_and_its_end_puts_the_board_back(monkeypatch, tmp_path):
    module = _module(monkeypatch)
    balanced = _profile(module, "balanced")
    helper = _Helper(module, gpu_range=(balanced["min"], balanced["max"]), fan_preset="quiet")
    plugin = _plugin(module, tmp_path, helper, monkeypatch)

    saved = asyncio.run(plugin.save_game_profile(1091500, "Cyberpunk 2077", "gaming", "boost"))
    assert saved["games"] == [{"app_id": "1091500", "name": "Cyberpunk 2077", "gpu": "gaming", "fan": "boost"}]

    started = asyncio.run(plugin.game_started("1091500", "Cyberpunk 2077"))
    assert started["ok"] and started["applied"] and (started["gpu"], started["fan"]) == ("gaming", "boost")
    assert ("gpu-profile", "gaming") in helper.calls and ("fan-system", "boost") in helper.calls
    assert asyncio.run(plugin.game_profiles())["session"]["app_id"] == "1091500"

    # Decky reloading mid-game must not apply it twice.
    helper.calls.clear()
    assert asyncio.run(plugin.game_started("1091500", "Cyberpunk 2077"))["reason"] == "already-applied"
    assert helper.calls == []

    stopped = asyncio.run(plugin.game_stopped(1091500))
    assert stopped["ok"] and stopped["restored"]
    assert ("gpu-profile", "balanced") in helper.calls and ("fan-system", "quiet") in helper.calls
    assert asyncio.run(plugin.game_profiles())["session"] is None


def test_the_desktop_fan_service_is_resumed_rather_than_overwritten(monkeypatch, tmp_path):
    module = _module(monkeypatch)
    helper = _Helper(module, gpu_range=(1000, 2100), fan_preset=None, fan_policy=True)
    plugin = _plugin(module, tmp_path, helper, monkeypatch)
    asyncio.run(plugin.save_game_profile("42", "Indie", "balanced", "quiet"))

    asyncio.run(plugin.game_started("42", "Indie"))
    helper.calls.clear()
    asyncio.run(plugin.game_stopped("42"))

    # The live range was a TOML safe point, and the fans belonged to the
    # desktop's service: both go back to exactly that.
    assert ("gpu-safe-point", "2100") in helper.calls
    assert ("fan-resume",) in helper.calls
    assert not any(call[0] == "fan-system" for call in helper.calls)


def test_custom_fans_fall_back_to_the_bios_and_no_profile_changes_nothing(monkeypatch, tmp_path):
    module = _module(monkeypatch)
    helper = _Helper(module, gpu_range=(1000, 1234), fan_preset=None)
    plugin = _plugin(module, tmp_path, helper, monkeypatch)

    assert asyncio.run(plugin.game_started("99", "Unknown"))["reason"] == "no-profile"
    assert helper.calls == []

    asyncio.run(plugin.save_game_profile("99", "Unknown", None, "boost"))
    asyncio.run(plugin.game_started("99", "Unknown"))
    helper.calls.clear()
    asyncio.run(plugin.game_stopped("99"))
    assert ("fan-system", "automatic") in helper.calls
    assert not any(call[0].startswith("gpu") for call in helper.calls)


def test_editing_mid_game_reapplies_from_the_pre_game_state(monkeypatch, tmp_path):
    module = _module(monkeypatch)
    balanced = _profile(module, "balanced")
    helper = _Helper(module, gpu_range=(balanced["min"], balanced["max"]), fan_preset="balanced")
    plugin = _plugin(module, tmp_path, helper, monkeypatch)
    asyncio.run(plugin.save_game_profile("5", "Game", "gaming", None))
    asyncio.run(plugin.game_started("5", "Game"))

    asyncio.run(plugin.save_game_profile("5", "Game", "benchmark", None))
    helper.calls.clear()
    result = asyncio.run(plugin.game_started("5", "Game", True))

    assert result["gpu"] == "benchmark"
    order = [call for call in helper.calls if call[0] == "gpu-profile"]
    assert order == [("gpu-profile", "balanced"), ("gpu-profile", "benchmark")]


def test_a_running_board_operation_is_never_interleaved(monkeypatch, tmp_path):
    module = _module(monkeypatch)
    helper = _Helper(module, gpu_range=(1000, 1500), fan_preset="quiet")
    plugin = _plugin(module, tmp_path, helper, monkeypatch)
    asyncio.run(plugin.save_game_profile("5", "Game", "gaming", None))

    async def busy_start():
        async with plugin._operation_lock:
            return await plugin.game_started("5", "Game")

    result = asyncio.run(busy_start())
    assert result["ok"] is False and result["applied"] is False
    assert "still running" in result["error"]


def test_saving_refuses_unknown_names_and_empty_choices(monkeypatch, tmp_path):
    module = _module(monkeypatch)
    plugin = module.Plugin()
    plugin._settings_dir = tmp_path
    assert asyncio.run(plugin.save_game_profile("5", "Game", "overdrive", None))["ok"] is False
    assert asyncio.run(plugin.save_game_profile("5", "Game", None, "max"))["ok"] is False
    assert asyncio.run(plugin.save_game_profile("5", "Game", None, None))["ok"] is False
    assert asyncio.run(plugin.set_game_profiles_enabled("yes"))["ok"] is False
    assert asyncio.run(plugin.set_game_profiles_enabled(False))["enabled"] is False


def _proc(tmp_path, compute_ns):
    proc = tmp_path / "proc"
    pid = proc / "4242"
    (pid / "fd").mkdir(parents=True, exist_ok=True)
    (pid / "fdinfo").mkdir(exist_ok=True)
    fd = pid / "fd" / "7"
    if not fd.is_symlink():
        os.symlink("/dev/dri/renderD128", fd)
    (pid / "fdinfo" / "7").write_text(
        f"drm-driver:\tamdgpu\ndrm-client-id:\t12\ndrm-engine-gfx:\t900 ns\ndrm-engine-compute:\t{compute_ns} ns\n",
        encoding="utf-8",
    )
    (pid / "comm").write_text("Cyberpunk2077.e\n", encoding="utf-8")
    (pid / "stat").write_text("4242 (game) S " + " ".join(["0"] * 50) + "\n", encoding="utf-8")
    (proc / "uptime").write_text("1000.0 900.0\n", encoding="utf-8")
    return proc


def test_ace_usage_comes_from_the_compute_engine_counter(monkeypatch, tmp_path):
    module = _module(monkeypatch)
    clock = iter([10.0, 11.0])
    sampler = module.AceSampler(str(_proc(tmp_path, 0)), clock=lambda: next(clock))

    first = sampler.sample()
    assert first == {"ace_available": True, "ace_busy_percent": None, "ace_process": ""}

    _proc(tmp_path, 340_000_000)  # 0.34 s of compute work in one second
    second = sampler.sample()
    assert second["ace_busy_percent"] == 34
    assert second["ace_process"] == "Cyberpunk2077.e"


def test_no_amdgpu_client_means_ace_unavailable(monkeypatch, tmp_path):
    module = _module(monkeypatch)
    proc = tmp_path / "proc"
    (proc / "1").mkdir(parents=True)
    (proc / "uptime").write_text("5.0 5.0\n", encoding="utf-8")
    sampler = module.AceSampler(str(proc), clock=lambda: 1.0)
    assert sampler.sample()["ace_available"] is False
