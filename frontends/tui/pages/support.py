"""Support: reporting, what was sent, the error handbook, diagnostics, history and the guides."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from bc250cc.application.system.feedback import reports
from bc250cc.shared import known_errors
from bc250cc.shared.version import __version__
from frontends.desktop.core.diagnostic_history import (
    clear_history,
    current_wording,
    diagnostic_report,
    history_entries,
)

from ..content import Choice, Field, Gap, Info, Note, Panel
from ..i18n import current_language, tr, tr_format
from ..support import report
from .base import Page, guarded, os_family
from .guides import GUIDES

TABS = (("report", "Support"), ("errors", "Known errors"), ("sent", "Sent reports"), ("diagnostics", "Diagnostics"),
        ("history", "Movement history"), ("guide", "Guide"))


def when(text: object) -> str:
    try:
        return datetime.fromisoformat(str(text)).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(text or "—")


def entry_text(entry: dict, family: str) -> str:
    """One handbook entry: what is seen, why, and what to do on this system."""
    language = current_language()
    said = known_errors.localized
    parts = [said(entry["guide"]["summary"], language), ""]
    for title, key in (("What you see", "symptom"), ("Why it happens", "cause")):
        parts += [tr(title), said(entry[key], language), ""]
    fix = known_errors.fix_for(entry, family)
    parts.append(tr("How to fix it"))
    if not fix:
        parts.append(tr("Not applicable"))
    for number_, step in enumerate((fix or {}).get("article") or (), 1):
        parts.append(f"{number_}. {said(step['text'], language)}")
        parts += [f"      {command}" for command in step.get("commands") or ()]
    if known_errors.needs_update(entry, __version__):
        parts += ["", tr("Update application")]
    return "\n".join(parts)


class SupportPage(Page):
    key = "support"
    title = "Support"
    interval = 10.0

    def tabs(self, ctx):
        return [(key, tr(label)) for key, label in TABS]

    def load(self, ctx):
        data = {"sent": reports.sent_reports(), "errors": history_entries()}
        try:
            data["activity"] = ctx.activity.list(100) if ctx.activity is not None else []
        except Exception:  # an unreadable history leaves the rest of the page
            data["activity"] = []
        return data

    def build(self, ctx, data, tab, ui):
        data = data or {}
        return {"errors": self._errors, "sent": self._sent, "diagnostics": self._diagnostics, "history": self._history,
                "guide": self._guide}.get(tab, self._report)(ctx, data, ui)

    # -- start -------------------------------------------------------------------------------------

    def _report(self, ctx, data, ui):
        def open_tab(key):
            return lambda ui_: ui_.show_tab(key)

        return [
            Panel(tr("Support"), [
                Choice(tr("Report a problem"), report, info=Info(tr("Tell us what failed. We attach the diagnostics for you."))),
                Choice(tr("Known errors") + " ›", open_tab("errors"), badge=str(len(known_errors.load())),
                       info=Info(tr("Find an error and how to fix it."))),
                Choice(tr("Sent reports") + " ›", open_tab("sent"), badge=str(len(data.get("sent") or ())),
                       info=Info(tr("Keep the ID to ask about a report on GitHub or Discord. The list only exists on this computer."))),
                Choice(tr("Diagnostics") + " ›", open_tab("diagnostics"),
                       info=Info(tr("System diagnostics and the movement history."))),
                Choice(tr("Guide") + " ›", open_tab("guide"))]),
            Panel("GitHub · Discord", [Note("https://github.com/movacx/bc250-control-center/issues", "accent"), Note("Discord: @_movacx", "dim")])]

    # -- the error handbook ------------------------------------------------------------------------

    def _errors(self, ctx, data, ui):
        state, language = ctx.state(self.key), current_language()
        query, module = state.get("query", ""), state.get("module", "")
        names = {item["id"]: item["label"] if not language.startswith("es") else item["title"]["es"] for item in known_errors.modules()}

        def search(ui_):
            text = ui_.ask_text(tr("Search"), query)
            if text is not None:
                state["query"] = text.strip()

        def pick(ui_):
            chosen = ui_.choose(tr("Area"), [("", tr("All")), *names.items()])
            if chosen is not None:
                state["module"] = chosen

        entries = [match.entry for match in known_errors.search_matches(query, module=module)] if query else [
            entry for entry in known_errors.load() if not module or entry["module"] == module]
        family = os_family(ctx)[0]
        rows = [Choice(known_errors.localized(entry["guide"]["title"], language),
                       lambda ui_, e=entry: ui_.show_text(
                           f"{e['id']}  {known_errors.localized(e['guide']['title'], language)}", entry_text(e, family)),
                       badge=entry["id"], id=entry["id"], info=Info("\n\n".join((
                           known_errors.localized(entry["guide"]["summary"], language),
                           " · ".join(entry.get("codes") or ()))))) for entry in entries]
        return [Panel("", [Choice(tr("Search"), search, (query or "--") + " ›"),
                                     Choice(tr("Area"), pick, (names.get(module) or tr("All")) + " ›")]),
                Panel(tr("Known errors"), rows or [Note(tr("No results"), "dim")], badge=str(len(rows)), wide=True)]

    # -- what this computer sent -------------------------------------------------------------------

    def _sent(self, ctx, data, ui):
        def detail(item):
            idea = item.get("kind") == "idea"
            return "\n".join((
                f"{tr('Problem')}: {item.get('summary') or tr('Suggestion')}",
                f"{tr('Area')}: {tr('Suggestion') if idea else tr(str(item.get('area') or '')) or '—'}",
                f"{tr('Code')}: {item.get('code') or '—'}", f"{tr('Version')}: {item.get('version') or '—'}",
                f"{tr('Sent')}: {when(item.get('sent_at'))}",
                *([f"{tr('What was attached')}: {tr('Version and system')} · {tr('Recent logs')} · {tr('System diagnostics')}"]
                  if item.get("attached") else [])))

        items = data.get("sent") or []
        rows = [Choice(str(item["id"]), lambda ui_, i=item: ui_.show_text(str(i["id"]), detail(i)),
                       f"{when(item.get('sent_at'))}   {item.get('summary') or tr('Suggestion')}", id=str(item["id"]),
                       info=Info(detail(item))) for item in items]
        return [Panel(tr("Sent reports"), rows or [Note(tr("No reports sent yet. Each report you send shows here with its ID."), "dim")],
                      badge=str(len(rows)), subtitle=tr(
                          "Keep the ID to ask about a report on GitHub or Discord. The list only exists on this computer."), wide=True)]

    # -- diagnostics -------------------------------------------------------------------------------

    def _diagnostics(self, ctx, data, ui):
        state = ctx.state(self.key)

        def read(ui_):
            from bc250cc.application.system.diagnostics import system_rows

            ok, result = ui_.run(tr("Diagnostics"), system_rows)
            if ok:
                state["system"] = result

        def save(ui_):
            path = ui_.ask_text(tr("File"), str(Path.home() / "bc250-diagnostics.txt"))
            if path:
                text = diagnostic_report(state.get("system") or [], data.get("errors") or [])
                ok, _result = ui_.run(tr("Save to a file"), lambda: Path(path).expanduser().write_text(text, encoding="utf-8"))
                ui_.notify(f"{tr('Saved')} · {path}" if ok else tr("The report was not sent."), "ok" if ok else "bad")

        def clear(ui_):
            if ui_.confirm(tr("Clear history"), danger=True):
                clear_history()
                ui_.refresh()

        rows = []
        for entry in data.get("errors") or ():
            wording = current_wording(entry)
            stamp = datetime.fromtimestamp(entry.at).strftime("%m-%d %H:%M")
            where = {"terminal": tr("Terminal"), "decky": tr("Decky Quick Access")}.get(entry.source, tr("Window"))
            text = "\n\n".join(filter(None, (tr(wording.summary), tr(wording.cause), tr(wording.action), entry.detail)))
            rows.append(Choice(f"{stamp}  {entry.code}", lambda ui_, t=text, c=entry.code: ui_.show_text(c, t), tr(wording.summary),
                               id=f"{entry.at}", info=Info(f"{where} · {entry.title}\n\n{tr(wording.cause)}", undo="", risk="")))
        system = [Field(tr(label), tr(value)) for label, value in state.get("system") or ()]
        return [Panel(tr("System"), [*system, *([Gap()] if system else []),
                                     Choice(tr("Refresh") if system else tr("Diagnostics"), read),
                                     Choice(tr("Save to a file"), save)], wide=True),
                Panel(tr("Diagnostic history"), [*(rows or [Note(tr(
                    "No errors recorded. Every error Control Center explains, in a window or in the terminal, appears here."), "dim")]),
                    *([Choice(tr("Clear history"), clear, tone="bad")] if rows else [])], badge=str(len(rows)), wide=True)]

    # -- what the application did ------------------------------------------------------------------

    def _history(self, ctx, data, ui):
        from frontends.desktop.i18n import translate_history_event

        rows = []
        for event in data.get("activity") or ():
            title, detail = translate_history_event(event)
            stamp = str(event.get("fecha") or "") if isinstance(event, dict) else ""
            rows.append(Choice(f"{stamp[:16]}  {title}", lambda ui_, t=title, d=detail: ui_.show_text(t, d), id=f"{stamp}{title}",
                               dense=True, info=Info(detail)))

        def clear(ui_):
            if ctx.activity is not None and ui_.confirm(tr("Clear history"), danger=True):
                guarded(ui_, tr("Clear history"), ctx.activity.clear)

        return [Panel(tr("Movement history"), [*(rows or [Note(tr("No recent activity"), "dim")]),
                                               *([Choice(tr("Clear history"), clear, tone="bad")] if rows else [])],
                      badge=str(len(rows)), wide=True)]

    # -- guides ------------------------------------------------------------------------------------

    def _guide(self, ctx, data, ui):
        return [Panel(tr("Guide"), [
            Choice(tr(title) + " ›", lambda ui_, t=title, b=build: ui_.show_text(tr(t), b()), info=Info(tr(summary) if summary else ""))
            for title, summary, build in GUIDES],
            subtitle=tr_format("Version {version} is available", version=__version__) if False else "")]
