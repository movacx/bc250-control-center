from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

#: The preset key of a manual slider value, kept like a named tier.
CUSTOM_FAN_PRESET = "custom"
FAN_PRESET_VALUES = {
    "quiet": 45,
    "balanced": 60,
    "cooling": 70,
    "maximum": 100,
    # A speed set with the slider rather than a named tier. It is saved the
    # same way, so the daemon restores it at login and the root service
    # follows it from boot (as a "fixed" policy), until the fan is handed
    # back to the BIOS.
    CUSTOM_FAN_PRESET: 70,
}
FAN_CURVE_MIN_POINTS = 3
FAN_CURVE_MAX_POINTS = 8
DEFAULT_FAN_CURVE_POINTS = ((50, 70), (65, 100), (70, 100))
FAN_TEMPERATURE_SENSORS = (
    ("gpu_temp", "gpu"),
    ("cpu_temp", "cpu"),
    ("vrm_temp", "vrm"),
    ("board_temp", "board"),
)
DEFAULT_CRITICAL_TEMPERATURES_C = {
    "gpu": 95.0,
    "cpu": 95.0,
    "vrm": 105.0,
    "board": 90.0,
}


@dataclass(frozen=True)
class FanControlMemory:
    last_apply: float = 0
    last_percent: int | None = None
    last_target: tuple[int, int, str] | None = None
    last_verify: float = 0
    missing_since: float | None = None
    last_temperature: float | None = None


@dataclass(frozen=True)
class FanTarget:
    pwm: int
    percent: int
    raw: int
    source: str
    temperature: object
    curve_enabled: bool
    temperature_sensor: str | None = None
    raw_temperature: float | None = None

    @property
    def identity(self) -> tuple[int, int, str]:
        return self.pwm, self.percent, self.source


@dataclass(frozen=True)
class FanControlDecision:
    action: str
    target: FanTarget | None = None
    missing_since: float | None = None
    reason: str = ""


def bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        parsed = int(default)
    return max(minimum, min(maximum, parsed))


