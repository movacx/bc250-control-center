"""Pure scheduling and metric policy for the background daemon cycle."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping


def safe_number(
    value: object, default: float, minimum: float, maximum: float,
    *, integer: bool = False,
) -> int | float:
    try:
        parsed = int(value) if integer else float(value)
        if not integer and not math.isfinite(parsed):
            raise ValueError("non-finite number")
    except (TypeError, ValueError, OverflowError):
        parsed = int(default) if integer else float(default)
    parsed = max(minimum, min(maximum, parsed))
    return int(parsed) if integer else float(parsed)


def safe_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled", ""}:
            return False
    return bool(default)


@dataclass(frozen=True)
class DaemonCyclePlan:
    governor_due: bool
    metrics_due: bool
    memory_due: bool
    health_due: bool
    alerts_enabled: bool
    gpu_temp_warning: float
    cpu_temp_warning: float


def plan_daemon_cycle(
    config: Mapping[str, object], *, now: float,
    last_governor: float, last_metrics: float,
    last_memory: float, last_health: float,
) -> DaemonCyclePlan:
    governor_interval = safe_number(
        config.get("daemon_governor_interval_seconds"), 10, 2, 300
    )
    metrics_interval = safe_number(
        config.get("daemon_metrics_interval_seconds"), 5, 1, 300
    )
    memory_interval = safe_number(
        config.get("daemon_memory_interval_seconds"), 30, 5, 600
    )
    return DaemonCyclePlan(
        governor_due=now - last_governor >= governor_interval,
        metrics_due=now - last_metrics >= metrics_interval,
        memory_due=now - last_memory >= memory_interval,
        health_due=now - last_health >= 10,
        # Desktop and daemon notifications are retired until a future explicit
        # opt-in implementation.  Ignore legacy configuration that may still
        # contain alertas_activas=true.
        alerts_enabled=False,
        gpu_temp_warning=float(safe_number(config.get("gpu_temp_warning"), 82, 30, 120)),
        cpu_temp_warning=float(safe_number(config.get("cpu_temp_warning"), 88, 30, 120)),
    )


def build_runtime_metric(
    performance: Mapping[str, object], gpu_state: Mapping[str, object],
) -> dict[str, object]:
    return {
        "cpu": performance.get("cpu"),
        "cpu_temp": performance.get("cpu_temp"),
        "gpu_temp": performance.get("gpu_temp"),
        "gpu_busy": performance.get("gpu_busy"),
        "gpu_power": performance.get("gpu_power"),
        "memoria_porcentaje": performance.get("memoria_porcentaje"),
        "swap_porcentaje": performance.get("swap_porcentaje"),
        "bc250": {
            "service_active": gpu_state.get("service_active"),
            "dbus_ok": gpu_state.get("dbus_ok"),
            "current_min": gpu_state.get("current_min"),
            "current_max": gpu_state.get("current_max"),
            "sclk_actual": gpu_state.get("sclk_actual"),
        },
    }


def governor_warning_needed(
    alerts_enabled: bool, gpu_state: Mapping[str, object],
) -> bool:
    return bool(
        alerts_enabled
        and gpu_state
        and gpu_state.get("service_active") not in ("active", "", None)
    )
