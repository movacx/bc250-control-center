"""CPU / SMU: profiles, live scale test, boot persistence and core unlock."""

from __future__ import annotations

from bc250cc.application.system.inline_terminal import make_runner

from ..content import Choice, Field, Gap, Heading, Meter, Note, Track, number, percent
from ..i18n import tr
from .base import Page, guarded, load_meter, metric_blocks, temperature_meter, trend
from .dashboard import _safe

# Mirrors cpu_command_policy.validate_detection_target, which stays the authority.
FREQUENCY_MHZ = (3100, 4200)
VID_MV = (950, 1325)
TEMPERATURE_C = (70, 90)
SCALE = (-50, 0)
PROFILES = (
    ("Mid board", 3550, 1050, 90),
    ("Balanced", 3700, 1150, 90),
    ("Mid point", 3850, 1150, 90),
    ("Maximum", 4000, 1275, 90),
)


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
        mine = ctx.state(self.key)
        target = mine.setdefault("target", {"freq": 3550, "vid": 1050, "temp": 90, "scale": -34, "manual": False,
                                            "force_mask": False})
        persistent = (data or {}).get("persistent") or {}
        unlock = (data or {}).get("unlock") or {}
        run_shell = make_runner(tr)

        out = [Heading(tr("Live core monitor")),
               load_meter(tr("CPU usage"), cpu.get("usage_percent")),
               Field(tr("Frequency"), number(cpu.get("frequency_mhz"), "MHz")),
               temperature_meter(tr("Temperature"), cpu.get("temperature_c")),
               Field(tr("Topology"), f"{cpu.get('physical_cores', '--')} / {cpu.get('logical_cores', '--')}"),
               trend(ctx, tr("Frequency"), "cpu_clock", "MHz")]
        clocks = cpu.get("per_core_frequency_mhz") or []
        for index, value in enumerate((cpu.get("per_core_percent") or [])[:8]):
            freq = clocks[index] if index < len(clocks) else None
            out.append(Meter(f"N{index + 1}", percent(value), f"{number(freq, 'MHz')}  {number(value, '%')}"))

        # -- operating profile
        out += [Gap(), Heading(tr("Operating profile"))]
        for name, freq, vid, limit in PROFILES:
            def pick(ui_, freq=freq, vid=vid, limit=limit):
                target.update(freq=freq, vid=vid, temp=limit)

            same = (target["freq"], target["vid"], target["temp"]) == (freq, vid, limit)
            out.append(Choice(f"({'x' if same else ' '}) {tr(name)}", pick, f"{freq} MHz · {vid} mV",
                              tone="ok" if same else ""))

        def number_choice(label, key, low, high, step, unit):
            def adjust(ui_, direction):
                target[key] = max(low, min(high, target[key] + step * direction))

            def edit(ui_):
                value = ui_.ask_int(f"{label} ({unit})", low, high, target[key])
                if value is not None:
                    target[key] = value

            return Choice(label, edit, f"◀ {target[key]} {unit} ▶" if ui.unicode else f"< {target[key]} {unit} >", adjust=adjust)

        out += [Track(tr("Frequency"), FREQUENCY_MHZ[0], FREQUENCY_MHZ[1], FREQUENCY_MHZ[0], target["freq"],
                      f"{target['freq']} MHz", "warn" if target["freq"] > 3850 else "accent"),
                number_choice(tr("Frequency"), "freq", *FREQUENCY_MHZ, 50, "MHz"),
                number_choice("VID", "vid", *VID_MV, 5, "mV"),
                number_choice(tr("Temperature"), "temp", *TEMPERATURE_C, 1, "°C")]

        # -- live scale test
        def toggle_manual(ui_):
            target["manual"] = not target["manual"]

        out += [Gap(), Heading(tr("Live scale test")),
                Choice(f"[{'x' if target['manual'] else ' '}] {tr('Use manual scale')}", toggle_manual)]
        if target["manual"]:
            out.append(number_choice(tr("Scale"), "scale", *SCALE, 1, "scale"))

        def apply(ui_):
            f, v, t, scale = target["freq"], target["vid"], target["temp"], target["scale"]
            if target["manual"]:
                text = f"{tr('Apply temporary OC + manual scale')}: {f} MHz · {t} °C · {scale}"
                if ui_.confirm(text, danger=True):
                    guarded(ui_, tr("CPU / SMU"), lambda: run_shell(service.comando_cpu_oc_manual_verificado_embebido(
                        f, scale, t, confirm_manual=True), tr("CPU / SMU")))
            elif ui_.confirm(f"{tr('Apply configuration + automatic scale')}: {f} MHz · {v} mV · {t} °C", danger=True):
                guarded(ui_, tr("CPU / SMU"), lambda: service.ejecutar_cpu_oc_temporal(f, v, t))

        out.append(Choice(tr("Apply temporary OC + manual scale") if target["manual"]
                          else tr("Apply configuration + automatic scale"), apply, tone="accent"))

        # -- boot persistence
        def save_boot(ui_):
            if ui_.confirm(tr("Enable / update CPU persistence"), danger=True):
                guarded(ui_, tr("Boot persistence"), lambda: run_shell(
                    service.comando_cpu_oc_persistente_embebido(), tr("Boot persistence")))

        def review(ui_):
            ok, result = ui_.run(tr("Boot persistence"), service.estado_cpu_oc_persistente)
            if ok and isinstance(result, dict):
                ui_.show_text(tr("Boot persistence"), "\n".join(f"{k}: {v}" for k, v in result.items()))

        def remove(ui_):
            if ui_.confirm(tr("Disable CPU boot service"), danger=True):
                guarded(ui_, tr("Boot persistence"), lambda: run_shell(
                    service.comando_cpu_oc_desactivar_persistente_embebido(), tr("Boot persistence")))

        out += [Gap(), Heading(tr("Boot persistence")),
                Field(tr("State"), str(persistent.get("ui_state") or "--"),
                      "ok" if persistent.get("applied") else ""),
                Field(tr("Detail"), str(persistent.get("ui_detail") or "--")),
                Choice(tr("Save for boot"), save_boot), Choice(tr("Review persistence"), review),
                Choice(tr("Remove from boot"), remove, tone="warn")]

        # -- core unlock
        def toggle_mask(ui_):
            target["force_mask"] = not target["force_mask"]

        def unlock_cores(ui_):
            if ui_.confirm(tr("Unlock CPU cores and restart"), danger=True):
                guarded(ui_, tr("Unlock cores"), lambda: run_shell(
                    service.comando_desbloquear_nucleos_cpu(ignore_core_mask=target["force_mask"]), tr("Unlock cores")))

        out += [Gap(), Heading(tr("Unlock cores")),
                Field(tr("CPU cores"), f"{unlock.get('physical_cores', '--')} / {unlock.get('logical_cpus', '--')}",
                      "ok" if unlock.get("unlocked") else ""),
                Choice(f"[{'x' if target['force_mask'] else ' '}] {tr('Force a non-standard core mask (-f)')}", toggle_mask),
                Choice(tr("Unlock CPU cores and restart"), unlock_cores, tone="bad")]

        def install(call, label):
            def handler(ui_):
                if ui_.confirm(tr("Install {name}").format(name=label)):
                    guarded(ui_, label, call)
            return handler

        out += [Gap(), Heading(tr("Components")),
                Choice(tr("Install {name}").format(name="bc250_smu_oc"), install(service.instalar_cpu_oc, "bc250_smu_oc")),
                Choice(tr("Prepare bc250-core-unlock"), install(service.instalar_core_unlock, "bc250-core-unlock")),
                Choice(tr("Install UMR"), install(service.instalar_umr, "UMR"))]
        return out
