"""CPU state models independent of persistence, init and privileged writes."""

from __future__ import annotations

from dataclasses import dataclass

from .limits import FREQUENCY_RANGE, SCALE_RANGE, TEMPERATURE_RANGE


def _validate_tuning_values(frequency_mhz: int, scale: int, temperature_c: int) -> None:
    values = (frequency_mhz, scale, temperature_c)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError("CPU tuning values must be integers.")
    if not FREQUENCY_RANGE[0] <= frequency_mhz <= FREQUENCY_RANGE[1]:
        raise ValueError("CPU frequency is outside the reviewed range.")
    if not SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]:
        raise ValueError("CPU scale is outside the reviewed range.")
    if not TEMPERATURE_RANGE[0] <= temperature_c <= TEMPERATURE_RANGE[1]:
        raise ValueError("CPU temperature is outside the reviewed range.")


@dataclass(frozen=True, slots=True)
class CpuTuningProfile:
    frequency_mhz: int
    scale: int
    temperature_c: int

    def __post_init__(self) -> None:
        _validate_tuning_values(self.frequency_mhz, self.scale, self.temperature_c)


@dataclass(frozen=True, slots=True)
class CpuBinding:
    hardware_id: str
    configuration_sha256: str
    frequency_mhz: int
    temperature_c: int
    scale: int

    def __post_init__(self) -> None:
        if not self.hardware_id.strip():
            raise ValueError("CPU binding hardware_id cannot be empty.")
        if not self.configuration_sha256.strip():
            raise ValueError("CPU binding configuration hash cannot be empty.")
        _validate_tuning_values(self.frequency_mhz, self.scale, self.temperature_c)
