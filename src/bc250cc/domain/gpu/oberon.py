"""Operating policy for the upstream two-OPP Oberon governor.

Oberon has two YAML endpoints, not Cyan's D-Bus safe-point curve.  Its
upstream sample config declares both endpoints at 1000 mV.  Control Center
must never derive Oberon voltages from Cyan's unrelated multipoint TOML.
"""

from __future__ import annotations

OBERON_REFERENCE_VOLTAGE_MV = 1000

# The first two profiles are the conservative choices also exposed in Quick
# Access.  Fixed 2000 MHz is the upstream sample shape and remains a Desktop
# Mode benchmark option behind the existing explicit high-risk confirmation.
OBERON_CONSERVATIVE_PROFILES: tuple[tuple[int, int], ...] = (
    (1000, 1500),
    (1000, 1850),
)
OBERON_BENCHMARK_PROFILE = (2000, 2000)
OBERON_DESKTOP_PROFILES: tuple[tuple[int, int], ...] = (
    *OBERON_CONSERVATIVE_PROFILES,
    OBERON_BENCHMARK_PROFILE,
)

# Compatibility name retained for Desktop callers.
OBERON_SAFE_PROFILES = OBERON_DESKTOP_PROFILES

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
