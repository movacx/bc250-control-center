"""Pure selection and formatting plan for GPU telemetry evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from bc250cc.domain.telemetry import valid_number, voltage_mv


@dataclass(frozen=True)
class TelemetryText:
    template: str
    values: tuple[tuple[str, object], ...] = ()
    literal: bool = False


@dataclass(frozen=True)
class GpuTelemetryPresentation:
    temperature: float
    utilization: int | None
    voltage_text: TelemetryText
    temperature_text: TelemetryText
    utilization_text: TelemetryText
    vram_value: TelemetryText
    vram_detail: TelemetryText
    power_label: TelemetryText
    power_text: TelemetryText
    power_detail: TelemetryText


def _number(value: object) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _integer(value: object) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _literal(value: object) -> TelemetryText:
    return TelemetryText(str(value), literal=True)


def _text(template: str, **values: object) -> TelemetryText:
    return TelemetryText(template, tuple(values.items()))


def format_bytes(value: object) -> str:
    amount = _number(value)
    if amount <= 0:
        return "--"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    index = 0
    while amount >= 1024 and index < len(units) - 1:
        amount /= 1024.0
        index += 1
    precision = 0 if index == 0 else 1
    return f"{amount:.{precision}f} {units[index]}"


def _vram_texts(total: float, used: float) -> tuple[TelemetryText, TelemetryText]:
    if not total:
        return _text("Not detected"), _text("VRAM counters unavailable")
    return (
        _literal(f"{(used / total * 100.0):.0f} %"),
        _text("{used} of {total}", used=format_bytes(used), total=format_bytes(total)),
    )


def _power_texts(perf: Mapping[str, object]) -> tuple[TelemetryText, TelemetryText, TelemetryText]:
    power = _number(perf.get("power_w"))
    if perf.get("power_is_total"):
        detail = "Dedicated total-board power sensor"
    elif str(perf.get("power_scope") or "") == "gpu_soc":
        detail = "AMDGPU SoC power sensor; total board power unavailable"
    else:
        detail = "No live power sensor exposed"
    return (
        _text(str(perf.get("power_label") or "Power sensor unavailable")),
        _literal(f"{power:.0f} W") if power else _text("Not detected"),
        _text(detail),
    )


def present_gpu_telemetry(
    gpu: Mapping[str, object], perf: Mapping[str, object],
) -> GpuTelemetryPresentation:
    temperature = valid_number(perf.get("gpu_temp"), 0.1, 130) or 0.0
    raw_utilization = gpu.get("gpu_busy")
    if raw_utilization is None:
        raw_utilization = perf.get("gpu_busy")
    valid_utilization = valid_number(raw_utilization, 0, 100)
    utilization = None if valid_utilization is None else round(valid_utilization)
    voltage = voltage_mv(gpu.get("voltaje_actual")) or 0
    raw_busy = gpu.get("gpu_busy")
    if raw_busy is None:
        raw_busy = perf.get("gpu_busy")
    idle_without_voltage = voltage == 0 and raw_busy is not None and _integer(raw_busy) == 0
    vram_total = _number(gpu.get("vram_total"))
    vram_used = _number(gpu.get("vram_usado"))
    vram_value, vram_detail = _vram_texts(vram_total, vram_used)
    power_label, power_text, power_detail = _power_texts(perf)
    return GpuTelemetryPresentation(
        temperature=temperature,
        utilization=utilization,
        voltage_text=(
            _literal(f"{voltage} mV")
            if voltage
            else _text("Not exposed at idle")
            if idle_without_voltage
            else _text("Not exposed")
        ),
        temperature_text=(
            _literal(f"{temperature:.1f} °C") if temperature else _text("Not detected")
        ),
        utilization_text=(
            _text("Not detected") if utilization is None else _literal(f"{utilization} %")
        ),
        vram_value=vram_value,
        vram_detail=vram_detail,
        power_label=power_label,
        power_text=power_text,
        power_detail=power_detail,
    )
