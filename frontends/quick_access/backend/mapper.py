"""Map application results to the stable Quick Access protocol."""

from __future__ import annotations

from collections.abc import Mapping


def map_gpu_status(status: Mapping[str, object]) -> dict[str, object]:
    """Expose backend-owned values; never recalculate profile ranges in QAM."""
    result = dict(status)
    profiles = result.get("gpu_profiles")
    result["gpu_profiles"] = list(profiles) if isinstance(profiles, list) else []
    return result
