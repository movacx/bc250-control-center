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

from ..compact import terminal_form
from ..content import (
    Buttons,
    Choice,
    Field,
    Grid,
    Heading,
    Info,
    Meter,
    Note,
    Panel,
    Slider,
    number,
    percent,
)
from ..i18n import tr
from .base import (
    Page,
    guarded,
    load_meter,
    metric_blocks,
    switch,
    temperature_meter,
    waiting,
)
from .sensor_list import GPU_FIRST, beside

TABS = (("governor", "Hardware control"), ("voltage", "Voltage laboratory"), ("monitor", "Sensors"))
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
        mine = ctx.state(self.key)
        if "profiles" not in mine and ctx.settings is not None:
            try:
                mine["saved"] = ctx.settings.read_local_config().get("tui_gpu_profiles") or ()
            except Exception:  # an unreadable config leaves the shipped profiles
                mine["saved"] = ()
        return ctx.service.estado_bc250()

    def build(self, ctx, data, tab, ui):
        state = data if isinstance(data, dict) else {}
        if not state:
            return waiting(ctx, self.key) or []
        if tab == "voltage":
            return beside(ctx, ui, terminal_form(self._voltage(ctx, state, ui)), [], GPU_FIRST)
        return self._governor(ctx, state, ui, tab)

    # ------------------------------------------------------------------ governor

    def _governor(self, ctx, state, ui, tab="governor"):
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
            mine.update(min=profile.minimum_mhz, max=profile.maximum_mhz, profile_key=profile.key)

        shipped = profiles_for_allowed_range(low, high, governor=governor)
        if "profiles" not in mine:
            kept = {item.get("key"): item for item in mine.pop("saved", None) or () if isinstance(item, dict)}
            mine["profiles"] = {item.key: replace(item, label=str(kept[item.key].get("label") or item.label),
                                                  minimum_mhz=kept[item.key]["min"], maximum_mhz=kept[item.key]["max"])
                                for item in shipped if item.key in kept and all(isinstance(kept[item.key].get(k), int) for k in ("min", "max"))
                                and low <= kept[item.key]["min"] <= kept[item.key]["max"] <= high}
        edited = mine["profiles"]
        shown = [edited.get(item.key, item) for item in shipped]

        def edit(ui_, profile):
            name = ui_.ask_text(tr("Profile name"), tr(profile.label))
            minimum = None if name is None else ui_.ask_int(tr("Minimum frequency"), low, high, profile.minimum_mhz)
            maximum = None if minimum is None else ui_.ask_int(tr("Maximum frequency"), minimum, high, profile.maximum_mhz)
            if maximum is not None:
                edited[profile.key] = replace(profile, label=name.strip() or profile.label, minimum_mhz=minimum,
                                              maximum_mhz=maximum)
                if ctx.settings is not None:
                    ctx.settings.save_local_config({"tui_gpu_profiles": [
                        {"key": item.key, "label": item.label, "min": item.minimum_mhz, "max": item.maximum_mhz}
                        for item in edited.values()]})

        def export(ui_):
            payload = [item.payload() for item in shown]
            guarded(ui_, tr("Export to Decky"), lambda: service.exportar_perfiles_gpu_decky(payload))

        matching = next((item for item in shown if (item.minimum_mhz, item.maximum_mhz) == (want_min, want_max)), None)

        def describe(item):
            return f"{tr(item.label)}   {item.minimum_mhz}–{item.maximum_mhz} MHz"

        def step_profile(ui_, direction):
            if shown:
                index = shown.index(matching) if matching in shown else (-1 if direction > 0 else 0)
                apply_profile(ui_, shown[(index + direction) % len(shown)])

        def pick_profile(ui_):
            chosen = ui_.choose(tr("Operating profile"), [(item.key, describe(item)) for item in shown])
            item = next((item for item in shown if item.key == chosen), None)
            if item is not None:
                apply_profile(ui_, item)

        # -- range: the rail over the TOML points, red past 2000 MHz
        def step(which):
            def adjust(ui_, direction):
                mine.pop("profile_key", None)
                index = stops.index(min(stops, key=lambda t: abs(t - (want_min if which == "min" else want_max))))
                new = stops[max(0, min(len(stops) - 1, index + direction))]
                if which == "min":
                    mine["min"], mine["max"] = new, max(want_max, new)
                else:
                    mine["max"], mine["min"] = new, min(want_min, new)
            return adjust

        def apply_range(ui_):
            if ui_.confirm(f"{tr('Apply range')}: {want_min}–{want_max} MHz", danger=want_max > SAFE_CEILING):
                method = service.aplicar_perfil_gpu if mine.get("profile_key") else service.aplicar_rango_bc250
                if guarded(ui_, tr("Apply range"), lambda: method(want_min, want_max)):
                    mine.pop("min", None), mine.pop("max", None), mine.pop("profile_key", None)

        def save_boot(ui_):
            if ui_.confirm(tr("Save active range for startup")):
                guarded(ui_, tr("Save active range for startup"), service.guardar_rango_gpu_arranque)

        def type_in(which):
            def edit_(ui_):
                label = tr("Minimum frequency" if which == "min" else "Maximum frequency")
                # The table's own points are what the governor holds; another number is still one line away.
                value = ui_.choose(label, [(f, f"{f} MHz" + (f"   {voltages[f]} mV" if voltages.get(f) else "")) for f in stops]
                                   + [("typed", tr("Manual value"))])
                if value == "typed":
                    value = ui_.ask_int(f"{label} (MHz)", low, high, want_min if which == "min" else want_max)
                if value is not None:
                    mine.pop("profile_key", None)
                    mine.update({"min": value, "max": max(value, want_max)} if which == "min" else
                                {"max": value, "min": min(value, want_min)})
            return edit_

        dirty = (want_min, want_max) != (current_min, current_max)
        def was(value, current):
            """A value not applied yet shows what it replaces."""
            mv = voltages.get(value)
            return f"< {value} MHz >" + (f"   {mv} mV" if mv else "") + ("" if value == current else f"   {current} {'→' if ui.unicode else '->'} {value}")

        rail = Panel(tr("Frequency range"), [
            Choice(tr("Operating profile"), pick_profile, f"< {tr(matching.label) if matching else tr('Custom')} >", adjust=step_profile,
                   edit=lambda ui_: edit(ui_, matching or shown[0]) if shown else None, enabled=bool(shown), id="profile",
                   info=Info(tr("Pick a validated profile or set the range by hand. Every change is checked against the board before it runs, and the telemetry beside it is read-only."))),
            Choice(tr("Minimum frequency"), type_in("min"), was(want_min, current_min), adjust=step("min"), id="min", info=Info(tr("Governor floor for this profile.")),
                   tone="warn" if want_min != current_min else ""),
            Choice(tr("Maximum frequency"), type_in("max"), was(want_max, current_max), adjust=step("max"), id="max", info=Info(tr("Governor ceiling for this profile.")),
                   tone="bad" if want_max > SAFE_CEILING else "warn" if want_max != current_max else ""),
            Slider(stops, want_min, want_max, SAFE_CEILING),
            Choice(tr("Review and apply range"), apply_range, tone="primary", enabled=dirty,
                   info=Info(tr("This updates the active governor range through D-Bus. The TOML safe-point configuration is not rewritten."))),
            Choice(tr("Reset selection"), lambda ui_: [mine.pop(key, None) for key in ("min", "max", "profile_key")], enabled=dirty, id="revert"),
            Choice(tr("Save for boot"), save_boot, enabled=not dirty,
                   info=Info(tr("This writes the currently active Cyan D-Bus range to the managed TOML. Cyan will use it at the next startup. The running GPU range and governor service will not be changed."),
                             blocked=tr("Apply the selected range before saving it for startup.") if dirty else "")),
            Choice(tr("Export to Decky"), export, info=Info(tr("Sends these three GPU cards to Decky, so Game Mode offers the same ranges. Export again whenever you edit one here.")))],
            badge=tr("Unapplied changes") if dirty else f"{current_min}–{current_max} MHz", badge_tone="warn" if dirty else "dim")

        left = [rail]
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
                    if guarded(ui_, tr("Cyan kernel compatibility"), lambda: service.configurar_compatibilidad_gpu_cyan(
                            opts["set_method"], opts["usage_method"], opts["metrics"], opts["frequencies"], opts["temp_read"])):
                        mine.pop("compat", None)

            def flip(key):
                return lambda ui_, _direction=1: opts.update({key: not opts[key]})

            saved = {"set_method": cyan.get("set_method", "smu"), "usage_method": cyan.get("method", "busy-flag"),
                     "temp_read": cyan.get("temp_read", "drm"), "metrics": bool(cyan.get("fix_metrics", True)),
                     "frequencies": bool(cyan.get("fix_frequency", False))}
            left.append(Panel(tr("Cyan kernel compatibility"), [
                picker("set_method", SET_METHODS, tr("Governor method")),
                picker("usage_method", USAGE_METHODS, tr("Usage reading")),
                picker("temp_read", TEMP_READS, tr("Temperature reading")),
                switch(governor_fix_label("metrics"), opts["metrics"], flip("metrics")),
                switch(governor_fix_label("frequency"), opts["frequencies"], flip("frequencies")),
                Choice(tr("Apply compatibility"), apply_compat, tone="warn" if opts != saved else "", enabled=True)]))

        # -- right: telemetry, service, laboratory, risk
        busy = gpu.get("usage_percent") if gpu.get("usage_percent") is not None else gpu.get("compute_busy_percent")
        temperature = gpu.get("temperature_c")
        ceiling = max(high, 1)
        clock = state.get("sclk_actual", gpu.get("frequency_mhz"))
        live = Panel(tr("Live"), [
            Meter(tr("Core clock"), percent(float(clock) / ceiling * 100) if clock else None, number(clock, "MHz"), ""),
            temperature_meter(tr("Temperature"), temperature),
            load_meter(tr("GPU load"), busy),
            Field(tr("GPU voltage"), number(state.get("voltaje_actual", gpu.get("voltage_mv")), "mV")),
            Field(tr("Memory clock"), number(state.get("mclk_actual", gpu.get("memory_frequency_mhz")), "MHz")),
            Field(tr("GPU power"), number(gpu.get("power_w"), "W"))])
        def control(action, label, danger=False):
            def handler(ui_):
                if ui_.confirm(label, danger=danger):
                    guarded(ui_, label, lambda: service.controlar_governor(action))
            return handler

        running = state.get("service_active") == "active"
        def service_menu(ui_):
            options = [("status", tr("View status")), ("restart", tr("Restart"))]
            options.append(("stop", tr("Stop governor")) if running else ("start", tr("Start governor")))
            chosen = ui_.choose(tr("Governor service"), options)
            if chosen == "status":
                guarded(ui_, tr("View status"), service.status_governor)
            elif chosen == "restart":
                control("reiniciar", tr("Restart service"))(ui_)
            elif chosen == "stop":
                control("desactivar", tr("Stop governor"), True)(ui_)
            elif chosen == "start":
                control("activar", tr("Start governor"))(ui_)

        service_panel = Panel(tr("Service"), [Choice(
            tr("Governor service") + " ›", service_menu, badge=tr("Active") if running else tr("Stopped"),
            badge_tone="ok" if running else "warn",
            info=Info(tr("Start governor runs it now and saves it for startup (enables the service). Stop governor stops it and removes it from startup (disables the service).")))])

        right = []
        if high_points.get("available"):  # -- the +2000 MHz points live behind a warning
            def toggle_high(ui_):
                label = tr("Re-comment the +2000 MHz points" if unlocked else "Uncomment +2000 MHz points")
                if ui_.confirm(label, danger=True):
                    guarded(ui_, label, lambda: service.alternar_puntos_gpu_altos(not unlocked))

            extra = list(high_points.get("frequencies") or ()) or [2050, 2400]
            right.append(Panel(tr("DANGER ZONE").capitalize(), [
                Choice(tr("Re-comment the +2000 MHz points" if unlocked else "Uncomment +2000 MHz points"), toggle_high, tone="bad",
                       info=Info("", f"{tr('TOML points above 2000 MHz')} · {extra[0]}–{extra[-1]} MHz · ≤ {EXTRA_VOLTAGE_MV} mV"))],
                badge=tr("Enabled" if unlocked else "Locked"), badge_tone="bad" if unlocked else "dim", danger=True))

        # -- advanced diagnostics: folded, as on the desktop
        folded = not mine.get("advanced", False)
        details = [] if folded else [Grid([tr("Frequency"), tr("Voltage")], [[f"{f} MHz", f"{v} mV"] for f, v in sorted(voltages.items())]),
                   Field(tr("Backend"), backend or "--"), Field("config.toml", str(state.get("config_path") or "--")),
                   Field("pp_dpm_sclk", " · ".join(str(state.get("pp_dpm_sclk") or "--").split()))]
        advanced = Panel(tr("Advanced GPU diagnostics"), details,
                         action=Choice(tr("Show" if folded else "Hide") + " ›", lambda ui_: mine.update(advanced=folded)))
        if tab == "service":
            return terminal_form([service_panel, *[item for item in left if isinstance(item, Panel)
                                  and item.title == tr("Cyan kernel compatibility")]])
        if tab == "monitor":
            return beside(ctx, ui, [advanced], [live], GPU_FIRST)
        compatibility = [item for item in left if isinstance(item, Panel) and item.title == tr("Cyan kernel compatibility")]
        risk = [item for item in right if isinstance(item, Panel) and item.danger]
        return beside(ctx, ui, [rail, service_panel, *compatibility, *risk], [live], GPU_FIRST)

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

        out = [Heading(tr("Curve boost"))]
        for value, label in LEVELS:
            on = level == value
            out.append(Choice(f"+{value * 10} mV  {tr(label)}", pick(value), mark=on))
        edit_points = tr("Custom\nEdit active points").split("\n")[-1]
        out.append(Choice(f"{tr('Custom')}  {edit_points}", pick(-1), mark=level == -1))
        out.append(Heading(tr("GPU voltage curve")))
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
                ok = guarded(ui_, tr("Voltage curve"), lambda: service.aplicar_laboratorio_voltaje_gpu_personalizado(dict(plan.custom_values)))
            else:
                ok = guarded(ui_, tr("Voltage curve"), lambda: service.aplicar_laboratorio_voltaje_gpu(chosen))
            if ok:
                custom.clear()

        def open_config(ui_):
            path = str(state.get("config_path") or "")
            ok, text = ui_.run("config.toml", lambda: Path(path).read_text(encoding="utf-8"))
            if ok and isinstance(text, str):
                ui_.show_text(path, text)

        out += [Buttons([Choice(tr("Review and apply"), review, tone="primary"),
                         Choice(tr("Restore governor defaults"), lambda ui_: review(ui_, True), tone="warn"),
                         Choice(tr("Open config.toml"), open_config, enabled=bool(state.get("config_path")))])]
        return out
