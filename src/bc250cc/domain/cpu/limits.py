"""BC-250 CPU tuning limits preserved from the reviewed upstream contract."""

from __future__ import annotations

FREQUENCY_RANGE = (3500, 4200)
SCALE_RANGE = (-50, 0)
TEMPERATURE_RANGE = (70, 90)
VID_LIMIT_MV = 1325


def estimated_vid(frequency: int, scale: int) -> int | None:
    if type(frequency) is not int or type(scale) is not int:
        raise TypeError("frequency and scale must be integers")
    if frequency < 3000:
        return None
    p = -1.519 + scale * 0.004325
    q = 2800.0 - scale * 10.0
    return round((0.0003 * frequency * frequency) + (p * frequency) + q)
