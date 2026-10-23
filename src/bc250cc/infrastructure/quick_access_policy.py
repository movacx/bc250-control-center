"""Finite operation policy shared by the SteamOS Quick Access integration.

Quick Access is primarily a *live-controls* surface.  Its only persistent CU
operations mirror the full application's already validated table/service
workflow: save one complete four-mask table, install its fixed boot service,
or remove that service without changing the live topology. CPU controls are
also finite: they reuse the root-owned profile's thermal limit and accept only
the audited upstream frequency/scale domain plus its 1325 mV estimated-VID
ceiling. It still cannot edit bootloaders, voltage curves or command lines.
Keeping every request as a named operation means a compromised or outdated
frontend cannot turn a UI parameter into an arbitrary root command.
"""
from __future__ import annotations

from bc250cc.domain.gpu.profiles import GpuProfile as QuickAccessGpuProfile
from bc250cc.domain.gpu.profiles import default_cyan_profiles

GPU_PROFILES: tuple[QuickAccessGpuProfile, ...] = default_cyan_profiles()

GPU_PROFILE_BY_KEY = {profile.key: profile for profile in GPU_PROFILES}

# The QAM exposes a closed, even-valued set of live dispatch targets.  The
# privileged helper derives the required WGP pairs from a freshly verified
# factory topology; callers still cannot provide arbitrary backend arguments.
CU_MODES = tuple(range(24, 41, 2))

# Kept for compatibility with callers that present the one-tap saved-profile
# action. Parameterized QAM CPU requests are independently constrained in the
# Decky backend and both privileged helpers; this token is not a command line.
CPU_SAVED_PROFILE_ACTION = "apply-saved-profile"
CPU_QAM_FREQUENCIES = tuple(range(3100, 4201, 50))
CPU_QAM_SCALES = tuple(range(-50, 1))
CPU_QAM_MAX_ESTIMATED_VID_MV = 1325

# PWM wiring is not standardized across every community BC-250 conversion.
# Earlier observations labelled PWM2 as a pump, but the user has explicitly
# identified it as the board-default control they need in QAM.  Expose only
# the four observed channels and keep PWM2's wiring uncertainty visible in the
# presentation instead of silently blocking it.  A manual 0% is intentionally
# unavailable: Automatic is the safe way to hand the channel back to NCT.
QAM_FAN_CHANNELS = (2, 3, 4, 5)
QAM_FAN_MIN_PERCENT = 20
QAM_FAN_MAX_PERCENT = 100

# Retained for compatibility with the original grouped QAM control.  New UI
# writes should use one selected channel and a bounded percentage instead.
FAN_SYSTEM_PRESETS = {
    "quiet": ("Quiet · 40%", 102),
    "balanced": ("Balanced · 60%", 153),
    "boost": ("Boost · 80%", 204),
    "automatic": ("Automatic", None),
}


def gpu_profile(key: str) -> QuickAccessGpuProfile:
    """Return a named safe profile or reject any caller-provided range."""
    try:
        return GPU_PROFILE_BY_KEY[str(key)]
    except KeyError as exc:
        raise ValueError("Unknown Quick Access GPU profile.") from exc


def cu_mode(key: str | int) -> int:
    """Return one finite live CU target, never a backend command line."""
    try:
        target = int(key)
    except (TypeError, ValueError) as exc:
        raise ValueError("Unknown Quick Access CU mode.") from exc
    if target not in CU_MODES:
        raise ValueError("Unknown Quick Access CU mode.")
    return target


def fan_system_preset(key: str) -> tuple[str, int | None]:
    """Return a named system-fan action; never a caller-provided duty value."""
    try:
        return FAN_SYSTEM_PRESETS[str(key)]
    except KeyError as exc:
        raise ValueError("Unknown Quick Access fan preset.") from exc
