"""Pure row and copy planning for the GPU voltage-curve table."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from bc250cc.application.gpu.voltage_lab_state import voltage_for_level
from bc250cc.domain.gpu.voltage_profiles import (
    SUPPORTED_VOLTAGE_LEVELS,
    VOLTAGE_BOOST_START_MHZ,
)


@dataclass(frozen=True)
class VoltageTableRow:
    frequency: int
    current: int
    original: int | None
    proposed: int | None
    added: int | None
    custom_available: bool
    editor_value: int


@dataclass(frozen=True)
class VoltageTablePlan:
    rows: tuple[VoltageTableRow, ...]
    selected_level: int
    custom_mode: bool
    active_frequencies: tuple[int, ...]
    detail_template: str
    detail_values: tuple[tuple[str, object], ...] = ()


def _detail(
    *, points: Sequence[tuple[int, int]], custom_mode: bool,
    selected_level: int, editable_count: int, profile_count: int,
    detected_level: int,
) -> tuple[str, tuple[tuple[str, object], ...]]:
    if not points:
        return (
            "No active voltage safe-points were found. Verify the governor TOML and refresh.",
            (),
        )
    if custom_mode:
        return (
            "Custom mode: all {count} active safe-points are unlocked, including low-frequency entries such as 500 MHz when present.",
            (("count", editable_count),),
        )
    if selected_level == 0:
        return (
            "Level 0 restores all {count} packaged original voltages and disables +2000 MHz TOML points. Detected curve: Level {detected}.",
            (("count", profile_count), ("detected", detected_level)),
        )
    return (
        "Level {level}: packaged defaults +{added} mV on every point from {start} MHz; all {count} original points are restored first. Detected curve: Level {detected}.",
        (
            ("level", selected_level),
            ("added", selected_level * 10),
            ("start", VOLTAGE_BOOST_START_MHZ),
            ("count", profile_count),
            ("detected", detected_level),
        ),
    )


def _row(
    frequency: int, current: int, *, custom_mode: bool,
    selected_level: int, editable: set[int], profile: set[int],
    custom_values: Mapping[int, int], packaged_voltages: Mapping[int, int],
    is_oberon: bool,
) -> VoltageTableRow:
    custom_available = frequency in editable
    original = packaged_voltages.get(frequency)
    if custom_mode and custom_available:
        proposed = int(custom_values.get(frequency, current or 900))
    elif frequency in profile:
        proposed = voltage_for_level(
            frequency, selected_level, is_oberon=is_oberon
        )
    else:
        proposed = current or None
    added = (
        None
        if proposed is None or original is None
        else int(proposed) - int(original)
    )
    return VoltageTableRow(
        frequency=frequency,
        current=current,
        original=original,
        proposed=proposed,
        added=added,
        custom_available=custom_available,
        editor_value=int(custom_values.get(frequency, current or proposed or 900)),
    )


def build_voltage_table_plan(
    *, points: Sequence[tuple[int, int]], selected_level: int,
    editable_frequencies: Sequence[int], profile_frequencies: Sequence[int],
    custom_values: Mapping[int, int], packaged_voltages: Mapping[int, int],
    detected_level: int, is_oberon: bool,
) -> VoltageTablePlan:
    selected_level = int(selected_level)
    if selected_level != -1 and selected_level not in SUPPORTED_VOLTAGE_LEVELS:
        raise ValueError(f"Unsupported GPU voltage level: {selected_level}")
    custom_mode = selected_level == -1
    editable = {int(value) for value in editable_frequencies}
    profile = {int(value) for value in profile_frequencies}
    active = editable if custom_mode else profile
    rows = tuple(
        _row(
            int(frequency), int(current or 0),
            custom_mode=custom_mode,
            selected_level=selected_level,
            editable=editable,
            profile=profile,
            custom_values=custom_values,
            packaged_voltages=packaged_voltages,
            is_oberon=is_oberon,
        )
        for frequency, current in points
    )
    template, values = _detail(
        points=points,
        custom_mode=custom_mode,
        selected_level=selected_level,
        editable_count=len(editable),
        profile_count=len(profile),
        detected_level=detected_level,
    )
    return VoltageTablePlan(
        rows=rows,
        selected_level=selected_level,
        custom_mode=custom_mode,
        active_frequencies=tuple(sorted(active)),
        detail_template=template,
        detail_values=values,
    )
