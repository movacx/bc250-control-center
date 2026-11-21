"""Immutable trust anchors for the privileged upstream core-unlock payloads."""

from __future__ import annotations

from .external_tools.catalog import EXTERNAL_TOOLS

REVIEWED_REVISION = EXTERNAL_TOOLS["core_unlock"].reviewed_revision
REVIEWED_SCRIPT_SHA256 = "b52bdcc14012c9dd222ebc71b4df11c3e976824a129f01f026bcc38c5482ccc5"

# The boot-service tool that makes the same unlock survive cold boots.
PERSISTENT_REVIEWED_REVISION = EXTERNAL_TOOLS["core_unlock_persistent"].reviewed_revision
PERSISTENT_REVIEWED_SCRIPT_SHA256 = "ada6acf9b9db3ab0375d8dff2a185586eadf1bceb467171fe1967c5597689f4b"
