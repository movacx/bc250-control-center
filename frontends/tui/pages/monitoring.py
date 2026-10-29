"""Monitoring: the recorded history of every sensor, as trends."""

from __future__ import annotations

from ..content import Field, Gap, Heading, Note, number
from ..i18n import tr
from .base import Page, metric_blocks, trend

SERIES = (
    ("GPU", (("gpu_clock", "Frequency", "MHz"), ("gpu_load", "Usage", "%"), ("gpu_temp", "Temperature", "°C"),
             ("gpu_volt", "Voltage", "mV"), ("gpu_power", "Power", "W"))),
    ("CPU", (("cpu_clock", "Frequency", "MHz"), ("cpu_load", "Usage", "%"), ("cpu_temp", "Temperature", "°C"))),
    ("Memory", (("ram", "Memory", "%"),)),
    ("Telemetry", (("vrm_temp", "VRM", "°C"),)),
)


class MonitoringPage(Page):
    key = "performance"
    title = "Performance"
    loads = False

    def build(self, ctx, data, tab, ui):
        if not ctx.metrics:
            return [Note(ctx.metrics_error or tr("Waiting for data…"), "dim")]
        out = []
        for group, rows in SERIES:
            out.append(Heading(tr(group)))
            for name, label, unit in rows:
                out.append(trend(ctx, tr(label), name, unit))
            out.append(Gap())
        network = metric_blocks(ctx)["network"]
        if network:
            out.append(Field(tr("Network"), f"↓ {number(network.get('download_bps'), 'B/s')}  ↑ {number(network.get('upload_bps'), 'B/s')}"))
        return out
