"""The problem report form, answered and sent from inside the app.

The answers go to the maintainer's Google Form exactly as the browser would
send them, after checking the live form still asks the same questions. When it
does not, or Google cannot be reached, nothing written is lost: the browser
takes over with the short answers filled in and the long ones on the clipboard.
"""

from __future__ import annotations

import json
import urllib.parse

import pytest
from PyQt6.QtWidgets import QApplication

from bc250cc.infrastructure import feedback_form as form
from frontends.desktop.components.feedback_dialog import FeedbackDialog

ALL_ENTRIES = [value for name, value in vars(form).items() if name.startswith("ENTRY_")]
OPEN_CHOICES = {form.ENTRY_AREA, form.ENTRY_SEEN, form.ENTRY_DISTRIBUTION, form.ENTRY_OTHER_TOOLS}
CHOICES = {
    form.ENTRY_KIND: (form.KIND_PROBLEM, form.KIND_IDEA),
    form.ENTRY_AREA: form.AREAS,
    form.ENTRY_SEEN: form.SEEN,
    form.ENTRY_FREQUENCY: form.FREQUENCIES,
    form.ENTRY_WORKED_BEFORE: form.WORKED_BEFORE,
    form.ENTRY_DISTRIBUTION: form.DISTRIBUTIONS,
    form.ENTRY_INSTALL: form.INSTALLS,
    form.ENTRY_BIOS: form.BIOSES,
    form.ENTRY_CORES: form.CORES,
    form.ENTRY_CUS: form.CUS,
    form.ENTRY_OTHER_TOOLS: form.OTHER_TOOLS,
}


def form_page(entries=ALL_ENTRIES, token="-123") -> str:
    """A viewform page shaped like Google's: questions in FB_PUBLIC_LOAD_DATA_."""
    items = []
    for entry in entries:
        choices = [[label, None, None] for label in CHOICES.get(entry, ())]
        if entry in OPEN_CHOICES:
            choices.append([None, None, None, None, 1])
        items.append([entry + 7, f"Q{entry}", None, 2 if choices else 0, [[entry, choices or None, 0]]])
    data = [None, [None, items]]
    return (
        f'<form><input name="fbzx" value="{token}"></form>'
        f"<script>var FB_PUBLIC_LOAD_DATA_ = {json.dumps(data)};</script>"
    )


CONFIRMED = '<div class="freebirdFormviewerViewResponseConfirmationMessage">Recorded</div>'


@pytest.fixture(autouse=True)
def fresh_rate_limit(monkeypatch):
    monkeypatch.setattr(form, "_last_sent", 0.0)


def _problem(**extra) -> form.FeedbackReport:
    values = {"summary": "GPU governor stops", "area": form.AREAS[2], "distribution": "Manjaro Linux"}
    values.update(extra)
    return form.FeedbackReport(**values)


def test_the_live_form_is_read_with_its_choices_and_session_token():
    shape = form.parse_form(form_page())
    assert set(ALL_ENTRIES) <= set(shape.questions)
    labels, has_other = shape.questions[form.ENTRY_AREA]
    assert labels == frozenset(form.AREAS) and has_other
    assert shape.token == "-123"


def test_a_choice_the_form_does_not_list_goes_into_its_other_box():
    fields = dict(form.form_fields(_problem(), form.parse_form(form_page())))
    assert fields[f"entry.{form.ENTRY_DISTRIBUTION}"] == form.OTHER
    assert fields[f"entry.{form.ENTRY_DISTRIBUTION}.other_option_response"] == "Manjaro Linux"
    assert fields[f"entry.{form.ENTRY_AREA}"] == form.AREAS[2]
    assert fields["pageHistory"] == form.PAGES_PROBLEM
    assert fields["fbzx"] == "-123"


def test_an_idea_walks_only_the_first_and_last_pages():
    report = form.FeedbackReport(kind=form.KIND_IDEA, ideas="A dark theme for the charts", contact="@me")
    fields = form.form_fields(report, form.parse_form(form_page()))
    names = {name for name, _value in fields}
    assert dict(fields)["pageHistory"] == form.PAGES_IDEA
    assert f"entry.{form.ENTRY_SUMMARY}" not in names
    assert dict(fields)[f"entry.{form.ENTRY_IDEAS}"] == "A dark theme for the charts"


def test_a_question_the_form_lost_stops_the_send_instead_of_misfiling_it():
    shape = form.parse_form(form_page([entry for entry in ALL_ENTRIES if entry != form.ENTRY_SUMMARY]))
    with pytest.raises(form.FeedbackError) as caught:
        form.form_fields(_problem(), shape)
    assert caught.value.fallback