def bounded_float(value, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("non-finite number")
    except (TypeError, ValueError, OverflowError):
        parsed = float(default)
    return max(minimum, min(maximum, parsed))


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


def _source_curve_points(source: dict) -> list[tuple[int, int]]:
    raw_points = source.get("points")
    points: list[tuple[int, int]] = []
    if isinstance(raw_points, (list, tuple)):
        for item in raw_points[:FAN_CURVE_MAX_POINTS]:
            if isinstance(item, dict):
                temperature = item.get("temperature", item.get("temp"))
                speed = item.get("speed", item.get("percent"))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                temperature, speed = item
            else:
                continue
            points.append((
                bounded_int(temperature, 50, 0, 120),
                bounded_int(speed, 70, 0, 100),
            ))
    if points:
        return points

    # Legacy 3-point configurations remain a first-class input. Additional
    # t4/s4...t8/s8 keys are accepted for forward compatibility.
    for index in range(1, FAN_CURVE_MAX_POINTS + 1):
        temperature_key = f"t{index}"
        speed_key = f"s{index}"
        if index > FAN_CURVE_MIN_POINTS and temperature_key not in source and speed_key not in source:
            continue
        default_temp, default_speed = DEFAULT_FAN_CURVE_POINTS[min(index - 1, 2)]
        points.append((
            bounded_int(source.get(temperature_key), default_temp, 0, 120),
            bounded_int(source.get(speed_key), default_speed, 0, 100),
        ))
    return points


def validate_fan_curve_points(points: object) -> tuple[bool, str]:
    if not isinstance(points, (list, tuple)):
        return False, "Fan curve points must be a list."
    if not FAN_CURVE_MIN_POINTS <= len(points) <= FAN_CURVE_MAX_POINTS:
        return False, "Fan curves require between 3 and 8 points."
    normalized = []
    for item in points:
        try:
            temperature, speed = item
            temperature = int(temperature)
            speed = int(speed)
        except (TypeError, ValueError):
            return False, "Each fan curve point requires a temperature and speed."
        if not 0 <= temperature <= 120:
            return False, "Fan curve temperatures must be between 0 and 120 C."
        if not 0 <= speed <= 100:
            return False, "Fan speeds must be between 0 and 100 percent."
        normalized.append((temperature, speed))
    temperatures = [temperature for temperature, _speed in sorted(normalized)]
    if any(current <= previous for previous, current in pairwise(temperatures)):
        return False, "Fan curve temperatures must be strictly increasing."
    return True, ""


def _repair_curve_points(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    points = sorted(points[:FAN_CURVE_MAX_POINTS], key=lambda item: item[0])
    while len(points) < FAN_CURVE_MIN_POINTS:
        points.append(DEFAULT_FAN_CURVE_POINTS[len(points)])
        points.sort(key=lambda item: item[0])

    repaired: list[tuple[int, int]] = []
    for temperature, speed in points:
        minimum = repaired[-1][0] + 1 if repaired else 0
        repaired.append((max(minimum, min(120, int(temperature))), max(0, min(100, int(speed)))))
    # Eight clamped values always fit in 0..120; shift the sequence back when
    # malformed input accumulated at the upper boundary.
    if repaired[-1][0] > 120:
        shift = repaired[-1][0] - 120
        repaired = [(temperature - shift, speed) for temperature, speed in repaired]
    return repaired


def normalize_fan_curve(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    points = _repair_curve_points(_source_curve_points(source))
    preset = str(source.get("preset") or "custom").strip().lower()
    # v2.1 renamed the misleading "Cool" curve to "Aggressive". Preserve
    # existing user configurations by migrating the stable identifier once.
    if preset == "cool":
        preset = "aggressive"
    result: dict[str, object] = {
        "enabled": safe_bool(source.get("enabled", False)),
        "edit_enabled": safe_bool(
            source.get("edit_enabled", source.get("enabled", False))
        ),
        "pwm": bounded_int(source.get("pwm"), 2, 1, 12),
        "preset": preset,
        "last_pwm_text": str(source.get("last_pwm_text") or "--"),
        "point_count": len(points),
        "points": [
            {"temperature": temperature, "speed": speed}
            for temperature, speed in points
        ],
    }
    for index, (temperature, speed) in enumerate(points, start=1):
        result[f"t{index}"] = temperature
        result[f"s{index}"] = speed
    return result


def normalize_fan_preset(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    preset = str(source.get("preset") or "").strip().lower()
    if preset not in FAN_PRESET_VALUES:
        return {"enabled": False, "preset": "", "percent": 0, "pwm": 2}
    expected = FAN_PRESET_VALUES[preset]
    return {
        "enabled": safe_bool(source.get("enabled", False)),
        "preset": preset,
        "percent": bounded_int(source.get("percent"), expected, 0, 100),
        "pwm": bounded_int(source.get("pwm"), 2, 1, 12),
    }


def fan_curve_percent_for_temp(temp: object, curve: object) -> int | None:
    try:
        temperature = float(temp)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(temperature):
        return None
    config = normalize_fan_curve(curve)
    points = config.get("points") or []
    target = int(points[0]["speed"])
    for point in points:
        if temperature >= int(point["temperature"]):
            target = int(point["speed"])
    return max(0, min(100, target))


def _temperature_readings(
    metric: object, config: object = None, *, now: float | None = None,
) -> list[tuple[float, float, str]]:
    """Return fresh ``(effective, raw, sensor)`` thermal readings.

    The curve operates on an effective temperature so installations can
    compensate for a known sensor offset without changing every curve point.
    Safety thresholds always use the unmodified hardware reading.
    """
    sample = metric if isinstance(metric, dict) else {}
    settings = config if isinstance(config, dict) else {}
    offsets = settings.get("fan_daemon_sensor_offsets_c")
    offsets = offsets if isinstance(offsets, dict) else {}
    timestamps = sample.get("temperature_sensor_times")
    has_timestamps = isinstance(timestamps, dict)
    timestamps = timestamps if has_timestamps else {}
    maximum_age = bounded_float(
        settings.get("fan_daemon_sensor_max_age_seconds"), 6, 1, 60
    )
    readings: list[tuple[float, float, str]] = []
    for key, sensor in FAN_TEMPERATURE_SENSORS:
        try:
            raw = float(sample.get(key))
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(raw) or not 0 < raw <= 130:
            continue
        if now is not None and has_timestamps:
            try:
                age = float(now) - float(timestamps.get(sensor))
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(age) or age < 0 or age > maximum_age:
                continue
        offset = bounded_float(offsets.get(sensor), 0, -30, 30)
        readings.append((raw + offset, raw, sensor))
    return readings


def select_fan_control_temperature(
    metric: object, config: object = None, *, now: float | None = None,
) -> tuple[float | None, str | None]:
    """Select the hottest fresh APU, VRM or board reading for the fan curve."""
    readings = _temperature_readings(metric, config, now=now)
    if not readings:
        return None, None
    effective, _raw, sensor = max(readings, key=lambda item: item[0])
    return effective, sensor


def _critical_temperature(
    metric: object, config: object, *, now: float,
) -> tuple[float, str] | None:
    settings = config if isinstance(config, dict) else {}
    configured = settings.get("fan_daemon_critical_temperatures_c")
    configured = configured if isinstance(configured, dict) else {}
    critical = []
    for _effective, raw, sensor in _temperature_readings(
        metric, settings, now=now
    ):
        threshold = bounded_float(
            configured.get(sensor), DEFAULT_CRITICAL_TEMPERATURES_C[sensor],
            50, 125,
        )
        if raw >= threshold:
            critical.append((raw - threshold, raw, sensor))
    if not critical:
        return None
    _excess, raw, sensor = max(critical, key=lambda item: (item[0], item[1]))
    return raw, sensor


def _smoothed_percent(
    percent: int, temperature: object, config: dict, memory: FanControlMemory,
    *, pwm: int, source: str,
) -> int:
    previous = memory.last_percent
    if source != "curve" or not memory.last_target or memory.last_target[0] != pwm:
        return percent
    hysteresis = bounded_float(config.get("fan_daemon_hysteresis_c"), 1.0, 0, 10)
    deadband = bounded_int(config.get("fan_daemon_duty_deadband_percent"), 2, 0, 20)
    if temperature is not None and memory.last_temperature is not None:
        try:
            if abs(float(temperature) - float(memory.last_temperature)) < hysteresis:
                percent = previous if previous is not None else percent
        except (TypeError, ValueError, OverflowError):
            pass
    if previous is not None and abs(percent - previous) <= deadband:
        percent = previous
    max_down = bounded_int(config.get("fan_daemon_max_down_step_percent"), 10, 1, 100)
    if previous is not None and percent < previous - max_down:
        percent = previous - max_down
    return percent


def plan_persistent_fan(
    metric: object, config: object, memory: FanControlMemory, *, now: float,
) -> FanControlDecision:
    """Return the next daemon action without reading or writing hardware."""
    settings = config if isinstance(config, dict) else {}
    sample = metric if isinstance(metric, dict) else {}
    curve = normalize_fan_curve(settings.get("fan_curve"))
    preset = normalize_fan_preset(settings.get("fan_preset"))
    curve_enabled = safe_bool(curve.get("enabled"))
    preset_enabled = safe_bool(preset.get("enabled"))
    if not curve_enabled and not preset_enabled:
        return FanControlDecision("disabled")

    temperature, temperature_sensor = select_fan_control_temperature(
        sample, settings, now=now
    )
    raw_temperature = next(
        (
            raw for _effective, raw, sensor in _temperature_readings(
                sample, settings, now=now
            )
            if sensor == temperature_sensor
        ),
        None,
    )
    missing_since = memory.missing_since
    critical = _critical_temperature(sample, settings, now=now)
    if curve_enabled:
        if critical is not None:
            raw_temperature, temperature_sensor = critical
            temperature = raw_temperature
            missing_since = None
            percent = bounded_int(
                settings.get("fan_daemon_failsafe_percent"), 100, 40, 100
            )
            source = "curve:critical"
        else:
            percent = fan_curve_percent_for_temp(temperature, curve)
        if critical is None and percent is None:
            if missing_since is None:
                return FanControlDecision(
                    "sensor-missing", missing_since=now,
                    reason="CPU and GPU temperature sensors unavailable",
                )
            timeout = bounded_float(
                settings.get("fan_daemon_sensor_timeout_seconds"), 15, 3, 300
            )
            if now - missing_since < timeout:
                return FanControlDecision("sensor-wait", missing_since=missing_since)
            percent = bounded_int(
                settings.get("fan_daemon_failsafe_percent"), 100, 40, 100
            )
            source = "curve:failsafe"
        elif critical is None:
            missing_since = None
            source = "curve"
        pwm = bounded_int(curve.get("pwm"), 2, 1, 12)
    else:
        percent = bounded_int(preset.get("percent"), 70, 0, 100)
        pwm = bounded_int(preset.get("pwm"), 2, 1, 12)
        source = f"preset:{preset.get('preset') or 'unknown'}"

    if source != "curve:critical" and now - memory.last_apply < 5:
        return FanControlDecision("rate-limited", missing_since=missing_since)
    percent = _smoothed_percent(
        percent, temperature, settings, memory, pwm=pwm, source=source
    )
    target = FanTarget(
        pwm=pwm, percent=percent, raw=round(percent * 255 / 100), source=source,
        temperature=temperature, curve_enabled=curve_enabled,
        temperature_sensor=temperature_sensor,
        raw_temperature=raw_temperature,
    )
    verify_seconds = bounded_float(
        settings.get("fan_daemon_verify_seconds"), 30, 5, 600
    )
    if memory.last_target == target.identity:
        action = "skip" if now - memory.last_verify < verify_seconds else "verify"
    else:
        action = "apply"
    return FanControlDecision(action, target, missing_since)
