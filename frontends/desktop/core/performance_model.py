"""The Performance page's model, without Qt: resources, views, histories, the sensor list's grouping.

The desktop page draws it with Qt and the terminal interface with curses; both
keep the same two-minute histories, offer the same views and summarise them
the same way.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from math import log10

from bc250cc.application.system.sensors import (
    CLOCK,
    CURRENT,
    DATA,
    FAN,
    GPU_DEVICE,
    GROUP_CPU,
    GROUP_GDDR6,
    GROUP_GPU,
    GROUP_MEMORY,
    GROUP_NETWORK,
    GROUP_STORAGE,
    GROUP_VRM,
    POWER,
    RATE,
    TEMPERATURE,
    USAGE,
    VOLTAGE,
    SensorReading,
)

from ..i18n import tr, tr_format
from .performance_views import MAX_LINES, MetricView
from .sensor_log import SensorLog, format_sensor_value


def _number(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _nice_ceiling(value: float) -> float:
    value = max(1.0, float(value))
    exponent = 10 ** max(0, int(log10(value)))
    normalized = value / exponent
    if normalized <= 1:
        step = 1
    elif normalized <= 2:
        step = 2
    elif normalized <= 5:
        step = 5
    else:
        step = 10
    return float(step * exponent)


@dataclass(frozen=True)
class ResourceDefinition:
    key: str
    title: str
    subtitle: str
    icon_name: str
    icon_background: str
    series: tuple[tuple[str, str], ...]
    stat_labels: tuple[str, str, str, str]
    fixed_maximum: float | None = None
    rate_scale: bool = False
    #: What the values are measured in: "%" (the summaries), or the unit of a
    #: view (MHz, °C, W, V), which frames its own range instead of 0–100.
    unit: str = "%"
    #: "lines", or "heatmap" for a view with one row per thread.
    form: str = "lines"


RESOURCE_DEFINITIONS = (
    ResourceDefinition(
        "cpu",
        "CPU",
        "Scheduler load and package frequency.",
        "cpu_blue",
        "blue_soft",
        (("Usage", "blue"),),
        ("Frequency", "Temperature", "Load average", "Peak"),
        fixed_maximum=100,
    ),
    ResourceDefinition(
        "gpu",
        "GPU",
        "Graphics engine load, clock, thermals, and power.",
        "gpu_purple",
        "purple_soft",
        (("Usage", "purple"),),
        ("SCLK", "Temperature", "SoC power", "Peak"),
        fixed_maximum=100,
    ),
    ResourceDefinition(
        "vram",
        "VRAM",
        "Dedicated graphics memory pressure.",
        "vram_gray",
        "purple_soft",
        (("Used", "purple"),),
        ("Used", "Available", "Total", "Peak"),
        fixed_maximum=100,
    ),
    ResourceDefinition(
        "memory",
        "RAM",
        "Memory pressure, availability, and swap usage.",
        "memory_green",
        "green_soft",
        (("Used", "green"),),
        ("Used", "Available", "Swap", "Peak"),
        fixed_maximum=100,
    ),
    ResourceDefinition(
        "disk",
        "Disk",
        "Root filesystem usage, throughput, and active I/O time.",
        "disk_orange",
        "orange_soft",
        (("Read", "blue"), ("Write", "orange")),
        ("Used", "Available", "Active time", "Peak I/O"),
        rate_scale=True,
    ),
    ResourceDefinition(
        "network",
        "Network",
        "Traffic on the active default interface.",
        "network_cyan",
        "cyan_soft",
        (("Download", "cyan"), ("Upload", "purple")),
        ("Interface", "Download", "Upload", "Peak"),
        rate_scale=True,
    ),
)
RESOURCE_BY_KEY = {definition.key: definition for definition in RESOURCE_DEFINITIONS}
#: The sensor list's tab, before the resources'. It has no chart of its own.
SENSORS_TAB = ResourceDefinition("sensors", "Sensors", "", "", "", (), ("", "", "", ""))
#: The sensor list's layouts, offered in its tab's menu like a part's views.
SENSOR_VIEWS = (
    MetricView("list", "sensors", "List", "Every sensor with its minimum, average and maximum."),
    MetricView("split", "sensors", "List + graphs", "The list, with the sensors you tick drawn beside it."),
    MetricView("graphs", "sensors", "Graphs", "Only the graphs of the sensors you tick, larger."),
)

#: The smallest range a view's axis spans, so an idle reading is not blown up
#: into a jagged line filling the plot.
MINIMUM_SPAN = {"MHz": 200.0, "°C": 10.0, "W": 10.0, "V": 0.1}


def view_definition(view: MetricView, names: Iterable[str]) -> ResourceDefinition:
    """The chart definition of a view, once its series are known."""
    names = tuple(names)
    resource = RESOURCE_BY_KEY[view.resource]
    single = len(names) == 1
    return ResourceDefinition(
        view.key,
        view.title,
        view.hint,
        resource.icon_name,
        resource.icon_background,
        # A series keeps its slot (core 3 is always the fourth colour), and
        # past eight there are no more slots: those views are heat maps.
        tuple((name, f"series_{index + 1}" if index < MAX_LINES else "blue") for index, name in enumerate(names)),
        ("Now", "Minimum", "Average", "Maximum") if single else ("Highest", "Lowest", "Mean", "Window peak"),
        fixed_maximum=100 if view.unit == "%" else None,
        unit=view.unit,
        form=view.form,
    )


class MetricHistory:
    """The last two minutes of one resource, with when each sample arrived.

    Timestamps place every point where it belongs on the time axis, so a
    stalled or late sample shows as a gap instead of silently compressing the
    rest of the line.
    """

    WINDOW_SECONDS = 120

    def __init__(self, definition: ResourceDefinition):
        self.definition = definition
        self.values = {name: deque(maxlen=120) for name, _color in definition.series}
        self.times: deque[float] = deque(maxlen=120)
        #: Bumped by every sample, so a chart knows its cached drawing is stale.
        self.revision = 0

    def append(self, values: dict[str, float], *, moment: float | None = None) -> None:
        self.times.append(time.monotonic() if moment is None else float(moment))
        for name, _color in self.definition.series:
            self.values[name].append(max(0.0, _number(values.get(name))))
        self.revision += 1

    def peak(self, name: str | None = None) -> float:
        if name is not None:
            return max(self.values.get(name, ()), default=0.0)
        return max((max(values, default=0.0) for values in self.values.values()), default=0.0)

    def average(self, name: str) -> float | None:
        values = self.values.get(name) or ()
        return sum(values) / len(values) if values else None

    def low(self) -> float:
        """The lowest value of any series in the window."""
        return min((min(values) for values in self.values.values() if values), default=0.0)

    def maximum(self) -> float:
        if self.definition.fixed_maximum is not None:
            return max(1.0, self.definition.fixed_maximum)
        peak = self.peak()
        return _nice_ceiling(peak * 1.15) if peak > 0 else 1024.0


def series_statistics(history: MetricHistory, name: str) -> tuple[float, float, float] | None:
    """Minimum, average and maximum of one series over the window."""
    values = list(history.values.get(name, ()))
    if not values:
        return None
    return min(values), sum(values) / len(values), max(values)


def view_summary(view: MetricView, history: MetricHistory, available: set[str]) -> tuple[str, str, tuple[str, str, str, str]]:
    """The header reading and the four boxes of a view."""
    unit = history.definition.unit

    def show(value: float | None) -> str:
        if value is None:
            return "--"
        return f"{value:.1f}%" if unit == "%" else format_sensor_value(value, unit)

    latest = [
        (values[-1], name)
        for name, _tone in history.definition.series
        if (values := history.values.get(name))
    ]
    if not latest:
        unavailable = view.unavailable_hint if view.key not in available else ""
        return "--", tr(unavailable or "Waiting for sample"), ("--", "--", "--", "--")
    if len(latest) == 1:
        value, name = latest[0]
        statistics = series_statistics(history, name)
        low, average, high = statistics if statistics else (None, None, None)
        return show(value), name, (show(value), show(low), show(average), show(high))
    high_value, high_name = max(latest)
    low_value, low_name = min(latest)
    mean = sum(value for value, _name in latest) / len(latest)
    return (
        show(high_value),
        tr_format("highest: {name} · {count} series", name=high_name, count=len(latest)),
        (
            f"{high_name} · {show(high_value)}",
            f"{low_name} · {show(low_value)}",
            show(mean),
            show(history.peak()),
        ),
    )


#: Rendered on first open, before the user has ticked anything.
DEFAULT_PLOTTED = ("hwmon/k10temp/temp1", "cpu/usage")

#: Filter choices: (label, kinds they keep). The first shows everything; the
#: others are chips that can be combined, the way a hardware monitor's type
#: buttons are: temperatures and fans together, say, while tuning a curve.
KIND_FILTERS = (
    ("All sensors", ()),
    ("Temperatures", (TEMPERATURE,)),
    ("Clocks", (CLOCK,)),
    ("Usage", (USAGE,)),
    ("Power", (POWER,)),
    ("Voltages", (VOLTAGE,)),
    ("Currents", (CURRENT,)),
    ("Fans", (FAN,)),
    ("Memory and throughput", (DATA, RATE)),
)

#: The view modes: the list, the list with its graphs, only the graphs.
MODES = (("list", "List"), ("split", "List + graphs"), ("graphs", "Graphs"))

#: Where each fixed group sits; hwmon chips go between the GPU parts and
#: memory, where a hardware monitor lists the board.
GROUP_RANK = {
    GROUP_CPU: 0, GROUP_GPU: 1, GROUP_GDDR6: 2, GROUP_VRM: 3,
    GROUP_MEMORY: 5, GROUP_STORAGE: 6, GROUP_NETWORK: 7,
}

def sensor_label(reading: SensorReading) -> str:
    """The row's name: the kernel's label as is, or a translated template."""
    if not reading.fields:
        return tr(reading.label) if not reading.key.startswith("hwmon/") else reading.label
    try:
        return tr(reading.label).format(**dict(reading.fields))
    except (KeyError, IndexError, ValueError):
        return reading.label.format(**dict(reading.fields))


def search_text(reading: SensorReading) -> str:
    """What the filter field is matched against, for the list and the graphs."""
    return f"{sensor_label(reading)} {reading.device} {reading.label}".casefold()


def group_title(group: str, reading: SensorReading) -> str:
    if group == GROUP_STORAGE:
        return tr_format("Storage · {device}", device=reading.device)
    if group == GROUP_NETWORK:
        return tr_format("Network · {device}", device=reading.device)
    if group in (GROUP_MEMORY, GROUP_GDDR6, GROUP_VRM, GROUP_GPU):
        return tr(reading.device) if reading.device != GPU_DEVICE else reading.device
    return reading.device


class PerformanceRecorder:
    """Two minutes of every resource and every view, plus the sensor list, fed one sample a second.

    What the desktop page does on each sample, without its widgets: the
    resource plans and their histories, the sensor log, and one history per
    view that the sample has something to draw for.
    """

    def __init__(self, inventory=None, translate=tr) -> None:
        from bc250cc.application.system.sensors import SensorInventory

        from .performance_sample_presenter import present_performance_sample
        from .performance_views import VIEW_BY_KEY

        self._present, self._views, self._translate = present_performance_sample, VIEW_BY_KEY, translate
        self.inventory = inventory if inventory is not None else SensorInventory()
        self.histories = {definition.key: MetricHistory(definition) for definition in RESOURCE_DEFINITIONS}
        self.views: dict[str, MetricHistory] = {}
        self.plans: dict = {}
        self.log = SensorLog()
        self.available = {key for key, view in VIEW_BY_KEY.items() if view.is_summary}
        self.sampled_at = ""

    def read(self, sample: dict) -> list:
        """The sensor list for ``sample``: the slow part, kept apart so it can run outside a lock."""
        try:
            return self.inventory.read(sample)
        except Exception:  # noqa: BLE001 - the list is extra; the resources still chart
            return []

    def record(self, sample: dict, readings: list | None = None) -> None:
        from datetime import datetime

        from .performance_views import available_views, series_label

        moment = time.monotonic()
        peaks = {key: history.peak() for key, history in self.histories.items()}
        for plan in self._present(sample, previous_peaks=peaks, translate=self._translate):
            self.plans[plan.key] = plan
            self.histories[plan.key].append(dict(plan.graph_values), moment=moment)
        readings = self.read(sample) if readings is None else readings
        if readings:
            self.log.record(readings, moment)
            self.available = available_views(readings)
            for key, view in self._views.items():
                series = [] if view.is_summary else view.series(readings)
                if not series:
                    continue
                names = tuple(series_label(item, self._translate) for item in series)
                history = self.views.get(key)
                if history is None or tuple(name for name, _tone in history.definition.series) != names:
                    history = self.views[key] = MetricHistory(view_definition(view, names))
                history.append({name: item.value or 0.0 for name, item in zip(names, series)}, moment=moment)
        self.sampled_at = datetime.now().strftime("%H:%M:%S")

    def history(self, view_key: str) -> MetricHistory | None:
        view = self._views[view_key]
        return self.histories[view.resource] if view.is_summary else self.views.get(view_key)

