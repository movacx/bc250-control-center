"""Canonical GPU profile policy bundled for the root Decky plugin runtime."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GpuProfile:
    key: str
    label: str
    minimum_mhz: int
    maximum_mhz: int

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("GPU profile key cannot be empty")
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("GPU profile label cannot be empty")
        if type(self.minimum_mhz) is not int or type(self.maximum_mhz) is not int:
            raise ValueError("GPU profile limits must be integers")
        if self.minimum_mhz < 0 or self.minimum_mhz > self.maximum_mhz:
            raise ValueError("GPU profile limits are invalid")

    def payload(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.label,
            "min": self.minimum_mhz,
            "max": self.maximum_mhz,
        }


def profiles_for_allowed_range(
    minimum_mhz: int,
    maximum_mhz: int,
    *,
    governor: str = "cyan",
) -> tuple[GpuProfile, ...]:
    """Calculate conservative profiles from the helper's allowed range."""

    if type(minimum_mhz) is not int or type(maximum_mhz) is not int:
        raise TypeError("GPU allowed range boundaries must be integers")
    minimum = minimum_mhz
    maximum = maximum_mhz
    if minimum > maximum:
        raise ValueError("GPU allowed minimum cannot exceed maximum")
    if governor == "oberon":
        candidates = (
            ("oberon-1500", "Balanced", 1000, 1500),
            ("oberon-1850", "Gaming", 1000, 1850),
            ("oberon-2000", "Benchmark", 1000, 2000),
        )
    else:
        candidates = (
            ("balanced", "Balanced", max(500, minimum), 1500),
            ("gaming", "Gaming", max(1000, minimum), 1850),
            ("benchmark", "Benchmark", max(1000, minimum), 2000),
        )
    profiles: list[GpuProfile] = []
    for key, label, profile_min, profile_max in candidates:
        bounded_min = max(minimum, profile_min)
        bounded_max = min(maximum, profile_max)
        if bounded_min <= bounded_max:
            profiles.append(GpuProfile(key, label, bounded_min, bounded_max))
    return tuple(profiles)


def profiles_payload(
    minimum_mhz: int,
    maximum_mhz: int,
    *,
    governor: str = "cyan",
) -> list[dict[str, object]]:
    return [
        profile.payload()
        for profile in profiles_for_allowed_range(
            minimum_mhz, maximum_mhz, governor=governor
        )
    ]
