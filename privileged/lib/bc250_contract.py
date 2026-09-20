"""Generated from src/bc250cc/shared/contract.py. Do not edit.

Run scripts/development/generate_contract.py after changing the contract; a
test byte-compares this file against the generator's output.

This module is loaded by absolute path and executed as root by helpers running
under ``python3 -I``. It therefore imports nothing, calls nothing at module
scope, and contains only data and pure functions.
"""

from __future__ import annotations

CONTRACT_REVISION = 1
QUICK_ACCESS_PROTOCOL = 16
CPU_SMU_HELPER_PROTOCOL = 8
GOVERNOR_CONFIG_PROTOCOL = 6
STEAMOS_GAME_HELPER_PROTOCOL = 21
QUICK_ACCESS_CU_RUNTIME_SCHEMA = 1
CPU_FREQUENCY_RANGE = (3100, 4200)
CPU_FREQUENCY_STEP_MHZ = 50
CPU_SCALE_RANGE = (-50, 0)
CPU_TEMPERATURE_RANGE = (70, 90)
CPU_VID_LIMIT_MV = 1325
CPU_VID_RANGE = (950, 1325)
CPU_VID_STEP_MV = 5
CPU_VID_MODEL = {'square': 0.0003, 'p_base': -1.519, 'p_scale': 0.004325, 'q_base': 2800.0, 'q_scale': -10.0, 'floor_mhz': 3000}
CU_TARGET_RANGE = (24, 40)
CU_TARGET_STEP = 2
OBERON_REFERENCE_VOLTAGE_MV = 1000
OBERON_CONSERVATIVE_PROFILES = ((1000, 1500), (1000, 1850))
OBERON_BENCHMARK_PROFILE = (1000, 2000)
OBERON_LEGACY_BENCHMARK_PROFILE = (2000, 2000)
OBERON_DESKTOP_PROFILES = ((1000, 1500), (1000, 1850), (1000, 2000))
OBERON_ACCEPTED_PROFILES = ((1000, 1500), (1000, 1850), (1000, 2000), (2000, 2000))
DESKTOP_FAN_PRESET_PERCENT = {'quiet': 45, 'balanced': 60, 'cooling': 70, 'maximum': 100}
DESKTOP_FAN_CHANNEL_RANGE = (1, 12)
QUICK_ACCESS_FAN_PRESET_DUTY = {'quiet': 102, 'balanced': 153, 'boost': 204, 'automatic': None}
QUICK_ACCESS_FAN_CHANNELS = (2, 3, 4, 5)
QUICK_ACCESS_FAN_PERCENT_RANGE = (20, 100)
QUICK_ACCESS_FAN_PERCENT_STEP = 5
VRAM_SIZE_PRESETS_MB = (256, 512, 1024, 2048, 3072, 4096, 5120, 6144, 7168, 8192, 12288)


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


def cu_targets() -> tuple[int, ...]:
    low, high = CU_TARGET_RANGE
    return tuple(range(low, high + 1, CU_TARGET_STEP))
