"""The sensor list of Performance, read beside the pages that change the hardware."""

from __future__ import annotations

from bc250cc.application.system.sensors import (
    GROUP_CPU,
    GROUP_GDDR6,
    GROUP_GPU,
    GROUP_VRM,
)
from frontends.desktop.core.performance_model import group_title, sensor_label
from frontends.desktop.core.sensor_log import format_sensor_value

from ..content import Note, Panel, Side, Spans, cell_width, clip, heat_tone, pad
from ..i18n import tr

CPU_FIRST = (GROUP_CPU, GROUP_VRM)
GPU_FIRST = (GROUP_GPU, GROUP_GDDR6, GROUP_VRM)
VALUE = 11  # a column of values
FULL = 26 + 4 * VALUE  # the list with its minimum and average too


def sensor_side(ctx, ui, head: list[Panel], first: tuple[str, ...], least_left: int = 0):
    """``head`` and, under it, every sensor (``first`` groups on top); None when the screen has no room for both."""
    from ..layout import side_widths
    from .performance import PerformancePage

    widths = side_widths(ui._content_box()[1], least_left) if hasattr(ui, "_content_box") else None
    if widths is None:
        return None
    recorder = PerformancePage.recorder(ctx)
    recorder.sensors = True
    width, log = widths[1], recorder.log
    entries = [entry for entry in (log.entries[key] for key in log.order) if entry.active]
    entries.sort(key=lambda entry: first.index(entry.reading.group) if entry.reading.group in first else len(first))
    if not entries:
        return Side([*head, Panel(tr("Sensors"), [Note(tr("Waiting for first sample"), "dim")])], [], least_left)
    full = width >= FULL
    names = width - VALUE * (4 if full else 2)

    def show(entry, value):
        return (format_sensor_value(value, entry.reading.unit) if value is not None else "--").rjust(VALUE)

    titles = ("Value", "Min", "Avg", "Max") if full else ("Value", "Max")
    heading = Panel(tr("Sensors"), [
        Spans([[(pad(tr("Sensor"), names), "dim"), ("".join(tr(title).rjust(VALUE) for title in titles), "dim")]])], badge=str(len(entries)))
    lines, group = [], None
    for entry in entries:
        reading = entry.reading
        if (reading.group, reading.device) != group:
            if group is not None:
                lines.append([("", "")])
            group = (reading.group, reading.device)
            title = clip(group_title(reading.group, reading), width - 2)
            rule = "─" if getattr(ui, "unicode", True) else "-"
            lines.append([(title, "!"), (" " + rule * (width - cell_width(title) - 1), "edge")])
        tone = heat_tone(entry.value) if reading.unit == "°C" else ""
        rest = (entry.minimum, entry.average, entry.maximum) if full else (entry.maximum,)
        lines.append([(pad(clip(sensor_label(reading), names - 1), names), "dim"),
                      (show(entry, entry.value), tone if tone in ("warn", "bad") else ""),
                      ("".join(show(entry, value) for value in rest), "dim")])
    return Side([*head, heading], [Spans(lines)], least_left)


def beside(ctx, ui, work: list, head: list[Panel], first: tuple[str, ...], least_left: int = 0) -> list:
    """A page: ``work`` with its sensors at the right, or ``work`` and ``head`` alone on a narrow screen."""
    side = sensor_side(ctx, ui, head, first, least_left)
    return [*work, *head] if side is None else [*work, side]
