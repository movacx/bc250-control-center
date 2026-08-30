"""CPU domain package."""

from .limits import (
    FREQUENCY_RANGE,
    SCALE_RANGE,
    TEMPERATURE_RANGE,
    VID_LIMIT_MV,
    estimated_vid,
)
from .models import CpuBinding, CpuTuningProfile

__all__ = [
    "CpuBinding",
    "CpuTuningProfile",
    "FREQUENCY_RANGE",
    "SCALE_RANGE",
    "TEMPERATURE_RANGE",
    "VID_LIMIT_MV",
    "estimated_vid",
]
