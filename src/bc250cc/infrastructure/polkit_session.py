"""Graphical Polkit session support for desktop hardware actions.

The desktop application has no controlling terminal.  When a compositor does
not start an authentication agent, pkexec otherwise falls back to /dev/tty and
returns an implementation error instead of showing a password dialog.  This
module starts an already-installed desktop agent and keeps every pkexec call
on the external graphical-agent path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

AUTH_AGENT_MESSAGE = (
    "The live dashboard needs administrator permissions. If the Polkit window "
    "does not appear, check that your desktop has an active authentication agent."
)

_AGENT_MARKERS = (
    "hyprpolkitagent",
    "polkit-kde-authentication-agent",
    "polkit-gnome-authentication-agent",
    "lxqt-policykit-agent",
    "mate-polkit",
    "xfce-polkit",
)


@dataclass(frozen=True)
class PolkitAgentState:
    ready: bool
    source: str
    detail: str = ""


@dataclass(frozen=True)
class _AgentCandidate:
    desktops: tuple[str, ...]
    unit: str
    binaries: tuple[Path, ...]


_CANDIDATES = (
    _AgentCandidate(
        ("hyprland",),
        "hyprpolkitagent.service",
        (
            Path("/usr/lib/hyprpolkitagent/hyprpolkitagent"),
            Path("/usr/libexec/hyprpolkitagent"),
            Path("/usr/bin/hyprpolkitagent"),
        ),
    ),
    _AgentCandidate(
        ("kde", "plasma", "lxqt", "hyprland"),
        "plasma-polkit-agent.service",
        (
            Path("/usr/lib/polkit-kde-authentication-agent-1"),
            Path("/usr/libexec/kf6/polkit-kde-authentication-agent-1"),
            Path("/usr/libexec/polkit-kde-authentication-agent-1"),
        ),
    ),
    _AgentCandidate(
        ("lxqt", "lxde"),
        "lxqt-policykit-agent.service",
        (Path("/usr/bin/lxqt-policykit-agent"),),
    ),
    _AgentCandidate(
        ("gnome", "unity", "budgie", "xfce", "i3", "sway", "hyprland"),
        "polkit-gnome-authentication-agent-1.service",
        (
            Path("/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1"),
            Path("/usr/libexec/polkit-gnome-authentication-agent-1"),
            Path("/usr/lib/policykit-1-gnome/polkit-gnome-authentication-agent-1"),
        ),
    ),
    _AgentCandidate(
        ("mate",),
        "mate-polkit.service",
        (Path("/usr/lib/mate-polkit/polkit-mate-authentication-agent-1"),),
    ),
    _AgentCandidate(
        ("xfce",),
        "xfce-polkit.service",
        (Path("/usr/lib/xfce-polkit/xfce-polkit"),),
    ),
)

_START_LOCK = threading.Lock()
_DEFAULT_READY_STATE: PolkitAgentState | None = None


def _graphical_session(environment: Mapping[str, str]) -> bool:
    return bool(environment.get("WAYLAND_DISPLAY") or environment.get("DISPLAY"))


def _desktop_name(environment: Mapping[str, str]) -> str:
    return " ".join(
        environment.get(name, "")
        for name in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION")
    ).casefold()


def _agent_running(proc_root: Path = Path("/proc"), uid: int | None = None) -> bool:
    owner = os.getuid() if uid is None else int(uid)
    try:
        processes = tuple(proc_root.glob("[0-9]*"))
    except OSError:
        return False
    for process in processes:
        try:
            status = (process / "status").read_text(encoding="utf-8", errors="ignore")
            uid_line = next(line for line in status.splitlines() if line.startswith("Uid:"))
            if int(uid_line.split()[1]) != owner:
                continue
            command = (process / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="ignore"
            ).casefold()
        except (OSError, StopIteration, ValueError, IndexError):
            continue
        if any(marker in command for marker in _AGENT_MARKERS):
            return True
        # GNOME Shell and Cinnamon provide their Polkit agent internally.
        executable = command.split(" ", 1)[0].rsplit("/", 1)[-1]
        if executable in {"gnome-shell", "cinnamon"}:
            return True
    return False


def _ordered_candidates(desktop: str) -> tuple[_AgentCandidate, ...]:
    preferred = tuple(
        candidate
        for candidate in _CANDIDATES
        if any(marker in desktop for marker in candidate.desktops)
    )
    return preferred + tuple(candidate for candidate in _CANDIDATES if candidate not in preferred)


def ensure_graphical_polkit_agent(
    *,
    environment: Mapping[str, str] | None = None,
    proc_root: Path = Path("/proc"),
    run=subprocess.run,
    spawn=subprocess.Popen,
    which=shutil.which,
    sleep=time.sleep,
) -> PolkitAgentState:
    """Start one installed user-session agent when the desktop omitted it.

    No package is installed and no system setting is changed.  Full desktop
    environments normally already have an agent, while standalone Wayland/X11
    compositors can reuse any supported agent that is present on the host.
    """
    global _DEFAULT_READY_STATE
    default_probe = environment is None and proc_root == Path("/proc")
    if default_probe and _DEFAULT_READY_STATE is not None:
        return _DEFAULT_READY_STATE
    env = dict(os.environ if environment is None else environment)
    if os.geteuid() == 0:
        return PolkitAgentState(False, "root", "Root does not need a Polkit agent.")
    if not _graphical_session(env):
        return PolkitAgentState(False, "non-graphical", "No graphical session was detected.")
    if _agent_running(proc_root):
        state = PolkitAgentState(True, "existing")
        if default_probe:
            _DEFAULT_READY_STATE = state
        return state

    with _START_LOCK:
        if _agent_running(proc_root):
            return PolkitAgentState(True, "existing")
        desktop = _desktop_name(env)
        systemctl = which("systemctl")
        for candidate in _ordered_candidates(desktop):
            binary = next((path for path in candidate.binaries if path.is_file()), None)
            if binary is None:
                continue
            if systemctl:
                try:
                    result = run(
                        [systemctl, "--user", "start", candidate.unit],
                        text=True,
                        capture_output=True,
                        timeout=3,
                        check=False,
                    )
                except (OSError, subprocess.SubprocessError):
                    result = None
                if result is not None and result.returncode == 0:
                    for _attempt in range(10):
                        if _agent_running(proc_root):
                            state = PolkitAgentState(True, f"user-unit:{candidate.unit}")
                            if default_probe:
                                _DEFAULT_READY_STATE = state
                            return state
                        sleep(0.05)
                    # A different agent may already own the Polkit session.
                    # systemctl still reports a successful activation before
                    # the redundant process exits, and pkexec can use that
                    # existing registered agent.
                    state = PolkitAgentState(True, f"user-unit:{candidate.unit}")
                    if default_probe:
                        _DEFAULT_READY_STATE = state
                    return state
            try:
                spawn(
                    [str(binary)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    close_fds=True,
                    env=env,
                )
            except OSError:
                continue
            for _attempt in range(10):
                if _agent_running(proc_root):
                    state = PolkitAgentState(True, f"process:{binary}")
                    if default_probe:
                        _DEFAULT_READY_STATE = state
                    return state
                sleep(0.05)
        return PolkitAgentState(False, "missing", AUTH_AGENT_MESSAGE)


def pkexec_prefix(executor: str, *, prepare_agent: bool = True) -> list[str]:
    """Return the graphical-only pkexec prefix used by desktop actions."""
    value = str(executor or "")
    if not value or "\x00" in value:
        raise ValueError("Invalid privileged command")
    if prepare_agent:
        ensure_graphical_polkit_agent()
    return [value, "--disable-internal-agent"]


def pkexec_argv(
    executor: str,
    program: str,
    *arguments: object,
    prepare_agent: bool = True,
) -> list[str]:
    """Build a desktop pkexec request without its unusable tty fallback."""
    values = [str(program or ""), *(str(item) for item in arguments)]
    if not values[0] or any("\x00" in value for value in values):
        raise ValueError("Invalid privileged command")
    return [*pkexec_prefix(executor, prepare_agent=prepare_agent), *values]


def normalize_polkit_error(command: Sequence[object], detail: object) -> str:
    """Replace pkexec's no-tty implementation detail with useful guidance."""
    text = str(detail or "").strip()
    if not command:
        return text
    executable = Path(str(command[0])).name
    if executable != "pkexec":
        return text
    lowered = text.casefold()
    if (
        "textual authentication agent" in lowered
        or "controlling terminal" in lowered
        or "/dev/tty" in lowered
        or "no authentication agent" in lowered
    ):
        return AUTH_AGENT_MESSAGE
    return text
