"""Pure fan-channel selection and telemetry normalization."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence


def _integer(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _number(value: object) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def pwm_to_percent(value: object) -> int | None:
    if value is None:
        return None
    return max(0, min(100, round(_integer(value) * 100 / 255)))


def visible_fans(
    state: Mapping[str, object],
    *,
    visible_order: Sequence[int],
) -> tuple[dict[str, object], ...]:
    raw_sensors = state.get("sensores")
    sensors = raw_sensors if isinstance(raw_sensors, Mapping) else {}
    raw_fans = sensors.get("fans")
    candidates = raw_fans if isinstance(raw_fans, (list, tuple)) else ()
    order = {int(index): position for position, index in enumerate(visible_order)}
    fans = [
        dict(fan)
        for fan in candidates
        if isinstance(fan, Mapping)
        and _integer(fan.get("index"), -1) in order
        and bool(fan.get("pwm_path"))
    ]
    return tuple(sorted(fans, key=lambda fan: order[_integer(fan.get("index"), -1)]))


@dataclass(frozen=True)
class FanStatePresentation:
    fans: tuple[dict[str, object], ...]
    main_fan: dict[str, object]
    selected_fan: dict[str, object]
    selected_index: int | None
    selected_percent: int | None
    gpu_temperature: float | None
    cpu_temperature: float | None
    driver: str
    module_raw: str
    control: bool
    chip: str
    path: str
    summary: str
    driver_mode: str
    driver_status: str
    driver_tone: str


def _main_fan(fans: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    active = [fan for fan in fans if _integer(fan.get("rpm")) > 0]
    if active:
        return max(active, key=lambda fan: _integer(fan.get("rpm")))
    return next(
        (fan for fan in fans if _integer(fan.get("index")) == 2),
        fans[0] if fans else {},
    )


def _selected_fan(
    fans: Sequence[Mapping[str, object]],
    selected_index: object,
    preferred_index: int,
) -> tuple[Mapping[str, object], int | None]:
    requested = selected_index if selected_index is not None else preferred_index
    selected = next(
        (fan for fan in fans if _integer(fan.get("index"), -1) == _integer(requested, -1)),
        fans[0] if fans else {},
    )
    index = _integer(selected.get("index"), -1) if selected else -1
    return selected, index if index >= 0 else None


def _gpu_temperature(
    performance: Mapping[str, object],
    gpu: Mapping[str, object],
) -> float | None:
    for source, key in ((performance, "gpu_temp"), (gpu, "gpu_temp"), (gpu, "temperature")):
        if source.get(key) is None:
            continue
        temperature = _number(source.get(key))
        if temperature is not None:
            return temperature
    return None


def _driver_presentation(
    modules: Mapping[str, object],
    *,
    control: bool,
    chip: str,
) -> tuple[str, str, str, str]:
    driver = "nct6687" if modules.get("nct6687") else "nct6683" if modules.get("nct6683") else "Not loaded"
    if control:
        return driver, "Writable PWM control", "PWM ready", "green"
    if chip:
        return driver, "Read-only monitoring", "Read only", "blue"
    return driver, "Controller not detected", "Not detected", "gray"


def present_fan_state(
    state: Mapping[str, object],
    performance: Mapping[str, object],
    gpu: Mapping[str, object],
    *,
    visible_order: Sequence[int],
    selected_index: object,
    preferred_index: int,
) -> FanStatePresentation:
    fans = visible_fans(state, visible_order=visible_order)
    main = _main_fan(fans)
    selected, selected_value = _selected_fan(fans, selected_index, preferred_index)
    cpu_temperature = _number(performance.get("cpu_temp"))
    raw_sensors = state.get("sensores")
    sensors = raw_sensors if isinstance(raw_sensors, Mapping) else {}
    raw_modules = state.get("modulos")
    modules = raw_modules if isinstance(raw_modules, Mapping) else {}
    control = bool(state.get("driver_control"))
    chip = str(sensors.get("chip") or "")
    driver, driver_mode, driver_status, driver_tone = _driver_presentation(
        modules,
        control=control,
        chip=chip,
    )
    return FanStatePresentation(
        fans=fans,
        main_fan=dict(main),
        selected_fan=dict(selected),
        selected_index=selected_value,
        selected_percent=pwm_to_percent(selected.get("pwm")) if selected else None,
        gpu_temperature=_gpu_temperature(performance, gpu),
        cpu_temperature=cpu_temperature,
        driver=driver,
        module_raw=str(modules.get("raw") or ""),
        control=control,
        chip=chip,
        path=str(sensors.get("path") or ""),
        summary=str(state.get("resumen") or ""),
        driver_mode=driver_mode,
        driver_status=driver_status,
        driver_tone=driver_tone,
    )
