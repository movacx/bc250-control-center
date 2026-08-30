"""Pure normalization and table presentation for GPU safe-points."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SafePointRow:
    frequency: int
    voltage: int
    original_voltage: int | None
    stable: bool
    role: str


@dataclass(frozen=True)
class SafePointPlan:
    points: tuple[tuple[int, int], ...]
    frequencies: tuple[int, ...]
    voltage_map: tuple[tuple[int, int], ...]
    rows: tuple[SafePointRow, ...]


def _integer(value: object) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def normalize_safe_points(points: object) -> tuple[tuple[int, int], ...]:
    cleaned: set[tuple[int, int]] = set()
    if not isinstance(points, (list, tuple)):
        return ()
    for point in points:
        if not isinstance(point, Mapping):
            continue
        frequency = _integer(point.get("frequency"))
        if frequency > 0:
            cleaned.add((frequency, _integer(point.get("voltage"))))
    return tuple(sorted(cleaned, key=lambda item: item[0]))


def _safe_point_role(
    frequency: int, *, current: int, active_maximum: int, stable: bool,
) -> str:
    if frequency == current:
        return "Current SCLK"
    if frequency == active_maximum:
        return "Active ceiling"
    if frequency > 2000:
        return "High OC safe-point" if stable else "High OC / undervolt lab"
    if frequency >= 1850:
        return "OC safe-point" if stable else "Undervolt warning"
    return "Safe-point"


def build_safe_point_plan(
    points: object,
    *,
    current: int,
    active_maximum: int,
    packaged_voltages: Mapping[int, int],
) -> SafePointPlan:
    normalized = normalize_safe_points(points)
    rows = []
    for frequency, voltage in normalized:
        original = packaged_voltages.get(frequency)
        stable = original is None or voltage >= original
        rows.append(SafePointRow(
            frequency=frequency,
            voltage=voltage,
            original_voltage=original,
            stable=stable,
            role=_safe_point_role(
                frequency,
                current=int(current),
                active_maximum=int(active_maximum),
                stable=stable,
            ),
        ))
    return SafePointPlan(
        points=normalized,
        frequencies=tuple(frequency for frequency, _voltage in normalized),
        voltage_map=tuple(
            (frequency, voltage)
            for frequency, voltage in normalized
            if voltage > 0
        ),
        rows=tuple(rows),
    )
