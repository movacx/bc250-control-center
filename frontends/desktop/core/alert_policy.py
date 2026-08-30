"""Pure smart-alert classification from passive telemetry snapshots."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True)
class AlertEvent:
    key: str
    title_key: str
    message_key: str
    values: Mapping[str, object] = field(default_factory=dict)
    level: str = "info"
    cooldown_seconds: int = 300

    def canonical_message(self) -> str:
        try:
            return self.message_key.format(**dict(self.values))
        except (KeyError, ValueError, IndexError):
            return self.message_key


@dataclass(frozen=True)
class AlertClassification:
    events: tuple[AlertEvent, ...]
    gpu_history: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class AlertCooldownDecision:
    accepted: bool
    reason: str
    accepted_at: float | None


def evaluate_alert_cooldown(
    event: AlertEvent,
    *,
    last_alerts: Mapping[str, float],
    now: float,
) -> AlertCooldownDecision:
    last = last_alerts.get(event.key)
    if last is None:
        return AlertCooldownDecision(True, "first-event", float(now))
    elapsed = float(now) - float(last)
    if elapsed < 0:
        return AlertCooldownDecision(True, "clock-reset", float(now))
    if elapsed < max(0, int(event.cooldown_seconds)):
        return AlertCooldownDecision(False, "cooldown", None)
    return AlertCooldownDecision(True, "elapsed", float(now))


def _number(value: object) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _temperature_event(
    temperature: float | None,
    *,
    critical: float,
    warning: float,
    critical_event: AlertEvent,
    warning_event: AlertEvent,
) -> AlertEvent | None:
    if temperature is None:
        return None
    template = critical_event if temperature >= critical else warning_event if temperature >= warning else None
    if template is None:
        return None
    return AlertEvent(
        template.key,
        template.title_key,
        template.message_key,
        {"temperature": temperature},
        template.level,
        template.cooldown_seconds,
    )


def _gpu_temperature_events(
    temperature: float | None,
    gpu_history: Sequence[tuple[float, float]],
    now: float,
) -> tuple[list[AlertEvent], tuple[tuple[float, float], ...]]:
    history = deque(gpu_history, maxlen=90)
    if temperature is None:
        return [], tuple(history)
    history.append((float(now), temperature))
    while history and float(now) - history[0][0] > 60:
        history.popleft()
    events: list[AlertEvent] = []
    thermal = _temperature_event(
        temperature,
        critical=85,
        warning=78,
        critical_event=AlertEvent("gpu-temp-critical", "Critical GPU temperature", "GPU edge is {temperature:.1f} °C. Reduce load or frequency and check cooling.", level="critical", cooldown_seconds=180),
        warning_event=AlertEvent("gpu-temp-high", "High GPU temperature", "GPU edge is {temperature:.1f} °C. Monitor overclock, 40CU mode, and cooling.", level="warning", cooldown_seconds=300),
    )
    if thermal is not None:
        events.append(thermal)
    if len(history) >= 4:
        rise = temperature - history[0][1]
        if temperature >= 70 and rise >= 8:
            events.append(AlertEvent("gpu-temp-rise", "Rapid GPU temperature rise", "GPU temperature increased {rise:.1f} °C in under one minute.", {"rise": rise}, "warning", 300))
    return events, tuple(history)


def _memory_event(memory_usage: float, swap_usage: float) -> AlertEvent | None:
    values = {"memory": memory_usage, "swap": swap_usage}
    if memory_usage >= 92 or swap_usage >= 70:
        return AlertEvent("memory-critical", "High memory pressure", "RAM {memory:.0f}% · swap {swap:.0f}%. Stutter or freezing is possible.", values, "critical", 240)
    if memory_usage >= 85 or swap_usage >= 45:
        return AlertEvent("memory-warning", "Memory pressure detected", "RAM {memory:.0f}% · swap {swap:.0f}%. Consider closing heavy applications.", values, "warning", 420)
    return None


def _governor_event(gpu_state: Mapping[str, object]) -> AlertEvent | None:
    service_state = str(gpu_state.get("service_active") or "").lower()
    if service_state and service_state not in {"active", "running"}:
        return AlertEvent("governor-inactive", "GPU governor is not active", "cyan-skillfish-governor-smu state: {state}.", {"state": service_state}, "critical", 180)
    if gpu_state and not bool(gpu_state.get("dbus_ok", True)):
        return AlertEvent("governor-dbus", "GPU governor D-Bus unavailable", "Monitoring remains available, but GPU ranges cannot be applied through D-Bus.", level="critical", cooldown_seconds=180)
    return None


def classify_alerts(
    metrics: Mapping[str, object],
    gpu_state: Mapping[str, object],
    *,
    gpu_history: Sequence[tuple[float, float]],
    now: float,
) -> AlertClassification:
    cpu = _mapping(metrics.get("cpu"))
    gpu = _mapping(metrics.get("gpu"))
    memory = _mapping(metrics.get("memory"))
    cpu_temp = _number(cpu.get("temperature_c"))
    gpu_temp = _number(gpu.get("temperature_c"))
    gpu_usage = _number(gpu.get("usage_percent"))
    memory_usage = _number(memory.get("usage_percent")) or 0.0
    swap_usage = _number(memory.get("swap_percent")) or 0.0
    current_max = _number(gpu_state.get("current_max")) or 0.0
    events: list[AlertEvent] = []
    gpu_events, history = _gpu_temperature_events(gpu_temp, gpu_history, now)
    events.extend(gpu_events)
    cpu_event = _temperature_event(
        cpu_temp,
        critical=90,
        warning=82,
        critical_event=AlertEvent("cpu-temp-critical", "Critical CPU temperature", "CPU Tctl is {temperature:.1f} °C. Throttling or shutdown may occur.", level="critical", cooldown_seconds=180),
        warning_event=AlertEvent("cpu-temp-high", "High CPU temperature", "CPU Tctl is {temperature:.1f} °C. Review CPU tuning and cooling.", level="warning", cooldown_seconds=300),
    )
    for event in (cpu_event, _memory_event(memory_usage, swap_usage), _governor_event(gpu_state)):
        if event is not None:
            events.append(event)

    if current_max >= 2000 and (gpu_usage or 0) >= 80 and (gpu_temp or 0) >= 72:
        events.append(AlertEvent("gpu-high-oc-load", "High GPU overclock under load", "GPU load {usage:.0f}% · maximum {maximum:.0f} MHz · {temperature:.1f} °C.", {"usage": gpu_usage or 0.0, "maximum": current_max, "temperature": gpu_temp or 0.0}, "warning", 240))
    return AlertClassification(tuple(events), history)
