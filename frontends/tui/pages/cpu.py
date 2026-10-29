"""CPU / SMU, laid out as the desktop's: profiles and scale test on the left, live state on the right."""

from __future__ import annotations

from frontends.desktop.core.cpu_refresh_presenter import (
    present_cpu_persistence,
    present_cpu_tuning,
)

from ..content import (
    Buttons,
    Choice,
    Field,
    Meter,
    Note,
    Panel,
    Split,
    Tile,
    Tiles,
    load_tone,
    number,
    percent,
)
from ..i18n import tr, tr_format
from .base import Page, check, guarded, metric_blocks, stepper
from .dashboard import _safe

# Mirrors cpu_command_policy.validate_detection_target, which stays the authority.
FREQUENCY_MHZ = (3100, 4200)
VID_MV = (950, 1325)
TEMPERATURE_C = (70, 90)
SCALE = (-50, 0)
PROFILES = (  # the desktop's shipped cards (DEFAULT_CPU_PROFILES)
    {"key": "board_average", "name": "Average board", "frequency": 3550, "vid": 1050, "temperature": 90},
    {"key": "mid_point", "name": "Mid point", "frequency": 3850, "vid": 1150, "temperature": 90},
    {"key": "safe_maximum", "name": "Safe maximum", "frequency": 4000, "vid": 1275, "temperature": 90},
)
GUIDE_URL = "https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script"
OVERVIEW = (("model_name", "Processor"), ("topology", "Topology"), ("microcode", "Microcode"),
            ("features", "Instruction features"), ("architecture", "Architecture"),
            ("platform_process", "Platform / process"), ("cache", "Cache hierarchy"))


def said(text) -> str:
    """A presenter's CpuText in the interface language."""
    return text.template if text.literal else tr_format(text.template, **dict(text.values)) if text.values \
        else tr(text.template)


