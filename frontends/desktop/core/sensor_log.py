"""What the sensor list remembers between samples.

A hardware monitor is read for its minimum, average and maximum as much as
for the value now: the peak a game reached, the lowest clock under load. The
log keeps those per sensor since it started (or since the user reset them),
plus the last two minutes of values for the traces drawn beside the list.
Pure Python: the page feeds it readings and draws what it holds.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field

from bc250cc.infrastructure.sensor_inventory import SensorReading

from .performance_sample_presenter import format_bytes, format_rate

#: Two minutes at the page's one-second cadence, like the main chart.
TRACE_POINTS = 120


def format_sensor_value(value: float | None, unit: str) -> str:
    """One reading in the precision its unit is read at, or an en dash."""
    if value is None or not math.isfinite(value):
        return "–"
    if unit == "°C":
        return f"{value:.1f} °C"
    if unit == "MHz":
        return f"{value:.0f} MHz"
    if unit == "%":
        return f"{value:.1f} %"
    if unit == "W":
        return f"{value:.1f} W"
    if unit == "V":
        return f"{value:.3f} V"
    if unit == "A":
        return f"{value:.1f} A"
    if unit == "RPM":
        return f"{value:.0f} RPM"
    if unit == "B":
        return format_bytes(value)
    if unit == "B/s":
        return format_rate(value)
    return f"{value:g} {unit}".strip()


@dataclass
class SensorEntry:
    """One sensor: its latest reading, its statistics and its trace."""

    reading: SensorReading
    minimum: float | None = None
    maximum: float | None = None
    total: float = 0.0
    count: int = 0
    trace: deque = field(default_factory=lambda: deque(maxlen=TRACE_POINTS))

    @property
    def value(self) -> float | None:
        return self.reading.value

    @property
    def average(self) -> float | None:
        return self.total / self.count if self.count else None

    @property
    def active(self) -> bool:
        """Ever read something other than zero.

        A Nuvoton channel with nothing wired to it reads 0 for ever; the list
        can leave those out without hiding a sensor that is merely idle now.
        """
        return any(
            value not in (None, 0.0) for value in (self.minimum, self.maximum)
        )

    def record(self, reading: SensorReading, moment: float) -> None:
        self.reading = reading
        value = reading.value
        if value is None or not math.isfinite(value):
            return
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)
        self.total += value
        self.count += 1
        self.trace.append((moment, value))

    def reset(self) -> None:
        self.minimum = self.maximum = None
        self.total = 0.0
        self.count = 0


class SensorLog:
    """Every sensor seen so far, in the order the inventory lists them."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self.entries: dict[str, SensorEntry] = {}
        self.order: list[str] = []
        self.started_at = clock()

    def record(self, readings: Iterable[SensorReading], moment: float | None = None) -> list[str]:
        """Take one sample; return the keys that appeared for the first time."""
        moment = self._clock() if moment is None else float(moment)
        added: list[str] = []
        for reading in readings:
            entry = self.entries.get(reading.key)
            if entry is None:
                entry = SensorEntry(reading)
                self.entries[reading.key] = entry
                self.order.append(reading.key)
                added.append(reading.key)
            entry.record(reading, moment)
        return added

    def reset_statistics(self) -> None:
        """Minimum, average and maximum start again from the next sample."""
        for entry in self.entries.values():
            entry.reset()
        self.started_at = self._clock()

    def get(self, key: str) -> SensorEntry | None:
        return self.entries.get(key)
