"""A report sends what did not fit in Google's 32 KB as attachments.

The first week of reports lost the end of long workflows, the unfiltered
kernel log and the service journals to the size limit. Attachments are
further responses of the same form, tied to the report by its Report ID.
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pytest

from bc250cc.infrastructure import feedback_form as form
from bc250cc.infrastructure import report_attachments

LIVE = Path(__file__).resolve().parents[1] / "fixtures" / "feedback_form_live_2026-10-27.json"
CONFIRMED = '<div class="freebirdFormviewerViewResponseConfirmationMessage">Recorded</div>'


def live_page() -> str:
    data = json.loads(LIVE.read_text(encoding="utf-8"))
    return (
        '<form><input name="fbzx" value="-42"></form>'
        f"<script>var FB_PUBLIC_LOAD_DATA_ = {json.dumps(data)};</script>"
    )


def _fields(request) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(request.data.decode("utf-8"))


def test_the_live_form_routes_each_kind_through_its_own_pages():
    shape = form.parse_form(live_page())
    assert shape.problem_pages == "0,1,2,3,4,5"
    assert shape.idea_pages == "0,5"
    assert shape.attachment_pages == "0,6"


def test_a_report_and_its_attachments_share_one_id(monkeypatch):
    monkeypatch.setattr(form, "_last_sent", 0.0)
    sent = []

    def fetch(request):
        sent.append(request)
        return live_page() if request.data is None else CONFIRMED

    monkeypatch.setattr(form.time, "sleep", lambda _s: None)
    report = form.FeedbackReport(
        summary="CU failed",
        details="Sent from: Control Center",
        terminal="noise\n" * 9000 + "ERROR: what failed",
        attachments=[("System state", "== Storage ==\n" + "x" * 50_000)],
    )
    form.submit(report, fetch=fetch, clock=lambda: 1000.0)

    posts = [request for request in sent if request.data is not None]
    main, *attachments = posts
    details = _fields(main)[f"entry.{form.ENTRY_DETAILS}"][0]
    report_id = details.split("\n", 1)[0].removeprefix("Report ID: ")
    assert report_id.startswith("R-")
    assert attachments
    names = []
    for request in posts:
        assert len(request.data) <= form.MAX_POST_BYTES
    for request in attachments:
        fields = _fields(request)
        assert fields[f"entry.{form.ENTRY_KIND}"] == [form.KIND_ATTACHMENT]
        assert fields[f"entry.{form.ENTRY_ATTACH_REPORT}"] == [report_id]
        assert fields["pageHistory"] == ["0,6"]
        names.append(fields[f"entry.{form.ENTRY_ATTACH_NAME}"][0])
    assert any(name.startswith("System state · part 1/") for name in names)
    # The terminal output was cut to fit the report: it goes whole after it.
    terminal = [request for request, name in zip(attachments, names, strict=True) if name.startswith("Terminal output")]
    assert terminal and _fields(terminal[-1])[f"entry.{form.ENTRY_ATTACH_CONTENT}"][0].endswith("ERROR: what failed")


def test_a_refused_attachment_never_fails_the_stored_report(monkeypatch):
    monkeypatch.setattr(form, "_last_sent", 0.0)
    monkeypatch.setattr(form.time, "sleep", lambda _s: None)
    calls = {"posts": 0}

    def fetch(request):
        if request.data is None:
            return live_page()
        calls["posts"] += 1
        if calls["posts"] > 1:
            raise form.FeedbackError("Google Forms answered with an error.")
        return CONFIRMED

    report = form.FeedbackReport(summary="x", details="d", attachments=[("System state", "y" * 1000)])
    form.submit(report, fetch=fetch, clock=lambda: 2000.0)
    assert calls["posts"] == 2


def test_without_the_automatic_report_nothing_is_attached(monkeypatch):
    monkeypatch.setattr(form, "_last_sent", 0.0)
    posts = []

    def fetch(request):
        if request.data is None:
            return live_page()
        posts.append(request)
        return CONFIRMED

    form.submit(form.FeedbackReport(summary="x"), fetch=fetch, clock=lambda: 3000.0)
    assert len(posts) == 1


@pytest.mark.parametrize("text", ["a\n" * 40_000, "é" * 70_000, "line\n" + "z" * 90_000 + "\nend"])
def test_parts_fit_the_budget_and_keep_every_character(text):
    parts = form.split_attachment(text, 20_000)
    assert all(len(urllib.parse.quote_plus(part)) <= 20_000 for part in parts)
    assert "".join(parts).replace("\n", "") == text.replace("\n", "")


def test_the_machine_name_account_and_addresses_stay_home(monkeypatch):
    monkeypatch.setattr(report_attachments.socket, "gethostname", lambda: "alices-pc.fritz.box")
    monkeypatch.setattr(report_attachments.getpass, "getuser", lambda: "alice")
    text = (
        "Linux alices-pc.fritz.box 7.2.9 #1\n"
        "[sudo] password for alice:\n"
        "/var/tmp/pamac-build-alice\n"
        "inet 192.168.1.20 ether aa:bb:cc:dd:ee:ff\n"
        "Operating system Bazzite on 127.0.0.1"
    )
    clean = report_attachments.redact_machine(text)
    for secret in ("alices-pc", "alice", "192.168.1.20", "aa:bb:cc"):
        assert secret not in clean
    assert "Bazzite" in clean and "127.0.0.1" in clean


def test_a_default_host_name_keeps_the_distribution_name(monkeypatch):
    monkeypatch.setattr(report_attachments.socket, "gethostname", lambda: "bazzite")
    assert report_attachments.redact_machine("Bazzite on bazzite") == "Bazzite on bazzite"


def test_the_report_service_takes_the_whole_report_in_one_request(monkeypatch):
    monkeypatch.setattr(form, "_last_sent", 0.0)
    payloads, google = [], []
    report = form.FeedbackReport(
        summary="CU failed", code="BC250-CU-001", details="Sent from: Control Center",
        attachments=[("System state", "== Storage ==\n" + "x" * 90_000)],
    )

    def endpoint(payload):
        payloads.append(payload)
        return True

    form.submit(report, fetch=lambda request: google.append(request), clock=lambda: 5000.0, endpoint=endpoint)
    assert google == []
    (payload,) = payloads
    assert payload["id"].startswith("R-") and payload["kind"] == "problem"
    assert payload["fields"]["Report details"].startswith("Report ID: " + payload["id"])
    assert payload["attachments"][0]["text"].endswith("x" * 1000)


def test_when_the_service_fails_the_form_takes_the_report(monkeypatch):
    monkeypatch.setattr(form, "_last_sent", 0.0)
    posts = []

    def fetch(request):
        if request.data is None:
            return live_page()
        posts.append(request)
        return CONFIRMED

    form.submit(form.FeedbackReport(summary="x"), fetch=fetch, clock=lambda: 6000.0, endpoint=lambda _payload: False)
    assert len(posts) == 1


def test_attachments_go_even_when_the_report_details_are_cut(monkeypatch):
    # 1.21.3: a big report had its details cut to fit, the Report ID line at
    # their end went with them, and not one attachment was sent.
    monkeypatch.setattr(form, "_last_sent", 0.0)
    monkeypatch.setattr(form.time, "sleep", lambda _s: None)
    posts = []

    def fetch(request):
        if request.data is None:
            return live_page()
        posts.append(request)
        return CONFIRMED

    report = form.FeedbackReport(
        summary="Cyan compatibility", details="Sent from: Control Center\n" + "detail line\n" * 400,
        hardware="h" * 32_000, recent_errors="e" * 20_000, specs="s" * 20_000,
        attachments=[("System state", "state\n" * 3000)],
    )
    form.submit(report, fetch=fetch, clock=lambda: 7000.0)
    main, *attachments = posts
    details = _fields(main)[f"entry.{form.ENTRY_DETAILS}"][0]
    assert details.startswith("Report ID: R-")
    assert attachments
    report_id = details.split("\n", 1)[0].removeprefix("Report ID: ")
    assert all(_fields(r)[f"entry.{form.ENTRY_ATTACH_REPORT}"] == [report_id] for r in attachments)
