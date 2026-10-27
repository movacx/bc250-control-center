"""Stable, frontend-neutral errors shared by application boundaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    code: str
    message: str
    retryable: bool = False
    safe_next_step: str | None = None


class BoundaryError(RuntimeError):
    """Base exception for errors crossing an application boundary."""

    def __init__(self, detail: ErrorDetail):
        super().__init__(detail.message)
        self.detail = detail


class ActionNeeded(RuntimeError):
    """A request refused before anything changed, until the user does one thing.

    Steam must be closed, HelixSR removed from the games first, dependencies
    prepared: nothing is broken, so the interface shows what to do instead of
    an error window that asks for a problem report.
    """
