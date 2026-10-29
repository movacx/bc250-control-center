"""GPU governor: profiles, frequency range, Cyan compatibility and the voltage laboratory."""

from __future__ import annotations

from bc250cc.application.gpu.voltage_apply import plan_voltage_apply
from bc250cc.application.gpu.voltage_lab_state import build_voltage_lab_state
from bc250cc.application.gpu.voltage_table import build_voltage_table_plan
from bc250cc.domain.gpu.profiles import profiles_for_allowed_range, profiles_payload
from bc250cc.domain.gpu.voltage_profiles import (
    CUSTOM_VOLTAGE_MAX_MV,
    CUSTOM_VOLTAGE_MIN_MV,
    GOVERNOR_DEFAULT_VOLTAGES,
)
from frontends.desktop.i18n import governor_fix_label

from ..content import (
    Choice,
    Field,
    Gap,
    Grid,
    Heading,
    Note,
    Track,
    number,
)
from ..i18n import tr
from .base import (
    Page,
    guarded,
    load_meter,
    metric_blocks,
    temperature_meter,
    waiting,
)

TABS = (("governor", "GPU governor"), ("voltage", "Voltage laboratory"))
#: Level -> label. 0 restores the governor's own curve; 1..5 add 10..50 mV above 2000 MHz.
LEVELS = ((1, "Gentle"), (2, "Moderate"), (3, "High"))
SET_METHODS = (("smu", "SMU"), ("kernel", "Kernel"))
USAGE_METHODS = (("busy-flag", "busy-flag"), ("process", "process"), ("kernel", "kernel"))
TEMP_READS = (("drm", "DRM"), ("sysfs", "sysfs"))


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
        points = [int(p["frequency"]) for p in state.get("safe_points") or [] if isinstance(p, dict)]
        ticks = sorted({f for f in points if low <= f <= high} | {low, high})
        want_min = min(max(mine.get("min", current_min), low), high)
        want_max = min(max(mine.get("max", current_max), want_min), high)
        backend = str(state.get("governor_backend") or "")
        cyan = state.get("cyan_telemetry") or {}
        is_cyan = backend.startswith("cyan")

        busy = gpu.get("usage_percent") if gpu.get("usage_percent") is not None else gpu.get("compute_busy_percent")
        live = [
            Heading(tr("Live")),
            Field(tr("Current frequency"), number(state.get("sclk_actual", gpu.get("frequency_mhz")), "MHz")),
            Field(tr("Voltage"), number(state.get("voltaje_actual", gpu.get("voltage_mv")), "mV")),
            temperature_meter(tr("Temperature"), gpu.get("temperature_c")),
            load_meter(tr("GPU load"), busy),
            Field(tr("Memory"), number(state.get("mclk_actual", gpu.get("memory_frequency_mhz")), "MHz")),
        ]

        # -- the three shipped profiles; one press sets the range
        out = [*live, Gap(), Heading(tr("Operating profile"))]
        for profile in profiles_for_allowed_range(low, high, governor="oberon" if backend.startswith("oberon") else "cyan"):
            def apply_profile(ui_, profile=profile):
                if ui_.confirm(f"{tr(profile.label)}: {profile.minimum_mhz}–{profile.maximum_mhz} MHz"):
                    guarded(ui_, tr(profile.label), lambda: service.aplicar_perfil_gpu(profile.minimum_mhz, profile.maximum_mhz))

            active = (profile.minimum_mhz, profile.maximum_mhz) == (current_min, current_max)
            out.append(Choice(f"({'x' if active else ' '}) {tr(profile.label)}", apply_profile,
                              f"{profile.minimum_mhz}–{profile.maximum_mhz} MHz", tone="ok" if active else ""))

        def export(ui_):
            payload = profiles_payload(low, high, governor="oberon" if backend.startswith("oberon") else "cyan")
            guarded(ui_, tr("Export to Decky"), lambda: service.exportar_perfiles_gpu_decky(payload))

        out.append(Choice(tr("Export to Decky"), export))

        # -- range: two sliders over the safe points
        def step(which, delta):
            def adjust(ui_, direction):
                index = ticks.index(min(ticks, key=lambda t: abs(t - (want_min if which == "min" else want_max))))
                new = ticks[max(0, min(len(ticks) - 1, index + direction))]
                if which == "min":
                    mine["min"], mine["max"] = new, max(want_max, new)
                else:
                    mine["max"], mine["min"] = new, min(want_min, new)
            return adjust

        def apply_range(ui_):
            if ui_.confirm(f"{tr('Apply range')}: {want_min}–{want_max} MHz"):
                guarded(ui_, tr("Apply range"), lambda: service.aplicar_rango_bc250(want_min, want_max))
                mine.clear()

        def save_boot(ui_):
            if ui_.confirm(tr("Save active range for startup")):
                guarded(ui_, tr("Save active range for startup"), service.guardar_rango_gpu_arranque)

        out += [Gap(), Heading(tr("Frequency range")),
                Track(tr("Active range"), low, high, want_min, want_max, f"{want_min} – {want_max} MHz",
                      "warn" if (want_min, want_max) != (current_min, current_max) else "accent"),
                Choice(tr("Minimum frequency"), None, f"< {want_min} MHz >", adjust=step("min", 0)),
                Choice(tr("Maximum frequency"), None, f"< {want_max} MHz >", adjust=step("max", 0)),
                Choice(tr("Review and apply range"), apply_range, tone="accent",
                       enabled=(want_min, want_max) != (current_min, current_max)),
                Choice(tr("Save active range for startup"), save_boot)]

        # -- service
        def control(action, label, danger=False):
            def handler(ui_):
                if ui_.confirm(label, danger=danger):
                    guarded(ui_, label, lambda: service.controlar_governor(action))
            return handler

        def status(ui_):
            guarded(ui_, tr("View status"), service.status_governor)

        out += [Gap(), Heading(tr("Governor service")),
                Field(tr("Backend"), backend or tr("Not detected")),
                Field(tr("Service"), f"{state.get('service_active', '--')} / {state.get('service_enabled', '--')}",
                      "ok" if state.get("service_active") == "active" else "warn"),
                Choice(tr("View status"), status),
                Choice(tr("Restart service"), control("reiniciar", tr("Restart service"))),
                Choice(tr("Start governor"), control("activar", tr("Start governor"))),
                Choice(tr("Stop governor"), control("desactivar", tr("Stop governor"), True), tone="warn")]

        # -- Cyan kernel compatibility
        if is_cyan:
            opts = mine.setdefault("compat", {
                "set_method": cyan.get("set_method", "smu"), "usage_method": cyan.get("method", "busy-flag"),
                "temp_read": cyan.get("temp_read", "drm"), "metrics": bool(cyan.get("fix_metrics", True)),
                "frequencies": bool(cyan.get("fix_frequency", False))})

            def picker(key, options, label):
                def adjust(ui_, direction):
                    opts[key] = _cycle(options, opts[key], direction)

                def choose(ui_):
                    picked = ui_.choose(label, [(k, n) for k, n in options])
                    if picked is not None:
                        opts[key] = picked
                names = dict(options)
                return Choice(label, choose, f"< {names[opts[key]]} >", adjust=adjust)

            def flag(key, label):
                def toggle(ui_):
                    opts[key] = not opts[key]
                return Choice(f"[{'x' if opts[key] else ' '}] {label}", toggle)

            def apply_compat(ui_):
                summary = ", ".join(f"{k}={v}" for k, v in opts.items())
                if ui_.confirm(f"{tr('Apply compatibility')}: {summary}", danger=opts["set_method"] == "kernel"):
                    guarded(ui_, tr("Cyan kernel compatibility"), lambda: service.configurar_compatibilidad_gpu_cyan(
                        opts["set_method"], opts["usage_method"], opts["metrics"], opts["frequencies"], opts["temp_read"]))
                    mine.pop("compat", None)

            out += [Gap(), Heading(tr("Cyan kernel compatibility")),
                    picker("set_method", SET_METHODS, tr("Governor method")),
                    picker("usage_method", USAGE_METHODS, tr("Usage reading")),
                    picker("temp_read", TEMP_READS, tr("Temperature reading")),
                    flag("metrics", governor_fix_label("metrics")), flag("frequencies", governor_fix_label("frequency")),
                    Choice(tr("Apply compatibility"), apply_compat)]

        # -- the +2000 MHz points live behind a warning
        high_points = state.get("high_frequency_points") or {}
        if high_points.get("available"):
            enabled = bool(high_points.get("enabled"))

            def toggle_high(ui_):
                if ui_.confirm(tr("Enable advanced +2000 MHz points") if not enabled else tr("Disable advanced +2000 MHz points"), danger=True):
                    guarded(ui_, tr("Enable advanced +2000 MHz points"), lambda: service.alternar_puntos_gpu_altos(not enabled))

            out += [Gap(), Heading(tr("GPU risk zone")),
                    Choice(tr("Disable advanced +2000 MHz points") if enabled else tr("Enable advanced +2000 MHz points"),
                           toggle_high, tone="bad")]
        return out

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
