"""Pure normalization and summary state for the GPU voltage laboratory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from bc250cc.domain.gpu.voltage_profiles import (
    GOVERNOR_DEFAULT_VOLTAGES,
    OBERON_SAFE_VOLTAGE_MIN_MV,
    SUPPORTED_VOLTAGE_LEVELS,
    voltage_profile,
)


def _integer(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


@dataclass(frozen=True)
class VoltageLabState:
    is_oberon: bool
    points: tuple[tuple[int, int], ...]
    current_voltages: tuple[tuple[int, int], ...]
    editable_frequencies: tuple[int, ...]
    profile_frequencies: tuple[int, ...]
    detected_level: int
    custom_defaults: tuple[tuple[int, int], ...]
    active_min: int
    active_max: int
    maximum_voltage: int
    curve_error_count: int
    safety_valid: bool


def voltage_for_level(frequency: int, level: int, *, is_oberon: bool) -> int | None:
    try:
        value = voltage_profile(int(level)).get(int(frequency))
    except (TypeError, ValueError, RuntimeError):
        return None
    if value is None:
        return None
    return max(OBERON_SAFE_VOLTAGE_MIN_MV, int(value)) if is_oberon else int(value)


def _normalize_points(state: Mapping[str, object]) -> tuple[tuple[int, int], ...]:
    source = state.get("safe_points_with_voltage") or state.get("safe_points") or ()
    cleaned: dict[int, int] = {}
    for point in source if isinstance(source, (list, tuple)) else ():
        if not isinstance(point, Mapping):
            continue
        frequency = _integer(point.get("frequency"))
        if frequency > 0:
            cleaned[frequency] = _integer(point.get("voltage"))
    return tuple(sorted(cleaned.items()))


def _detected_level(
    current: Mapping[int, int], *, is_oberon: bool,
    levels: Sequence[int], lab_frequencies: Sequence[int],
) -> int:
    best_level = 0
    best_error: int | None = None
    for level in levels:
        pairs = (
            (current.get(int(frequency)), voltage_for_level(frequency, level, is_oberon=is_oberon))
            for frequency in lab_frequencies
        )
        comparable = tuple((actual, expected) for actual, expected in pairs if actual is not None and expected is not None)
        if not comparable:
            continue
        error = sum(abs(int(actual) - int(expected)) for actual, expected in comparable)
        if best_error is None or error < best_error:
            best_level, best_error = int(level), error
    return best_level


def build_voltage_lab_state(
    state: Mapping[str, object], *, active_min_default: int = 500,
    active_max_default: int = 1500,
    levels: Sequence[int] = SUPPORTED_VOLTAGE_LEVELS,
    lab_frequencies: Sequence[int] = tuple(GOVERNOR_DEFAULT_VOLTAGES),
) -> VoltageLabState:
    is_oberon = str(state.get("governor_backend") or "") == "oberon-governor"
    points = _normalize_points(state)
    current = {frequency: voltage for frequency, voltage in points if voltage > 0}
    editable = tuple(frequency for frequency, _voltage in points)
    profile = editable if is_oberon else tuple(int(value) for value in lab_frequencies)
    detected = _detected_level(
        current, is_oberon=is_oberon, levels=levels, lab_frequencies=lab_frequencies
    )
    defaults = tuple(
        (
            frequency,
            int(current.get(frequency) or voltage_for_level(
                frequency, detected, is_oberon=is_oberon
            ) or 900),
        )
        for frequency in editable
    )
    errors = tuple(state.get("safe_points_voltage_errors") or ())
    return VoltageLabState(
        is_oberon=is_oberon,
        points=points,
        current_voltages=tuple(sorted(current.items())),
        editable_frequencies=editable,
        profile_frequencies=profile,
        detected_level=detected,
        custom_defaults=defaults,
        active_min=_integer(state.get("current_min"), active_min_default),
        active_max=_integer(state.get("current_max"), active_max_default),
        maximum_voltage=max(current.values(), default=0),
        curve_error_count=len(errors),
        safety_valid=bool(points) and not errors,
    )
