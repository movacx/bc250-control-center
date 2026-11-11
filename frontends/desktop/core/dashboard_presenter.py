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
    channel_selected: bool = False
    rpm_known: bool = False
    duty_known: bool = False

    @property
    def needs_fallback(self) -> bool:
        return self.rpm <= 0 and not self.channel_selected

    def with_fallback(self, rpm: int, label: str) -> "DashboardFanPresentation":
        if self.channel_selected:
            return self
        fallback_rpm = _integer(rpm, -1)
        measured = fallback_rpm >= 0 and bool(label)
        available = self.available or measured
        mode = self.mode
        if available and mode.lower() in {"unavailable", "unknown", "not detected", ""}:
            mode = "manual" if self.pwm_ready else "read only"
        return replace(
            self,
            available=available,
            rpm=fallback_rpm if measured else self.rpm,
            label=str(label or self.label),
            mode=mode,
            rpm_known=measured or self.rpm_known,
        )


def _pump_row(fan: Mapping[str, object]) -> Mapping[str, object]:
    sensors = fan.get("sensores")
    rows = sensors.get("fans") if isinstance(sensors, Mapping) else ()
    if not isinstance(rows, (list, tuple)):
        return {}
    # The pump header is CPU_FAN1 (Linux fan2). The five J4003 headers all
    # carry "j4003" in their label, and the first one listed is Fan 5, so a
    # bare "j4003" match picked an empty header and the card read 0 RPM.
    # Prefer the pump by name, then any J4003 header that is actually
    # spinning, and only then the first J4003 header.
    candidates = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        label = str(row.get("label") or row.get("canal") or row.get("name") or "").lower()
        if any(token in label for token in ("pump", "cpu_fan1", "fan2")):
            return row
        if "j4003" in label:
            candidates.append(row)
    for row in candidates:
        if _integer(row.get("rpm", row.get("input")), 0) > 0:
            return row
    return candidates[0] if candidates else {}


def _pwm_percent(value: object, default: int = 0) -> int:
    pwm = _integer(value, -1)
    if pwm < 0:
        return max(0, min(100, int(default)))
    return max(0, min(100, round(pwm * 100 / 255)))


#: What a user reads for each owner of the fan's PWM.
FAN_OWNER_LABELS = {
    "system": "System service",
    "daemon": "Desktop daemon",
    "firmware": "Firmware (BIOS)",
    "manual": "Manual value",
    "external": "Another program",
}


def fan_owner(
    *,
    system_owned: bool,
    pwm_enable: object,
    curve_enabled: bool,
    preset_enabled: bool,
    external: bool = False,
) -> str:
    """Who sets the fan's duty right now.

    Another program (CoolerControl...) once the fan was handed to it; the
    root service when it holds the fan; the board firmware when the
    channel is in automatic mode (pwm_enable 2); the desktop daemon when a
    curve or preset is saved for it; otherwise a value someone wrote by hand.
    """
    if external:
        return "external"
    if system_owned:
        return "system"
    if _integer(pwm_enable, -1) == 2:
        return "firmware"
    if curve_enabled or preset_enabled:
        return "daemon"
    return "manual"


def dashboard_fan_owner(
    fan: Mapping[str, object], *, system_owned: bool, config: Mapping[str, object],
    external: bool = False,
) -> str:
    """``fan_owner`` for the dashboard's pump fan, from the saved settings."""
    row = _pump_row(fan) if fan else {}
    curve = config.get("fan_curve")
    preset = config.get("fan_preset")
    return fan_owner(
        system_owned=system_owned,
        pwm_enable=row.get("pwm_enable"),
        curve_enabled=isinstance(curve, Mapping) and bool(curve.get("enabled")),
        preset_enabled=isinstance(preset, Mapping) and bool(preset.get("enabled")),
        external=external,
    )


def present_dashboard_fan(
    fan: Mapping[str, object],
    *,
    performance_rpm: object,
) -> DashboardFanPresentation:
    available = bool(fan)
    pwm_ready = bool(fan) and bool(
        fan.get("control_disponible")
        or fan.get("pwm_writable")
        or fan.get("driver_control")
        or fan.get("nct6687_loaded")
    )
    mode = str(fan.get("modo") or fan.get("mode") or ("manual" if pwm_ready else "read only")) if fan else "Not detected"
    row = _pump_row(fan)
    label = str(row.get("label") or row.get("canal") or row.get("name") or "Not detected").replace(" / ", " · ")
    selected = bool(row)
    if row:
        rpm = _integer(row.get("rpm", row.get("input")), -1)
        raw_pwm = row.get("pwm")
    else:
        raw_rpm = fan.get("fan2_rpm", fan.get("pump_fan_rpm"))
        raw_pwm = fan.get("pwm2", fan.get("pump_fan_pwm"))
        selected = raw_rpm is not None or raw_pwm is not None
        rpm = _integer(raw_rpm if selected else performance_rpm, -1)
        if selected:
            label = "Pump Fan"
    duty = _pwm_percent(raw_pwm)
    if available and mode.lower() in {"unavailable", "unknown", "not detected", ""}:
        mode = "manual" if pwm_ready else "read only"
    return DashboardFanPresentation(
        available=available,
        pwm_ready=pwm_ready,
        rpm=max(0, rpm),
        channel_selected=selected,
        rpm_known=rpm >= 0 and (selected or rpm > 0),
        duty_known=_integer(raw_pwm, -1) >= 0,
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
