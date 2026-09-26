"""Axis arithmetic shared by the live charts.

Kept free of Qt so it can be tested on its own. The tick rules are the usual
ones for measurement charts: steps of 1, 2 or 5 times a power of ten, a range
that starts at zero for quantities that cannot be negative, and time marks on
round seconds counted back from "now".
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def nice_step(span: float, target_ticks: int = 5) -> float:
    """The 1/2/5×10ⁿ step that divides ``span`` into about ``target_ticks``."""
    span = abs(float(span))
    if not math.isfinite(span) or span <= 0:
        return 1.0
    raw = span / max(1, int(target_ticks))
    exponent = math.floor(math.log10(raw))
    base = 10.0 ** exponent
    for multiplier in (1.0, 2.0, 2.5, 5.0, 10.0):
        if raw <= multiplier * base * (1 + 1e-9):
            return multiplier * base
    return 10.0 * base


@dataclass(frozen=True)
class ValueAxis:
    minimum: float
    maximum: float
    step: float

    @property
    def ticks(self) -> tuple[float, ...]:
        count = int(round((self.maximum - self.minimum) / self.step))
        return tuple(self.minimum + index * self.step for index in range(count + 1))

    @property
    def minor_ticks(self) -> tuple[float, ...]:
        """Half steps between the labelled ones."""
        half = self.step / 2
        return tuple(tick + half for tick in self.ticks[:-1])


def value_axis(
    peak: float,
    *,
    fixed_maximum: float | None = None,
    minimum_span: float = 0.0,
    headroom: float = 1.15,
    target_ticks: int = 5,
) -> ValueAxis:
    """A zero-based axis whose top is a round number above ``peak``.

    With ``fixed_maximum`` the axis is that range exactly (0–100 %). Without
    it, the top leaves ``headroom`` above the peak and never shrinks below
    ``minimum_span``, so an idle line does not fill the whole plot with noise.
    """
    if fixed_maximum is not None:
        step = nice_step(fixed_maximum, target_ticks)
        return ValueAxis(0.0, float(fixed_maximum), step)
    wanted = max(float(minimum_span), max(0.0, float(peak)) * headroom)
    if wanted <= 0:
        wanted = 1.0
    step = nice_step(wanted, target_ticks)
    top = math.ceil(wanted / step - 1e-9) * step
    return ValueAxis(0.0, top, step)


def zoomed_percent_axis(
    peak: float, *, minimum_span: float = 10.0, target_ticks: int = 5
) -> ValueAxis:
    """0–100 % data shown on the smallest round range that holds it."""
    axis = value_axis(peak, minimum_span=minimum_span, target_ticks=target_ticks)
    if axis.maximum >= 100:
        return value_axis(0, fixed_maximum=100, target_ticks=target_ticks)
    return axis


def range_axis(
    low: float,
    high: float,
    *,
    minimum_span: float = 1.0,
    margin: float = 0.12,
    target_ticks: int = 5,
) -> ValueAxis:
    """Round numbers around a band of data that does not start at zero.

    A clock between 3,380 and 3,493 MHz or a temperature between 47 and 52 °C
    drawn from zero is a flat line at the top. This axis frames the data,
    keeps ``minimum_span`` so idle noise is not blown up to fill the plot,
    and never goes below zero for data that never does.
    """
    low, high = sorted((float(low), float(high)))
    span = max(high - low, float(minimum_span), 1e-9)
    centre = (low + high) / 2.0
    bottom = centre - span * (0.5 + margin)
    top = centre + span * (0.5 + margin)
    if low >= 0.0:
        bottom = max(0.0, bottom)
    step = nice_step(top - bottom, target_ticks)
    bottom = math.floor(bottom / step + 1e-9) * step
    top = math.ceil(top / step - 1e-9) * step
    if top <= bottom:
        top = bottom + step
    return ValueAxis(bottom, top, step)


def ticks_for_height(
    height: float, *, spacing: float = 48.0, minimum: int = 4, maximum: int = 10
) -> int:
    """How many labelled steps a plot this tall can hold legibly.

    A taller chart gets a finer scale instead of the same five lines drawn
    further apart.
    """
    try:
        count = int(float(height) // max(1.0, float(spacing)))
    except (TypeError, ValueError):
        count = minimum
    return max(minimum, min(maximum, count))


def time_ticks(window_seconds: float, *, width_pixels: float = 800.0) -> tuple[int, ...]:
    """Seconds before "now" to mark, on a round interval the width can hold."""
    window = max(1, int(window_seconds))
    for interval in (5, 10, 15, 30, 60, 120, 300, 600, 900, 1800):
        marks = window // interval
        if marks <= 8 and width_pixels / max(1, marks) >= 70:
            return tuple(range(0, window + 1, interval))
    return (0, window)


def format_age(seconds: int) -> str:
    """"-1:30" style label for a time mark counted back from now."""
    seconds = int(seconds)
    if seconds <= 0:
        return ""
    minutes, rest = divmod(seconds, 60)
    return f"-{minutes}:{rest:02d}" if minutes else f"-{rest} s"
