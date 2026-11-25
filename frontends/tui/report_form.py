"""The problem report, as the terminal fills it in: the desktop's questions, one value each."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from bc250cc.application.system.feedback import reports as form
from bc250cc.shared.version import application_version

#: The part of the app each page of this interface is.
AREA_BY_PAGE = {"dashboard": "DASH", "cpu": "CPU", "cu": "CU", "gpu": "GPU", "extras": "DIST", "performance": "TEL",
                "fans": "FAN", "processes": "PROC", "firmware": "FW", "settings": "SET", "about": "UPD",
                "support": "DIAG", "black_box": "TEL"}
TEXTS = ("summary", "code", "steps", "expected", "media", "contact", "notes", "terminal", "version",
         "area", "frequency", "worked_before", "distribution", "install", "bios", "cores", "cus")


@dataclass
class Draft:
    """What has been written so far; nothing leaves this computer until Send."""

    kind: str = form.KIND_PROBLEM
    values: dict[str, str] = field(default_factory=dict)
    seen: set[str] = field(default_factory=set)
    other_tools: set[str] = field(default_factory=set)
    attach: bool = True
    title: str = ""  # of the error it is about; empty for a report someone starts by themselves
    raw: str = ""
    where: str = ""
    reference: str = ""
    details: dict = field(default_factory=dict)
    facts: dict = field(default_factory=dict)
    complete: bool = False  # the facts include the diagnosis
    earlier: str = ""
    sent: str = ""  # its ID, once it left

    @property
    def from_error(self) -> bool:
        return bool(self.title)

    def get(self, key: str) -> str:
        return self.values.get(key, "")


def new_draft(*, title: str = "", log: str = "", error: BaseException | None = None, page: str = "", details=None) -> Draft:
    """A report, with what the failure it is about already says."""
    from frontends.desktop.core.error_diagnostics import diagnose_error

    draft = Draft(title=title, details=dict(details or {}))
    draft.values["version"] = application_version()
    if not title:
        return draft
    draft.raw = str(error or "").strip()
    if error is not None:
        draft.where = where_of(error)
    diagnosis = diagnose_error(draft.raw or log or title, context=title)
    draft.values.update(summary=title, code=diagnosis.code or "", terminal=form.clean_log(log))
    draft.seen.add(form.SEEN[1] if log.strip() else form.SEEN[0])
    area = form.AREA_BY_SECTION.get(AREA_BY_PAGE.get(page, "")) or form.suggested_area(title)
    if area:
        draft.values["area"] = area
    known = form.earlier_report(draft.get("code"), title, application_version())
    draft.earlier = str(known["id"]) if known else ""
    return draft


def where_of(error: BaseException) -> str:
    """The function that raised it, as the desktop's error window says it."""
    import os
    import traceback

    frames = traceback.extract_tb(error.__traceback__)
    if not frames:
        return ""
    last = frames[-1]
    return f"Raised in: {os.path.basename(last.filename)} · {last.name}"


def read_light_facts(draft: Draft) -> None:
    """Fill in the system's part of the form, off the drawing thread and without asking for a password."""
    def read() -> None:
        from frontends.desktop.core.report_facts import read_report_facts

        try:
            facts = read_report_facts(attachments=False)
        except Exception:  # the report still goes, with what was written
            return
        if not draft.complete:
            draft.facts = facts
        prefill(draft, facts)

    threading.Thread(target=read, name="bc250-tui-report", daemon=True).start()


def prefill(draft: Draft, facts: dict) -> None:
    for key in ("install", "cores", "distribution", "bios"):
        if facts.get(key):
            draft.values.setdefault(key, str(facts[key]))


def read_all_facts(draft: Draft) -> None:
    """The diagnosis too. Reading the kernel log may ask for the password, so this runs in the console pane."""
    if draft.complete or not draft.attach or draft.kind != form.KIND_PROBLEM:
        return
    from frontends.desktop.core.report_facts import read_report_facts

    draft.facts = read_report_facts()
    draft.complete = True
    prefill(draft, draft.facts)


def report_of(draft: Draft) -> form.Report:
    """The document, exactly what Send sends and what the preview shows."""
    from frontends.desktop.core.error_diagnostics import diagnose_error, explain_code
    from frontends.desktop.i18n import canonical_source, current_language

    get, facts = draft.get, draft.facts
    common = {"version": get("version") or application_version(), "opened_from": "tui", "language": current_language(),
              "contact": get("contact"), "notes": get("notes")}
    if draft.kind != form.KIND_PROBLEM:
        return form.Report(kind=form.KIND_IDEA, **common)
    code = get("code").strip()
    if not code and draft.raw:
        code = diagnose_error(draft.raw).code
    known = explain_code(code) if code else None
    automatic = {}
    if draft.attach:
        automatic = {key: dict(facts.get(key) or {}) for key in ("identity", "system", "os_release", "firmware")}
        automatic["history"] = [{**item, "title": canonical_source(item["title"])} for item in form.history_items(
            facts.get("history") or (), exclude_raw=draft.raw, exclude_title=draft.title)]
        automatic["attachments"] = [(str(name), str(text)) for name, text in facts.get("attachments") or ()]
    return form.Report(
        kind=form.KIND_PROBLEM, seen=[item for item in form.SEEN if item in draft.seen],
        other_tools=[item for item in form.OTHER_TOOLS if item in draft.other_tools],
        error=form.ErrorEvidence(code=code, title=draft.title, where=draft.where, raw=draft.raw, reference=draft.reference,
                                 what=known.summary if known else "", cause=known.cause if known else "",
                                 fix=known.action if known else ""),
        workflow_title=(draft.title or get("summary")) if get("terminal").strip() else "",
        workflow_log=form.clean_log(get("terminal")), workflow_details=dict(draft.details),
        **{key: get(key) for key in ("summary", "area", "frequency", "worked_before", "steps", "expected", "media",
                                     "distribution", "install", "bios", "cores", "cus")},
        **common, **automatic)
