"""Presentation switches for features that remain available in the backend."""

from __future__ import annotations

from collections.abc import Mapping

# Keep the reviewed implementation available while its public workflow is
# validated on more BC-250 configurations.
FSR4_UI_ENABLED = True

# Preserve the table and contract widgets for a later diagnostics redesign.
# Their live data still feeds the console and diagnostic copy actions.
GPU_REFERENCE_PANELS_ENABLED = False


def mastag_stack_replaces_gfx1013_card(tools: Mapping[str, object]) -> bool:
    """Return whether the matched MastaG stack is the active Arch-family path."""
    stack = tools.get("masta_bc250_stack")
    if isinstance(stack, Mapping) and "supported" in stack:
        return bool(stack.get("supported"))
    if "masta_bc250_stack_supported" in tools:
        return bool(tools.get("masta_bc250_stack_supported"))

    os_id = str(tools.get("os_id") or "").strip().lower()
    family = str(tools.get("os_family") or "").strip().lower()
    return os_id in {"arch", "cachyos"} or (
        not os_id and family in {"arch", "cachyos"}
    )
