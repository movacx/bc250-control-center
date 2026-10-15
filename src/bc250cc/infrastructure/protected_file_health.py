"""Pure ownership/mode evaluation for privileged helpers and payloads."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProtectedFileEvidence:
    exists: bool
    is_symlink: bool
    mode: int | None
    uid: int | None


@dataclass(frozen=True)
class ProtectedFileDecision:
    safe: bool
    reason: str
    uid: int | None
    mode_text: str | None