class CpuPage(Page):
    key = "cpu"
    title = "CPU / SMU"
    interval = 5.0

    def load(self, ctx):
        service = ctx.service
        return {
            "persistent": _safe(service.estado_cpu_oc_persistente),
            "unlock": _safe(service.estado_desbloqueo_nucleos_cpu),
            "detection": _safe(service.estado_resultado_deteccion_cpu),
            "scale": _safe(service.estado_prueba_escala_cpu),
            "quick": _safe(service.estado_cpu_qam_runtime),
        }

    def build(self, ctx, data, tab, ui):
        service, data = ctx.service, data or {}
        mine = ctx.state(self.key)
        profiles = mine.setdefault("profiles", [dict(item) for item in PROFILES])
        target = mine.setdefault("target", {"profile": 0, "scale": -34, "manual": False, "force_mask": False})
        chosen = profiles[target["profile"]]
        persistent, unlock = data.get("persistent") or {}, data.get("unlock") or {}
        processor = unlock.get("processor") or {}
        cpu = metric_blocks(ctx)["cpu"]

        # -- operating profile: the three cards are the inputs
        def edit(ui_, index):
            profile = dict(profiles[index])
            name = ui_.ask_text(tr("Profile name"), tr(profile["name"]))
            if name is None:
                return
            for key, label, (low, high) in (("frequency", "Frequency", FREQUENCY_MHZ), ("vid", "VID", VID_MV),
                                            ("temperature", "Temperature cap", TEMPERATURE_C)):
                value = ui_.ask_int(tr(label), low, high, profile[key])
                if value is None:
                    return
                profile[key] = value
            profiles[index] = {**profile, "name": name.strip() or profile["name"]}

        def export(ui_):
            payload = [{key: item[key] for key in ("key", "name", "frequency", "vid", "temperature")} for item in profiles]
            guarded(ui_, tr("Export to Decky"), lambda: service.exportar_perfiles_cpu_decky(payload))

        cards = Tiles([Tile(tr(item["name"]), f"{item['frequency']} MHz", f"{item['vid']} mV · {item['temperature']} °C",
                            handler=lambda ui_, i=index: target.update(profile=i), active=index == target["profile"],
                            edit=lambda ui_, i=index: edit(ui_, i), edit_label=tr("Edit")) for index, item in enumerate(profiles)], minimum=20)
        profile_panel = Panel(tr("Operating profile"), [cards], action=Choice(tr("Export to Decky"), export))

        # -- live scale test, then the one apply button
        def apply(ui_):
            f, v, t, scale = chosen["frequency"], chosen["vid"], chosen["temperature"], target["scale"]
            if target["manual"]:
                if ui_.confirm(f"{tr('Apply temporary OC + manual scale')}: {f} MHz · {t} °C · {scale}", danger=True):
                    guarded(ui_, tr("CPU / SMU"), lambda: ui_.shell(service.comando_cpu_oc_manual_verificado_embebido(
                        f, scale, t, confirm_manual=True)))
                    mine["last"] = f
            elif ui_.confirm(f"{tr('Apply configuration + automatic scale')}: {f} MHz · {v} mV · {t} °C", danger=True):
                guarded(ui_, tr("CPU / SMU"), lambda: service.ejecutar_cpu_oc_temporal(f, v, t))
                mine["last"] = f

        scale_panel = Panel(tr("Live scale test"), [
            check(tr("Use manual scale"), target["manual"], lambda ui_: target.update(manual=not target["manual"])),
            stepper(tr("Scale"), target, "scale", *SCALE, 1, "scale", enabled=target["manual"])])
        apply_button = Buttons([Choice(tr("Apply temporary OC + manual scale") if target["manual"]
                                       else tr("Apply configuration + automatic scale"), apply, tone="primary")])

        overview = [Field(tr(label), str(processor.get(key) or tr("Not exposed"))) for key, label in OVERVIEW]
        overview.append(Field(tr("Total CPU load"), number(processor.get("total_usage_percent", cpu.get("usage_percent")), "%", 0)))
        overview_panel = Panel(tr("Processor overview"), [Split(overview[:4], overview[4:], ratio=0.5, minimum=90)])

        # -- runtime status: what this session uses and what the next boot does
        enabled = str(persistent.get("enabled") or "").lower() == "enabled"
        stored = present_cpu_persistence(persistent, {} if persistent else {"persistent": "--"})
        tuning = present_cpu_tuning(persistent, data.get("detection") or {}, data.get("scale") or {}, data.get("quick"),
                                    last_applied_frequency=mine.get("last"), scale_override_enabled=target["manual"])
        last = mine.get("last")
        live = f"{number(cpu.get('temperature_c'), '°C', 0)} | {number(cpu.get('frequency_mhz'), 'MHz')}"
        runtime = Panel(tr("Runtime status"), [Tiles([
            Tile(tr("Boot persistence"), said(stored.status_value), tone="ok" if enabled else ""),
            Tile(tr("Last operation"), f"{last} MHz" if last else tr("None")),
            Tile(tr("Applied tuning"), said(tuning.applied_value)),
            Tile(tr("Detection reference"), said(tuning.detection_value)),
            Tile(tr("Active scale"), said(tuning.live_value)),
            Tile(tr("Live CPU status"), live)], minimum=20)],
            badge=tr("Persistence" if enabled else "Temporary"), badge_tone="accent" if enabled else "ok")

        # -- live cores: eight slots, the ones the board hides read "Hidden"
        cores = {item.get("index"): item for item in unlock.get("cores") or [] if isinstance(item, dict)}
        if not cores:  # the unlock helper has not answered yet: the metrics poller's per-thread reading
            clocks = cpu.get("per_core_frequency_mhz") or []
            cores = {index: {"frequency_mhz": clocks[index] if index < len(clocks) else None, "usage_percent": value}
                     for index, value in enumerate((cpu.get("per_core_percent") or [])[:6])}
        slots = []
        for index in range(8):
            item = cores.get(index)
            if item is None:
                slots.append(Field(f"N{index + 1}", tr("Hidden"), "dim"))
                continue
            usage, clock = item.get("usage_percent"), item.get("frequency_mhz")
            slots.append(Meter(f"N{index + 1}", percent(usage),
                               f"{clock / 1000:.2f} GHz {number(usage, '%', 0):>5}" if clock else number(usage, "%", 0),
                               load_tone(usage)))
        shape = tr_format("{cores} cores / {threads} threads", cores=unlock.get("physical_cores") or "--",
                          threads=unlock.get("logical_cpus") or "--")
        cores_panel = Panel(tr("Live core monitor"), [Split(slots[:4], slots[4:], ratio=0.5, minimum=64)],
                            badge=shape, badge_tone="accent")

        # -- boot persistence
        def save_boot(ui_):
            if ui_.confirm(tr("Enable / update CPU persistence"), danger=True):
                guarded(ui_, tr("Boot persistence"), lambda: ui_.shell(service.comando_cpu_oc_persistente_embebido()))

        def review(ui_):
            ok, result = ui_.run(tr("Boot persistence"), service.estado_cpu_oc_persistente)
            if ok and isinstance(result, dict):
                ui_.show_text(tr("Boot persistence"), "\n".join(f"{k}: {v}" for k, v in result.items()))

        def remove(ui_):
            if ui_.confirm(tr("Disable CPU boot service"), danger=True):
                guarded(ui_, tr("Boot persistence"), lambda: ui_.shell(
                    service.comando_cpu_oc_desactivar_persistente_embebido()))

        persistence = Panel(tr("Boot persistence"), [Buttons([
            Choice(tr("Save for startup"), save_boot), Choice(tr("Review persistence"), review),
            Choice(tr("Remove from boot"), remove, tone="bad", enabled=enabled)])])

        # -- danger zone: the hidden-core unlock lasts until a cold start and needs a restart
        def unlock_cores(ui_):
            if ui_.confirm(tr("Unlock CPU cores and restart"), danger=True):
                guarded(ui_, tr("Unlock cores"), lambda: ui_.shell(
                    service.comando_desbloquear_nucleos_cpu(ignore_core_mask=target["force_mask"])))

        def guide(ui_):
            ui_.show_text(tr("Firmware persistence guide"), tr(
                "The core unlock does not last: it is applied after the system starts, so a full power-off or a cold "
                "start brings the board back to 6 cores. If the board is ever unstable with 8 cores, shut it down "
                "completely and start it again: it comes back to 6. If it is stable and you want 8 cores at every "
                "start, the permanent way is the firmware, through the external UEFI menu workflow. The guide opens in "
                "your browser; this application does not flash firmware, change NVRAM, or reboot the system.")
                + f"\n\n{GUIDE_URL}")

        danger = Panel(tr("DANGER ZONE"), [
            Note(tr("Unlock hidden CPU cores"), "bad"),
            check(tr("Force a non-standard core mask (-f)"), target["force_mask"],
                  lambda ui_: target.update(force_mask=not target["force_mask"])),
            Choice(tr("Firmware persistence guide") + " ›", guide),
            Buttons([Choice(tr("Unlock cores and restart"), unlock_cores, tone="bad",
                            enabled=not unlock.get("unlocked"))])], danger=True)

        left = [profile_panel, scale_panel, apply_button, overview_panel]
        return [Split(left, [runtime, cores_panel, persistence, danger], ratio=0.55)]
