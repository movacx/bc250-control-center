"""Operating policy for the upstream two-OPP Oberon governor.

Oberon has two YAML endpoints, not Cyan's D-Bus safe-point curve.  Its
upstream sample config declares both endpoints at 1000 mV.  Control Center
must never derive Oberon voltages from Cyan's unrelated multipoint TOML.
"""

from __future__ import annotations

from bc250cc.shared.contract import (
    OBERON_ACCEPTED_PROFILES,
    OBERON_BENCHMARK_PROFILE,
    OBERON_CONSERVATIVE_PROFILES,
    OBERON_DESKTOP_PROFILES,
    OBERON_LEGACY_BENCHMARK_PROFILE,
    OBERON_REFERENCE_VOLTAGE_MV,
)

# Benchmark is (1000, 2000), not a fixed 2000 MHz lock.
#
# The two sides disagreed: the desktop declared (2000, 2000) while the Quick
# Access helper wrote (1000, 2000) into /etc/oberon-config.yaml, so tapping
# Benchmark in Game Mode produced a configuration the desktop's own validator
# rejected and the GPU page then demanded Oberon recovery. The written shape
# is the one that wins; it also lets the GPU clock down at idle.
#
# ``OBERON_SAFE_PROFILES`` stays the acceptance set and still contains the old
# fixed-2000 shape, so a desktop that already applied it is not suddenly told
# its configuration is invalid. It is not offered any more — see
# ``OBERON_DESKTOP_PROFILES`` for what the interface presents.
OBERON_SAFE_PROFILES = OBERON_ACCEPTED_PROFILES

__all__ = [
    "OBERON_ACCEPTED_PROFILES",
    "OBERON_BENCHMARK_PROFILE",
    "OBERON_CONSERVATIVE_PROFILES",
    "OBERON_DESKTOP_PROFILES",
    "OBERON_LEGACY_BENCHMARK_PROFILE",
    "OBERON_REFERENCE_VOLTAGE_MV",
    "OBERON_SAFE_PROFILES",
]

OBERON_IDLE_MAX_BUSY_PERCENT = 5
# The benchmark profile holds the idle clock at 2000 MHz. A zero-load
# transition from that profile to 1500/1850 MHz is safe to validate; the busy
# percentage remains the authoritative guard against restarting under load.
OBERON_IDLE_MAX_CLOCK_MHZ = 2000


def require_oberon_safe_profile(minimum: int, maximum: int) -> tuple[int, int]:
    """Return a supported Desktop profile before any root write."""
    requested = int(minimum), int(maximum)
    if requested not in OBERON_SAFE_PROFILES:
        choices = ", ".join(f"{low}-{high} MHz" for low, high in OBERON_SAFE_PROFILES)
        raise ValueError(
            f"Unsupported Oberon profile {requested[0]}-{requested[1]} MHz. "
            f"Use one of: {choices}."
        )
    return requested


def oberon_reference_endpoints(minimum: int, maximum: int) -> tuple[int, int]:
    """Return the upstream baseline voltage for one supported profile."""
    require_oberon_safe_profile(minimum, maximum)
    return OBERON_REFERENCE_VOLTAGE_MV, OBERON_REFERENCE_VOLTAGE_MV
