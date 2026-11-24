"""Settings of the terminal interface, and the hardware preferences it shares with the other frontends."""

from __future__ import annotations

from pathlib import Path

from bc250cc.application.system import daemon_service
from frontends.desktop.core.temperature_unit import UNITS, unit_symbol, use_unit
from frontends.desktop.i18n import LANGUAGE_OPTIONS

from .. import preferences
from ..content import Choice, Info, Note, Panel
from ..i18n import set_language, tr
from . import compat
from .base import Page, guarded, switch

THEMES = (("auto", "System"), ("light", "Light"), ("dark", "Dark"), ("mono", "No colour"))
TABS = (("general", "General"), ("appearance", "Appearance"), ("hardware", "Hardware"), ("terminal", "Terminal"),
        ("telemetry", "Telemetry"), ("notifications", "Notifications"), ("backup", "Recovery"))
ALERT_FIELDS = (
    ("ram_warning_percent", "RAM warning (%)", 50, 99),
    ("ram_critical_percent", "RAM critical (%)", 50, 100),
    ("swap_warning_percent", "Swap warning (%)", 10, 100),
    ("gpu_temp_warning", "GPU temperature warning", 60, 110),
    ("cpu_temp_warning", "CPU temperature warning", 60, 110),
)
GOVERNORS = (("auto", "Automatic detection"), ("cyan-skillfish-governor-smu", "Cyan Skillfish Governor (SMU)"),
             ("oberon-governor", "Oberon Governor"))
INTERVALS = ((1, "1 second"), (2, "2 seconds"), (5, "5 seconds"), (10, "10 seconds"))


def theme_label(code: str) -> str:
    label = tr(dict(THEMES).get(code, "System"))
    return f"{label} (mono)" if code == "mono" else label


