"""One set of numbers for three processes that cannot import each other.

The desktop, the privileged helpers and the Decky backend are separate
processes with separate import environments. The helpers run under
``python3 -I``, which removes their own directory from ``sys.path`` and ignores
``PYTHONPATH``, so they cannot ``import bc250cc`` at all. The Decky backend
runs inside Decky Loader with only the handful of files its installer stages.

The answer had been to write the same rule down in each place, and four of
those copies had already drifted:

* ``cu_repository`` expected runtime protocol 9 while the helper published 13,
  so every Compute Units change made in Game Mode was discarded in silence and
  the desktop quietly showed a stale cache instead.
* The Decky backend capped CPU frequency at 3500 MHz where canon, the desktop
  and the root helper all say 3100, and the panel rounded a saved 3200 MHz
  profile *up* to 3500 before re-applying it.
* A vendored copy of the GPU profile table grew an ``oberon-2000`` entry that
  canon did not have, in a shape the desktop's Oberon validator rejected.
* A TypeScript reimplementation of the error catalogue disagreed with it on
  eight of thirty-two markers.

So the values live here once. This module is importable normally, which
matters: ``test_cpu_frequency_bound_is_single_sourced`` asserts *identity*
(``is``) between the re-exports and these tuples, and a path-based loader on
the desktop side would break that while adding four layout permutations of
"works on my machine".

The two root processes read a generated copy of this file instead
(``privileged/lib/bc250_contract.py``, produced by
``scripts/development/generate_contract.py``). Keep this module importing
nothing outside the standard library and declaring nothing but data and pure
functions — the generated copy is ``exec``'d as root.
"""

from __future__ import annotations

# ---------------------------------------------------------------- versioning

# The shape of *this file*. A consumer stamps the revision it was built against
# and refuses to run against a different one, so a half-finished upgrade fails
# with a sentence instead of behaving strangely.
CONTRACT_REVISION = 1

# Wire protocols, deliberately separate numbers. Merging them would force a
# SteamOS helper bump every time a fan preset changed.
#
# Protocol 14 adds the read-only "gddr6-sensors" action: it never applies the
# SMU patch (that stays desktop-only, pkexec-gated), it only detects whether
# an already-applied patch lets it read the eight per-chip temperatures.
#
# Protocol 15 adds "gpu-high-points": comment/uncomment the Cyan TOML
# safe-points above 2000 MHz through the existing governor-config helper.
# A pure persistent-file edit; it never restarts Cyan or touches the live
# D-Bus range.
#
# Protocol 16 adds "vram-apply": write the UMA_SIZE (VRAM) preset directly
# into the battery-backed CMOS bank, the same mechanism the desktop's own
# VRAM control uses. Like that control, the new size only takes effect after
# the next reboot; it never touches a live allocation.
#
# Protocol 19 adds the Desktop's fan profiles as the quiet/balanced/boost
# presets ("fan_profiles" in the status), "fan-resume" and the
# system_fan_* ownership fields that per-game profiles restore from.
QUICK_ACCESS_PROTOCOL = 19
CPU_SMU_HELPER_PROTOCOL = 8
GOVERNOR_CONFIG_PROTOCOL = 6
STEAMOS_GAME_HELPER_PROTOCOL = 21

# Shape of the /run snapshot the Quick Access helper publishes for the desktop.
QUICK_ACCESS_CU_RUNTIME_SCHEMA = 1

# ---------------------------------------------------------------------- CPU

CPU_FREQUENCY_RANGE = (3100, 4200)
CPU_FREQUENCY_STEP_MHZ = 50
CPU_SCALE_RANGE = (-50, 0)
CPU_TEMPERATURE_RANGE = (70, 90)
CPU_VID_LIMIT_MV = 1325
CPU_VID_RANGE = (950, 1325)
CPU_VID_STEP_MV = 5

# Coefficients of the upstream VID estimate. Kept as data so the panel can do
# the same arithmetic without a second copy of the numbers.
CPU_VID_MODEL = {
    "square": 0.0003,
    "p_base": -1.519,
    "p_scale": 0.004325,
    "q_base": 2800.0,
    "q_scale": -10.0,
    "floor_mhz": 3000,
}


def cpu_frequency_ladder() -> tuple[int, ...]:
    """Every frequency the interfaces may offer, derived rather than retyped."""
    low, high = CPU_FREQUENCY_RANGE
    return tuple(range(low, high + 1, CPU_FREQUENCY_STEP_MHZ))


