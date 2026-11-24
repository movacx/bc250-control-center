"""What the failure says itself is what the window shows, and a step to take is not a fault."""

from __future__ import annotations

from pathlib import Path

import pytest

from bc250cc.infrastructure import helixsr
from bc250cc.shared.errors import ActionNeeded, ActionNeededValue
from frontends.desktop.core.error_diagnostics import diagnose_error, error_sections


def test_a_gpu_failure_without_a_rule_shows_its_own_sentence():
    text = "VRChat has an unknown lock that this version cannot handle yet."
    sections, code = error_sections(text, context="GPU governor")
    assert code == "BC250-GPU-900" and dict(sections)["What happened"] == text


def test_a_dump_is_not_taken_for_a_sentence():
    sections, _code = error_sections(chr(10).join(("first line of a dump", "second line of it.")), context="GPU governor")
    assert dict(sections)["What happened"] == "The GPU operation could not be completed."


@pytest.mark.parametrize("text", [
    "[Errno 30] Read-only file system: '~/.local/state/x.sh'",
    "[Errno 30] File system in sola lettura: '~/.local/state/x.sh'",
])
def test_a_read_only_disk_is_named_in_every_language(text):
    assert diagnose_error(text, context="GPU governor").code == "BC250-DISK-001"


def test_a_frequency_cyan_does_not_accept_asks_for_a_step():
    assert issubclass(ActionNeededValue, ActionNeeded) and issubclass(ActionNeededValue, ValueError)


def test_taking_helixsr_out_of_a_game_that_has_none_is_done(monkeypatch):
    def refuse(*_arguments):
        raise RuntimeError("HelixSR is not installed in Some Game")

    monkeypatch.setattr(helixsr, "_run_bridge", refuse)
    helixsr._remove_with_bridge(Path("/game"))
    monkeypatch.setattr(helixsr, "_run_bridge", lambda *_a: (_ for _ in ()).throw(RuntimeError("the file is in use")))
    with pytest.raises(RuntimeError, match="in use"):
        helixsr._remove_with_bridge(Path("/game"))
