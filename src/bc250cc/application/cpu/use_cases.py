"""Pure CPU use-case validation; live/persistent writes remain adapters."""

from __future__ import annotations

from bc250cc.domain.cpu import FREQUENCY_RANGE, SCALE_RANGE, TEMPERATURE_RANGE
from bc250cc.shared import ErrorDetail, Result


def validate_tuning_target(frequency: int, scale: int, temperature: int) -> Result[tuple[int, int, int]]:
    if any(type(value) is not int for value in (frequency, scale, temperature)):
        return Result.failure(ErrorDetail("CPU_INPUT_INVALID", "CPU tuning values must be integers."))
    values = (frequency, scale, temperature)
    if not FREQUENCY_RANGE[0] <= values[0] <= FREQUENCY_RANGE[1]:
        return Result.failure(ErrorDetail("CPU_FREQUENCY_RANGE", "CPU frequency is outside the reviewed range."))
    if not SCALE_RANGE[0] <= values[1] <= SCALE_RANGE[1]:
        return Result.failure(ErrorDetail("CPU_SCALE_RANGE", "CPU scale is outside the reviewed range."))
    if not TEMPERATURE_RANGE[0] <= values[2] <= TEMPERATURE_RANGE[1]:
        return Result.failure(ErrorDetail("CPU_TEMPERATURE_RANGE", "CPU temperature limit is outside the reviewed range."))
    return Result.success(values)
