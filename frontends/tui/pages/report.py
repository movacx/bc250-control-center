"""Report a problem: the desktop's form, a row for each question.

It opens empty from the sidebar, and filled in with the error, its code and
its log when something fails and the person accepts to report it.
"""

from __future__ import annotations

import json

from bc250cc.application.system.feedback import reports as form

from .. import report_form
from ..content import Buttons, Choice, Field, Info, Note, Panel, clip
from ..i18n import tr, tr_format
from .base import Page, switch


class ReportPage(Page):
    key = "report"
    title = "Report a problem"
    loads = False

    def __init__(self) -> None:
        self._draft: report_form.Draft | None = None

    def open(self, draft: report_form.Draft) -> None:
        """Start over with ``draft`` (a failure to report)."""
        self._draft = draft
        report_form.read_light_facts(draft)

    def draft(self) -> report_form.Draft:
        if self._draft is None:
            self.open(report_form.new_draft())
        return self._draft

    def build(self, ctx, data, tab, ui):
        draft = self.draft()
        if draft.sent:
            return [Panel(tr("Thanks, it was sent"), [
                Field("ID", draft.sent, "ok"),
                Note(tr("The developer reads every report. If you left a username, the answer arrives there."), "dim"),
                Choice(tr("Sent reports") + " ›", lambda ui_: (ui_.goto("support"), ui_.show_tab("sent"))),
                Choice(tr("Report a problem"), lambda ui_: self.open(report_form.new_draft()))])]
        kind = self._kind(draft)
        if draft.kind != form.KIND_PROBLEM:
            return [Panel(tr("Suggest an idea"), [kind, self._text(draft, "notes", "Suggestions and ideas", required=True),
                                                  self._contact(draft)]), self._send_panel(draft), self._elsewhere()]
        return [*([self._about(draft)] if draft.from_error else []), self._problem(draft, kind), self._system(draft),
                self._extra(draft), self._send_panel(draft),
                *([self._automatic(draft)] if draft.attach else []), self._elsewhere()]

    # -- rows -------------------------------------------------------------------------------------

    @staticmethod
    def _kind(draft):
        names = {form.KIND_PROBLEM: tr("Report a problem"), form.KIND_IDEA: tr("Suggest an idea")}

        def swap(ui_, _direction=1):
            draft.kind = form.KIND_IDEA if draft.kind == form.KIND_PROBLEM else form.KIND_PROBLEM

        return Choice(tr("Type"), swap, f"< {names[draft.kind]} >", adjust=swap)

    @staticmethod
    def _text(draft, key, label, *, required=False, hint=""):
        value = draft.get(key)
        lines = value.strip().splitlines()
        shown = lines[0] if lines else tr("Required") if required else "—"
        if len(lines) > 1:
            shown = lines[-1].strip() + " …"

        def edit(ui_):
            if len(lines) > 1:  # a captured log: read or removed, never retyped on one line
                picked = ui_.choose(tr(label), [("read", tr("Details")), ("clear", tr("Remove"))])
                if picked == "read":
                    ui_.show_text(tr(label), value)
                elif picked == "clear":
                    draft.values[key] = ""
                return
            text = ui_.ask_text(tr(label), value)
            if text is not None:
                draft.values[key] = text.strip()

        return Choice(tr(label), edit, clip(shown, 200), tone="warn" if required and not lines else "", id=key,
                      info=Info(tr(hint)) if hint else None)

    @staticmethod
    def _pick(draft, key, label, options):
        def choose(ui_):
            picked = ui_.choose(tr(label), [("", "—"), *((item, tr(item)) for item in options)])
            if picked == form.OTHER:
                picked = ui_.ask_text(tr(label), "" if draft.get(key) in options else draft.get(key))
            if picked is not None:
                draft.values[key] = picked.strip()

        value = draft.get(key)
        return Choice(tr(label), choose, (tr(value) if value else "—") + " ›", id=key)

    @staticmethod
    def _checks(store, options):
        def toggle(item):
            return lambda ui_: store.symmetric_difference_update({item})

        return [Choice(f"[{'x' if item in store else ' '}] {tr(item)}", toggle(item), id=item) for item in options]

    def _contact(self, draft):
        return self._text(draft, "contact", "Telegram or Discord username", hint="Optional. Only if you want an answer.")

    # -- sections ---------------------------------------------------------------------------------

    @staticmethod
    def _about(draft):
        """The failure this report is about, already attached."""
        from frontends.desktop.core.error_diagnostics import explain_code

        known = explain_code(draft.get("code")) if draft.get("code") else None
        rows = [Note(draft.title, "bad")]
        if known is not None:
            rows += [Note(f"{draft.get('code')} · {tr(known.summary)}"), Note(tr(known.action), "dim")]
        if draft.earlier:
            rows.append(Note(tr_format("You already sent this one: {id}. Send it again only if something changed.",
                                       id=draft.earlier), "warn"))
        return Panel(tr("Operation failed"), rows, wide=True)

    def _problem(self, draft, kind):
        rows = [kind, self._text(draft, "summary", "What went wrong?", required=True, hint=form.SUMMARY_HINT),
                self._pick(draft, "area", "Which part of the app?", form.AREAS)]
        if not draft.from_error:
            rows += [self._text(draft, "code", "Error code"),
                     self._pick(draft, "frequency", "How often does it happen?", form.FREQUENCIES),
                     self._pick(draft, "worked_before", "Did it work before?", form.WORKED_BEFORE)]
        rows.append(self._text(draft, "steps", "What were you doing just before?" if draft.from_error else "Steps to reproduce"))
        if not draft.from_error:
            rows.append(self._text(draft, "expected", "What did you expect to happen?"))
            rows += [Note(tr("What did you see?"), "dim"), *self._checks(draft.seen, form.SEEN)]
        return Panel(tr("Problem"), rows)

    def _system(self, draft):
        return Panel(tr("Your system"), [
            self._pick(draft, "distribution", "Distribution", (*form.DISTRIBUTIONS,)),
            self._text(draft, "version", "Control Center version"),
            self._pick(draft, "install", "How did you install it?", form.INSTALLS),
            self._pick(draft, "bios", "BIOS", form.BIOSES), self._pick(draft, "cores", "CPU cores", form.CORES),
            self._pick(draft, "cus", "GPU compute units", form.CUS),
            Note(tr("Other BC-250 tools you used on this system"), "dim"), *self._checks(draft.other_tools, form.OTHER_TOOLS)],
            subtitle=tr("Filled in from this system. Change anything that is wrong."))

    def _extra(self, draft):
        return Panel(tr("Logs") + " · " + tr("Contact and ideas"), [
            self._text(draft, "terminal", "Terminal output"), self._text(draft, "media", "Screenshot or video link"),
            self._contact(draft), self._text(draft, "notes", "Suggestions and ideas")])

    @staticmethod
    def _automatic(draft):
        facts = draft.facts
        attachments = facts.get("attachments") or ()
        size = sum(len(str(text)) for _name, text in attachments) // 1024
        rows = [Field(tr("Error code"), draft.get("code"))] if draft.get("code") else []
        if draft.where:
            label, _sep, value = draft.where.partition(": ")
            rows.append(Field(tr(label), value))
        rows += [Field(tr("System specifications"), tr("Included") if facts.get("system") else "…"),
                 Field(tr("Hardware diagnostics"), tr_format("{count} sections · {size} KB", count=len(attachments), size=size)
                       if attachments else "…"),
                 Field(tr("Terminal output"), tr("Included") if draft.get("terminal") else "—")]
        return Panel(tr("Automatic report"), rows)

    @staticmethod
    def _elsewhere():
        return Panel("GitHub · Discord", [Note("https://github.com/movacx/bc250-control-center/issues"),
                                          Note("Discord: @_movacx", "dim")])

    # -- sending ----------------------------------------------------------------------------------

    def _send_panel(self, draft):
        rows = []
        if draft.kind == form.KIND_PROBLEM:
            def flip(ui_):
                draft.attach = not draft.attach

            rows.append(switch(tr("Send the automatic report"), draft.attach, flip, info=Info(tr(
                "The error, where it happened, this system's specifications and the recent errors.") + " " + tr(
                "Linux may ask for your password once to read the kernel log for this report. "
                "If you cancel it, the report is still sent, without that log."))))
        rows.append(Buttons([
            Choice(tr("See what is sent"), lambda ui_: self._preview(draft, ui_)),
            Choice(tr("Send"), lambda ui_: self._send(draft, ui_), tone="primary"),
            Choice(tr("Discard"), lambda ui_: self._discard(draft, ui_), id="revert")]))
        return Panel(tr("Send"), rows, subtitle=tr("Goes straight to the developer. Only the developer sees it."))

    def _discard(self, draft, ui):
        if ui.confirm(tr("Discard")):
            self.open(report_form.new_draft())

    @staticmethod
    def _document(draft, ui, label):
        """``(report, its text)`` once everything it carries has been read, or None.

        In the console pane: reading the logs may ask for a password, and
        finding what is personal in them asks the system too.
        """
        def build():
            report_form.read_all_facts(draft)
            document = report_form.report_of(draft)
            return document, json.dumps(form.payload(document), indent=2, ensure_ascii=False)

        ok, built = ui.run(label, build)
        return built if ok and isinstance(built, tuple) else None

    def _preview(self, draft, ui):
        built = self._document(draft, ui, tr("See what is sent"))
        if built is not None:
            ui.show_text(tr("See what is sent"), built[1])

    def _send(self, draft, ui):
        missing = report_form.report_of(draft).missing()
        if missing:
            ui.notify(tr(form.SUMMARY_HINT) if draft.kind == form.KIND_PROBLEM
                      else tr_format("Answer this first: {question}", question=tr(missing)), "warn")
            return
        built = self._document(draft, ui, tr("Automatic report"))
        if built is None or not ui.confirm(f"{tr('Send')}: {tr('Goes straight to the developer. Only the developer sees it.')}"):
            return

        def send() -> str:
            try:
                return form.submit(built[0])
            except form.ReportError as error:
                message = tr_format("It was not sent: {reason}. What you wrote is still here.",
                                    reason=tr(str(error)).rstrip("."))
                if error.saved is not None:
                    message += " " + tr_format("A copy was saved to {path}.", path=str(error.saved))
                raise RuntimeError(message) from error

        ok, result = ui.run(tr("Send"), send)
        if ok:
            draft.sent = str(result)
            ui.notify(f"{tr('Thanks, it was sent')} ({result})", "ok")
        else:
            ui.notify(str(result), "bad")