def cpu_vid_ladder() -> tuple[int, ...]:
    low, high = CPU_VID_RANGE
    return tuple(range(low, high + 1, CPU_VID_STEP_MV))


def estimated_vid(frequency: int, scale: int) -> int | None:
    """The upstream VID estimate for a frequency and scale.

    Returns ``None`` below ``floor_mhz``: the fit is not meaningful there, and
    a reimplementation that dropped this guard reported a confident number for
    frequencies the detector would never choose.
    """
    if type(frequency) is not int or type(scale) is not int:
        raise TypeError("frequency and scale must be integers")
    if frequency < CPU_VID_MODEL["floor_mhz"]:
        return None
    p = CPU_VID_MODEL["p_base"] + scale * CPU_VID_MODEL["p_scale"]
    q = CPU_VID_MODEL["q_base"] + scale * CPU_VID_MODEL["q_scale"]
    return round((CPU_VID_MODEL["square"] * frequency * frequency) + (p * frequency) + q)


# --------------------------------------------------------------- Compute Units

CU_TARGET_RANGE = (24, 40)
CU_TARGET_STEP = 2


def cu_targets() -> tuple[int, ...]:
    low, high = CU_TARGET_RANGE
    return tuple(range(low, high + 1, CU_TARGET_STEP))


# ------------------------------------------------------------------------ GPU

OBERON_REFERENCE_VOLTAGE_MV = 1000

# Oberon exposes two YAML operating points, not Cyan's multipoint curve.
#
# Benchmark used to be written two ways: the desktop said (2000, 2000) and the
# Decky helper wrote (1000, 2000) into /etc/oberon-config.yaml, which the
# desktop's own validator then rejected — tapping Benchmark in Game Mode left
# the GPU page asking for Oberon recovery. (1000, 2000) is the one that ships,
# so it is the one that stays; it also lets the GPU clock down at idle, which
# a fixed 2000 MHz floor did not.
OBERON_CONSERVATIVE_PROFILES: tuple[tuple[int, int], ...] = (
    (1000, 1500),
    (1000, 1850),
)
OBERON_BENCHMARK_PROFILE = (1000, 2000)

# Read tolerance, not an offered profile. A desktop that already applied the
# old fixed-2000 shape must not be told its configuration is invalid.
OBERON_LEGACY_BENCHMARK_PROFILE = (2000, 2000)

OBERON_DESKTOP_PROFILES: tuple[tuple[int, int], ...] = (
    *OBERON_CONSERVATIVE_PROFILES,
    OBERON_BENCHMARK_PROFILE,
)
OBERON_ACCEPTED_PROFILES: tuple[tuple[int, int], ...] = (
    *OBERON_DESKTOP_PROFILES,
    OBERON_LEGACY_BENCHMARK_PROFILE,
)

# ---------------------------------------------------------------------- fans

# Two different preset sets, deliberately kept apart and named for what they
# are. The desktop speaks percentages and drives any channel; Quick Access
# speaks raw PWM on the system channels and refuses to stop a fan.
DESKTOP_FAN_PRESET_PERCENT = {
    "quiet": 45,
    "balanced": 60,
    "cooling": 70,
    "maximum": 100,
}
DESKTOP_FAN_CHANNEL_RANGE = (1, 12)

QUICK_ACCESS_FAN_PRESET_DUTY = {
    "quiet": 102,
    "balanced": 153,
    "boost": 204,
    "automatic": None,
}
QUICK_ACCESS_FAN_CHANNELS = (2, 3, 4, 5)
QUICK_ACCESS_FAN_PERCENT_RANGE = (20, 100)
QUICK_ACCESS_FAN_PERCENT_STEP = 5

# ----------------------------------------------------------- VRAM (UMA_SIZE)

# Fixed CMOS presets, aligned to the 16 MiB granularity the firmware itself
# enforces (github.com/fanoush/bc250_memcfg). Below 1 GiB the desktop's label
# stays in MiB; every other preset here is an exact GiB multiple. Kept as one
# ladder so the desktop dropdown and the Quick Access dropdown can never
# offer different sizes for the same preset.
VRAM_SIZE_PRESETS_MB: tuple[int, ...] = (
    256, 512, 1024, 2048, 3072, 4096, 5120, 6144, 7168, 8192, 12288,
)
