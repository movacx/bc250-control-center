"""Pure action availability and automatic-curve gates for the fan page."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class FanActionAvailability:
    channel_select: bool
    use_live: bool
    apply_pwm: bool
    apply_curve: bool
    save_curve: bool
    add_point: bool
    remove_point: bool
    edit_curve: bool
    driver_setup: bool


@dataclass(frozen=True)
class AutomaticCurveDecision:
    action: str
    reason: str
    pwm: int | None = None
    percent: int | None = None
    touched_at: float | None = None


def plan_fan_action_availability(
    *,
    control_ready: bool,
    channel_count: int,
    curve_point_count: int,
    busy: bool,
) -> FanActionAvailability:
    idle = not busy
    has_channels = int(channel_count) > 0
    writable = idle and control_ready and has_channels
    return FanActionAvailability(
        channel_select=idle and has_channels,
        use_live=idle and has_channels,
        apply_pwm=writable,
        apply_curve=writable,
        save_curve=idle,
        add_point=idle and int(curve_point_count) < 8,
        remove_point=idle and int(curve_point_count) > 3,
        edit_curve=idle,
        driver_setup=idle,
    )


def plan_automatic_curve(
    *,
    busy: bool,
    curve_enabled: bool,
    control_ready: bool,
    validation_error: str,
    temperature: float | None,
    now: float,
    last_apply: float,
    last_percent: int | None,
    calculated_percent: int | None,
    selected_pwm: object,
    minimum_interval: float = 5.0,
) -> AutomaticCurveDecision:
    if busy:
        return AutomaticCurveDecision("skip", "busy")
    if not curve_enabled:
        return AutomaticCurveDecision("skip", "disabled")
    if not control_ready:
        return AutomaticCurveDecision("skip", "read-only")
    if validation_error:
        return AutomaticCurveDecision("skip", "invalid-curve")
    if temperature is None or not math.isfinite(float(temperature)):
        return AutomaticCurveDecision("skip", "sensor-missing")
    if selected_pwm is None:
        return AutomaticCurveDecision("skip", "channel-missing")
    if float(now) - float(last_apply) < float(minimum_interval):
        return AutomaticCurveDecision("skip", "rate-limited")
    if calculated_percent is None:
        return AutomaticCurveDecision("skip", "target-missing")
    percent = max(0, min(100, int(calculated_percent)))
    if last_percent == percent:
        return AutomaticCurveDecision("touch", "target-unchanged", touched_at=float(now))
    try:
        pwm = int(selected_pwm)
    except (TypeError, ValueError):
        return AutomaticCurveDecision("skip", "channel-invalid")
    if pwm <= 0:
        return AutomaticCurveDecision("skip", "channel-invalid")
    return AutomaticCurveDecision("apply", "target-changed", pwm=pwm, percent=percent)
