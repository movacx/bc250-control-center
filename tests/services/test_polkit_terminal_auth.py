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
