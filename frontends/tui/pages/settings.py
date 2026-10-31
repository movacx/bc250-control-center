"""Settings: language, appearance, alerts, history and recovery."""

from __future__ import annotations

from bc250cc.shared.version import __version__
from frontends.desktop.i18n import LANGUAGE_OPTIONS

from ..content import Choice, Field, Gap, Heading, Note
from ..i18n import current_language, set_language, tr, tr_format
from ..support import available_version, check_in_background, install_update, report
from .base import Page, guarded, os_family

THEMES = (("auto", "System"), ("light", "Light"), ("dark", "Dark"), ("mono", "No colour"))
TABS = (("general", "General"), ("notifications", "Notifications"), ("history", "History & reports"),
        ("security", "Security"), ("about", "About"))
ALERT_FIELDS = (
    ("ram_warning_percent", "RAM warning (%)", 50, 99),
    ("ram_critical_percent", "RAM critical (%)", 50, 100),
    ("swap_warning_percent", "Swap warning (%)", 10, 100),
    ("gpu_temp_warning", "GPU temperature warning", 60, 110),
    ("cpu_temp_warning", "CPU temperature warning", 60, 110),
)


class SettingsPage(Page):
    key = "settings"
    title = "Settings"
    interval = 5.0

    def tabs(self, ctx):
        return [(key, tr(label)) for key, label in TABS]

    def load(self, ctx):
        return {"config": ctx.settings.read_local_config()}

    def _save(self, ctx, ui, updates: dict) -> None:
        def write():
            config = ctx.settings.read_local_config()
            config.update(updates)
            ctx.settings.save_local_config(config)
            ctx.page_data.setdefault(self.key, {})["config"] = config
            return tr("Saved")

        guarded(ui, tr("Settings"), write)

    def build(self, ctx, data, tab, ui):
        config = (data or {}).get("config") or {}
        tab = tab or "general"
        service = ctx.service
        out = [Heading(tr(dict(TABS).get(tab, tab)))]
        if tab == "general":
            def language(ui_):
                chosen = ui_.choose(tr("Language"), [(code, name) for code, name in LANGUAGE_OPTIONS])
                if chosen is None:
                    return
                set_language(chosen)
                self._save(ctx, ui_, {"idioma": chosen})

            def theme(ui_):
                chosen = ui_.choose(tr("Theme"), [(code, tr(name)) for code, name in THEMES])
                if chosen is not None:
                    ctx.state("ui")["theme"] = chosen
                    ui_.apply_theme(chosen)
                    ui_.notify(tr("Saved"), "ok")

            out += [Choice(tr("Language"), language, f"{config.get('idioma', 'auto')} ({current_language()})"),
                    Choice(tr("Theme"), theme, str(ctx.state("ui").get("theme", "auto")))]
        elif tab == "notifications":
            out.append(Field(tr("Alerts"), tr("Yes") if config.get("alertas_activas") else tr("No")))

            def toggle(ui_):
                self._save(ctx, ui_, {"alertas_activas": not config.get("alertas_activas")})

            out.append(Choice(tr("Alerts"), toggle))
            for key, label, low, high in ALERT_FIELDS:
                def edit(ui_, key=key, label=label, low=low, high=high):
                    value = ui_.ask_int(tr(label), low, high, int(config.get(key) or low))
                    if value is not None:
                        self._save(ctx, ui_, {key: value})

                out.append(Choice(tr(label), edit, str(config.get(key, "--"))))
        elif tab == "history":
            def snapshot(ui_):
                if ui_.confirm(tr("Create a recovery snapshot")):
                    guarded(ui_, tr("Recovery"), service.create_recovery_snapshot)

            def snapshots(ui_):
                ok, result = ui_.run(tr("Recovery"), service.recovery_inventory)
                if ok:
                    lines = [str(item) for item in (result or [])] or [tr("(empty)")]
                    ui_.show_text(tr("Recovery"), "\n".join(lines))

            def diagnose(ui_):
                from bc250cc.application.system.diagnostics import collect_diagnostics

                ok, result = ui_.run(tr("Diagnostics"), collect_diagnostics)
                if ok:
                    ui_.show_text(tr("Diagnostics"), str(result))

            def events(ui_):
                from frontends.desktop.i18n import translate_history_event

                lines = []
                for event in ctx.activity.list(100) if ctx.activity is not None else []:
                    title, detail = translate_history_event(event)
                    lines.append(f"{event.get('fecha', '') if isinstance(event, dict) else ''} {title}: {detail}".strip())
                ui_.show_text(tr("History & reports"), "\n".join(lines) or tr("(empty)"))

            from .extras import INSTALL, run

            out += [Choice(tr("Diagnostics"), diagnose), Choice(tr("Recovery"), snapshots),
                    Choice(tr("Create a recovery snapshot"), snapshot), Choice(tr("History & reports"), events),
                    # The desktop keeps these two with its settings and dashboard, not with Additional settings.
                    Choice(tr("BC250-Telemetry service") + " ›", lambda ui_: run(
                        ui_, "BC250-Telemetry service", ctx.service.gestionar_apu_telemetry, INSTALL)),
                    Choice(tr("Eight-core GPU telemetry") + " ›", lambda ui_: run(
                        ui_, "Eight-core GPU telemetry", ctx.service.gestionar_acpi,
                        (("telemetry-fix", "Install"), ("telemetry-restore", "Restore"))))]
        elif tab == "security":
            out.append(Field(tr("Discreet mode"), tr("Yes") if config.get("modo_discreto") else tr("No")))
        else:
            out += self._about(ctx)
        return out

    def _about(self, ctx):
        status = ctx.state("ui").get("update")
        newer = available_version(ctx)

        def check(ui_):
            check_in_background(ctx, force=True)
            ui_.notify(tr("Checking…"))

        def update(ui_):
            if ui_.confirm(f"{tr('Update now')}: {__version__} → {newer}"):
                guarded(ui_, tr("Update now"), lambda: install_update(ctx, os_family(ctx)[0]))

        if newer:
            state, tone = tr_format("Version {version} is available", version=newer), "warn"
        elif status is not None:
            state, tone = tr("You have the latest version."), "ok"
        else:  # not asked yet, switched off, or no network: nothing to claim
            state, tone = "", ""
        return [Field(tr("Version"), f"{__version__}  ·  {state}" if state else __version__, tone),
                Choice(tr("Update now"), update, enabled=bool(newer), tone="accent"),
                Choice(tr("Check for updates"), check),
                Choice(tr("Report a problem or suggest an idea"), report),
                Gap(), Note("https://github.com/movacx/bc250-control-center", "dim")]
