"""CPU / SMU terminal forms: tuning, monitoring, boot persistence and core recovery."""

from __future__ import annotations

from bc250cc.application.cpu.core_unlock import (
    CORE_MASK_BOOT_RISK,
    CORE_MASK_PICK_HINT,
    CORE_MASK_READ_TEXT,
    CORE_MASK_SEEN,
    CORE_MASK_SEEN_TEXT,
    CORE_MASK_STANDARD_TEXT,
    CORE_MASK_STOCK,
    CORE_MASK_WARNINGS,
    IGNORE_CORE_MASK_HINT,
    accepted_mask,
    core_unlock_controls,
    reported_core_mask,
)
from frontends.desktop.core.cpu_refresh_presenter import (
    present_cpu_persistence,
    present_cpu_tuning,
)

from ..content import (
    Buttons,
    Choice,
    Field,
    Gauges,
    Info,
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
from .base import (
    Page,
    check,
    guarded,
    load_meter,
    metric_blocks,
    stepper,
    temperature_meter,
    trend,
)
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


def valid_profile(saved, shipped: dict) -> dict:
    """A saved profile, or the shipped one when anything in it is out of range."""
    if not isinstance(saved, dict):
        return dict(shipped)
    for key, (low, high) in (("frequency", FREQUENCY_MHZ), ("vid", VID_MV), ("temperature", TEMPERATURE_C)):
        if not isinstance(saved.get(key), int) or not low <= saved[key] <= high:
            return dict(shipped)
    return {**shipped, **{key: saved[key] for key in ("frequency", "vid", "temperature")}, "name": str(saved.get("name") or shipped["name"])}


def mask_text(mask: int, board_mask: int | None) -> str:
    if mask == CORE_MASK_STOCK:
        return tr(CORE_MASK_STANDARD_TEXT)
    text = tr_format(CORE_MASK_READ_TEXT if mask == board_mask else CORE_MASK_SEEN_TEXT, mask=f"0x{mask:02X}")
    warning = CORE_MASK_WARNINGS.get(mask)
    return f"{text} ({tr(warning)})" if warning else text


class CpuPage(Page):
    key = "cpu"
    title = "CPU / SMU"
    interval = 5.0

    def tabs(self, ctx):
        return [(key, tr(label)) for key, label in (("tuning", "Hardware control"), ("monitor", "Sensors"),
                ("cores", "Unlock cores"))]

    def load(self, ctx):
        service = ctx.service
        return {
            "persistent": _safe(service.estado_cpu_oc_persistente),
            "unlock": _safe(service.estado_desbloqueo_nucleos_cpu),
            "detection": _safe(service.estado_resultado_deteccion_cpu),
            "scale": _safe(service.estado_prueba_escala_cpu),
            "quick": _safe(service.estado_cpu_qam_runtime),
            "config": _safe(ctx.settings.read_local_config) if ctx.settings is not None else {},
        }

    def build(self, ctx, data, tab, ui):
        service, data = ctx.service, data or {}
        mine = ctx.state(self.key)
        if "profiles" not in mine:
            kept = {item.get("key"): item for item in (data.get("config") or {}).get("tui_cpu_profiles") or () if isinstance(item, dict)}
            mine["profiles"] = [valid_profile(kept.get(item["key"]), item) for item in PROFILES]
        profiles = mine["profiles"]
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
            if ctx.settings is not None:
                ctx.settings.save_local_config({"tui_cpu_profiles": [dict(item) for item in profiles]})

        def export(ui_):
            payload = [{key: item[key] for key in ("key", "name", "frequency", "vid", "temperature")} for item in profiles]
            guarded(ui_, tr("Export to Decky"), lambda: service.exportar_perfiles_cpu_decky(payload))

        def keep() -> None:
            if ctx.settings is not None:
                ctx.settings.save_local_config({"tui_cpu_profiles": [dict(item) for item in profiles]})

        def pick_profile(ui_):
            index = ui_.choose(tr("Operating profile"), [(i, f"{tr(item['name'])}   {item['frequency']} MHz · {item['vid']} mV")
                                                         for i, item in enumerate(profiles)])
            if index is not None:
                target.update(profile=index)

        def value_row(key, label, unit, low, high, by):
            def adjust(ui_, direction):
                chosen[key] = max(low, min(high, chosen[key] + by * direction))
                keep()

            def type_in(ui_):
                value = ui_.ask_int(f"{tr(label)} ({unit})", low, high, chosen[key])
                if value is not None:
                    chosen[key] = value
                    keep()

            return Choice(tr(label), type_in, f"< {chosen[key]} {unit} >", adjust=adjust, id=key, info=Info(tr(
                "This is the voltage limit used by automatic detection. A lower VID asks the detector to use less voltage. It is a detection target, not a fixed voltage saved for boot."))
                if key == "vid" else None)

        cards = [
            Choice(tr("Operating profile"), pick_profile, f"< {tr(chosen['name'])} >", id="profile",
                   adjust=lambda ui_, d: target.update(profile=(target["profile"] + d) % len(profiles)),
                   edit=lambda ui_: edit(ui_, target["profile"])),
            value_row("frequency", "Frequency", "MHz", *FREQUENCY_MHZ, 50),
            value_row("vid", "VID", "mV", *VID_MV, 5),
            value_row("temperature", "Temperature cap", "°C", *TEMPERATURE_C, 1)]

        # -- live scale test, then the one apply button
        def apply(ui_):
            f, v, t, scale = chosen["frequency"], chosen["vid"], chosen["temperature"], target["scale"]
            if target["manual"]:
                if ui_.confirm(f"{tr('Apply temporary OC + manual scale')}: {f} MHz · {t} °C · {scale}", danger=True):
                    if guarded(ui_, tr("CPU / SMU"), lambda: ui_.shell(service.comando_cpu_oc_manual_verificado_embebido(
                            f, scale, t, confirm_manual=True))):
                        mine["last"] = f
            elif ui_.confirm(f"{tr('Apply configuration + automatic scale')}: {f} MHz · {v} mV · {t} °C", danger=True):
                if guarded(ui_, tr("CPU / SMU"), lambda: service.ejecutar_cpu_oc_temporal(f, v, t)):
                    mine["last"] = f

        scale_rows = [
            Choice(tr("Use manual scale"), lambda ui_: target.update(manual=not target["manual"]),
                   f"< {tr('Enabled' if target['manual'] else 'Disabled')} >", adjust=lambda ui_, d: target.update(manual=not target["manual"]),
                   info=Info(tr("Scale is not mV. More negative means less voltage. Test it live first; only then can it be saved for boot."))),
            *([stepper(tr("Scale"), target, "scale", *SCALE, 1, "scale")] if target["manual"] else [])]
        apply_button = Buttons([Choice(tr("Apply temporary OC + manual scale") if target["manual"]
                                       else tr("Apply configuration + automatic scale"), apply, tone="primary"),
                                Choice(tr("Export to Decky"), export, info=Info(tr("Sends these three cards to the Decky Quick Access panel, so in Game Mode you pick the same profiles with the controller. Edit here, export, and Decky shows your names and values.")))])
        profile_panel = Panel(tr("Operating profile"), [*cards, *scale_rows, apply_button])
        clock = cpu.get("frequency_mhz")
        live_panel = Panel(tr("Live"), [
            Meter(tr("Frequency"), percent(float(clock) / FREQUENCY_MHZ[1] * 100) if clock else None, number(clock, "MHz"), ""),
            temperature_meter(tr("Temperature"), cpu.get("temperature_c")),
            load_meter(tr("CPU usage"), cpu.get("usage_percent")),
            trend(ctx, "°C · 2 min", "cpu_temp", "°C")])

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
                slots.append(Meter(f"N{index + 1}", None, tr("Hidden")))
                continue
            usage, clock = item.get("usage_percent"), item.get("frequency_mhz")
            slots.append(Meter(f"N{index + 1}", percent(usage),
                               f"{clock / 1000:.2f} GHz {number(usage, '%', 0):>5}" if clock else number(usage, "%", 0),
                               load_tone(usage)))
        shape = tr_format("{cores} cores / {threads} threads", cores=unlock.get("physical_cores") or "--",
                          threads=unlock.get("logical_cpus") or "--")
        cores_panel = Panel(tr("Live core monitor"), [Gauges(slots, minimum=25)],
                            badge=shape, badge_tone="dim")

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

        persistence = Panel(tr("Boot persistence"), [
            Field(tr("Status"), said(stored.status_value)),
            Field(tr("Applied tuning"), said(tuning.applied_value)),
            Note(tr("Save the applied configuration for startup after testing it."), "dim"), Buttons([
            Choice(tr("Save for startup"), save_boot), Choice(tr("Review persistence"), review),
            Choice(tr("Remove from boot"), remove, tone="bad", enabled=enabled)])])

        # -- core unlock: separate from overclock persistence above
        controls = core_unlock_controls(unlock)
        mode = target.get("unlock_mode", "persistent" if controls["installed"] else "temporary")
        persistent_mode = mode == "persistent"
        unlock_allowed = controls["persist_allowed"] if persistent_mode else controls["temporary_allowed"]
        unlock_label = controls["action"] if persistent_mode else (
            "Already unlocked" if unlock.get("unlocked") else "Unlock cores and restart"
        )

        # The mask a tool read on this board, when one has said it.
        board_mask = reported_core_mask((unlock.get("persistence") or {}).get("boot_service_note"))
        target.setdefault("mask", board_mask or CORE_MASK_STOCK)
        masks = list(dict.fromkeys((CORE_MASK_STOCK, *([board_mask] if board_mask else []), *CORE_MASK_SEEN)))

        def pick_mask(ui_):
            chosen = ui_.choose(tr("Core mask of this board"), [(mask, mask_text(mask, board_mask)) for mask in masks])
            if chosen is not None:
                target["mask"] = chosen

        def unlock_cores(ui_):
            message = tr(unlock_label)
            if persistent_mode:
                message += "\n\n" + tr(
                    "This installs a small boot service that unlocks the two extra cores again "
                    "early on every cold boot, without flashing the BIOS. Each cold boot then "
                    "restarts once by itself, about 30 seconds. If the board cannot keep the "
                    "unlock, the service stops itself after two restarts. To skip it for one "
                    "boot, add bc250.core_unlock=0 to the kernel command line."
                )
            if target["force_mask"]:
                message += "\n\n" + tr(IGNORE_CORE_MASK_HINT) + "\n\n" + tr(CORE_MASK_BOOT_RISK)
            elif target["mask"] != CORE_MASK_STOCK:
                message += "\n\n" + mask_text(target["mask"], board_mask) + "\n\n" + tr(CORE_MASK_BOOT_RISK)
            if ui_.confirm(message, danger=True):
                command = (service.comando_persistir_desbloqueo_nucleos_cpu if persistent_mode
                           else service.comando_desbloquear_nucleos_cpu)
                mask = accepted_mask(target["mask"], target["force_mask"])
                guarded(ui_, tr("Unlock cores"), lambda: ui_.shell(
                    command(ignore_core_mask=target["force_mask"], accept_mask=mask)))

        def remove_unlock_persistence(ui_):
            if ui_.confirm(tr(
                "The boot service is removed. Nothing restarts: the cores stay unlocked "
                "until the next full power-off, which brings the board back to 6 cores."
            ), danger=True):
                guarded(ui_, tr("Remove persistence"), lambda: ui_.shell(
                    service.comando_quitar_persistencia_nucleos_cpu()))

        def guide(ui_):
            ui_.show_text(tr("Firmware persistence guide"), GUIDE_URL)

        danger = Panel(tr("DANGER ZONE").capitalize(), [
            Note(tr("Unlock hidden CPU cores"), "bad"),
            Choice(tr("Temporary"), lambda ui_: target.update(unlock_mode="temporary"),
                   detail=tr("Until the next full power-off. Nothing is installed."),
                   badge=tr("Selected") if not persistent_mode else ""),
            Choice(tr("Persistence"), lambda ui_: target.update(unlock_mode="persistent"),
                   detail=tr("Applied again by itself on every cold boot, without flashing the BIOS."),
                   badge=tr("Selected") if persistent_mode else tr(controls["status"]),
                   enabled=controls["offered"]),
            *([Field(tr("Status"), tr(controls["status"]))] if persistent_mode else []),
            *([Note(tr(controls["note"]), "bad")] if controls["note"] else []),
            *([Note(tr(controls["hint"]), "dim")] if controls["hint"] and
              (persistent_mode or not controls["offered"]) else []),
            Choice(tr("Core mask of this board"), pick_mask, mask_text(target["mask"], board_mask) + " ›",
                   enabled=unlock_allowed and not target["force_mask"],
                   info=Info(tr(CORE_MASK_PICK_HINT), tr(CORE_MASK_BOOT_RISK))),
            check(tr("Force a non-standard core mask (-f)"), target["force_mask"],
                  lambda ui_: target.update(force_mask=not target["force_mask"]), enabled=unlock_allowed),
            Buttons([Choice(tr(unlock_label), unlock_cores, tone="bad", enabled=unlock_allowed),
                     *([Choice(tr("Remove persistence"), remove_unlock_persistence, tone="bad",
                               enabled=controls["remove_allowed"])]
                       if persistent_mode and controls["installed"] else [])]),
            *([] if persistent_mode else [Choice(tr("Firmware persistence guide") + " ›", guide)]),
        ], danger=True)

        sections = {"tuning": [profile_panel, persistence, live_panel, cores_panel],
                    "monitor": [runtime, cores_panel, overview_panel],
                    "boot": [persistence], "cores": [cores_panel, danger]}
        return sections.get(tab, sections["tuning"])
