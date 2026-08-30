from bc250cc.infrastructure.dependencias_repository import DependenciasRepository


class FailingPlatformRepository(DependenciasRepository):
    def _steamos_game_mode_detected(self):
        raise OSError("session probe failed")

    def _steamos_game_helper_path(self):
        raise RuntimeError("helper probe failed")


def test_steamos_platform_probe_contains_protected_session_failures(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.steamos_cu_backend_status",
        lambda: (_ for _ in ()).throw(PermissionError("protected")),
    )
    repo = FailingPlatformRepository()

    state = repo._probe_platform_inventory(
        is_steamos=True,
        expected_steamos_repo=tmp_path,
    )

    assert state["cu_privileged_ready"] is False
    assert "Run Prepare dependencies" in state["cu_privileged_reason"]
    assert state["cu_compat_ready"] is False
    assert state["game_mode"] is False
    assert state["game_helper"] == ""
    assert state["game_helper_ready"] is False


def test_platform_probe_uses_one_consistent_game_mode_snapshot(monkeypatch, tmp_path):
    compat = tmp_path / "bc250-cu-live-manager-bc250.sh"
    compat.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.steamos_cu_backend_status",
        lambda: (True, "verified"),
    )
    repo = FailingPlatformRepository()
    repo._steamos_game_mode_detected = lambda: True
    repo._steamos_game_helper_path = lambda: "/usr/libexec/bc250-game-helper"

    state = repo._probe_platform_inventory(
        is_steamos=True,
        expected_steamos_repo=tmp_path,
    )

    assert state == {
        "cu_privileged_ready": True,
        "cu_privileged_reason": "verified",
        "cu_compat_ready": True,
        "game_mode": True,
        "game_helper": "/usr/libexec/bc250-game-helper",
        "game_helper_ready": True,
    }


def test_non_steamos_platform_probe_does_not_touch_steamos_checks(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.steamos_cu_backend_status",
        lambda: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.generic_cu_backend_status",
        lambda: (True, "verified generic backend"),
    )

    state = FailingPlatformRepository()._probe_platform_inventory(
        is_steamos=False,
        expected_steamos_repo=tmp_path,
    )

    # Generic desktop installations now stage the reviewed root backend too;
    # only the SteamOS-specific compatibility and Game Mode probes stay off.
    assert state["cu_privileged_ready"] is True
    assert state["cu_privileged_reason"] == "verified generic backend"
    assert state["game_mode"] is False
    assert state["game_helper"] == ""
