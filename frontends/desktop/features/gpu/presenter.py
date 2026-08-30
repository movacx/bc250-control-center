"""Desktop translation boundary: domain/application results to view data."""

from __future__ import annotations

from collections.abc import Mapping

from bc250cc.domain.gpu.profiles import GpuProfile, profiles_payload


def gpu_profile_options(allowed: Mapping[str, object], governor: str = "cyan") -> list[dict[str, object]]:
    try:
        minimum_value = allowed.get("min", 0)
        maximum_value = allowed.get("max", 0)
        if type(minimum_value) is not int or type(maximum_value) is not int:
            return []
        minimum = minimum_value
        maximum = maximum_value
    except (TypeError, ValueError, OverflowError):
        return []
    try:
        return profiles_payload(minimum, maximum, governor=governor)
    except ValueError:
        return []


def profile_label(profile: GpuProfile) -> str:
    return profile.label
