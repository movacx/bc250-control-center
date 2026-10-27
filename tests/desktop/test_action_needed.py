"""A request refused until the user does one thing is not an error.

Ten reports of the first week were such refusals (close Steam, remove
HelixSR from the games first, prepare dependencies) shown as red GPU error
windows with a code, so users reported them as bugs.
"""

from __future__ import annotations

import pytest

from bc250cc.infrastructure import helixsr
from bc250cc.shared.errors import ActionNeeded
from frontends.desktop.components import widgets
from frontends.desktop.core import raw_errors


def _window(qtbot, monkeypatch, error: Exception):
    recorded = []
    monkeypatch.setattr(widgets, "record_window_error", lambda *args, **kwargs: recorded.append(args))
    raw_errors.remember(error)
    dialog = widgets.InfoDialog("Could not change the Steam launch option", str(error), tone="red")
    qtbot.addWidget(dialog)
    return dialog, recorded


def test_a_refusal_that_asks_for_an_action_has_no_error_code(qtbot, monkeypatch):
    dialog, recorded = _window(
        qtbot, monkeypatch, ActionNeeded("Close Steam completely first (Steam > Exit), then try again.")
    )
    assert dialog.report_code == ""
    assert recorded == []


def test_a_real_failure_is_still_an_error(qtbot, monkeypatch):
    dialog, recorded = _window(qtbot, monkeypatch, RuntimeError("Cyan D-Bus range could not be read here."))
    assert dialog.report_code
    assert recorded


def test_a_native_linux_game_is_refused_before_the_bridge_runs(tmp_path):
    (tmp_path / "game.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "cs2").write_bytes(b"\x7fELF")
    with pytest.raises(ActionNeeded, match="natively on Linux"):
        helixsr._refuse_native_game(tmp_path)


def test_a_proton_game_passes_the_native_check(tmp_path):
    (tmp_path / "Binaries" / "Win64").mkdir(parents=True)
    (tmp_path / "Binaries" / "Win64" / "Game.EXE").write_bytes(b"MZ")
    helixsr._refuse_native_game(tmp_path)
