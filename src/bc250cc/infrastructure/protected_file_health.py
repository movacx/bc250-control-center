"""Pure ownership/mode evaluation for privileged helpers and payloads."""

from __future__ import annotations

import stat
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


def evaluate_protected_file(
    evidence: ProtectedFileEvidence,
    *,
    executable: bool,
) -> ProtectedFileDecision:
    mode = evidence.mode
    mode_text = oct(mode & 0o777) if mode is not None else None
    if not evidence.exists or mode is None:
        return ProtectedFileDecision(False, "missing", evidence.uid, mode_text)
    if evidence.is_symlink:
        return ProtectedFileDecision(False, "symlink", evidence.uid, mode_text)
    if not stat.S_ISREG(mode):
        return ProtectedFileDecision(False, "not-regular", evidence.uid, mode_text)
    if evidence.uid != 0:
        return ProtectedFileDecision(False, "not-root-owned", evidence.uid, mode_text)
    if mode & 0o022:
        return ProtectedFileDecision(False, "group-or-world-writable", evidence.uid, mode_text)
    if executable and not mode & 0o111:
        return ProtectedFileDecision(False, "not-executable", evidence.uid, mode_text)
    if not executable and mode & 0o111:
        return ProtectedFileDecision(False, "payload-executable", evidence.uid, mode_text)
    return ProtectedFileDecision(True, "protected", evidence.uid, mode_text)
