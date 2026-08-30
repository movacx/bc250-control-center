import json
from types import SimpleNamespace

import bc250cc.infrastructure.cpu_runtime_snapshot as runtime
from bc250cc.domain.cpu.active_tuning import resolve_active_cpu_tuning
from bc250cc.infrastructure.cpu_oc_config import estimated_vid
from frontends.desktop.core.cpu_refresh_presenter import present_cpu_tuning

BOOT_ID = "12345678-1234-1234-1234-123456789abc"


def _payload(**profile_changes):
    profile = {
        "mode": "manual",
        "frequency": 3700,
        "scale": -30,
        "temperature": 90,
        "estimated_vid": estimated_vid(3700, -30),
        "reference_scale": -34,
        "observed_at": 1_000,
        "persistable": True,
    }
    profile.update(profile_changes)
    return {
        "schema": 1,
        "producer": "bc250-cpu-smu-helper",
        "helper_protocol": 8,
        "boot_id": BOOT_ID,
        "observed_at_unix_ms": 1_000_000,
        "action_observed_at_unix_ns": 1_000_000_000_000,
        "active_profile": profile,
    }


def _reader(monkeypatch, payload):
    metadata = SimpleNamespace(st_mode=0o100644, st_uid=0, st_size=100, st_dev=1, st_ino=2)
    monkeypatch.setattr(runtime, "_safe_metadata", lambda _path: metadata)
    monkeypatch.setattr(runtime, "_read_bytes", lambda _path, _expected: json.dumps(payload).encode())
    monkeypatch.setattr(runtime, "_boot_id", lambda _path: BOOT_ID)
    return runtime.read_cpu_runtime_snapshot(now_unix_ms=1_000_000)


def test_cpu_runtime_snapshot_accepts_exact_same_boot_profile(monkeypatch):
    state = _reader(monkeypatch, _payload())

    assert state is not None
    assert state["source_kind"] == "quick_access"
    assert state["active_profile"]["frequency"] == 3700


def test_cpu_runtime_snapshot_rejects_wrong_boot_protocol_and_vid(monkeypatch):
    wrong_boot = _payload()
    wrong_boot["boot_id"] = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert _reader(monkeypatch, wrong_boot) is None

    wrong_protocol = _payload()
    wrong_protocol["helper_protocol"] = 7
    assert _reader(monkeypatch, wrong_protocol) is None

    assert _reader(monkeypatch, _payload(estimated_vid=999)) is None


def test_newer_quick_access_cpu_profile_wins_but_newer_desktop_action_recovers():
    qam = {
        "available": True,
        "active_profile": _payload()["active_profile"],
    }
    older_desktop = {
        "same_boot": True,
        "matches_current_config": True,
        "snapshot": {
            "recorded_at_epoch_ns": 900_000_000_000,
            "frequency": 3600,
            "scale": -35,
            "temperature": 90,
        },
    }
    active = resolve_active_cpu_tuning({}, older_desktop, {}, qam)
    assert active["source_kind"] == "quick_access"
    assert active["frequency"] == 3700

    newer_desktop = {
        "same_boot": True,
        "matches_current_config": True,
        "snapshot": {
            "recorded_at_epoch_ns": 1_100_000_000_000,
            "frequency": 3800,
            "scale": -32,
            "temperature": 90,
        },
    }
    active = resolve_active_cpu_tuning({}, newer_desktop, {}, qam)
    assert active["source_kind"] == "desktop"
    assert active["frequency"] == 3800


def test_quick_access_source_is_explicit_in_cpu_presentation():
    qam = {"available": True, "active_profile": _payload()["active_profile"]}
    view = present_cpu_tuning(
        {}, {}, {}, qam,
        last_applied_frequency=None,
        scale_override_enabled=False,
    )

    assert view.active_source_kind == "quick_access"
    assert view.applied_detail.template.startswith("Quick Access verified snapshot")
