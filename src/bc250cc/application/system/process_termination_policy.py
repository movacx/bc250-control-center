"""Pure authorization policy for destructive process termination."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    create_time: float
    uid: int
    name: str
    command: str


@dataclass(frozen=True)
class TerminationDecision:
    allowed: bool
    reason: str


def authorize_process_termination(
    identity: ProcessIdentity,
    *,
    expected_create_time: object,
    owner_uid: int,
    controller_pid: int,
    critical: bool,
) -> TerminationDecision:
    """Authorize a signal only for the same, owned, noncritical process."""

    if identity.pid == int(controller_pid):
        return TerminationDecision(False, "controller-process")
    if identity.uid != int(owner_uid):
        return TerminationDecision(False, "different-owner")
    if critical:
        return TerminationDecision(False, "critical-process")
    if expected_create_time is not None:
        try:
            if float(expected_create_time) != identity.create_time:
                return TerminationDecision(False, "pid-reused")
        except (TypeError, ValueError, OverflowError):
            return TerminationDecision(False, "invalid-identity")
    return TerminationDecision(True, "authorized")
