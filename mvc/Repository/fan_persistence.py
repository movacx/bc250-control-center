from __future__ import annotations

import math


FAN_PRESET_VALUES = {
    "quiet": 45,
    "balanced": 60,
    "cooling": 70,
    "maximum": 100,
}


def bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        parsed = int(default)
    return max(minimum, min(maximum, parsed))


def normalize_fan_curve(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    points = [
        (
            bounded_int(source.get(f"t{index}"), default_temp, 0, 120),
            bounded_int(source.get(f"s{index}"), default_speed, 0, 100),
        )
        for index, (default_temp, default_speed) in enumerate(
            ((50, 70), (65, 100), (70, 100)),
            start=1,
        )
    ]
    points.sort(key=lambda item: item[0])
    preset = str(source.get("preset") or "custom")
    result: dict[str, object] = {
        "enabled": bool(source.get("enabled", False)),
        "edit_enabled": bool(source.get("edit_enabled", source.get("enabled", False))),
        "pwm": bounded_int(source.get("pwm"), 2, 1, 12),
        "preset": preset,
        "last_pwm_text": str(source.get("last_pwm_text") or "--"),
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
        "enabled": bool(source.get("enabled", False)),
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
    target = int(config["s1"])
    for index in range(1, 4):
        if temperature >= int(config[f"t{index}"]):
            target = int(config[f"s{index}"])
    return max(0, min(100, target))
