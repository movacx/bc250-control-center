"""Pure validation and argv construction for the privileged CPU/SMU boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bc250cc.infrastructure.cpu_oc_config import estimated_vid


@dataclass(frozen=True)
class CPUDetectionTarget:
    frequency: int
    vid: int
    temperature: int


@dataclass(frozen=True)
class CPUScaleTarget:
    frequency: int
    scale: int
    temperature: int
    estimated_vid: int | None


def _integer(value, message: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(message) from error


def validate_detection_target(frequency, vid, temperature) -> CPUDetectionTarget:
    target = CPUDetectionTarget(
        _integer(frequency, "CPU frequency must be an integer"),
        _integer(vid, "CPU VID must be an integer"),
        _integer(temperature, "CPU temperature must be an integer"),
    )
    if not 3500 <= target.frequency <= 4200:
        raise ValueError("The UI limits temporary CPU OC to 3500-4200 MHz")
    if not 950 <= target.vid <= 1325:
        raise ValueError("The UI limits VID to 950-1325 mV")
    if not 70 <= target.temperature <= 90:
        raise ValueError("The UI limits CPU/GPU temperature to 70-90 C")
    return target


def validate_scale_target(frequency, scale, temperature) -> CPUScaleTarget:
    frequency = _integer(frequency, "CPU frequency must be an integer")
    scale = _integer(scale, "CPU scale must be an integer")
    temperature = _integer(temperature, "CPU temperature must be an integer")
    if not 3500 <= frequency <= 4200:
        raise ValueError("CPU frequency must be between 3500 and 4200 MHz")
    if not -50 <= scale <= 0:
        raise ValueError("CPU scale must be between -50 and 0")
    if not 70 <= temperature <= 90:
        raise ValueError("CPU temperature limit must be between 70 and 90 C")
    voltage = estimated_vid(frequency, scale)
    if voltage is not None and voltage > 1325:
        raise ValueError(
            f"CPU scale would estimate ~{voltage} mV at {frequency} MHz, "
            "above the upstream 1325 mV ceiling"
        )
    return CPUScaleTarget(frequency, scale, temperature, voltage)


def _boundary(executor, helper) -> list[str]:
    executor, helper = str(executor or ""), str(helper or "")
    if not executor or "\x00" in executor:
        raise ValueError("The privileged command executor is invalid")
    if not helper or "\x00" in helper:
        raise ValueError("The CPU/SMU helper path is invalid")
    return [executor, helper]


def build_detect_command(executor, helper, target: CPUDetectionTarget, config_path) -> list[str]:
    raw_config = str(config_path or "")
    if not raw_config or "\x00" in raw_config:
        raise ValueError("The CPU detector configuration path is invalid")
    config = str(Path(raw_config))
    return _boundary(executor, helper) + [
        "detect",
        str(target.frequency),
        str(target.vid),
        str(target.temperature),
        config,
    ]


def build_scale_command(executor, helper, action: str, target: CPUScaleTarget) -> list[str]:
    if action not in {"apply-live", "install-boot"}:
        raise ValueError("Unsupported privileged CPU scale action")
    return _boundary(executor, helper) + [
        action,
        str(target.frequency),
        str(target.scale),
        str(target.temperature),
    ]


def build_disable_command(executor, helper) -> list[str]:
    return _boundary(executor, helper) + ["disable-boot"]
