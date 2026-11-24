"""Processes: the desktop's table of applications, with the same protected close and pause."""

from __future__ import annotations

from frontends.desktop.core.process_entries import build_entries

from ..content import Choice, Info, Note, Panel, cell_width, clip, number, pad, size
from ..i18n import tr, tr_format
from .base import Page, guarded

MAX_ROWS = 200
TABS = (("apps", "Applications"), ("background", "Background"), ("system", "System"), ("all", "All"))
SORTS = (("memory", "Memory"), ("cpu", "CPU"), ("gpu", "GPU"), ("vram", "GPU memory"), ("name", "Name"))
#: Columns after the name: CPU, GPU, memory, GPU memory.
WIDTHS = (7, 7, 11, 11)


class ProcessesPage(Page):
    key = "processes"
    title = "Processes"
    interval = 4.0

    def tabs(self, ctx):
        return [(key, tr(label)) for key, label in TABS]

    def load(self, ctx):
        return ctx.service.inventario_procesos()

    def build(self, ctx, data, tab, ui):
        service, state = ctx.service, ctx.state(self.key)
        data = data if isinstance(data, dict) else {}
        picked: set[str] = state.setdefault("picked", set())
        sort, query = state.setdefault("sort", "memory"), state.setdefault("query", "")
        entries = build_entries(data.get("processes") or (), grouped=True, view=tab or "apps", query=query)
        entries.sort(key=lambda entry: entry.sort_value(sort), reverse=sort != "name")
        picked.intersection_update(entry.key for entry in entries)
        out = []
        game = next((entry for entry in entries if entry.kind == "game"), None)
        if game is not None:
            out.append(Panel(game.name, [
                Note(self._numbers(game), ""),
                Choice(tr("Resume game" if game.paused else "Pause game"),
                       lambda ui_: self._pause(ui_, service, [game]), enabled=bool(game.closable))],
                badge=tr("Paused" if game.paused else "Running"), badge_tone="warn" if game.paused else "ok"))

        def find(ui_):
            text = ui_.ask_text(tr("Search"), query)
            if text is not None:
                state["query"] = text.strip()

        def order(ui_):
            chosen = ui_.choose(tr("Sort by"), [(key, tr(label)) for key, label in SORTS])
            if chosen is not None:
                state["sort"] = chosen

        chosen = [entry for entry in entries if entry.key in picked]
        out.append(Panel("", [
            Choice(tr("Search"), find, (query or "--") + " ›"),
            Choice(tr("Sort by"), order, tr(dict(SORTS)[sort]) + " ›"),
            Choice(tr("End selected tasks") if chosen else tr("No applications selected"),
                   lambda ui_: self._end(ui_, service, chosen), tone="bad", enabled=bool(chosen)),
            Choice(tr("Resume" if chosen and all(e.paused for e in chosen) else "Pause"),
                   lambda ui_: self._pause(ui_, service, chosen), enabled=bool(chosen)),
            Choice(tr("Free cache"), lambda ui_: ui_.confirm(tr("Release Linux page cache"))
                   and guarded(ui_, tr("Free cache"), service.limpiar_cache)),
        ], subtitle=tr("systemd-oomd is running: if the paused game's memory goes to swap, it may close the game and "
                       "Steam with it.") if data.get("oomd") and game is not None and game.paused else ""))
        name_w = min(34, max([cell_width(entry.name) for entry in entries] + [12]) + 5)
        heads = (tr("CPU"), tr("GPU"), tr("Memory"), tr("GPU memory"))
        rows = [Note(" " * name_w + "".join(clip(head, width - 1).rjust(width) for head, width in zip(heads, WIDTHS)), "dim")]
        if not entries:
            rows.append(Note(ctx.page_error.get(self.key) or (tr("No results") if data else tr("Waiting for data…")), "dim"))
        rows += [self._row(service, picked, entry, name_w) for entry in entries[:MAX_ROWS]]
        return [*out, Panel(tr("Processes"), rows, badge=str(len(entries)))]

    @staticmethod
    def _numbers(entry) -> str:
        return (f"CPU {number(entry.cpu, '%')}   GPU {number(entry.gpu, '%')}   {tr('Memory')} {size(entry.memory)}   "
                f"{tr('GPU memory')} {size(entry.vram)}")

    def _row(self, service, picked, entry, name_w):
        mark = "[x] " if entry.key in picked else "    " if entry.fully_protected else "[ ] "
        cells = (number(entry.cpu, "%"), number(entry.gpu, "%"), size(entry.memory), size(entry.vram) if entry.vram else "--")

        def toggle(_ui):
            picked.symmetric_difference_update({entry.key})

        status, _tone, reason = entry.status()
        return Choice(pad(mark + entry.name, name_w) + "".join(cell.rjust(width) for cell, width in zip(cells, WIDTHS)),
                      None if entry.fully_protected else toggle, dense=True, enabled=not entry.fully_protected, id="app:" + entry.key,
                      tone="dim" if entry.fully_protected else "",
                      info=Info(f"{tr(status)} · {entry.subtitle}", "", "", reason if entry.fully_protected else ""))

    @staticmethod
    def _end(ui, service, entries):
        targets = [process for entry in entries for process in entry.closable]
        kept = sum(entry.protected_count for entry in entries)
        names = ", ".join(entry.name for entry in entries[:6])
        note = " " + tr_format("Partial · {count} protected", count=kept) if kept else ""
        if targets and ui.confirm(f"{tr('Close')}: {names} ({len(targets)}){note}", danger=True):
            guarded(ui, tr("Close"), lambda: service.cerrar_procesos(targets))

    @staticmethod
    def _pause(ui, service, entries):
        targets = [process for entry in entries for process in entry.closable]
        pausing = not all(entry.paused for entry in entries)
        if targets:
            guarded(ui, tr("Pause" if pausing else "Resume"), lambda: service.pausar_procesos(targets, pausar=pausing))
