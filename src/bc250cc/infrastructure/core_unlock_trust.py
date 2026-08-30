"""Immutable trust anchors for the privileged upstream core-unlock payload."""

from __future__ import annotations

import hashlib

from .external_tools.catalog import EXTERNAL_TOOLS

REVIEWED_REVISION = EXTERNAL_TOOLS["core_unlock"].reviewed_revision
REVIEWED_SCRIPT_SHA256 = "b52bdcc14012c9dd222ebc71b4df11c3e976824a129f01f026bcc38c5482ccc5"


def payload_matches_review(
    revision: str, working_bytes: bytes, committed_bytes: bytes
) -> bool:
    """Require both the pinned Git object and independently reviewed payload hash."""
    if revision != REVIEWED_REVISION or working_bytes != committed_bytes:
        return False
    return hashlib.sha256(working_bytes).hexdigest() == REVIEWED_SCRIPT_SHA256
