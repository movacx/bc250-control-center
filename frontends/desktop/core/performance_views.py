"""The other ways of looking at the CPU, the GPU and VRAM.

Each Performance tile charts one summary: CPU load, GPU load, VRAM in use.
Hovering the tile offers the rest of what that part reports, drawn in the
same chart: each core's load, each thread's, each core's clock, the GPU's
clocks, rails and power, the GDDR6 chips while a reading session runs.

Every view is a selection over the sensor list (see
``bc250cc.infrastructure.sensor_inventory``), so nothing here reads hardware
and a view shows exactly what the Sensors list shows for the same moment.
Pure Python: the page builds histories and draws from these.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from bc250cc.infrastructure.sensor_inventory import (
    CLOCK,
    GROUP_CPU,
    GROUP_GDDR6,
    GROUP_GPU,
    POWER,
    TEMPERATURE,
    VOLTAGE,
    SensorReading,
)

#: More lines than this and a line chart stops being readable: a view that
#: can exceed it is drawn as a heat map instead (one row per series).
MAX_LINES = 8


@dataclass(frozen=True)
class ChartSeries:
    """One series of a view: a name template, its fields, and the reading."""

    name: str
    fields: tuple[tuple[str, int], ...]
    value: float | None


@dataclass(frozen=True)
class MetricView:
    key: str
    resource: str
    title: str
    hint: str
    unit: str = "%"
    #: "lines", or "heatmap" for the views with one row per thread.
    form: str = "lines"
    #: Picks this view's series out of a sample; None for the tile's own
    #: summary, which the page already charts.
    pick: Callable[[Sequence[SensorReading]], list[ChartSeries]] | None = None
    #: Shown greyed out, with this reason, while the view has nothing to draw.
    unavailable_hint: str = ""

    @property
    def is_summary(self) -> bool:
        return self.pick is None

    def series(self, readings: Sequence[SensorReading]) -> list[ChartSeries]:
        return [] if self.pick is None else self.pick(readings)


def _by_key(pattern: str, name: str, fields: Iterable[str]) -> Callable[[Sequence[SensorReading]], list[ChartSeries]]:
    expression = re.compile(pattern)
    names = tuple(fields)

    def pick(readings: Sequence[SensorReading]) -> list[ChartSeries]:
        result = []
        for reading in readings:
            match = expression.fullmatch(reading.key)
            if match is None:
                continue
            values = tuple((field, int(group)) for field, group in zip(names, match.groups()))
            result.append(ChartSeries(name, values, reading.value))
        return result

    return pick


def _keys(pairs: Sequence[tuple[str, str]]) -> Callable[[Sequence[SensorReading]], list[ChartSeries]]:
    wanted = dict(pairs)

    def pick(readings: Sequence[SensorReading]) -> list[ChartSeries]:
        found = {reading.key: reading for reading in readings if reading.key in wanted}
        return [
            ChartSeries(wanted[key], (), found[key].value)
            for key, _name in pairs
            if key in found
        ]

    return pick


def _channels(group: str, kind: str, *, hwmon_only: bool = True, upper: bool = False) -> Callable[[Sequence[SensorReading]], list[ChartSeries]]:
    """A group's hwmon channels of one kind, named as the kernel names them."""

    def pick(readings: Sequence[SensorReading]) -> list[ChartSeries]:
        return [
            ChartSeries(reading.label.upper() if upper else reading.label, (), reading.value)
            for reading in readings
            if reading.group == group
            and reading.kind == kind
            and (not hwmon_only or reading.key.startswith("hwmon/"))
        ]

    return pick


def _gddr6(readings: Sequence[SensorReading]) -> list[ChartSeries]:
    return [
        ChartSeries("Chip {chip}", reading.fields, reading.value)
        for reading in readings
        if reading.group == GROUP_GDDR6 and reading.key.startswith("gddr6/chip")
    ]


