"""Pure presentation state for GPU governor diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class DiagnosticText:
    template: str
    values: tuple[tuple[str, object], ...] = ()
    literal: bool = False
    translate_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiagnosticLine:
    value: DiagnosticText
    detail: DiagnosticText


@dataclass(frozen=True)
class GpuDiagnosticsPresentation:
    device: DiagnosticLine
    driver: DiagnosticLine
    config: DiagnosticLine
    curve: DiagnosticLine
    missing: DiagnosticLine
    duplicates: DiagnosticLine
    power: DiagnosticLine


def _literal(value: object) -> DiagnosticText:
    return DiagnosticText(str(value), literal=True)


def _text(template: str, **values: object) -> DiagnosticText:
    return DiagnosticText(template, tuple(values.items()))


def compact_diagnostic_path(value: object) -> str:
    text = str(value or "--")
    if text in {"", "--"}:
        return "--"
    return f"…/{text.rsplit('/', 1)[-1]}"


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _integer(value: object) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _range_value(value: object) -> DiagnosticText:
    state = _mapping(value)
    if not state.get("valid"):
        return _text("invalid: {error}", error=str(state.get("error") or "--"))
    if state.get("mode") == "floor":
        return _text(
            "persistent floor {minimum}; runtime profile maximum",
            minimum=_integer(state.get("min")),
        )
    if not state.get("enabled"):
        return DiagnosticText("profile mode; section disabled")
    maximum: object = _integer(state.get("max")) or "unlimited"
    return DiagnosticText(
        "custom {minimum}–{maximum}",
        (("minimum", _integer(state.get("min"))), ("maximum", maximum)),
        translate_values=("maximum",) if maximum == "unlimited" else (),
    )


def _curve_line(errors: tuple[object, ...]) -> DiagnosticLine:
    if not errors:
        return DiagnosticLine(
            DiagnosticText("Valid"),
            DiagnosticText("Voltage does not decrease as frequency rises"),
        )
    parts = []
    for item in errors:
        evidence = _mapping(item)
        parts.append(
            f"{evidence.get('previous_frequency')}/{evidence.get('previous_voltage')} > "
            f"{evidence.get('frequency')}/{evidence.get('voltage')}"
        )
    return DiagnosticLine(DiagnosticText("Invalid"), _literal("; ".join(parts)))


def _frequency_value(item: object) -> object:
    return _mapping(item).get("frequency") or item


def _collection_line(
    values: tuple[object, ...], *, empty_detail: str,
) -> DiagnosticLine:
    if not values:
        return DiagnosticLine(DiagnosticText("None"), DiagnosticText(empty_detail))
    detail = ", ".join(str(_frequency_value(item)) for item in values)
    return DiagnosticLine(_literal(len(values)), _literal(detail))


def present_gpu_diagnostics(
    state: Mapping[str, object], *, detailed: bool,
) -> GpuDiagnosticsPresentation:
    gpu_path = str(state.get("gpu_path") or "--")
    config_path = str(state.get("config_path") or "--")
    if not detailed:
        gpu_path = compact_diagnostic_path(gpu_path)
        config_path = compact_diagnostic_path(config_path)
    errors = tuple(state.get("safe_points_voltage_errors") or ())
    missing = tuple(state.get("safe_points_missing_voltage") or ())
    duplicates = tuple(state.get("safe_points_duplicate_frequencies") or ())
    return GpuDiagnosticsPresentation(
        device=DiagnosticLine(
            _literal(f"{state.get('vendor') or '--'} / {state.get('device') or '--'}"),
            DiagnosticText("AMD BC250 PCI identifiers"),
        ),
        driver=DiagnosticLine(_literal(state.get("driver") or "--"), _literal(gpu_path)),
        config=DiagnosticLine(_range_value(state.get("frequency_range")), _literal(config_path)),
        curve=_curve_line(errors),
        missing=_collection_line(missing, empty_detail="Every active point exposes voltage"),
        duplicates=_collection_line(
            duplicates, empty_detail="No duplicate frequency entries detected"
        ),
        power=DiagnosticLine(
            _literal(state.get("power_state") or "--"),
            _text(
                "force performance level: {level}",
                level=str(state.get("power_level") or "--"),
            ),
        ),
    )
