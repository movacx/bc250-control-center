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
    # Status 7 is not a status any helper emits, so it resolves to the generic
    # entry with actionable guidance instead of a bare number.
    assert "The workflow did not finish successfully." in evidence
    assert "Diagnostic code: BC250-GENERAL-001" in evidence
    assert "What happened:" in evidence
    assert "How to fix it:" in evidence


def test_wrapper_explains_configuration_exit_status(tmp_path):
    status = tmp_path / "status"
    log = tmp_path / "log"
    wrapped = workflow_wrapper("exit 65", status, log)
    result = subprocess.run(
        ["/usr/bin/bash", "-c", wrapped],
        input="\n",
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 65
    assert "rejected an existing or inconsistent configuration" in result.stdout
    assert "Diagnostic code: BC250-DATA-001" in result.stdout


def _run_wrapper(tmp_path, command):
    wrapped = workflow_wrapper(command, tmp_path / "status", tmp_path / "log")
    return subprocess.run(["/usr/bin/bash", "-c", wrapped], input="\n", check=False, capture_output=True, text=True)


def test_wrapper_explains_the_error_that_stopped_the_workflow(tmp_path):
    # The AUR build failed and was recovered from; Cyan failed later.
    result = _run_wrapper(tmp_path, (
        "echo '[ERROR] AUR/makepkg builds must run as a regular user, not root.'; "
        "echo '[WARN] The AUR build failed; the official Cyan release is installed next instead'; "
        "echo 'ERROR: active init service is not prepared to use the validated Cyan binary'; exit 61"
    ))
    explanation = result.stdout.split("What happened:")[1].split("Last lines from the workflow output:")[0]
    assert "active init service is not prepared" in explanation
    assert "makepkg" not in explanation


def test_wrapper_keeps_the_scripts_own_remediation_lines(tmp_path):
    result = _run_wrapper(tmp_path, "echo '[ERROR] Headers do not match 7.1'; echo '[ERROR] Install linux-headers'; exit 61")
    assert "What happened: Headers do not match 7.1" in result.stdout
    assert "  Install linux-headers" in result.stdout


def test_a_corrupt_download_is_explained_as_one(tmp_path):
    result = _run_wrapper(tmp_path, "echo 'sha256sum: WARNING: 1 computed checksum did NOT match'; exit 1")
    assert "Diagnostic code: BC250-NET-001" in result.stdout


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


def test_a_package_the_repositories_do_not_have_is_explained_as_one(tmp_path):
    result = _run_wrapper(tmp_path, "echo ' - nothing provides python3-sounddevice needed by trcc-linux'; exit 1")
    assert "Diagnostic code: BC250-PKG-004" in result.stdout


def test_a_locked_package_database_is_explained_as_busy(tmp_path):
    result = _run_wrapper(tmp_path, "echo 'error: failed to init transaction (unable to lock database)'; exit 1")
    assert "Diagnostic code: BC250-PKG-001" in result.stdout


def test_a_system_out_of_processes_is_explained_as_one(tmp_path):
    result = _run_wrapper(tmp_path, "echo 'bash: fork: retry: Resource temporarily unavailable'; exit 254")
    assert "Diagnostic code: BC250-RESOURCE-001" in result.stdout


def test_web_workflow_logs_and_keeps_the_parent_authorization_tty(tmp_path):
    """A workflow must not create a second tty and lose sudo's session cache."""
    import shlex

    from frontends.tui.console import Console
    command = "python3 -c 'import os; print(\"same tty:\", os.ttyname(0) == os.environ[\"BC250_EXPECTED_TTY\"]); raise SystemExit(7)'"
    log, status = tmp_path / "workflow.log", tmp_path / "status"
    wrapped = workflow_wrapper(command, status, log, hold=False, inherit_tty=True)
    script = 'export BC250_EXPECTED_TTY="$(tty)"; exec bash -c ' + shlex.quote(wrapped)
    console = Console("harmless tty check")
    assert console.run(["bash", "-c", script]) == 7
    assert "same tty: True" in log.read_text()
    assert status.read_text().strip() == "7"
    assert "Diagnostic code:" in log.read_text()
