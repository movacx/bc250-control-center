"""Pure presentation plan for the GPU voltage-laboratory summary."""

from __future__ import annotations

from dataclasses import dataclass

from bc250cc.application.gpu.voltage_lab_state import VoltageLabState


@dataclass(frozen=True)
class VoltageLabText:
    template: str
    values: tuple[tuple[str, object], ...] = ()
    literal: bool = False


@dataclass(frozen=True)
class VoltageLabSummary:
    value: VoltageLabText
    detail: VoltageLabText


@dataclass(frozen=True)
class VoltageLabPresentation:
    summaries: tuple[VoltageLabSummary, ...]
    table_count: int
    table_tone: str
    controls_status: str
    controls_tone: str
    workflow_status: str
    workflow_tone: str


def _literal(value: object) -> VoltageLabText:
    return VoltageLabText(str(value), literal=True)


def _text(template: str, **values: object) -> VoltageLabText:
    return VoltageLabText(template, tuple(values.items()))


def present_voltage_lab(
    state: VoltageLabState, *, custom_voltage_maximum: int,
) -> VoltageLabPresentation:
    maximum = (
        _literal(f"{state.maximum_voltage} mV")
        if state.maximum_voltage
        else _text("Not detected")
    )
    active_range = (
        _literal(f"{state.active_min}–{state.active_max} MHz")
        if state.active_min or state.active_max
        else _text("Not available")
    )
    if state.safety_valid:
        safety_value = _text("Valid")
        safety_detail = _text("monotonic curve")
    elif state.curve_error_count:
        safety_value = _text("Review")
        safety_detail = _text("{count} curve errors", count=state.curve_error_count)
    else:
        safety_value = _text("Review")
        safety_detail = _text("no safe-points detected")

    ready = bool(state.editable_frequencies)
    summaries = (
        VoltageLabSummary(_literal(len(state.points)), _text("active TOML entries")),
        VoltageLabSummary(
            _text("Level {level}", level=state.detected_level),
            _text("closest defined curve"),
        ),
        VoltageLabSummary(
            maximum,
            _text(
                "advanced editor range up to {maximum} mV",
                maximum=int(custom_voltage_maximum),
            ),
        ),
        VoltageLabSummary(active_range, _text("restored after governor restart")),
        VoltageLabSummary(safety_value, safety_detail),
    )
    return VoltageLabPresentation(
        summaries=summaries,
        table_count=len(state.points),
        table_tone="green" if state.points else "orange",
        controls_status="Ready",
        controls_tone="orange",
        workflow_status="Armed" if ready else "Locked",
        workflow_tone="orange" if ready else "gray",
    )