RESOURCE_VIEWS: dict[str, tuple[MetricView, ...]] = {
    "cpu": (
        MetricView("cpu", "cpu", "Total usage", "All threads together"),
        MetricView(
            "cpu.cores", "cpu", "Usage per core", "One line per physical core",
            pick=_by_key(r"cpu/core(\d+)/usage", "Core {core}", ("core",)),
        ),
        MetricView(
            "cpu.threads", "cpu", "Usage per thread", "One row per thread; the stronger the colour, the busier",
            form="heatmap",
            pick=_by_key(r"cpu/core(\d+)/t(\d+)/usage", "C{core}·T{thread}", ("core", "thread")),
        ),
        MetricView(
            "cpu.clocks", "cpu", "Clock per core", "Effective clock of each core",
            unit="MHz", pick=_by_key(r"cpu/core(\d+)/clock", "Core {core}", ("core",)),
        ),
        MetricView(
            "cpu.temperature", "cpu", "Temperature", "Tctl, the temperature the CPU is controlled by",
            unit="°C", pick=_channels(GROUP_CPU, TEMPERATURE),
        ),
    ),
    "gpu": (
        MetricView("gpu", "gpu", "Usage", "How busy the graphics engine is"),
        MetricView(
            "gpu.compute", "gpu", "Async compute", "Time on the compute (ACE) queues; above zero while a game uses them",
            pick=_keys((("gpu/compute", "ACE"),)),
            unavailable_hint="Read from amdgpu's per-client counters once the GPU load is sampled.",
        ),
        MetricView(
            "gpu.clock", "gpu", "Core clock", "SCLK, as amdgpu reports it",
            unit="MHz", pick=_channels(GROUP_GPU, CLOCK, upper=True),
        ),
        MetricView(
            "gpu.fabric", "gpu", "Memory, SoC and fabric clocks", "The clocks that feed memory",
            unit="MHz", pick=_keys((("gpu/mclk", "MCLK"), ("gpu/socclk", "SOCCLK"), ("gpu/fclk", "FCLK"))),
        ),
        MetricView(
            "gpu.temperature", "gpu", "Temperature", "The GPU's edge sensor",
            unit="°C", pick=_channels(GROUP_GPU, TEMPERATURE),
        ),
        MetricView(
            "gpu.power", "gpu", "Power", "PPT, the power of the whole SoC package",
            unit="W", pick=_channels(GROUP_GPU, POWER),
        ),
        MetricView(
            "gpu.voltage", "gpu", "Voltage", "The vddgfx and vddnb rails",
            unit="V", pick=_channels(GROUP_GPU, VOLTAGE),
        ),
    ),
    "vram": (
        MetricView("vram", "vram", "Used", "Dedicated graphics memory in use"),
        MetricView(
            "vram.gtt", "vram", "GTT", "System memory the GPU has mapped",
            pick=_keys((("gpu/gtt_percent", "GTT"),)),
        ),
        MetricView(
            "vram.gddr6", "vram", "GDDR6 chip temperature", "One line per memory chip",
            unit="°C", pick=_gddr6,
            unavailable_hint="Start a GDDR6 reading on the Dashboard to chart the chips.",
        ),
        MetricView(
            "vram.clock", "vram", "Memory clock", "MCLK",
            unit="MHz", pick=_keys((("gpu/mclk", "MCLK"),)),
        ),
    ),
}

VIEW_BY_KEY: dict[str, MetricView] = {
    view.key: view for views in RESOURCE_VIEWS.values() for view in views
}


def views_for(resource: str) -> tuple[MetricView, ...]:
    return RESOURCE_VIEWS.get(resource, ())


def available_views(readings: Sequence[SensorReading]) -> set[str]:
    """The views that would draw something from this sample."""
    available = set()
    for key, view in VIEW_BY_KEY.items():
        if view.is_summary or any(item.value is not None for item in view.series(readings)):
            available.add(key)
    return available


def series_label(series: ChartSeries, translate: Callable[[str], str]) -> str:
    fields: Mapping[str, int] = dict(series.fields)
    try:
        return translate(series.name).format(**fields)
    except (KeyError, IndexError, ValueError):
        return series.name.format(**fields)
