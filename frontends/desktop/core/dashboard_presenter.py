"""Pure normalization helpers for the passive Dashboard snapshot."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence


def _integer(value: object, default: int = 0) -> int:
    try:
        return int(float(value)) if value is not None else default
    except (TypeError, ValueError, OverflowError):
        return default


def present_cu_labels(cu_state: Mapping[str, object]) -> tuple[str, str]:
    mode_key = str(cu_state.get("mode_key") or "").lower()
    mode = {"full": "full dispatch", "custom": "Custom", "factory": "Factory"}.get(
        mode_key,
        mode_key.replace("_", " ") if mode_key else "Not verified",
    )
    boot_key = str(cu_state.get("boot_sync_key") or "").lower()
    boot = {"saved": "Saved", "pending": "Pending", "not_saved": "Not saved"}.get(
        boot_key,
        boot_key.replace("_", " ") if boot_key else "Not detected",
    )
    return mode, boot


@dataclass(frozen=True)
class DashboardFanPresentation:
    available: bool
    pwm_ready: bool
    rpm: int
    duty_percent: int
    mode: str
    label: str

    @property
    def needs_fallback(self) -> bool:
        return self.rpm <= 0

    def with_fallback(self, rpm: int, label: str) -> "DashboardFanPresentation":
        fallback_rpm = _integer(rpm)
        available = self.available or fallback_rpm > 0
        mode = self.mode
        if available and mode.lower() in {"unavailable", "unknown", "not detected", ""}:
            mode = "manual" if self.pwm_ready else "read only"
        return replace(
            self,
            available=available,
            rpm=fallback_rpm if fallback_rpm > 0 else self.rpm,
            label=str(label or self.label),
            mode=mode,
        )


def _pump_row(fan: Mapping[str, object]) -> Mapping[str, object]:
    sensors = fan.get("sensores")
    rows = sensors.get("fans") if isinstance(sensors, Mapping) else ()
    if not isinstance(rows, (list, tuple)):
        return {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        label = str(row.get("label") or row.get("canal") or row.get("name") or "")
        if any(token in label.lower() for token in ("pump", "j4003", "fan2")):
            return row
    return {}


def _pwm_percent(value: object, default: int = 0) -> int:
    pwm = _integer(value, -1)
    if pwm < 0:
        return max(0, min(100, int(default)))
    return max(0, min(100, round(pwm * 100 / 255)))


def present_dashboard_fan(
    fan: Mapping[str, object],
    *,
    performance_rpm: object,
) -> DashboardFanPresentation:
    available = bool(fan)
    rpm = _integer(performance_rpm)
    pwm_ready = bool(fan) and bool(
        fan.get("control_disponible")
        or fan.get("pwm_writable")
        or fan.get("driver_control")
        or fan.get("nct6687_loaded")
    )
    mode = str(fan.get("modo") or fan.get("mode") or ("manual" if pwm_ready else "read only")) if fan else "Not detected"
    rpm = _integer(fan.get("fan2_rpm") or fan.get("pump_fan_rpm") or rpm, rpm)
    raw_pwm = fan.get("pwm2") or fan.get("pump_fan_pwm")
    duty = _pwm_percent(raw_pwm)
    row = _pump_row(fan)
    label = str(row.get("label") or row.get("canal") or row.get("name") or "Not detected").replace(" / ", " · ")
    if row:
        rpm = _integer(row.get("rpm") or row.get("input") or rpm, rpm)
        duty = _pwm_percent(row.get("pwm"), duty)
    if available and mode.lower() in {"unavailable", "unknown", "not detected", ""}:
        mode = "manual" if pwm_ready else "read only"
    return DashboardFanPresentation(
        available=available,
        pwm_ready=pwm_ready,
        rpm=rpm,
        duty_percent=max(0, min(100, duty)),
        mode=mode,
        label=label,
    )


def present_activities(events: Sequence[object], limit: int = 5) -> tuple[tuple[str, str, str], ...]:
    activities = []
    for item in events[: max(0, int(limit))]:
        if not isinstance(item, Mapping):
            continue
        title = str(item.get("titulo") or item.get("title") or item.get("detalle") or "System event")
        timestamp = str(item.get("fecha") or item.get("timestamp") or item.get("hora") or "")
        when = timestamp[-8:] if timestamp else "recent"
        level = str(item.get("nivel") or item.get("level") or "success")
        activities.append((title[:78], when, level))
    return tuple(activities)
