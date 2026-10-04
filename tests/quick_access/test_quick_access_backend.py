"""Isolated protocol checks for the optional Decky backend."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "integrations" / "decky" / "bc250-quick-access" / "main.py"


def _backend_module(monkeypatch):
    decky = types.ModuleType("decky")
    decky.logger = types.SimpleNamespace(info=lambda *_args, **_kwargs: None)
    # Decky always passes this; without it the backend falls back to a path
    # next to the plugin, which in a checkout is inside the repository.
    decky.DECKY_PLUGIN_SETTINGS_DIR = tempfile.mkdtemp(prefix="bc250-qam-settings-")
    monkeypatch.setitem(sys.modules, "decky", decky)
    spec = importlib.util.spec_from_file_location("bc250_quick_access_backend_test", BACKEND)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backend_refuses_an_incompatible_helper_before_hardware_operation(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    calls: list[tuple[str, ...]] = []

    def fake_run(*args, **_kwargs):
        calls.append(args)
        return {"ok": True, "protocol": module.HELPER_PROTOCOL + 1}

    monkeypatch.setattr(plugin, "_run", fake_run)
    result = plugin._run_verified("gpu-profile", "gaming", timeout=30)

    assert result["ok"] is False
    assert "protocol is incompatible" in result["error"]
    assert calls == [("status",)]


def test_backend_checks_protocol_then_delegates_named_operation(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    calls: list[tuple[str, ...]] = []

    def fake_run(*args, **_kwargs):
        calls.append(args)
        if args == ("status",):
            return {"ok": True, "protocol": module.HELPER_PROTOCOL}
        return {"ok": True, "gpu_range": [1000, 1850]}

    monkeypatch.setattr(plugin, "_run", fake_run)
    result = plugin._run_verified("gpu-profile", "gaming", timeout=30)

    assert result == {"ok": True, "gpu_range": [1000, 1850]}
    assert calls == [("status",), ("gpu-profile", "gaming")]


def test_backend_gpu_profile_skips_the_redundant_full_status_preflight(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    calls: list[tuple[str, ...]] = []

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(
        plugin,
        "_run",
        lambda *args, **_kwargs: calls.append(args) or {"ok": True, "gpu_range": [1000, 1850]},
    )

    result = asyncio.run(plugin.apply_gpu_profile("benchmark"))

    assert result["ok"] is True
    assert calls == [("gpu-profile", "benchmark")]


def test_backend_safe_point_delegates_advertisement_validation_to_root_helper(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    calls: list[tuple[str, ...]] = []

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(
        plugin,
        "_run",
        lambda *args, **_kwargs: calls.append(args) or {"ok": True, "gpu_range": [1000, 2200]},
    )

    result = asyncio.run(plugin.apply_gpu_safe_point(2200))

    assert result["ok"] is True
    assert calls == [("gpu-safe-point", "2200")]


def test_gpu_range_write_does_not_wait_behind_a_passive_status_scan(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(plugin, "_run", lambda *_args, **_kwargs: {"ok": True, "gpu_range": [1000, 2000]})

    async def exercise():
        # A status() scan holds the helper lock; the D-Bus-only GPU write
        # must not queue behind it.
        await plugin._helper_lock.acquire()
        try:
            return await asyncio.wait_for(plugin.apply_gpu_profile("benchmark"), 1)
        finally:
            plugin._helper_lock.release()

    assert asyncio.run(exercise())["gpu_range"] == [1000, 2000]


def test_status_overlapping_a_gpu_write_reports_the_verified_new_range(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    def stale_status():
        # The write lands while this scan is still reading the old range.
        plugin._note_gpu_write({"ok": True, "gpu_range": [1000, 2000], "gpu_performance_enabled": False})
        return {"ok": True, "protocol": module.HELPER_PROTOCOL, "gpu_range": [1000, 1850]}

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(plugin, "_verified_status", stale_status)

    result = asyncio.run(plugin.status())

    assert result["gpu_range"] == [1000, 2000]
    assert result["gpu_performance_enabled"] is False


def test_cpu_telemetry_remains_available_during_exclusive_cpu_operation(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    calls: list[tuple[str, ...]] = []

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    def fake_run(*args, **_kwargs):
        calls.append(args)
        return {
            "ok": True,
            "protocol": module.HELPER_PROTOCOL,
            "cpu_frequency_mhz": 3875,
            "cpu_temperature_c": 61.5,
        }

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(plugin, "_run", fake_run)

    async def exercise():
        await plugin._operation_lock.acquire()
        await plugin._helper_lock.acquire()
        try:
            return await plugin.cpu_telemetry()
        finally:
            plugin._helper_lock.release()
            plugin._operation_lock.release()

    result = asyncio.run(exercise())

    assert result["cpu_frequency_mhz"] == 3875
    assert result["cpu_temperature_c"] == 61.5
    assert calls == [("cpu-telemetry",)]


def test_backend_status_keeps_a_bounded_session_only_action_history(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    for index in range(module.MAX_RECENT_ACTIONS + 2):
        plugin._record_action("gpu", f"profile-{index}", {"ok": index % 2 == 0})
    monkeypatch.setattr(plugin, "_verified_status", lambda: {"ok": True, "protocol": module.HELPER_PROTOCOL})

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    result = asyncio.run(plugin.status())

    assert len(result["recent_actions"]) == module.MAX_RECENT_ACTIONS
    assert result["recent_actions"][0]["target"] == f"profile-{module.MAX_RECENT_ACTIONS + 1}"
    assert result["recent_actions"][-1]["target"] == "profile-2"


def test_backend_action_history_uses_unix_milliseconds(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    before = int(time.time() * 1000)

    plugin._record_action("cpu", "saved", {"ok": True})

    after = int(time.time() * 1000)
    observed = plugin._recent_actions[-1]["at"]
    assert isinstance(observed, int)
    assert before <= observed <= after
    assert observed >= 10_000_000_000


def test_backend_repeated_gpu_apply_runs_one_verified_transition_per_completed_press(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    calls: list[tuple[str, ...]] = []

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    def verified(*args, **_kwargs):
        calls.append(args)
        return {"ok": True, "gpu_range": [1000, 1850]}

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(plugin, "_run", verified)

    first = asyncio.run(plugin.apply_gpu_profile("gaming"))
    second = asyncio.run(plugin.apply_gpu_profile("gaming"))

    assert first["ok"] is True
    assert second["ok"] is True
    assert calls == [("gpu-profile", "gaming"), ("gpu-profile", "gaming")]


def test_backend_refuses_to_queue_a_second_operation(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    plugin._operation_lock = asyncio.Lock()

    async def exercise():
        await plugin._operation_lock.acquire()
        try:
            return await plugin.apply_system_fan_preset("balanced")
        finally:
            plugin._operation_lock.release()

    result = asyncio.run(exercise())
    assert result["ok"] is False
    assert "already applying" in result["error"]


def test_backend_delegates_one_bounded_fan_channel_operation(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    calls: list[tuple[str, ...]] = []

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(
        plugin,
        "_run_verified",
        lambda *args, **_kwargs: calls.append(args) or {"ok": True, "fan_channel": 2, "percent": 60},
    )

    result = asyncio.run(plugin.apply_fan_channel(2, 60))

    assert result["ok"] is True
    assert calls == [("fan-channel", "2", "60")]
    assert plugin._recent_actions[-1]["target"] == "pwm2:60"


def test_backend_delegates_selected_channel_automatic_mode(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    calls: list[tuple[str, ...]] = []

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(
        plugin,
        "_run_verified",
        lambda *args, **_kwargs: calls.append(args) or {"ok": True, "fan_channel": 5, "mode": "automatic"},
    )

    result = asyncio.run(plugin.apply_fan_channel("5", "automatic"))

    assert result["ok"] is True
    assert calls == [("fan-channel", "5", "automatic")]


def test_backend_rejects_out_of_contract_fan_channel_before_helper(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    monkeypatch.setattr(plugin, "_run_verified", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not run")))

    for channel, target in ((1, 60), (6, 60), (2, 19), (2, 101), (2, 50.0), (True, 60), (2, False)):
        result = asyncio.run(plugin.apply_fan_channel(channel, target))
        assert result["ok"] is False


def test_backend_delegates_one_complete_bounded_cu_table(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    calls: list[tuple[str, ...]] = []

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(
        plugin,
        "_run_verified",
        lambda *args, **_kwargs: calls.append(args)
        or {"ok": True, "cu_masks": [15, 15, 7, 7], "cu_active_cus": 28},
    )

    result = asyncio.run(plugin.apply_cu_table([15, 15, 7, 7]))

    assert result["ok"] is True
    assert calls == [("cu-table", "15", "15", "7", "7")]
    assert plugin._recent_actions[-1]["target"] == "28cu:0f-0f-07-07"


def test_backend_exposes_closed_cu_persistence_operations(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    calls: list[tuple[str, ...]] = []

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(
        plugin,
        "_run_verified",
        lambda *args, **_kwargs: calls.append(args) or {"ok": True},
    )

    assert asyncio.run(plugin.save_cu_table([15, 15, 7, 7]))["ok"] is True
    assert asyncio.run(plugin.install_cu_service())["ok"] is True
    assert asyncio.run(plugin.remove_cu_service())["ok"] is True
    assert calls == [
        ("cu-save", "15", "15", "7", "7"),
        ("cu-service", "install"),
        ("cu-service", "remove"),
    ]
    assert [item["target"] for item in plugin._recent_actions] == [
        "saved-28cu:0f-0f-07-07",
        "service-install",
        "service-remove",
    ]


def test_backend_rejects_out_of_contract_cu_tables_before_helper(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    monkeypatch.setattr(
        plugin,
        "_run_verified",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not run")),
    )

    invalid = (
        [7, 7, 7],
        [7, 7, 7, 7, 7],
        [7, 7, 7, True],
        [7, 7, 7, "7"],
        [7, 7, 7, 32],
        [7, 7, 7, 3],  # 16 routed WGPs? No: only 22 CUs, below QAM floor.
    )
    for masks in invalid:
        result = asyncio.run(plugin.apply_cu_table(masks))
        assert result["ok"] is False


def test_backend_delegates_cpu_vid_detection_and_protected_service_operations(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    calls: list[tuple[str, ...]] = []

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(
        plugin,
        "_run_verified",
        lambda *args, **_kwargs: calls.append(args) or {"ok": True},
    )

    assert asyncio.run(plugin.apply_cpu_tuning(3700, 1200))["ok"] is True
    assert asyncio.run(plugin.apply_cpu_scale(3700, -30))["ok"] is True
    assert asyncio.run(plugin.install_cpu_service())["ok"] is True
    assert asyncio.run(plugin.remove_cpu_service())["ok"] is True
    assert calls == [
        ("cpu-detect", "3700", "1200"),
        ("cpu-scale", "3700", "-30"),
        ("cpu-service", "install"),
        ("cpu-service", "remove"),
    ]


def test_backend_leaves_cpu_service_evidence_validation_to_root_helper(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(
        plugin,
        "_run_verified",
        lambda *args, **_kwargs: {"ok": False, "error": "same-boot detector evidence required", "args": args},
    )

    result = asyncio.run(plugin.install_cpu_service())
    assert result["ok"] is False
    assert "same-boot detector evidence" in result["error"]
    assert result["args"] == ("cpu-service", "install")


def test_backend_rejects_out_of_contract_cpu_values_before_helper(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    monkeypatch.setattr(
        plugin,
        "_run_verified",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not run")),
    )

    invalid = (
        (3499, 1200),
        (4201, 1200),
        (3725, 1200),
        (3700, 949),
        (3700, 1326),
        (3700, 1201),
        (3700.0, 1200),
        (True, 1200),
        (3700, False),
        ("03700", "1200"),
    )
    for frequency, vid in invalid:
        assert asyncio.run(plugin.apply_cpu_tuning(frequency, vid))["ok"] is False

    invalid_scale = (
        (3499, -30),
        (4201, -30),
        (3725, -30),
        (3700, -51),
        (3700, 1),
        (3700, -30.0),
        (True, -30),
        (3700, False),
        ("03700", "-30"),
    )
    for frequency, scale in invalid_scale:
        assert asyncio.run(plugin.apply_cpu_scale(frequency, scale))["ok"] is False


def test_cpu_profiles_default_to_the_desktop_tiers_until_exported(monkeypatch):
    module = _backend_module(monkeypatch)

    defaults = module._validated_cpu_profiles(None)
    assert [(p["key"], p["frequency"], p["vid"]) for p in defaults] == [
        ("board_average", 3550, 1050), ("mid_point", 3850, 1150), ("safe_maximum", 4000, 1275),
    ]
    assert all(p["default"] for p in defaults)

    exported = module._validated_cpu_profiles([
        {"key": "mid_point", "name": "Mine", "frequency": 3900, "vid": 1160},
    ])
    assert exported[1] == {"key": "mid_point", "name": "Mine", "frequency": 3900, "vid": 1160}
    assert exported[0]["default"] and exported[2]["default"]


def test_status_during_a_long_operation_answers_from_the_last_scan(monkeypatch):
    """A remounted panel must not wait minutes behind a CPU run for its cards."""
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()

    async def immediate_to_thread(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", immediate_to_thread)
    monkeypatch.setattr(plugin, "_verified_status", lambda: {"ok": True, "protocol": module.HELPER_PROTOCOL, "cu_active_cus": 34})
    first = asyncio.run(plugin.status())
    assert first["operation_in_progress"] is None

    async def exercise():
        await plugin._helper_lock.acquire()
        plugin._running_operation = {"action": "cpu-detect", "arguments": ["3850", "1150"], "started_at": 1}
        try:
            return await asyncio.wait_for(plugin.status(), 1)
        finally:
            plugin._running_operation = None
            plugin._helper_lock.release()

    cached = asyncio.run(exercise())
    assert cached["cu_active_cus"] == 34
    assert cached["status_cached"] is True
    assert cached["operation_in_progress"]["action"] == "cpu-detect"


def test_failed_operations_are_kept_for_the_desktop_diagnostics(monkeypatch, tmp_path):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    plugin._settings_dir = tmp_path

    plugin._record_action("cpu", "detect-3850:1150", {"ok": False, "error": "ERR SMU_IN_USE: busy"})
    plugin._record_action("gpu", "gaming", {"ok": True})

    lines = (tmp_path / module.DIAGNOSTICS_FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["module"] == "cpu" and entry["target"] == "detect-3850:1150"
    assert entry["error"] == "ERR SMU_IN_USE: busy"
    assert (tmp_path / module.DIAGNOSTICS_FILENAME).stat().st_mode & 0o777 == 0o644


def test_cpu_cores_carry_their_physical_core(monkeypatch, tmp_path):
    module = _backend_module(monkeypatch)
    # Six of the die's eight cores enabled, two SMT threads each (ids 3 and 7 locked).
    for index, core_id in enumerate((0, 0, 1, 1, 2, 2, 4, 4, 5, 5, 6, 6)):
        topology = tmp_path / f"cpu{index}" / "topology"
        topology.mkdir(parents=True)
        (topology / "core_id").write_text(f"{core_id}\n")
    ids = module._read_core_ids(tmp_path)
    assert sorted(set(ids.values())) == [0, 1, 2, 4, 5, 6]
    assert len(ids) == 12
    assert module.BC250_PHYSICAL_CORES == 8
