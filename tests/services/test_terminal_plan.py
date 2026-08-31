import os
import subprocess
from pathlib import Path

import pytest

import bc250cc.infrastructure.terminal_repository as terminal_repository
from bc250cc.infrastructure.terminal_plan import terminal_candidates, workflow_wrapper
from bc250cc.infrastructure.terminal_repository import (
    TerminalLaunchResult,
    TerminalRepository,
)


def test_wrapper_preserves_command_exit_status_and_logs_quoted_text(tmp_path):
    status = tmp_path / "result status"
    log = tmp_path / "workflow log"
    wrapped = workflow_wrapper(
        "printf '%s\\n' \"literal ; \\\"quoted\\\" $HOME\"; exit 7",
        status,
        log,
    )
    assert "PIPESTATUS" not in wrapped
    assert "status=$?" in wrapped
    result = subprocess.run(
        ["/usr/bin/bash", "-c", wrapped],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {"HOME": "/tmp/fixed-home"},
    )
    assert result.returncode == 7
    assert status.read_text(encoding="utf-8") == "7\n"
    evidence = log.read_text(encoding="utf-8")
    assert 'literal ; "quoted" /tmp/fixed-home' in evidence
    assert "Process finished with exit code 7" in evidence


@pytest.mark.parametrize(
    ("terminal_env", "prefix"),
    (
        ("konsole --fullscreen", ("konsole", "--fullscreen", "--new-tab")),
        ("gnome-terminal", ("gnome-terminal", "--")),
        ("kitty", ("kitty", "--title")),
        ("alacritty", ("alacritty", "-T")),
        ("wezterm", ("wezterm", "start")),
        ("foot", ("foot", "-T")),
        ("custom-term --flag", ("custom-term", "--flag", "-e")),
    ),
)
def test_terminal_environment_is_tokenized_into_expected_argv(terminal_env, prefix):
    candidates = terminal_candidates(
        "echo wrapped", "BC250 title", terminal_env=terminal_env, home=Path("/home/test")
    )
    assert candidates[0][:len(prefix)] == prefix
    assert all(isinstance(candidate, tuple) for candidate in candidates)
    assert len(candidates) == len(set(candidates))


def test_malformed_terminal_environment_falls_back_without_raising():
    candidates = terminal_candidates(
        "true", "title", terminal_env="'unterminated", home=Path("/home/test")
    )
    assert candidates[0][0] == "xdg-terminal-exec"


def test_repository_launches_first_available_healthy_candidate(tmp_path, monkeypatch):
    repository = TerminalRepository()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setenv("TERMINAL", "kitty")
    monkeypatch.setattr(terminal_repository.shutil, "which", lambda name: f"/usr/bin/{name}")

    class Process:
        pid = 1234

        @staticmethod
        def poll():
            return None

    calls = []
    monkeypatch.setattr(
        terminal_repository.subprocess,
        "Popen",
        lambda argv, **kwargs: calls.append((argv, kwargs)) or Process(),
    )
    monkeypatch.setattr(terminal_repository.time, "sleep", lambda _seconds: None)
    result = repository._abrir_terminal("true", "Fixture")
    assert isinstance(result, TerminalLaunchResult)
    assert result.terminal == "kitty"
    assert result.pid == 1234
    assert calls[0][1] == {"start_new_session": True}
    launched = " ".join(calls[0][0])
    assert "launch-" in launched
    assert "PIPESTATUS" not in launched


def test_no_terminal_creates_private_manual_script(tmp_path, monkeypatch):
    repository = TerminalRepository()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("TERMINAL", raising=False)
    monkeypatch.setattr(terminal_repository.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="Run it manually with: bash") as captured:
        repository._abrir_terminal("printf safe", "Manual")
    script_text = str(captured.value).split("bash ", 1)[1].rstrip(".")
    script = Path(script_text)
    assert script.is_file()
    assert script.stat().st_mode & 0o077 == 0
    assert "printf safe" in script.read_text(encoding="utf-8")


def test_empty_workflow_is_rejected_before_any_launch(tmp_path, monkeypatch):
    repository = TerminalRepository()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(
        terminal_repository.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("empty workflow must not launch"),
    )
    with pytest.raises(RuntimeError, match="empty"):
        repository._abrir_terminal("  ")
