"""The terminal interface's own password prompts: no desktop agent is started for it."""

from pathlib import Path

from bc250cc.infrastructure.polkit_session import (
    TERMINAL_AUTH_ENV,
    ensure_graphical_polkit_agent,
)


def test_terminal_auth_never_starts_or_relies_on_a_graphical_agent(tmp_path):
    started = []
    state = ensure_graphical_polkit_agent(
        environment={TERMINAL_AUTH_ENV: "1", "WAYLAND_DISPLAY": "wayland-0"}, proc_root=Path(tmp_path),
        spawn=lambda *a, **k: started.append(a), run=lambda *a, **k: started.append(a))
    assert not state.ready and state.source == "terminal" and not started


def test_web_sudo_route_is_explicit_and_desktop_keeps_polkit(monkeypatch):
    from bc250cc.infrastructure import polkit_session as auth
    monkeypatch.delenv(auth.WEB_SUDO_AUTH_ENV, raising=False)
    assert auth.pkexec_prefix("pkexec", prepare_agent=False) == ["pkexec", "--disable-internal-agent"]
    monkeypatch.setenv(auth.WEB_SUDO_AUTH_ENV, "1")
    monkeypatch.setattr(auth.shutil, "which", lambda name: "/usr/bin/sudo" if name == "sudo" else None)
    assert auth.pkexec_argv("pkexec", "/usr/libexec/protected-helper", "status", prepare_agent=False) == [
        "/usr/bin/sudo", "-p", "BC250 Linux password: ", "--", "/usr/libexec/protected-helper", "status"]
    monkeypatch.setattr(auth, "ensure_graphical_polkit_agent", lambda: (_ for _ in ()).throw(AssertionError("GUI agent started")))
    assert auth.pkexec_prefix("pkexec")[0] == "/usr/bin/sudo"
