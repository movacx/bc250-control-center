"""Fail-closed command and call-count policy for fast passive telemetry."""

from __future__ import annotations

import contextvars
import subprocess
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

_ALLOWED_PROBES = frozenset({"sensors"})
_ALLOWED_GOVERNOR_SERVICES = frozenset(
    {"cyan-skillfish-governor-smu.service", "oberon-governor.service"}
)
_ALLOWED_OPENRC_GOVERNOR_SERVICES = frozenset(
    {"cyan-skillfish-governor-smu", "oberon-governor"}
)
_MUTATING_OR_REMOTE = frozenset(
    {
        "apt", "dnf", "git", "pacman", "pkexec", "rpm-ostree", "sudo",
        "systemctl", "rc-service", "rc-update", "openrc-run",
    }
)
_budget: contextvars.ContextVar[tuple[int, int] | None] = contextvars.ContextVar(
    "bc250_passive_probe_budget", default=None
)
_daemon_budget: contextvars.ContextVar[tuple[int, int] | None] = contextvars.ContextVar(
    "bc250_daemon_probe_budget", default=None
)


@contextmanager
def passive_probe_budget(max_calls: int) -> Iterator[None]:
    """Bound subprocess probes for one refresh, including nested UI helpers."""
    limit = max(0, int(max_calls))
    token = _budget.set((limit, 0))
    try:
        yield
    finally:
        _budget.reset(token)


def run_passive_probe(
    command: Sequence[str], *, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Run one allowlisted read-only probe within the active refresh budget."""
    argv = tuple(str(item) for item in command)
    if not argv or not argv[0] or any("\x00" in item for item in argv):
        raise ValueError("A passive telemetry probe requires a valid argv sequence.")
    executable = Path(argv[0]).name
    if executable in _MUTATING_OR_REMOTE or executable not in _ALLOWED_PROBES:
        raise PermissionError(f"Command is not approved for passive telemetry: {executable}")
    current = _budget.get()
    if current is None:
        raise RuntimeError("Passive telemetry subprocess attempted outside a refresh budget.")
    limit, used = current
    if used >= limit:
        raise RuntimeError(f"Passive telemetry subprocess budget exceeded ({limit}).")
    _budget.set((limit, used + 1))
    return subprocess.run(
        list(argv),
        text=True,
        capture_output=True,
        check=False,
        timeout=max(0.1, min(float(timeout), 5.0)),
    )


@contextmanager
def daemon_governor_probe_budget(max_calls: int = 3) -> Iterator[None]:
    """Bound the daemon's slower read-only governor health refresh."""
    limit = max(0, min(int(max_calls), 3))
    token = _daemon_budget.set((limit, 0))
    try:
        yield
    finally:
        _daemon_budget.reset(token)


def _approved_daemon_governor_probe(argv: tuple[str, ...]) -> bool:
    executable = Path(argv[0]).name if argv else ""
    if executable == "systemctl":
        return (
            len(argv) == 4
            and argv[1] == "show"
            and argv[2] in _ALLOWED_GOVERNOR_SERVICES
            and argv[3] == "--property=ActiveState,SubState"
        )
    if executable == "rc-service":
        return (
            len(argv) == 3
            and argv[1] in _ALLOWED_OPENRC_GOVERNOR_SERVICES
            and argv[2] == "status"
        )
    if executable == "busctl":
        return (
            len(argv) == 6
            and argv[1:4] == (
                "get-property",
                "com.cyanskillfish.Governor",
                "/com/cyanskillfish/Governor/Range/Current",
            )
            and argv[4] == "com.cyanskillfish.Governor.Range"
            and argv[5] in {"Min", "Max"}
        )
    return False


def run_daemon_governor_probe(
    command: Sequence[str], *, timeout: float = 2
) -> subprocess.CompletedProcess[str]:
    """Run one exact, read-only service/D-Bus query in the slow daemon lane."""
    argv = tuple(str(item) for item in command)
    if not argv or any(not item or "\x00" in item for item in argv):
        raise ValueError("A daemon governor probe requires a valid argv sequence.")
    if not _approved_daemon_governor_probe(argv):
        raise PermissionError("Command is not approved for daemon governor telemetry.")
    current = _daemon_budget.get()
    if current is None:
        raise RuntimeError("Daemon governor probe attempted outside a refresh budget.")
    limit, used = current
    if used >= limit:
        raise RuntimeError(f"Daemon governor probe budget exceeded ({limit}).")
    _daemon_budget.set((limit, used + 1))
    return subprocess.run(
        list(argv),
        text=True,
        capture_output=True,
        check=False,
        timeout=max(0.1, min(float(timeout), 2.0)),
    )
