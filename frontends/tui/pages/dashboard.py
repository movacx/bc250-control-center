"""Dashboard: the live telemetry the desktop shows first."""

from __future__ import annotations

from ..content import Field, Gap, Heading, Meter, Note, number, size
from ..i18n import tr
from .base import (
    Page,
    load_meter,
    metric_blocks,
    temperature_meter,
    trend,
)


def _safe(call):
    try:
        return call()
    except Exception:
        return None


def memory_meter(label: str, used: object, total: object) -> Meter:
    try:
        fraction = float(used) / float(total)
    except (TypeError, ValueError, ZeroDivisionError):
        return Meter(label, None, "--")
    tone = "bad" if fraction >= 0.95 else "warn" if fraction >= 0.85 else "ok"
    return Meter(label, fraction, f"{size(used)} / {size(total)}", tone)


class DashboardPage(Page):
    key = "dashboard"
    title = "Dashboard"
    interval = 3.0

    def load(self, ctx):
        service = ctx.service
        return {
            "daemon": _safe(service.estado_bc250_daemon),
            "fans": _safe(service.estado_fans_bc250),
        }

    def build(self, ctx, data, tab, ui):
        blocks = metric_blocks(ctx)
        gpu, cpu, memory, sensors, power = (
            blocks["gpu"], blocks["cpu"], blocks["memory"], blocks["sensors"], blocks["power"],
        )
        if not ctx.metrics:
            return [Note(ctx.metrics_error or tr("Waiting for data…"), "bad" if ctx.metrics_error else "dim")]
        busy = gpu.get("usage_percent") if gpu.get("usage_percent") is not None else gpu.get("compute_busy_percent")
        out = [
            Heading(tr("GPU")),
            load_meter(tr("Usage"), busy),
            Field(tr("Frequency"), number(gpu.get("frequency_mhz"), "MHz")),
            temperature_meter(tr("Temperature"), gpu.get("temperature_c")),
            Field(tr("Voltage"), number(gpu.get("voltage_mv"), "mV")),
            Field(tr("Power"), number(power.get("value_w", gpu.get("power_w")), "W", 1)),
            memory_meter("VRAM", gpu.get("vram_used"), gpu.get("vram_total")),
            memory_meter("GTT", gpu.get("gtt_used"), gpu.get("gtt_total")),
            trend(ctx, tr("Frequency"), "gpu_clock", "MHz"),
            trend(ctx, tr("Temperature"), "gpu_temp", "°C", "warn"),
            Gap(),
            Heading(tr("CPU")),
            load_meter(tr("Usage"), cpu.get("usage_percent")),
            Field(tr("Frequency"), number(cpu.get("frequency_mhz"), "MHz")),
            temperature_meter(tr("Temperature"), cpu.get("temperature_c")),
            trend(ctx, tr("Usage"), "cpu_load", "%"),
            Gap(),
            Heading(tr("Memory")),
            load_meter("RAM", memory.get("usage_percent")),
            memory_meter("Swap", memory.get("swap_used"), memory.get("swap_total")),
            Gap(),
            Heading(tr("Telemetry")),
            temperature_meter("VRM", sensors.get("vrm_temperature_c")),
            temperature_meter(tr("Board"), sensors.get("board_temperature_c")),
            temperature_meter("NVMe", sensors.get("nvme_temperature_c")),
        ]
        daemon = (data or {}).get("daemon") or {}
        if daemon:
            out += [
                Gap(),
                Heading(tr("GPU governor")),
                Field(tr("Service"), str(daemon.get("service_active", "--")),
                      "ok" if daemon.get("service_active") == "active" else "warn"),
                Field(tr("Range"), f"{daemon.get('current_min', '--')}–{daemon.get('current_max', '--')} MHz"),
            ]
        fans = ((data or {}).get("fans") or {}).get("sensores", {}).get("fans") or []
        for fan in fans:
            if isinstance(fan, dict) and fan.get("rpm"):
                out.append(Field(str(fan.get("label") or "Fan"), number(fan.get("rpm"), "RPM")))
        return out
