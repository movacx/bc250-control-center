"""Immutable trust anchors for the privileged upstream core-unlock payloads."""

from __future__ import annotations

from .external_tools.catalog import EXTERNAL_TOOLS

REVIEWED_REVISION = EXTERNAL_TOOLS["core_unlock"].reviewed_revision
REVIEWED_SCRIPT_SHA256 = "b52bdcc14012c9dd222ebc71b4df11c3e976824a129f01f026bcc38c5482ccc5"

# The boot-service tool that makes the same unlock survive cold boots.
PERSISTENT_REVIEWED_REVISION = EXTERNAL_TOOLS["core_unlock_persistent"].reviewed_revision
PERSISTENT_REVIEWED_SCRIPT_SHA256 = "f937350feaff53658b5f21f0709ca594d8f3625cf6f4a57c7e052c8d1fceea5f"