def test_long_answers_are_bounded():
    fields = dict(form.form_fields(_problem(terminal="x" * 50000), form.parse_form(form_page())))
    assert len(fields[f"entry.{form.ENTRY_TERMINAL}"]) == form.MAX_LONG_TEXT


def test_submit_posts_to_the_form_and_needs_googles_confirmation():
    requests = []

    def fetch(request):
        requests.append(request)
        return form_page() if request.data is None else CONFIRMED

    form.submit(_problem(), fetch=fetch, clock=lambda: 1000.0)
    post = requests[1]
    assert post.full_url.startswith(form.RESPONSE_URL) and post.get_method() == "POST"
    body = urllib.parse.parse_qs(post.data.decode())
    assert body[f"entry.{form.ENTRY_SUMMARY}"] == ["GPU governor stops"]
    assert all(r.full_url.startswith("https://docs.google.com/") for r in requests)


def test_a_redrawn_form_means_the_answers_were_refused():
    def fetch(request):
        return form_page()

    with pytest.raises(form.FeedbackError, match="did not confirm"):
        form.submit(_problem(), fetch=fetch, clock=lambda: 1000.0)


def test_a_second_press_right_after_does_not_send_twice():
    def fetch(request):
        return form_page() if request.data is None else CONFIRMED

    form.submit(_problem(), fetch=fetch, clock=lambda: 1000.0)
    with pytest.raises(form.FeedbackError) as caught:
        form.submit(_problem(), fetch=fetch, clock=lambda: 1005.0)
    assert not caught.value.fallback


def test_the_required_answer_is_checked_before_anything_is_sent():
    def fetch(request):  # pragma: no cover - must not be reached
        raise AssertionError("sent without a summary")

    with pytest.raises(form.FeedbackError):
        form.submit(form.FeedbackReport(summary="  "), fetch=fetch)


def test_the_browser_fallback_carries_the_short_answers_only():
    url = form.prefill_url(_problem(steps="1. open\n2. press", diagnostics="big report"))
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query[f"entry.{form.ENTRY_SUMMARY}"] == ["GPU governor stops"]
    assert query[f"entry.{form.ENTRY_DISTRIBUTION}"] == [form.OTHER]
    assert f"entry.{form.ENTRY_STEPS}" not in query and f"entry.{form.ENTRY_DIAGNOSTICS}" not in query


@pytest.mark.parametrize(
    ("release", "expected"),
    (
        ({"ID": "bazzite", "ID_LIKE": "fedora"}, "Bazzite"),
        ({"ID": "arch"}, "Arch Linux"),
        ({"ID": "cachyos", "ID_LIKE": "arch"}, "CachyOS"),
        ({"ID": "manjaro", "ID_LIKE": "arch", "PRETTY_NAME": "Manjaro Linux"}, "Manjaro Linux"),
    ),
)
def test_the_distribution_is_answered_from_os_release(release, expected):
    assert form.suggested_distribution(release) == expected


def test_the_installation_row_maps_to_the_forms_choice():
    assert form.suggested_install("Source checkout") == form.INSTALLS[2]
    assert form.suggested_install("Package (pacman: bc250-control-center)") == form.INSTALLS[0]
    assert form.suggested_install("install-local.sh (/home/a/.local)") == form.INSTALLS[1]


def _dialog(qtbot, **kwargs):
    facts = {"report": "BC250 diagnostic report", "specs": "Kernel  7.1.13\nBIOS    P3.00",
             "recent": "2026-10-20 22:41:03 · BC250-UPSCALE-001 · window · HelixSR\n  What happened: x",
             "hardware": "== Modules ==\nnct6687  61440  0", "session": "KDE · wayland", "version": "1.21.2", "install": form.INSTALLS[2],
             "distribution": "Manjaro Linux", "cores": form.CORES[0]}
    dialog = FeedbackDialog(read_report=lambda: facts, **kwargs)
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: bool(dialog._diagnostics))
    return dialog


def test_an_error_window_opens_the_form_already_filled(qtbot):
    dialog = _dialog(
        qtbot, code="BC250-UPSCALE-001", summary="HelixSR could not be installed",
        context="HelixSR", area_hint="UPS", reference="BC250-UPSCALE-001 @ GPU-0142",
        where="Origin: GPU-0142 · gpu_governor.py:812 · Page.run\nRaised in: UPS-0181 · helixsr.py:640 · install",
        raw="Traceback (most recent call last):\nRuntimeError: bridge failed",
    )
    report = dialog.report()
    assert report.code == "BC250-UPSCALE-001"
    assert report.area == "FSR4 / OptiScaler"
    assert form.SEEN[0] in report.seen
    assert report.install == form.INSTALLS[2] and report.cores == form.CORES[0]
    assert report.distribution == "Manjaro Linux"
    # The automatic page: one answer per column, none of it typed.
    assert report.reference == "BC250-UPSCALE-001 @ GPU-0142"
    assert "Raised in: UPS-0181" in report.where
    assert report.raw.endswith("RuntimeError: bridge failed")
    assert report.specs.startswith("Kernel") and "BC250-UPSCALE-001" in report.recent_errors
    assert "Opened from: Error window" in report.details and "Interface language:" in report.details
    assert report.diagnostics == "" and report.terminal == ""
    fields = dict(form.form_fields(report, form.parse_form(form_page())))
    assert fields[f"entry.{form.ENTRY_RAW}"].endswith("bridge failed")
    assert fields[f"entry.{form.ENTRY_SPECS}"].startswith("Kernel")
    assert "nct6687" in fields[f"entry.{form.ENTRY_HARDWARE}"]


