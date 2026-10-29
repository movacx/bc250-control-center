"""CPU: per-core telemetry and the same tuning entry points as the desktop."""

from __future__ import annotations

from bc250cc.domain.cpu.limits import VID_LIMIT_MV

from ..content import Choice, Field, Gap, Heading, Meter, Note, number, percent
from ..i18n import tr
from .base import Page, guarded, load_meter, metric_blocks, temperature_meter, trend
from .dashboard import _safe

# Mirrors cpu_command_policy.validate_detection_target, which stays the authority.
FREQUENCY_MHZ = (3100, 4200)
VID_MV = (950, 1325)
TEMPERATURE_C = (70, 90)


class CpuPage(Page):
    key = "cpu"
    title = "CPU"
    interval = 5.0

    def load(self, ctx):
        service = ctx.service
        return {
            "persistent": _safe(service.estado_cpu_oc_persistente),
            "unlock": _safe(service.estado_desbloqueo_nucleos_cpu),
        }

    def build(self, ctx, data, tab, ui):
        cpu = metric_blocks(ctx)["cpu"]
        if not cpu:
            return [Note(ctx.metrics_error or tr("Waiting for data…"), "dim")]
        service = ctx.service
        out = [
            Heading(tr("CPU")),
            load_meter(tr("Usage"), cpu.get("usage_percent")),
            Field(tr("Frequency"), number(cpu.get("frequency_mhz"), "MHz")),
            temperature_meter(tr("Temperature"), cpu.get("temperature_c")),
            Field(tr("CPU cores"), f"{cpu.get('physical_cores', '--')} / {cpu.get('logical_cores', '--')}"),
        ]
        load = cpu.get("load_average") or []
        if load:
            out.append(Field(tr("Load average"), " ".join(f"{value:.2f}" for value in load)))
        out += [trend(ctx, tr("Usage"), "cpu_load", "%"), trend(ctx, tr("Frequency"), "cpu_clock", "MHz"), Gap()]
        clocks = cpu.get("per_core_frequency_mhz") or []
        for index, value in enumerate(cpu.get("per_core_percent") or []):
            freq = clocks[index] if index < len(clocks) else None
            out.append(Meter(f"#{index}", percent(value), f"{number(value, '%')}  {number(freq, 'MHz')}"))

        persistent = (data or {}).get("persistent") or {}
        unlock = (data or {}).get("unlock") or {}
        out += [Gap(), Heading(tr("CPU / SMU"))]
        if persistent:
            out.append(Field(tr("Boot persistence"), str(persistent.get("ui_state") or "--")))
        if unlock:
            out.append(Field(
                tr("Unlock cores"),
                f"{unlock.get('physical_cores', '--')} / {unlock.get('logical_cpus', '--')}",
                "ok" if unlock.get("unlocked") else "",
            ))

        def temporary(ui_):
            frequency = ui_.ask_int(tr("Frequency") + " (MHz)", *FREQUENCY_MHZ, 3500)
            if frequency is None:
                return
            vid = ui_.ask_int("VID (mV)", VID_MV[0], min(VID_MV[1], int(VID_LIMIT_MV)), 1000)
            if vid is None:
                return
            limit = ui_.ask_int(tr("Temperature") + " (°C)", *TEMPERATURE_C, 90)
            if limit is None:
                return
            if ui_.confirm(
                f"{tr('Temporary CPU overclock')}: {frequency} MHz · {vid} mV · {limit} °C", danger=True,
            ):
                guarded(ui_, tr("CPU / SMU"), lambda: service.ejecutar_cpu_oc_temporal(frequency, vid, limit))

        def install(call, label):
            def handler(ui_):
                if ui_.confirm(tr("Install {name}").format(name=label)):
                    guarded(ui_, label, call)
            return handler

        out += [
            Gap(),
            Heading(tr("Actions")),
            Choice(tr("Temporary CPU overclock"), temporary, tone="warn"),
            Choice(tr("Install {name}").format(name="bc250_smu_oc"), install(service.instalar_cpu_oc, "bc250_smu_oc")),
            Choice(tr("Prepare bc250-core-unlock"), install(service.instalar_core_unlock, "bc250-core-unlock")),
            Choice(tr("Install UMR"), install(service.instalar_umr, "UMR")),
        ]
        return out
