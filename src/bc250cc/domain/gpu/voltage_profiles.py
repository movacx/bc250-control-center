"""Reviewed GPU voltage-profile rules independent of TOML transport."""

from __future__ import annotations

# Exact curve reviewed for cyan-skillfish-governor-smu v0.4.12
# (smu/default-config.toml).  This is business calibration shared by every
# frontend; parsing and writing the TOML remain infrastructure concerns.
GOVERNOR_DEFAULT_SAFE_POINTS = (
    (500, 700), (1000, 800), (1175, 850), (1500, 900), (1600, 910),
    (1700, 920), (1850, 930), (2000, 960), (2050, 980), (2100, 1000),
    (2125, 1020), (2150, 1035), (2200, 1050), (2230, 1085), (2300, 1110),
    (2350, 1130), (2400, 1150),
)
GOVERNOR_DEFAULT_VOLTAGES = dict(GOVERNOR_DEFAULT_SAFE_POINTS)
# Keep the legacy restore/default and +60 mV profiles available while exposing
# the compact +10..+50 mV laboratory ladder in the desktop drawer.
SUPPORTED_VOLTAGE_LEVELS = (0, 1, 2, 3, 4, 5, 6)
VOLTAGE_BOOST_START_MHZ = 2000
CUSTOM_VOLTAGE_MIN_MV = 600
CUSTOM_VOLTAGE_MAX_MV = 1210
OBERON_FREQUENCY_MIN_MHZ = 500
OBERON_FREQUENCY_MAX_MHZ = 2400
OBERON_SAFE_VOLTAGE_MIN_MV = 920
OBERON_SAFE_VOLTAGE_MAX_MV = 1210


def voltage_profile(level: int) -> dict[int, int]:
    """Return the complete reviewed voltage curve for a supported level."""
    try:
        normalized = int(level)
    except (TypeError, ValueError) as error:
        raise ValueError("Voltage level must be an integer.") from error
    if normalized not in SUPPORTED_VOLTAGE_LEVELS:
        allowed = ", ".join(str(item) for item in SUPPORTED_VOLTAGE_LEVELS)
        raise ValueError(f"Unsupported voltage level {normalized}; use {allowed}.")
    addition = normalized * 10
    return {
        frequency: voltage + (addition if frequency >= VOLTAGE_BOOST_START_MHZ else 0)
        for frequency, voltage in GOVERNOR_DEFAULT_SAFE_POINTS
    }
