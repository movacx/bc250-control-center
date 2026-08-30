"""Pure preflight planning for GPU voltage-curve actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from bc250cc.application.gpu.voltage_lab_state import voltage_for_level
from bc250cc.domain.gpu.voltage_profiles import SUPPORTED_VOLTAGE_LEVELS


@dataclass(frozen=True)
class VoltageCurveViolation:
    frequency: int
    voltage: int
    previous_frequency: int
    previous_voltage: int


@dataclass(frozen=True)
class VoltageApplyPlan:
    available: bool
    level: int
    custom_mode: bool
    active_frequencies: tuple[int, ...]
    custom_values: tuple[tuple[int, int], ...]
    proposed_values: tuple[tuple[int, int], ...]
    maximum_voltage: int
    violation: VoltageCurveViolation | None = None


def _positive_map(values: Mapping[int, int]) -> dict[int, int]:
    return {
        int(frequency): int(voltage)
        for frequency, voltage in values.items()
        if int(frequency) > 0 and int(voltage) > 0
    }


def _first_monotonic_violation(
    values: Mapping[int, int],
) -> VoltageCurveViolation | None:
    previous: tuple[int, int] | None = None
    for frequency, voltage in sorted(_positive_map(values).items()):
        if previous is not None and voltage < previous[1]:
            return VoltageCurveViolation(frequency, voltage, previous[0], previous[1])
        previous = frequency, voltage
    return None


def plan_voltage_apply(
    *, level: int,
    editable_frequencies: Sequence[int],
    profile_frequencies: Sequence[int],
    current_voltages: Mapping[int, int],
    custom_values: Mapping[int, int] | None = None,
    is_oberon: bool = False,
) -> VoltageApplyPlan:
    """Build the exact proposal validated before a confirmation is displayed."""
    level = int(level)
    custom_mode = level == -1
    if not custom_mode and level not in SUPPORTED_VOLTAGE_LEVELS:
        raise ValueError(f"Unsupported GPU voltage level: {level}")
    active = tuple(sorted({
        int(value) for value in (
            editable_frequencies if custom_mode else profile_frequencies
        ) if int(value) > 0
    }))
    if not active:
        return VoltageApplyPlan(False, level, custom_mode, (), (), (), 0)

    if custom_mode:
        selected = {
            frequency: int((custom_values or {}).get(frequency, 0))
            for frequency in active
            if frequency in (custom_values or {})
        }
        custom = tuple(sorted(selected.items()))
        proposed = dict(selected)
        maximum = max(selected.values(), default=0)
    else:
        custom = ()
        proposed = {
            frequency: int(
                voltage_for_level(frequency, level, is_oberon=is_oberon)
                or current_voltages.get(frequency)
                or 0
            )
            for frequency in active
        }
        maximum = max(
            (
                voltage_for_level(frequency, level, is_oberon=is_oberon) or 0
                for frequency in active
            ),
            default=0,
        )

    merged = _positive_map(current_voltages)
    merged.update(_positive_map(proposed))
    violation = _first_monotonic_violation(merged)
    return VoltageApplyPlan(
        True,
        level,
        custom_mode,
        active,
        custom,
        tuple(sorted(proposed.items())),
        maximum,
        violation,
    )
