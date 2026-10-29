"""Black box: the recorder, its latest rows, and the full diagnosis in tabs."""

from __future__ import annotations

from frontends.desktop.core.diagnosis_groups import (
    TABS,
    as_text,
    section_group,
    size_kb,
)

from ..content import Choice, Field, Gap, Grid, Heading, Note
from ..i18n import tr
from .base import Page, guarded

PAGE_ROWS = 12


class BlackBoxPage(Page):
    key = "black_box"
    title = "Black box"
    interval = 2.0

    def tabs(self, ctx):
        return [("recorder", tr("Black box"))] + [(key, tr(label)) for key, label in TABS]

    def load(self, ctx):
        # The diagnosis gathers many files and runs lsblk/journalctl, so it is
        # read once per visit (and on refresh), not on every recorder tick.
        return {"status": ctx.service.blackbox_estado(PAGE_ROWS)}

    def _diagnosis(self, ctx):
        cache = ctx.state(self.key)
        if "sections" not in cache:
            cache["sections"] = None
        return cache

    def build(self, ctx, data, tab, ui):
        if tab and tab != "recorder":
            return self._diagnosis_tab(ctx, tab, ui)
        status = (data or {}).get("status") or {}
        service = ctx.service
        if not status:
            return [Note(ctx.page_error.get(self.key) or tr("Waiting for data…"), "dim")]
        running = bool(status.get("running"))
        autostart = status.get("autostart") or {}
        out = [
            Heading(tr("Black box")),
            Field(tr("State"), str(status.get("state_text") or status.get("state") or "--"), "ok" if running else "warn"),
            Field(tr("Folder"), str(status.get("directory") or "--")),
            Field(tr("Start with the session"), tr("Yes") if autostart.get("enabled") else tr("No")),
        ]
        rows = status.get("rows") or []
        if rows:
            out += [Gap(), Grid(
                ["time", "clock", "busy", "t_gpu", "t_cpu", "volts", "watts", "rpm"],
                [[str(row.get(key, "")) for key in
                  ("time", "clock", "busy", "t_gpu", "t_cpu", "volts", "watts", "rpm")] for row in rows],
            )]

        def start(ui_):
            guarded(ui_, tr("Start"), service.blackbox_iniciar)

        def stop(ui_):
            if ui_.confirm(tr("Stop")):
                guarded(ui_, tr("Stop"), service.blackbox_detener)

        def autostart_toggle(ui_):
            enable = not autostart.get("enabled")
            guarded(ui_, tr("Start with the session"), lambda: service.blackbox_con_la_sesion(enable))

        out += [Gap(), Heading(tr("Actions"))]
        out.append(Choice(tr("Stop"), stop) if running else Choice(tr("Start"), start))
        out.append(Choice(tr("Start with the session"), autostart_toggle,
                          tr("Yes") if autostart.get("enabled") else tr("No"),
                          enabled=bool(autostart.get("supported", True))))
        return out

    def _diagnosis_tab(self, ctx, tab, ui):
        cache = self._diagnosis(ctx)
        sections = cache.get("sections")
        service = ctx.service

        def load(ui_):
            ok, result = ui_.run(tr("Full diagnosis"), service.diagnostico_completo)
            if ok:
                cache["sections"] = list(result)
            ui_.refresh()

        if sections is None:
            return [Choice(tr("View full diagnosis"), load)]
        chosen = [(title, body) for title, body in sections if tab == "all" or section_group(title) == tab]
        out = [Heading(f"{tr(dict(TABS).get(tab, tab))} · {len(chosen)}"),
               Choice(tr("Refresh"), load),
               Choice(tr("Save to a file"), lambda ui_: self._save(ctx, ui_, sections))]
        for title, body in chosen:
            def show(ui_, title=title, body=body):
                ui_.show_text(title, body)
            out.append(Choice(title, show, f"{size_kb(body)} KB"))
        return out

    def _save(self, ctx, ui, sections):
        from pathlib import Path

        path = ui.ask_text(tr("File"), str(Path.home() / "bc250-diagnosis.txt"))
        if not path:
            return
        try:
            Path(path).expanduser().write_text(as_text(sections), encoding="utf-8")
        except OSError as error:
            ui.notify(str(error), "bad")
            return
        ui.notify(f"{tr('Full log saved to')} {path}", "ok")