def test_the_preview_is_exactly_what_the_automatic_page_sends(qtbot):
    dialog = _dialog(qtbot, summary="x", reference="BC250-FAN-001 @ FAN-0007")
    text = dialog.preview_text()
    for heading in ("Error reference", "Where it happened", "Raw error", "System specifications",
                    "Recent errors", "Report details", "Hardware diagnostics"):
        assert f"== {heading} ==" in text
    assert "BC250-FAN-001 @ FAN-0007" in text and "Kernel  7.1.13" in text


def test_the_route_through_the_pages_is_read_from_the_live_form():
    items = [
        [1, "Kind", None, 2, [[form.ENTRY_KIND, [[form.KIND_PROBLEM, None, 10], [form.KIND_IDEA, None, 40]], 1]]],
        [10, "The problem", None, 8],
        [11, "What went wrong?", None, 0, [[form.ENTRY_SUMMARY, None, 1]]],
        [20, "Your system", None, 8],
        [30, "Automatic report", None, 8],
        [40, "Contact and ideas", None, 8],
        [41, "Ideas", None, 1, [[form.ENTRY_IDEAS]]],
    ]
    page = f"<script>var FB_PUBLIC_LOAD_DATA_ = {json.dumps([None, [None, items]])};</script>"
    shape = form.parse_form(page)
    assert shape.problem_pages == "0,1,2,3,4"
    assert shape.idea_pages == "0,4"


def test_the_automatic_report_can_be_left_out(qtbot):
    dialog = _dialog(qtbot, summary="x", reference="BC250-FAN-001 @ FAN-0007", raw="ValueError: x")
    dialog.attach.setChecked(False)
    report = dialog.report()
    assert not (report.reference or report.raw or report.specs or report.recent_errors or report.details or report.hardware)


def test_send_without_the_required_answer_points_at_it(qtbot):
    sent = []
    dialog = _dialog(qtbot, submit=sent.append)
    dialog.summary.clear()
    dialog._send()
    assert not sent and dialog.status.isVisibleTo(dialog)


def test_a_sent_report_shows_the_thanks_page(qtbot):
    sent = []
    dialog = _dialog(qtbot, summary="Fans stop", submit=sent.append)
    dialog._send()
    qtbot.waitUntil(lambda: dialog.pages.currentIndex() == 2)
    assert sent[0].summary == "Fans stop"


def test_a_failed_send_keeps_the_text_and_offers_the_browser(qtbot, monkeypatch):
    def fail(_report):
        raise form.FeedbackError("Google Forms could not be reached. Check the internet connection.")

    opened = []
    monkeypatch.setattr(
        "frontends.desktop.components.feedback_dialog.open_external_url",
        lambda url: (opened.append(url), (True, ""))[1],
    )
    dialog = _dialog(qtbot, summary="Fans stop", submit=fail)
    dialog.steps.setPlainText("1. Open Fans")
    dialog._send()
    qtbot.waitUntil(lambda: dialog.browser_button.isVisibleTo(dialog))
    assert dialog.summary.text() == "Fans stop"
    dialog.browser_button.click()
    assert opened and opened[0].startswith(form.FORM_URL)
    assert "1. Open Fans" in QApplication.clipboard().text()


def test_an_idea_needs_only_the_idea(qtbot):
    sent = []
    dialog = _dialog(qtbot, idea=True, submit=sent.append)
    dialog.ideas.setPlainText("Per-game fan curves")
    dialog._send()
    qtbot.waitUntil(lambda: bool(sent))
    assert sent[0].kind == form.KIND_IDEA and sent[0].ideas == "Per-game fan curves"


def test_a_page_that_still_carries_the_form_is_not_a_confirmation():
    # A rejected answer comes back as the form again, whatever else it holds.
    assert not form.confirmed(form_page() + '<div class="vHW8K">x</div>')
    assert form.confirmed(CONFIRMED)
    assert form.confirmed("<p>Your response has been recorded.</p>")
    assert not form.confirmed("<html>Something went wrong</html>")


