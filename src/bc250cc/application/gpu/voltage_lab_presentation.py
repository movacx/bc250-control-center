"""Pure presentation plan for the GPU voltage-laboratory summary."""

from __future__ import annotations

from dataclasses import dataclass


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

