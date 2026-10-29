"""GPU governor: profiles, frequency range, Cyan compatibility and the voltage laboratory."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from bc250cc.application.gpu.voltage_apply import plan_voltage_apply
from bc250cc.application.gpu.voltage_lab_state import build_voltage_lab_state
from bc250cc.application.gpu.voltage_table import build_voltage_table_plan
from bc250cc.domain.gpu.profiles import profiles_for_allowed_range
from bc250cc.domain.gpu.voltage_profiles import (
    CUSTOM_VOLTAGE_MAX_MV,
    CUSTOM_VOLTAGE_MIN_MV,
    GOVERNOR_DEFAULT_VOLTAGES,
)
from frontends.desktop.i18n import governor_fix_label

from ..content import (
    Buttons,
    Choice,
    Field,
    Gap,
    Grid,
    Heading,
    Note,
    Panel,
    Slider,
    Split,
    Tile,
    Tiles,
    heat_tone,
    load_tone,
    number,
)
from ..i18n import tr
from .base import Page, check, guarded, metric_blocks, waiting

TABS = (("governor", "GPU governor"), ("voltage", "Voltage laboratory"))
#: Level -> label. 0 restores the governor's own curve; 1..5 add 10..50 mV above 2000 MHz.
LEVELS = ((1, "Gentle"), (2, "Moderate"), (3, "High"))
SET_METHODS = (("smu", "SMU"), ("kernel", "Kernel"))
USAGE_METHODS = (("busy-flag", "busy-flag"), ("process", "process"), ("kernel", "kernel"))
TEMP_READS = (("drm", "DRM"), ("sysfs", "sysfs"))
SAFE_CEILING = 2000  # the factory TOML's last point; past it the rail turns red
EXTRA_VOLTAGE_MV = 1150  # the highest commented-out point's voltage (2400 MHz)


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _cycle(options, current, step):
    keys = [key for key, _label in options]
    index = keys.index(current) if current in keys else 0
    return keys[(index + step) % len(keys)]


class GpuPage(Page):
    key = "gpu"
    title = "GPU Governor"
    interval = 3.0

    def tabs(self, ctx):
        return [(key, tr(label)) for key, label in TABS]

    def load(self, ctx):
        return ctx.service.estado_bc250()

    def build(self, ctx, data, tab, ui):
        state = data if isinstance(data, dict) else {}
        if not state:
            return waiting(ctx, self.key) or []
        if tab == "voltage":
            return self._voltage(ctx, state, ui)
        return self._governor(ctx, state, ui)

    # ------------------------------------------------------------------ governor

    def _governor(self, ctx, state, ui):
        gpu = metric_blocks(ctx)["gpu"]
        service = ctx.service
        mine = ctx.state(self.key)
        low, high = _int(state.get("allowed_min"), 500), _int(state.get("allowed_max"), 2000)
        current_min, current_max = _int(state.get("current_min"), low), _int(state.get("current_max"), high)
        voltages = {int(p["frequency"]): p.get("voltage") for p in state.get("safe_points") or [] if isinstance(p, dict)}
        stops = sorted({f for f in voltages if low <= f <= high} | {low, high})
        want_min = min(max(mine.get("min", current_min), low), high)
        want_max = min(max(mine.get("max", current_max), want_min), high)
        backend = str(state.get("governor_backend") or "")
        governor = "oberon" if backend.startswith("oberon") else "cyan"
        cyan = state.get("cyan_telemetry") or {}
        high_points = state.get("high_frequency_points") or {}
        unlocked = bool(high_points.get("enabled_frequencies"))

        # -- operating profile: one press sets the range
        def apply_profile(ui_, profile):
            if ui_.confirm(f"{tr(profile.label)}: {profile.minimum_mhz}–{profile.maximum_mhz} MHz"):
                guarded(ui_, tr(profile.label), lambda: service.aplicar_perfil_gpu(profile.minimum_mhz, profile.maximum_mhz))

        edited = mine.setdefault("profiles", {})
        shown = [edited.get(item.key, item) for item in profiles_for_allowed_range(low, high, governor=governor)]

        def edit(ui_, profile):
            name = ui_.ask_text(tr("Profile name"), tr(profile.label))
            minimum = None if name is None else ui_.ask_int(tr("Minimum frequency"), low, high, profile.minimum_mhz)
            maximum = None if minimum is None else ui_.ask_int(tr("Maximum frequency"), minimum, high, profile.maximum_mhz)
            if maximum is not None:
                edited[profile.key] = replace(profile, label=name.strip() or profile.label, minimum_mhz=minimum,
                                              maximum_mhz=maximum)

        def export(ui_):
            payload = [item.payload() for item in shown]
            guarded(ui_, tr("Export to Decky"), lambda: service.exportar_perfiles_gpu_decky(payload))

        profiles = Panel(tr("Operating profile"), [Tiles([
            Tile(tr(item.label), f"{item.minimum_mhz} – {item.maximum_mhz} MHz",
                 f"{voltages.get(item.maximum_mhz) or '--'} mV", handler=lambda ui_, item=item: apply_profile(ui_, item),
                 active=(item.minimum_mhz, item.maximum_mhz) == (current_min, current_max),
                 edit=lambda ui_, item=item: edit(ui_, item), edit_label=tr("Edit")) for item in shown], minimum=20)],
            action=Choice(tr("Export to Decky"), export))

        # -- range: the rail over the TOML points, red past 2000 MHz
        def step(which):
            def adjust(ui_, direction):
                index = stops.index(min(stops, key=lambda t: abs(t - (want_min if which == "min" else want_max))))
                new = stops[max(0, min(len(stops) - 1, index + direction))]
                if which == "min":
                    mine["min"], mine["max"] = new, max(want_max, new)
                else:
                    mine["max"], mine["min"] = new, min(want_min, new)
            return adjust

        def apply_range(ui_):
            if ui_.confirm(f"{tr('Apply range')}: {want_min}–{want_max} MHz", danger=want_max > SAFE_CEILING):
                guarded(ui_, tr("Apply range"), lambda: service.aplicar_rango_bc250(want_min, want_max))
                mine.pop("min", None), mine.pop("max", None)

        def save_boot(ui_):
            if ui_.confirm(tr("Save active range for startup")):
                guarded(ui_, tr("Save active range for startup"), service.guardar_rango_gpu_arranque)

        rail = Panel(tr("Frequency range"), [
            Slider(stops, want_min, want_max, SAFE_CEILING),
            Choice(tr("Minimum frequency"), None, f"< {want_min} MHz >", adjust=step("min")),
            Choice(tr("Maximum frequency"), None, f"< {want_max} MHz >", adjust=step("max"))],
            badge=f"{want_min} – {want_max} MHz", badge_tone="warn" if (want_min, want_max) != (current_min, current_max)
            else "accent")

        left = [profiles, rail]
        if backend.startswith("cyan"):  # -- Cyan kernel compatibility
            opts = mine.setdefault("compat", {
                "set_method": cyan.get("set_method", "smu"), "usage_method": cyan.get("method", "busy-flag"),
                "temp_read": cyan.get("temp_read", "drm"), "metrics": bool(cyan.get("fix_metrics", True)),
                "frequencies": bool(cyan.get("fix_frequency", False))})

            def picker(key, options, label):
                def adjust(ui_, direction):
                    opts[key] = _cycle(options, opts[key], direction)

                def choose(ui_):
                    picked = ui_.choose(label, list(options))
                    if picked is not None:
                        opts[key] = picked
                return Choice(label, choose, f"< {dict(options)[opts[key]]} >", adjust=adjust)

            def apply_compat(ui_):
                summary = " · ".join([dict(SET_METHODS)[opts["set_method"]], opts["usage_method"],
                                      dict(TEMP_READS)[opts["temp_read"]]])
                if ui_.confirm(f"{tr('Apply compatibility')}: {summary}", danger=opts["set_method"] == "kernel"):
                    guarded(ui_, tr("Cyan kernel compatibility"), lambda: service.configurar_compatibilidad_gpu_cyan(
                        opts["set_method"], opts["usage_method"], opts["metrics"], opts["frequencies"], opts["temp_read"]))
                    mine.pop("compat", None)

            left.append(Panel(tr("Cyan kernel compatibility"), [
                picker("set_method", SET_METHODS, tr("Governor method")),
                picker("usage_method", USAGE_METHODS, tr("Usage reading")),
                picker("temp_read", TEMP_READS, tr("Temperature reading")),
                check(governor_fix_label("metrics"), opts["metrics"], lambda ui_: opts.update(metrics=not opts["metrics"])),
                check(governor_fix_label("frequency"), opts["frequencies"],
                      lambda ui_: opts.update(frequencies=not opts["frequencies"])),
                Buttons([Choice(tr("Apply compatibility"), apply_compat)])],
                badge=tr("Extended range") if unlocked else "", badge_tone="bad"))
        left.append(Buttons([Choice(tr("Save for boot"), save_boot),
                             Choice(tr("Review and apply range"), apply_range, tone="primary",
                                    enabled=(want_min, want_max) != (current_min, current_max))]))

        # -- right: telemetry, service, laboratory, risk
        busy = gpu.get("usage_percent") if gpu.get("usage_percent") is not None else gpu.get("compute_busy_percent")
        temperature = gpu.get("temperature_c")
        tiles = Tiles([
            Tile(tr("Core clock"), number(state.get("sclk_actual", gpu.get("frequency_mhz")), "MHz")),
            Tile(tr("GPU voltage"), number(state.get("voltaje_actual", gpu.get("voltage_mv")), "mV")),
            Tile(tr("Thermal"), number(temperature, "°C", 1), tone=heat_tone(temperature)),
            Tile(tr("GPU load"), number(busy, "%", 0), tone=load_tone(busy)),
            Tile(tr("Memory clock"), number(state.get("mclk_actual", gpu.get("memory_frequency_mhz")), "MHz")),
            Tile(tr("Active range"), f"{current_min}–{current_max} MHz")], minimum=20)

        def control(action, label, danger=False):
            def handler(ui_):
                if ui_.confirm(label, danger=danger):
                    guarded(ui_, label, lambda: service.controlar_governor(action))
            return handler

        running = state.get("service_active") == "active"
        service_panel = Panel(tr("Governor service"), [Buttons([
            Choice(tr("View status"), lambda ui_: guarded(ui_, tr("View status"), service.status_governor)),
            Choice(tr("Restart"), control("reiniciar", tr("Restart service"))),
            Choice(tr("Stop governor"), control("desactivar", tr("Stop governor"), True), tone="bad") if running
            else Choice(tr("Start governor"), control("activar", tr("Start governor")), tone="primary")])],
            badge=backend or tr("Not detected"), badge_tone="ok" if running else "warn")

        def open_config(ui_):
            path = str(state.get("config_path") or "")
            ok, text = ui_.run("config.toml", lambda: Path(path).read_text(encoding="utf-8"))
            if ok and isinstance(text, str):
                ui_.show_text(path, text)

        lab = Panel(tr("Voltage laboratory"), [Buttons([
            Choice(tr("Open laboratory"), lambda ui_: ui_.show_tab("voltage"), tone="primary"),
            Choice(tr("Open config.toml"), open_config, enabled=bool(state.get("config_path")))])],
            badge=f"{want_max} MHz · {voltages.get(want_max) or '--'} mV", badge_tone="accent")

        right = [tiles, service_panel, lab]
        if high_points.get("available"):  # -- the +2000 MHz points live behind a warning
            def toggle_high(ui_):
                label = tr("Re-comment the +2000 MHz points" if unlocked else "Uncomment +2000 MHz points")
                if ui_.confirm(label, danger=True):
                    guarded(ui_, label, lambda: service.alternar_puntos_gpu_altos(not unlocked))

            extra = list(high_points.get("frequencies") or ()) or [2050, 2400]
            right.append(Panel(tr("DANGER ZONE"), [
                Note(f"{tr('TOML points above 2000 MHz')} · {extra[0]}–{extra[-1]} MHz · ≤ {EXTRA_VOLTAGE_MV} mV", "bad"),
                Buttons([Choice(tr("Re-comment the +2000 MHz points" if unlocked else "Uncomment +2000 MHz points"),
                                toggle_high, tone="bad")])],
                badge=tr("Enabled" if unlocked else "Locked"), badge_tone="bad" if unlocked else "dim", danger=True))

        # -- advanced diagnostics: folded, as on the desktop
        folded = not mine.get("advanced", False)
        details = [] if folded else [Grid([tr("Frequency"), tr("Voltage")], [[f"{f} MHz", f"{v} mV"] for f, v in sorted(voltages.items())]),
                   Field(tr("Backend"), backend or "--"), Field("config.toml", str(state.get("config_path") or "--")),
                   Field("pp_dpm_sclk", " · ".join(str(state.get("pp_dpm_sclk") or "--").split()))]
        advanced = Panel(tr("Advanced GPU diagnostics"), details,
                         action=Choice(tr("Show" if folded else "Hide") + " ›", lambda ui_: mine.update(advanced=folded)))
        return [Split(left, right, ratio=0.55), advanced]

    # ------------------------------------------------------------ voltage laboratory

    def _voltage(self, ctx, state, ui):
        service = ctx.service
        mine = ctx.state(self.key)
        lab = build_voltage_lab_state(state)
        level = mine.get("level", 1)
        custom = mine.setdefault("custom", {})
        if not lab.points:
            return [Note(tr("Waiting for data…"), "warn")]
        table = build_voltage_table_plan(
            points=lab.points, selected_level=level, editable_frequencies=lab.editable_frequencies,
            profile_frequencies=lab.profile_frequencies, custom_values=custom,
            packaged_voltages=dict(GOVERNOR_DEFAULT_VOLTAGES), detected_level=lab.detected_level,
            is_oberon=lab.is_oberon)

        def pick(value):
            def handler(ui_):
                mine["level"] = value
            return handler

        out = [Heading(tr("GPU voltage curve")), Note(tr("Choose a curve or a preset first"), "dim"),
               Heading(tr("Curve boost"))]
        for value, label in LEVELS:
            on = level == value
            out.append(Choice(f"({'x' if on else ' '}) +{value * 10} mV  {tr(label)}", pick(value), tone="ok" if on else ""))
        edit_points = tr("Custom\nEdit active points").split("\n")[-1]
        out.append(Choice(f"({'x' if level == -1 else ' '}) {tr('Custom')}  {edit_points}", pick(-1),
                          tone="ok" if level == -1 else ""))
        out.append(Gap())
        rows = []
        for row in table.rows:
            if table.custom_mode and row.custom_available:
                def edit(ui_, row=row):
                    value = ui_.ask_int(f"{row.frequency} MHz (mV)", CUSTOM_VOLTAGE_MIN_MV, CUSTOM_VOLTAGE_MAX_MV,
                                        int(custom.get(row.frequency, row.editor_value)))
                    if value is not None:
                        custom[row.frequency] = value

                def nudge(ui_, direction, row=row):
                    now = int(custom.get(row.frequency, row.editor_value))
                    custom[row.frequency] = max(CUSTOM_VOLTAGE_MIN_MV, min(CUSTOM_VOLTAGE_MAX_MV, now + 5 * direction))

                shown = int(custom.get(row.frequency, row.editor_value))
                out.append(Choice(f"{row.frequency} MHz", edit, f"{row.current} mV → {shown} mV", adjust=nudge,
                                  tone="warn" if shown != row.current else ""))
            else:
                delta = (row.proposed or row.current) - row.current if row.proposed else 0
                rows.append([f"{row.frequency} MHz", f"{row.current} mV",
                             f"{row.proposed or row.current} mV", f"+{delta}" if delta > 0 else "—" if ui.unicode else "-"])
        if rows:
            out.append(Grid([tr("Frequency"), tr("Current"), tr("Selected"), "Δ"], rows))

        def values_for_apply():
            return {int(k): int(v) for k, v in custom.items()} if level == -1 else {}

        def review(ui_, restore=False):
            chosen = 0 if restore else level
            plan = plan_voltage_apply(
                level=chosen, editable_frequencies=lab.editable_frequencies, profile_frequencies=lab.profile_frequencies,
                current_voltages=dict(lab.current_voltages), custom_values=values_for_apply(), is_oberon=lab.is_oberon)
            if not plan.available:
                ui_.notify(tr("Waiting for data…"), "warn")
                return
            if plan.violation:
                v = plan.violation
                ui_.notify(f"{v.frequency} MHz {v.voltage} mV < {v.previous_frequency} MHz {v.previous_voltage} mV", "bad")
                return
            summary = (f"{len(plan.active_frequencies)} · {plan.maximum_voltage} mV · "
                       + tr("Stop every game, benchmark, and 3D workload before continuing."))
            if not ui_.confirm(f"{tr('Apply voltage curve')}: {summary}", danger=True):
                return
            if plan.custom_mode:
                guarded(ui_, tr("Voltage curve"), lambda: service.aplicar_laboratorio_voltaje_gpu_personalizado(dict(plan.custom_values)))
            else:
                guarded(ui_, tr("Voltage curve"), lambda: service.aplicar_laboratorio_voltaje_gpu(chosen))
            custom.clear()

        out += [Gap(),
                Choice(tr("Restore governor defaults"), lambda ui_: review(ui_, True), tone="warn"),
                Choice(tr("Review and apply"), review, tone="accent")]
        return out
