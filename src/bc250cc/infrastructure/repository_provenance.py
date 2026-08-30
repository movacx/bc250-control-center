"""Pure provenance classification for local external-tool sources."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ProvenanceState(StrEnum):
    ORIGIN_INVALID = "origin-invalid"
    CONNECTIVITY_INVALID = "connectivity-invalid"
    REVISION_INVALID = "revision-invalid"
    STATUS_UNREADABLE = "status-unreadable"
    DIRTY = "dirty"
    VERIFIED = "verified"
    ARCHIVE_ORIGIN_INVALID = "archive-origin-invalid"
    ARCHIVE_REVISION_INVALID = "archive-revision-invalid"
    ARCHIVE_VERIFIED = "archive-verified"


@dataclass(frozen=True)
class GitProvenanceEvidence:
    origin_ok: bool
    connectivity_ok: bool
    revision_required: bool
    revision_ok: bool
    status_readable: bool
    dirty: bool


def read_bounded_text(path: Path, maximum: int = 4096) -> str:
    """Read a small regular file without following a final symlink."""
    if maximum < 1:
        raise ValueError("maximum must be positive")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(Path(path), flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("provenance marker is not a regular file")
        if metadata.st_size > maximum:
            raise ValueError("provenance marker exceeds the size limit")
        payload = os.read(descriptor, maximum + 1)
        if len(payload) > maximum:
            raise ValueError("provenance marker exceeds the size limit")
        return payload.decode("utf-8", errors="strict")
    finally:
        os.close(descriptor)


def classify_git_provenance(evidence: GitProvenanceEvidence) -> ProvenanceState:
    if not evidence.origin_ok:
        return ProvenanceState.ORIGIN_INVALID
    if not evidence.connectivity_ok:
        return ProvenanceState.CONNECTIVITY_INVALID
    if evidence.revision_required and not evidence.revision_ok:
        return ProvenanceState.REVISION_INVALID
    if not evidence.status_readable:
        return ProvenanceState.STATUS_UNREADABLE
    if evidence.dirty:
        return ProvenanceState.DIRTY
    return ProvenanceState.VERIFIED


def classify_archive_provenance(
    *, origin_ok: bool, revision_required: bool, revision_ok: bool
) -> ProvenanceState:
    if not origin_ok:
        return ProvenanceState.ARCHIVE_ORIGIN_INVALID
    if revision_required and not revision_ok:
        return ProvenanceState.ARCHIVE_REVISION_INVALID
    return ProvenanceState.ARCHIVE_VERIFIED