class SettingsPage(Page):
    key = "settings"
    title = "Settings"
    interval = 5.0

    def tabs(self, ctx):
        return [(key, tr(label)) for key, label in TABS]

    def load(self, ctx):
        data = {"config": ctx.settings.read_local_config()}
        data["daemon"] = daemon_service.running()
        try:
            data["tools"] = ctx.service.estado_herramientas_bc250()
        except Exception:
            data["tools"] = {}
        return data

    # -- saving ------------------------------------------------------------------------------------

    def _save(self, ctx, ui, updates: dict) -> bool:
        try:
            ctx.settings.save_local_config(updates)
        except Exception as error:
            ui.notify(str(error), "bad")
            return False
        config = {**((ctx.page_data.get(self.key) or {}).get("config") or {}), **updates}
        ctx.page_data.setdefault(self.key, {})["config"] = config
        ctx.config = {**(ctx.config or {}), **updates}
        if any(key.startswith("tui_") for key in updates):
            ui.apply_preferences(config)
        ui.notify(tr("Saved"), "ok")
        return True

    def _pick(self, ctx, title: str, key: str, options, current, *, detail: str = "", after=None) -> Choice:
        """A setting with a list of values: Enter lists them, left and right step through them."""
        options = list(options)
        keys = [value for value, _label in options]
        shown = dict(options).get(current, str(current))

        def store(ui, value):
            if value is not None and value != current and self._save(ctx, ui, {key: value}) and after:
                after(value)

        def step(ui, direction):
            index = keys.index(current) if current in keys else 0
            store(ui, keys[(index + direction) % len(keys)])

        return Choice(tr(title), lambda ui: store(ui, ui.choose(tr(title), options)), f"< {shown} >", adjust=step,
                      info=Info(tr(detail)) if detail else None, id=key)

    def _switch(self, ctx, title: str, key: str, value: bool, *, detail: str = "") -> Choice:
        return switch(tr(title), value, lambda ui: self._save(ctx, ui, {key: not value}),
                      info=Info(tr(detail)) if detail else None, id=key)

    # -- tabs --------------------------------------------------------------------------------------

    def build(self, ctx, data, tab, ui):
        data = data or {}
        config = data.get("config") or {}
        mine = preferences.read(config)
        return getattr(self, f"_{tab or 'general'}")(ctx, data, config, mine, ui)

    def _general(self, ctx, data, config, mine, ui):
        from ..screen import SIDEBAR_ORDER
        from . import build_pages

        titles = {key: tr(page.title) for key, page in build_pages().items()}
        language = mine["tui_language"] or str(config.get("idioma") or "auto")

        def speak(value):
            set_language(value)

        def unit(value):
            use_unit(value)

        def reset(ui_):
            if ui_.confirm(tr("Reset preferences"), danger=True):
                self._save(ctx, ui_, dict(preferences.DEFAULTS))

        return [
            Panel(tr("Language"), [
                self._pick(ctx, "Language", "tui_language", LANGUAGE_OPTIONS, language, after=speak, detail=(
                    "Set the interface language. The change is applied immediately to the interface and its dialogs.")),
                self._pick(ctx, "Temperature unit", "tui_temperature_unit", [(key, unit_symbol(key)) for key in UNITS],
                           mine["tui_temperature_unit"] or ("fahrenheit" if unit_symbol() == "°F" else "celsius"), after=unit, detail=(
                               "How temperatures are shown everywhere in the app. Limits and fan curves are still kept in Celsius."))]),
            Panel(tr("Startup"), [
                self._pick(ctx, "Start page", "tui_start_page", [(key, titles[key]) for key in SIDEBAR_ORDER if key in titles],
                           mine["tui_start_page"], detail="Choose the module to open by default."),
                self._switch(ctx, "Reopen last module", "tui_reopen", mine["tui_reopen"],
                             detail="Restore the last visited module when the application starts."),
                self._switch(ctx, "Collapsed sidebar at launch", "tui_sidebar_collapsed", mine["tui_sidebar_collapsed"],
                             detail="Open the main navigation in compact mode.")]),
            Panel("", [Choice(tr("Reset preferences"), reset, tone="bad")])]

    def _appearance(self, ctx, data, config, mine, ui):
        return [
            Panel(tr("Theme and color"), [
                self._pick(ctx, "Theme", "tui_theme", [(key, theme_label(key)) for key, _label in THEMES], mine["tui_theme"]),
                self._pick(ctx, "Accent color", "tui_accent", [(key, tr(label)) for key, label in preferences.ACCENT_LABELS.items()],
                           mine["tui_accent"], detail="Select the main interface accent used across modules.")]),
            Panel(tr("Layout"), [
                self._pick(ctx, "Density", "tui_density", [(key, tr(label)) for key, label in preferences.DENSITIES.items()],
                           mine["tui_density"]),
                self._switch(ctx, "Live", "tui_live_bar", mine["tui_live_bar"]),
                self._switch(ctx, "Details", "tui_details", mine["tui_details"])])]

    def _hardware(self, ctx, data, config, mine, ui):
        return [Panel(tr("GPU governor"), [
            self._pick(ctx, "GPU governor backend", "gpu_governor", [(key, tr(label)) for key, label in GOVERNORS],
                       str(config.get("gpu_governor") or "auto"), detail=(
                           "Only one GPU governor can be enabled at a time. Preparing another governor will ask before stopping the "
                           "active one."))],
            subtitle=tr("Backends the hardware modules rely on. Frequencies, voltages and fan curves are set in each module."))]

    def _terminal(self, ctx, data, config, mine, ui):
        return [Panel(tr("Built-in terminal"), [
            self._switch(ctx, "Hide the terminal when a workflow finishes without errors", "tui_auto_hide", mine["tui_auto_hide"],
                         detail="A workflow that fails keeps the terminal open so its output can be read."),
            self._pick(ctx, "Sampling interval", "tui_interval", [(value, tr(label)) for value, label in INTERVALS], mine["tui_interval"])])]

    def _telemetry(self, ctx, data, config, mine, ui):
        service, tools = ctx.service, data.get("tools") or {}
        accessories = tools.get("accessories") or {}
        sensors = [row for row in (compat.accessory(service, key, title, detail, accessories.get(key) or {})
                                   for key, title, detail in compat.SENSORS) if row is not None]
        active = bool(data.get("daemon"))

        def flip(ui_):
            enable = not active
            text = tr("This runs systemctl --user enable --now bc250-control-centerd.service. The daemon records telemetry and "
                      "restores the saved fan mode after login: an enabled automatic curve, a named preset or the last manual "
                      "speed. It does not apply overclock automatically.") if enable else \
                tr("This stops and disables bc250-control-centerd.service for the current user. Saved configuration and history "
                   "files are preserved.")
            label = tr("Enable optional daemon" if enable else "Disable optional daemon")
            if ui_.confirm(f"{label}: {text}"):
                guarded(ui_, label, lambda: ui_.shell(daemon_service.command(enable)))

        return [
            Panel(tr("Sensor sources"), [*sensors, Choice(
                tr("Board sensors guide: I2C wiring, bc250-vrm and bc250-memory") + " ›",
                lambda ui_: (ui_.goto("support"), ui_.show_tab("guide")))],
                subtitle=tr("Where the board readings come from, and the background monitor.")),
            Panel(tr("Optional daemon"), [
                switch(tr("Optional daemon"), active, flip, info=Info(tr("bc250-control-centerd keeps sampling while the app is closed."))),
                self._pick(ctx, "Sampling interval", "daemon_interval_seconds", [(value, tr(label)) for value, label in INTERVALS],
                           config.get("daemon_interval_seconds", 2), detail="How often the daemon reads the sensors.")]),
            Panel(tr("Eight-core GPU telemetry"), [compat.component(
                tr("Eight-core GPU telemetry"), "", "dim", "", [
                    compat.Action(tr("Install"), lambda: service.gestionar_acpi("telemetry-fix"), "", True),
                    compat.Action(tr("Restore"), lambda: service.gestionar_acpi("telemetry-restore"))])])]

    def _notifications(self, ctx, data, config, mine, ui):
        rows = [self._switch(ctx, "Alerts", "alertas_activas", bool(config.get("alertas_activas")))]
        for key, label, low, high in ALERT_FIELDS:
            def edit(ui_, key=key, label=label, low=low, high=high):
                value = ui_.ask_int(tr(label), low, high, int(config.get(key) or low))
                if value is not None:
                    self._save(ctx, ui_, {key: value})

            def step(ui_, direction, key=key, low=low, high=high):
                self._save(ctx, ui_, {key: max(low, min(high, int(config.get(key) or low) + direction))})

            rows.append(Choice(tr(label), edit, f"< {config.get(key, '--')} >", adjust=step, id=key))
        return [Panel(tr("Notifications"), rows)]

    def _backup(self, ctx, data, config, mine, ui):
        service = ctx.service
        state = ctx.state(self.key)

        def export(ui_):
            path = ui_.ask_text(tr("Export settings and profiles"), str(Path.home() / "bc250-settings.zip"))
            if path:
                guarded(ui_, tr("Export settings and profiles"), lambda: ctx.settings.export_profile_bundle(Path(path).expanduser()))

        def bring_in(ui_):
            path = ui_.ask_text(tr("Import settings and profiles"), str(Path.home() / "bc250-settings.zip"))
            if not path:
                return
            source = Path(path).expanduser()
            ok, preview = ui_.run(tr("Preview"), lambda: ctx.settings.preview_profile_bundle(source))
            if not ok or not isinstance(preview, dict):
                return
            ui_.show_text(tr("Preview"), "\n".join(f"{key}: {value}" for key, value in preview.items()))
            if ui_.confirm(tr("Import portable settings and profiles"), danger=True):
                guarded(ui_, tr("Import settings and profiles"), lambda: ctx.settings.import_profile_bundle(source))

        def snapshot(ui_):
            if ui_.confirm(tr("Create a recovery snapshot")):
                guarded(ui_, tr("Recovery"), service.create_recovery_snapshot)
                state.pop("snapshots", None)

        def listing(ui_):
            ok, result = ui_.run(tr("Recovery"), service.recovery_inventory)
            if ok:
                state["snapshots"] = result.get("snapshots", result) if isinstance(result, dict) else result

        def plan(ui_, item):
            identity = str(item.get("id") or item.get("snapshot_id") or "") if isinstance(item, dict) else str(item)
            ok, result = ui_.run(tr("Recovery"), lambda: service.recovery_plan(identity))
            if ok:
                ui_.show_text(identity, "\n".join(f"{k}: {v}" for k, v in result.items()) if isinstance(result, dict) else str(result))

        shots = state.get("snapshots") or ()
        return [
            Panel(tr("Export settings and profiles"), [Choice(tr("Export settings and profiles"), export),
                                                       Choice(tr("Import settings and profiles"), bring_in)]),
            Panel(tr("Recovery"), [
                Choice(tr("Create a recovery snapshot"), snapshot), Choice(tr("Refresh"), listing),
                *[Choice(str(item.get("id") or item.get("snapshot_id") or item) if isinstance(item, dict) else str(item),
                         lambda ui_, i=item: plan(ui_, i), str(item.get("created_at") or item.get("label") or "") if isinstance(item, dict) else "")
                  for item in shots],
                *([] if shots else [Note(tr("(empty)"), "dim")])])]
