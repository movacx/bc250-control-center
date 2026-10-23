"""Pure provenance classification for local external-tool sources."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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

