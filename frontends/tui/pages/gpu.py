"""GPU governor: clocks, the allowed range and the service that holds it."""

from __future__ import annotations

from ..content import Choice, Field, Gap, Heading, Note, number
from ..i18n import tr
from .base import (
    Page,
    guarded,
    load_meter,
    metric_blocks,
    temperature_meter,
    trend,
    waiting,
)
from .dashboard import memory_meter


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class GpuPage(Page):
    key = "gpu"
    title = "GPU"
    interval = 3.0

    def load(self, ctx):
        return ctx.service.estado_bc250()

    def build(self, ctx, data, tab, ui):
        state = data if isinstance(data, dict) else {}
        gpu = metric_blocks(ctx)["gpu"]
        service = ctx.service
        if state.get("operation_message"):
            pass
        low, high = _int(state.get("allowed_min"), 500), _int(state.get("allowed_max"), 2000)
        current_min, current_max = _int(state.get("current_min"), low), _int(state.get("current_max"), high)

        out = [
            Heading(tr("GPU")),
            load_meter(tr("Usage"), gpu.get("usage_percent") if gpu.get("usage_percent") is not None else gpu.get("compute_busy_percent")),
            Field(tr("Frequency"), number(state.get("sclk_actual", gpu.get("frequency_mhz")), "MHz")),
            Field(tr("Memory"), number(state.get("mclk_actual", gpu.get("memory_frequency_mhz")), "MHz")),
            Field(tr("Voltage"), number(state.get("voltaje_actual", gpu.get("voltage_mv")), "mV")),
            temperature_meter(tr("Temperature"), gpu.get("temperature_c")),
            memory_meter("VRAM", gpu.get("vram_used"), gpu.get("vram_total")),
            trend(ctx, tr("Frequency"), "gpu_clock", "MHz"),
            trend(ctx, tr("Voltage"), "gpu_volt", "mV", "warn"),
            Gap(),
            Heading(tr("GPU governor")),
            Field(tr("Backend"), str(state.get("governor_backend") or tr("Not detected"))),
            Field(tr("Service"), f"{state.get('service_active', '--')} / {state.get('service_enabled', '--')}",
                  "ok" if state.get("service_active") == "active" else "warn"),
            Field(tr("Range"), f"{current_min}–{current_max} MHz"),
            Field(tr("Allowed D-Bus range"), f"{low}–{high} MHz"),
        ]
        if state.get("telemetry_warning"):
            out.append(Note(str(state["telemetry_warning"]), "warn"))
        if not data:
            waiting_block = waiting(ctx, self.key)
            if waiting_block:
                out += waiting_block

        def apply_range(ui_):
            minimum = ui_.ask_int(tr("Minimum") + " (MHz)", low, high, current_min)
            if minimum is None:
                return
            maximum = ui_.ask_int(tr("Maximum") + " (MHz)", minimum, high, max(current_max, minimum))
            if maximum is None:
                return
            if ui_.confirm(f"{tr('Apply range')}: {minimum}–{maximum} MHz"):
                guarded(ui_, tr("Apply"), lambda: service.aplicar_rango_bc250(minimum, maximum))

        def fix_frequency(ui_):
            frequency = ui_.ask_int(tr("Frequency") + " (MHz)", low, high, current_max)
            if frequency is not None and ui_.confirm(f"{tr('Fix frequency')}: {frequency} MHz"):
                guarded(ui_, tr("Apply"), lambda: service.fijar_frecuencia_bc250(frequency))

        def save_boot(ui_):
            if ui_.confirm(tr("Save active range for startup")):
                guarded(ui_, tr("Save active range for startup"), service.guardar_rango_gpu_arranque)

        def control(action, label):
            def handler(ui_):
                if ui_.confirm(label):
                    guarded(ui_, label, lambda: service.controlar_governor(action))
            return handler

        out += [
            Gap(),
            Heading(tr("Actions")),
            Choice(tr("Apply range"), apply_range),
            Choice(tr("Fix frequency"), fix_frequency),
            Choice(tr("Save active range for startup"), save_boot),
            Choice(tr("Start governor"), control("activar", tr("Start governor"))),
            Choice(tr("Restart service"), control("reiniciar", tr("Restart service"))),
            Choice(tr("Stop governor"), control("desactivar", tr("Stop governor")), tone="warn"),
        ]
        return out
