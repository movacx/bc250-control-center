"""Canonical GPU profile policy shared by Desktop and Quick Access.

The Decky plugin cannot import this package — it only receives the files its
installer stages — so it carries a copy at
``integrations/decky/bc250-quick-access/bc250cc/domain/gpu/profiles.py``.
That copy is byte-identical and a test says so; it drifted once, gaining an
Oberon profile this file did not have, and the desktop rejected what Game Mode
then wrote.
"""

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
    """Calculate conservative profiles from the backend's real allowed range."""

    if type(minimum_mhz) is not int or type(maximum_mhz) is not int:
        raise TypeError("GPU allowed range boundaries must be integers")
    minimum = minimum_mhz
    maximum = maximum_mhz
    if minimum > maximum:
        raise ValueError("GPU allowed minimum cannot exceed maximum")
    if governor == "oberon":
        # Benchmark lived only in the Decky-side copy of this file, in a shape
        # the desktop's Oberon validator then rejected. It ships, so it belongs
        # here too.
        #
        # Written out rather than derived from ``contract.OBERON_DESKTOP_PROFILES``
        # because this module is copied verbatim into the Decky plugin, which
        # receives four files and cannot import the contract. A test asserts
        # the two agree, so they cannot drift apart again in silence.
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
        if governor == "oberon":
            # Oberon's profiles are fixed YAML endpoints, not a ladder to clamp
            # to whatever the backend allows. Clamping produced the duplicate
            # the panel showed: "Gaming 1000-1850" and "Benchmark 1000-1850",
            # both marked current, the second applying 1000-2000. A profile
            # that does not fit is not offered.
            if profile_min < minimum or profile_max > maximum:
                continue
            profiles.append(GpuProfile(key, label, profile_min, profile_max))
            continue
        bounded_min = max(minimum, profile_min)
        bounded_max = min(maximum, profile_max)
        if bounded_min <= bounded_max:
            profiles.append(GpuProfile(key, label, bounded_min, bounded_max))
    return tuple(profiles)


def profiles_payload(minimum_mhz: int, maximum_mhz: int, *, governor: str = "cyan"):
    return [profile.payload() for profile in profiles_for_allowed_range(minimum_mhz, maximum_mhz, governor=governor)]


def default_cyan_profiles() -> tuple[GpuProfile, ...]:
    return profiles_for_allowed_range(500, 2400)
