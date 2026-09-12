"""The Game Mode helper runs as root without asking. Its gate has to hold.

``allow_active=yes`` in the Polkit policy means any active local session on
SteamOS, Bazzite or CachyOS can execute this helper as root with no
authentication at all. That is deliberate: gamescope frequently cannot display
a Polkit dialog, so a prompt would make the feature unusable in the one place
it exists for. Everything therefore rests on the helper proving for itself that
it was called from Game Mode.

It did not hold. ``SteamClientLaunch`` counted as a "direct marker" — a signal
strong enough to override the "a desktop shell wins" veto — but the Steam
client exports it into *every* game it launches, Desktop Mode included. So
starting any Steam game from the desktop and pointing ``--origin-pid`` at it
cleared the veto and scored 6 against a threshold of 3: unauthenticated root
for fan-pwm, gpu-voltage, governor-config, governor-restart and cpu-oc.

Two things close it. Only signals unique to a gamescope session may override
the veto, and the actions whose effect outlives the session need direct
evidence of gamescope rather than a weighted score.
"""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

HELPER = Path("privileged/helpers/bc250-steamos-game-helper")
POLICY = Path("privileged/policies/io.github.movacx.bc250-control-center.policy")


@pytest.fixture(scope="module")
def helper():
    if not HELPER.is_file():  # pragma: no cover - packaging layouts
        pytest.skip("the Game Mode helper is not present in this checkout")
    return runpy.run_path(str(HELPER))


def _patch(helper, monkeypatch, *, env, tree=(), global_names=()):
    """Patch what the helper's own functions see.

    ``runpy.run_path`` hands back a *copy* of the namespace, and the functions
    in it keep their original ``__globals__``. Replacing entries in the
    returned dict changes nothing the helper will actually call — so patch the
    globals the functions really resolve against.
    """
    namespace = helper["detect_game_mode"].__globals__
    monkeypatch.setitem(namespace, "read_proc_environ", lambda _pid: dict(env))
    monkeypatch.setitem(namespace, "process_tree", lambda _pid: list(tree))
    monkeypatch.setitem(namespace, "global_process_names", lambda: set(global_names))


def _detect(helper, monkeypatch, *, env, tree=(), global_names=()):
    _patch(helper, monkeypatch, env=env, tree=tree, global_names=global_names)
    return helper["detect_game_mode"](1234, {})


# --------------------------------------------------------------- the bypass


def test_a_steam_game_launched_from_the_desktop_is_not_game_mode(helper, monkeypatch):
    """The exact bypass: Steam sets SteamClientLaunch in Desktop Mode too."""
    allowed, _reasons, negatives = _detect(
        helper,
        monkeypatch,
        env={
            "XDG_CURRENT_DESKTOP": "KDE",
            "SteamClientLaunch": "1",
            "SteamAppId": "570",
        },
    )
    assert allowed is False
    assert any("desktop" in item.lower() for item in negatives)


def test_the_deck_hardware_marker_alone_is_not_game_mode(helper, monkeypatch):
    """``SteamDeck`` says which hardware this is, not which session."""
    allowed, _reasons, _negatives = _detect(
        helper,
        monkeypatch,
        env={"XDG_CURRENT_DESKTOP": "KDE", "SteamDeck": "1"},
    )
    assert allowed is False


def test_no_marker_that_the_desktop_also_sets_can_override_the_veto(helper):
    source = HELPER.read_text(encoding="utf-8")
    block = source[source.index("direct_markers = ("):]
    block = block[: block.index(")")]
    for shared in ("SteamClientLaunch", "SteamDeck"):
        assert shared not in block, (
            f"{shared} is set outside Game Mode, so it cannot be a direct marker"
        )


# ------------------------------------------------------- what still works


