from pathlib import Path

import pytest

from bc250cc.infrastructure.privilege_repository import PrivilegeRepository
from bc250cc.infrastructure.session_privilege_policy import (
    SteamSessionSignals,
    classify_steamos_game_mode,
    trusted_helper_metadata,
)


def signals(**overrides):
    values = {"is_steamos": True}
    values.update(overrides)
    return SteamSessionSignals(**values)


@pytest.mark.parametrize(
    "candidate",
    (
        signals(gamescope_ancestor=True),
        signals(direct_game_marker=True),
        signals(wayland_display="gamescope-0"),
        signals(steam_ids=True, steam_ancestor=True),
    ),
)
def test_game_mode_requires_a_coherent_steamos_signal(candidate):
    assert classify_steamos_game_mode(candidate) is True


@pytest.mark.parametrize(
    "candidate",
    (
        signals(is_steamos=False, gamescope_ancestor=True),
        signals(),
        signals(steam_ids=True, steam_ancestor=False),
        signals(steam_ids=False, steam_ancestor=True),
    ),
)
def test_ambiguous_or_non_steamos_sessions_fail_closed(candidate):
    assert classify_steamos_game_mode(candidate) is False


def test_desktop_shell_overrides_spoofable_ambient_steam_markers():
    candidate = signals(
        desktop="KDE:Plasma",
        direct_game_marker=True,
        wayland_display="steam-spoof",
        steam_ids=True,
        steam_ancestor=True,
    )
    assert classify_steamos_game_mode(candidate) is False


def test_real_gamescope_ancestor_remains_authoritative_over_inherited_desktop_label():
    assert classify_steamos_game_mode(
        signals(desktop="KDE", gamescope_ancestor=True)
    ) is True


@pytest.mark.parametrize(
    ("values", "trusted"),
    (
        ({"is_regular": True, "is_symlink": False, "owner_uid": 0, "mode": 0o100755, "executable": True}, True),
        ({"is_regular": True, "is_symlink": True, "owner_uid": 0, "mode": 0o120777, "executable": True}, False),
        ({"is_regular": True, "is_symlink": False, "owner_uid": 1000, "mode": 0o100755, "executable": True}, False),
        ({"is_regular": True, "is_symlink": False, "owner_uid": 0, "mode": 0o100775, "executable": True}, False),
        ({"is_regular": True, "is_symlink": False, "owner_uid": 0, "mode": 0o100777, "executable": True}, False),
        ({"is_regular": True, "is_symlink": False, "owner_uid": 0, "mode": 0o100644, "executable": False}, False),
    ),
)
def test_helper_metadata_requires_root_owned_nonwritable_executable(values, trusted):
    assert trusted_helper_metadata(**values) is trusted


def test_environment_cannot_replace_the_polkit_annotated_helper(monkeypatch):
    monkeypatch.setenv("BC250_STEAMOS_GAME_HELPER", "/tmp/user-controlled-helper")
    candidates = PrivilegeRepository()._steamos_game_helper_candidates()
    assert all(str(path).startswith(("/usr/libexec/", "/usr/local/libexec/")) for path in candidates)
    assert "/tmp/user-controlled-helper" not in {str(path) for path in candidates}


def test_repository_detection_never_uses_systemwide_pgrep(monkeypatch):
    repository = PrivilegeRepository()
    repository._es_steamos = lambda: True
    repository._process_tree_contains = lambda *_args: False
    for name in (
        "XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION",
        "GAMESCOPE_WAYLAND_DISPLAY", "STEAM_GAMEPADUI", "SteamGamepadUI",
        "SteamTenfoot", "SteamDeck", "SteamClientLaunch", "SteamAppId",
        "SteamGameId", "WAYLAND_DISPLAY",
    ):
        monkeypatch.delenv(name, raising=False)
    assert repository._steamos_game_mode_detected() is False
    assert "pgrep" not in PrivilegeRepository._steamos_game_mode_detected.__code__.co_names


def test_protocol_reader_is_bounded(tmp_path):
    helper = tmp_path / "helper"
    helper.write_text(
        "BC250_HELPER_PROTOCOL=9\n" + ("x" * 100_000), encoding="utf-8"
    )
    assert PrivilegeRepository()._steamos_game_helper_protocol(helper) == 9


def test_gui_requires_the_protocol_exported_by_the_staged_game_mode_helper():
    helper = (
        Path(__file__).resolve().parents[2]
        / "privileged/helpers/bc250-steamos-game-helper"
    )
    required = PrivilegeRepository._STEAMOS_GAME_HELPER_PROTOCOL

    assert f"BC250_HELPER_PROTOCOL={required}" in helper.read_text(encoding="utf-8")


def test_newer_trusted_game_mode_helper_remains_compatible_with_an_older_gui(tmp_path):
    helper = tmp_path / "game-helper"
    helper.write_text("BC250_HELPER_PROTOCOL=21\n", encoding="utf-8")
    repository = PrivilegeRepository()
    repository._steamos_game_helper_path = lambda: str(helper)
    repository._command_path = lambda name: "/usr/bin/pkexec" if name == "pkexec" else ""

    command = repository._comando_steamos_game_helper(
        "governor-restart", "cyan-skillfish-governor-smu.service"
    )

    assert command[:2] == ["pkexec", str(helper)]


def test_game_mode_helper_older_than_the_minimum_is_rejected(tmp_path):
    helper = tmp_path / "game-helper"
    helper.write_text("BC250_HELPER_PROTOCOL=1\n", encoding="utf-8")
    repository = PrivilegeRepository()
    repository._steamos_game_helper_path = lambda: str(helper)

    with pytest.raises(RuntimeError, match="minimum required"):
        repository._comando_steamos_game_helper(
            "governor-restart", "cyan-skillfish-governor-smu.service"
        )
