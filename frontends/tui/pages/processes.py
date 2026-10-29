"""Processes: what runs, and the same close / pause / cache actions."""

from __future__ import annotations

from ..content import Choice, Gap, Heading, Note, size
from ..i18n import tr
from .base import Page, guarded

MAX_ROWS = 200


class ProcessesPage(Page):
    key = "processes"
    title = "Processes"
    interval = 4.0

    def load(self, ctx):
        return ctx.service.procesos(ocultar_sistema=True)

    def build(self, ctx, data, tab, ui):
        service = ctx.service
        processes = sorted(data or [], key=lambda proc: getattr(proc, "memoria", 0), reverse=True)[:MAX_ROWS]
        out = [Heading(tr("Processes"))]
        if not processes:
            out.append(Note(ctx.page_error.get(self.key) or tr("Waiting for data…"), "dim"))
        for proc in processes:
            name = str(getattr(proc, "nombre", "?"))
            pid = getattr(proc, "pid", 0)
            protected = bool(getattr(proc, "protegido", False))

            def act(ui_, proc=proc, name=name, pid=pid):
                choice = ui_.choose(f"{name} ({pid})", [
                    ("close", tr("Close")), ("pause", tr("Pause")), ("resume", tr("Resume")),
                ])
                if choice is None:
                    return
                if choice == "close":
                    if ui_.confirm(f"{tr('Close')}: {name} ({pid})", danger=True):
                        guarded(ui_, tr("Close"), lambda: service.cerrar_procesos([proc]))
                else:
                    paused = choice == "pause"
                    guarded(ui_, name, lambda: service.pausar_procesos([proc], pausar=paused))

            out.append(Choice(
                name, act if not protected else None,
                f"{pid:>7}  {size(getattr(proc, 'memoria', None)):>10}" + ("  *" if protected else ""),
                enabled=not protected, tone="dim" if protected else "",
            ))

        def clean(ui_):
            if ui_.confirm(tr("Release Linux page cache")):
                guarded(ui_, tr("Free cache"), service.limpiar_cache)

        out += [Gap(), Heading(tr("Actions")), Choice(tr("Free cache"), clean)]
        return out
