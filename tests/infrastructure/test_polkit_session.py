from pathlib import Path

from bc250cc.infrastructure import polkit_session


def _process(proc_root: Path, pid: int, uid: int, command: str) -> None:
    process = proc_root / str(pid)
    process.mkdir(parents=True, exist_ok=True)
    (process / "status").write_text(f"Name:\tagent\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
    (process / "cmdline").write_bytes(command.encode() + b"\0")


def test_existing_current_user_agent_is_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(polkit_session.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(polkit_session.os, "getuid", lambda: 1000)
    _process(tmp_path, 42, 1000, "/usr/lib/polkit-kde-authentication-agent-1")

    state = polkit_session.ensure_graphical_polkit_agent(
        environment={"WAYLAND_DISPLAY": "wayland-1", "XDG_CURRENT_DESKTOP": "Hyprland"},
        proc_root=tmp_path,
        run=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not start")),
    )

    assert state.ready is True
    assert state.source == "existing"


def test_standalone_compositor_starts_an_installed_user_agent(tmp_path, monkeypatch):
    monkeypatch.setattr(polkit_session.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(polkit_session.os, "getuid", lambda: 1000)
    binary = tmp_path / "polkit-kde-authentication-agent-1"
    binary.write_text("agent")
    candidate = polkit_session._AgentCandidate(
        ("hyprland",), "test-polkit-agent.service", (binary,)
    )
    monkeypatch.setattr(polkit_session, "_CANDIDATES", (candidate,))
    calls = []

    class Result:
        returncode = 0

    def run(command, **_kwargs):
        calls.append(command)
        _process(tmp_path, 43, 1000, str(binary))
        return Result()

    state = polkit_session.ensure_graphical_polkit_agent(
        environment={"DISPLAY": ":1", "XDG_CURRENT_DESKTOP": "Hyprland"},
        proc_root=tmp_path,
        run=run,
        spawn=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unit worked")),
        which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None,
        sleep=lambda _seconds: None,
    )

    assert state == polkit_session.PolkitAgentState(
        True, "user-unit:test-polkit-agent.service"
    )
    assert calls == [["/usr/bin/systemctl", "--user", "start", "test-polkit-agent.service"]]


def test_no_tty_pkexec_error_becomes_actionable_and_translatable():
    raw = (
        "Error creating textual authentication agent: Error opening current "
        "controlling terminal for the process (/dev/tty): No such device or address"
    )

    assert polkit_session.normalize_polkit_error(["pkexec", "/helper"], raw) == (
        polkit_session.AUTH_AGENT_MESSAGE
    )
    assert polkit_session.normalize_polkit_error(["systemctl"], raw) == raw


def test_pkexec_argv_disables_the_text_terminal_fallback(monkeypatch):
    monkeypatch.setattr(
        polkit_session,
        "ensure_graphical_polkit_agent",
        lambda: polkit_session.PolkitAgentState(True, "test"),
    )

    assert polkit_session.pkexec_argv("/usr/bin/pkexec", "/protected/helper", "apply") == [
        "/usr/bin/pkexec",
        "--disable-internal-agent",
        "/protected/helper",
        "apply",
    ]


def test_passwordless_game_helper_does_not_start_a_desktop_agent(monkeypatch):
    monkeypatch.setattr(
        polkit_session,
        "ensure_graphical_polkit_agent",
        lambda: (_ for _ in ()).throw(AssertionError("no prompt is required")),
    )

    assert polkit_session.pkexec_argv(
        "pkexec", "/protected/game-helper", "status", prepare_agent=False
    ) == [
        "pkexec",
        "--disable-internal-agent",
        "/protected/game-helper",
        "status",
    ]