def test_a_real_gamescope_session_is_still_game_mode(helper, monkeypatch):
    allowed, reasons, _negatives = _detect(
        helper,
        monkeypatch,
        env={"GAMESCOPE_WAYLAND_DISPLAY": "gamescope-0", "SteamGamepadUI": "1"},
        tree=[(1, "gamescope"), (2, "steam")],
        global_names={"gamescope"},
    )
    assert allowed is True
    assert reasons


def test_gamescope_in_the_process_tree_survives_a_desktop_looking_session(helper, monkeypatch):
    """Bazzite reports a desktop name for its gamescope session."""
    allowed, _reasons, _negatives = _detect(
        helper,
        monkeypatch,
        env={"XDG_CURRENT_DESKTOP": "KDE", "GAMESCOPE_WAYLAND_DISPLAY": "gamescope-0"},
        tree=[(1, "gamescope")],
    )
    assert allowed is True


# --------------------------------------------- the second level of authority


def test_the_persistent_actions_are_named(helper):
    """Whatever rewrites /etc, restarts a service or moves the voltage ladder."""
    assert helper["PERSISTENT_ACTIONS"] == frozenset(
        {"gpu-voltage", "governor-config", "governor-restart", "cpu-oc-service"}
    )


def test_a_persistent_action_needs_proven_gamescope_not_a_score(helper, monkeypatch):
    _patch(helper, monkeypatch, env={"SteamAppId": "570"}, tree=[(1, "steam")])
    assert helper["gamescope_session_proven"](1234) is False


def test_the_compositor_socket_is_proof(helper, monkeypatch):
    _patch(helper, monkeypatch, env={"GAMESCOPE_WAYLAND_DISPLAY": "gamescope-0"})
    assert helper["gamescope_session_proven"](1234) is True


def test_gamescope_in_the_ancestry_is_proof(helper, monkeypatch):
    _patch(helper, monkeypatch, env={}, tree=[(9, "GameScope"), (1, "systemd")])
    assert helper["gamescope_session_proven"](1234) is True


def test_no_origin_process_is_not_proof(helper):
    assert helper["gamescope_session_proven"](None) is False
    assert helper["gamescope_session_proven"](1) is False


def test_every_persistent_action_passes_through_the_second_gate(helper):
    """A new persistent action must not be able to skip it by being new."""
    source = HELPER.read_text(encoding="utf-8")
    assert "if action in PERSISTENT_ACTIONS:" in source
    assert "require_persistent_action(origin_pid)" in source
    dispatch = source[source.index("def main("):]
    gate = dispatch.index("PERSISTENT_ACTIONS")
    for name in helper["PERSISTENT_ACTIONS"]:
        handled = dispatch.index(f"if action == '{name}':")
        assert gate < handled, f"{name} is dispatched before the gate runs"


def test_the_reversible_actions_are_deliberately_outside_it(helper):
    """Fan duty and live CU routing stay promptless; that is the decision."""
    for reversible in ("fan-pwm", "fan-pwm-auto", "cu", "cu-batch"):
        assert reversible not in helper["PERSISTENT_ACTIONS"]


# -------------------------------------------------------------- the policy


def test_the_policy_still_documents_why_this_helper_asks_for_nothing():
    text = POLICY.read_text(encoding="utf-8")
    action = text[text.index("steamos-game-helper"):]
    action = action[: action.index("</action>")]
    assert "<allow_any>no</allow_any>" in action
    assert "<allow_inactive>no</allow_inactive>" in action
    # If this ever becomes auth_admin the helper's own gates stop being the
    # only thing standing between a local session and root.
    assert "<allow_active>yes</allow_active>" in action


def test_no_other_helper_is_allowed_to_skip_authentication():
    text = POLICY.read_text(encoding="utf-8")
    permissive = [
        block.split('id="', 1)[1].split('"', 1)[0]
        for block in text.split("<action ")[1:]
        if "<allow_active>yes</allow_active>" in block
    ]
    assert permissive == ["io.github.movacx.bc250-control-center.steamos-game-helper"]