def test_the_forms_own_confirmation_message_counts_even_with_the_form_data():
    # Google now also carries the form data on the "recorded" page, and the
    # form uses its own confirmation message instead of Google's sentence.
    shown = '<div class="vHW8K">Thanks, received. I read every one of them. If you left a contact I may write to you.</div>'
    assert form.confirmed(form_page() + shown)
    assert form.confirmed(form_page() + "<p>Your response has been recorded.</p>")


def test_the_message_inside_the_form_data_is_not_a_confirmation():
    # The viewform page holds the confirmation message in its scripts; a
    # rejected answer drawn again must not pass for a stored one.
    hidden = "<script>var FB_PUBLIC_LOAD_DATA_ = [null,[\"Thanks, received. I read every one of them.\"]];</script>"
    assert not form.confirmed(form_page() + hidden)


def test_send_waits_for_the_automatic_report(qtbot):
    import threading

    gate = threading.Event()
    facts = {"report": "r", "specs": "Kernel 7.1"}
    dialog = FeedbackDialog(read_report=lambda: (gate.wait(5), facts)[1], summary="x")
    qtbot.addWidget(dialog)
    assert not dialog.send_button.isEnabled()
    gate.set()
    qtbot.waitUntil(dialog.send_button.isEnabled)
    assert dialog.report().specs == "Kernel 7.1"


def test_a_report_on_its_way_cannot_be_cancelled(qtbot):
    import threading

    gate = threading.Event()
    dialog = _dialog(qtbot, summary="Fans stop", submit=lambda report: gate.wait(5))
    dialog._send()
    assert not dialog.cancel_button.isEnabled()
    dialog.reject()
    assert dialog.isVisible() or dialog.result() == 0
    assert dialog._sending
    gate.set()
    qtbot.waitUntil(lambda: dialog.pages.currentIndex() == 2)


def test_the_browser_fallback_clipboard_has_no_home_folder(qtbot, monkeypatch):
    monkeypatch.setattr(
        "frontends.desktop.components.feedback_dialog.open_external_url", lambda url: (True, ""),
    )
    dialog = _dialog(qtbot, summary="x")
    dialog.terminal.setPlainText("Traceback in /home/alice/projects/app.py")
    dialog._open_in_browser()
    assert "alice" not in QApplication.clipboard().text()


def test_a_report_too_big_for_google_is_cut_to_fit_least_important_first():
    # Google answers 413 over ~32 KB; fifteen tracebacks and the hardware
    # diagnosis together went over it and the report was never stored.
    shape = form.parse_form(form_page())
    trace = '  File "bc250cc/infrastructure/gpu_repository.py", line 921, in _editar_governor_toml\n'
    report = _problem(recent_errors=trace * 300, hardware="== Kernel ==\nLinux 7.1\n" + "x" * 25000,
                      raw="Traceback\n" + "y" * 5000 + "\nRuntimeError: the real cause")
    fitted = form.fit_report(report, shape)
    body = urllib.parse.urlencode(form.form_fields(fitted, shape)).encode()
    assert len(body) <= form.MAX_POST_BYTES
    assert fitted.recent_errors.endswith(form.CUT_NOTE)
    assert fitted.summary == report.summary
    assert fitted.raw.endswith("RuntimeError: the real cause")


def test_a_report_that_fits_is_sent_untouched():
    shape = form.parse_form(form_page())
    report = _problem(hardware="== Kernel ==\nLinux 7.1")
    assert form.fit_report(report, shape) == report


def test_submit_never_posts_more_than_google_accepts():
    posted = []

    def fetch(request):
        if request.data:
            posted.append(len(request.data))
            return CONFIRMED
        return form_page()

    form.submit(_problem(recent_errors="z" * 20000, hardware="h" * 32000, specs="s" * 20000), fetch=fetch)
    assert posted and posted[0] <= form.MAX_POST_BYTES


def test_the_password_note_shows_only_when_polkit_will_ask(qtbot):
    for needed in (True, False):
        dialog = FeedbackDialog(read_report=lambda: {}, needs_password=lambda needed=needed: needed)
        qtbot.addWidget(dialog)
        assert dialog.polkit_note.isHidden() is (not needed)


def test_the_terminal_output_outlives_the_hardware_diagnosis():
    # A report opened from the terminal arrived with its terminal output cut
    # away while the hardware diagnosis took the room.
    shape = form.parse_form(form_page())
    report = _problem(terminal="[ERROR] the real failure\n" * 300, hardware="h" * 32000)
    fitted = form.fit_report(report, shape)
    assert "[ERROR] the real failure" in fitted.terminal
    assert len(fitted.hardware) < len(report.hardware)
