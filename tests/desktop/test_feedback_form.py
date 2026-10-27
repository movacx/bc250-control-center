"""The problem report: the form, the document it becomes, and how it is sent.

The document goes to the maintainer's report service in one request. These
tests hold the parts that matter for whoever reads a report: every fact has
one place, what the app detected is never asked again, an "Other" answer is
typed, and a report that cannot be sent is kept on disk.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import problem_report as form
from bc250cc.infrastructure import report_attachments
from frontends.desktop.components.feedback_dialog import FeedbackDialog

FACTS = {
    "system": {"Operating system": "Manjaro Linux", "Kernel": "7.1.13", "Session": "KDE · wayland"},
    "os_release": {"ID": "manjaro", "ID_LIKE": "arch"},
    "firmware": {"version": "P3.00", "date": "12/09/2021", "variant": "MeiMeiDXE v3"},
    "history": [],
    "attachments": [("Modules", "nct6687  61440  0"), ("Storage", "/dev/nvme0n1p2 ext4 50%")],
    "version": "1.21.3",
    "install": form.INSTALLS[2],
    "distribution": "Manjaro",
    "bios": "MeiMeiDXE v3",
    "cores": form.CORES[0],
}


@pytest.fixture(autouse=True)
def fresh_rate_limit(monkeypatch):
    monkeypatch.setattr(form, "_last_sent", 0.0)


def _entry(at, code, title, detail="", raw="", source="window"):
    return SimpleNamespace(at=at, code=code, title=title, detail=detail, raw=raw, source=source)


def _dialog(qtbot, facts=None, **kwargs):
    facts = dict(FACTS if facts is None else facts)
    kwargs.setdefault("needs_password", lambda: False)
    dialog = FeedbackDialog(read_report=lambda: facts, **kwargs)
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: bool(dialog._facts))
    return dialog


# --- The document -------------------------------------------------------------------


def test_every_fact_has_one_place_in_the_document():
    report = form.Report(
        summary="Fans stop", version="1.21.3",
        system={"Operating system": "Fedora Linux 44", "Kernel": "7.1"},
        firmware={"version": "P3.00", "variant": "MeiMeiDXE v3"},
        distribution="Fedora", bios="MeiMeiDXE v3",
        error=form.ErrorEvidence(code="BC250-FAN-001", raw="RuntimeError: no pwm"),
        attachments=[("Modules", "nct6687")],
    )
    document = form.payload(report, now=datetime(2026, 10, 27, tzinfo=timezone.utc))
    assert document["schema"] == form.SCHEMA and document["id"] == report.id
    assert document["app"]["version"] == "1.21.3"
    assert document["system"]["Operating system"] == "Fedora Linux 44"
    assert document["firmware"]["variant"] == "MeiMeiDXE v3"
    assert document["owner"] == {"distribution": "Fedora", "bios": "MeiMeiDXE v3"}
    assert document["error"] == {"code": "BC250-FAN-001", "raw": "RuntimeError: no pwm"}
    assert document["attachments"] == [{"name": "Modules", "text": "nct6687"}]
    # Nothing empty is sent: no blank workflow, no blank history.
    assert "workflow" not in document and "history" not in document


def test_an_idea_carries_only_the_idea():
    document = form.payload(form.Report(kind=form.KIND_IDEA, notes="Dark mode for the LCD\nmore", contact="@me"))
    assert document["idea"] == "Dark mode for the LCD\nmore"
    assert document["summary"] == "Dark mode for the LCD"
    assert not {"problem", "error", "system", "attachments"} & document.keys()


def test_a_long_log_keeps_its_end_where_it_failed():
    log = "step\n" * 60000 + "ERROR: the real failure"
    document = form.payload(form.Report(summary="x", workflow_title="Prepare", workflow_log=log))
    assert len(document["workflow"]["log"]) <= form.MAX_LONG_TEXT
    assert document["workflow"]["log"].endswith("ERROR: the real failure")


def test_the_machine_name_account_and_addresses_stay_home(monkeypatch):
    monkeypatch.setattr(report_attachments.socket, "gethostname", lambda: "alices-pc.fritz.box")
    monkeypatch.setattr(report_attachments.getpass, "getuser", lambda: "alice")
    report = form.Report(
        summary="x",
        workflow_log="Linux alices-pc.fritz.box 7.2.9\n[sudo] password for alice:\ninet 192.168.1.20 ether aa:bb:cc:dd:ee:ff",
        attachments=[("Kernel", "/home/alice/.local/share/app 127.0.0.1")],
    )
    text = json.dumps(form.payload(report))
    for secret in ("alices-pc", "alice", "192.168.1.20", "aa:bb:cc"):
        assert secret not in text
    assert "127.0.0.1" in text


def test_a_default_host_name_keeps_the_distribution_name(monkeypatch):
    monkeypatch.setattr(report_attachments.socket, "gethostname", lambda: "bazzite")
    assert report_attachments.redact_machine("Bazzite on bazzite") == "Bazzite on bazzite"


def test_the_current_error_is_not_repeated_in_the_history():
    entries = [
        _entry(30, "BC250-GPU-001", "Could not update Cyan", raw="RuntimeError: kernel"),
        _entry(20, "BC250-FAN-001", "Fan PWM failed", detail="pwm1 missing"),
        _entry(19, "BC250-FAN-001", "Fan PWM failed", detail="pwm1 missing"),
        _entry(10, "BC250-NET-001", "Update failed", detail="x" * 900),
    ]
    items = form.history_items(entries, exclude_raw="RuntimeError: kernel")
    assert [item["code"] for item in items] == ["BC250-FAN-001", "BC250-NET-001"]
    assert len(items[1]["detail"]) <= 300


def test_workflow_logs_lose_terminal_strings_and_the_credits():
    log = (
        "== Third-party credits ==\nExplicit workflows use upstream projects.\n- cyan: https://x\n- oberon: https://y\n"
        "[INFO] Installing\n\x1b]777;bc250-log-sync\x07ERROR: failed"
    )
    assert form.clean_log(log) == "[INFO] Installing\nERROR: failed"


# --- Sending ------------------------------------------------------------------------


def test_submit_posts_the_document_once_and_returns_its_id():
    posted = []
    report = form.Report(summary="Fans stop")
    assert form.submit(report, post=posted.append) == report.id
    assert len(posted) == 1 and posted[0]["id"] == report.id


def test_a_report_the_service_did_not_take_is_saved_on_disk(tmp_path):
    def refuse(_document):
        raise form.ReportError("The report service could not be reached. Check the internet connection.")

    report = form.Report(summary="Fans stop")
    with pytest.raises(form.ReportError) as raised:
        form.submit(report, post=refuse, save=lambda document: form.save_copy(document, tmp_path))
    assert raised.value.saved == tmp_path / f"{report.id}.json"
    assert json.loads(raised.value.saved.read_text())["summary"] == "Fans stop"


def test_a_second_press_right_after_does_not_send_twice():
    posted = []
    form.submit(form.Report(summary="a"), post=posted.append, clock=lambda: 100.0)
    with pytest.raises(form.ReportError):
        form.submit(form.Report(summary="b"), post=posted.append, clock=lambda: 110.0)
    assert len(posted) == 1


def test_the_required_answer_is_checked_before_anything_is_sent():
    posted = []
    with pytest.raises(form.ReportError):
        form.submit(form.Report(summary="  "), post=posted.append)
    assert not posted


def test_the_service_answer_must_name_the_same_report(monkeypatch):
    class Answer:
        status = 200

        def __init__(self, body):
            self.body = body

        def read(self, _limit):
            return json.dumps(self.body).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(form.urllib.request, "urlopen", lambda *_a, **_k: Answer({"ok": True, "id": "R-00000000"}))
    with pytest.raises(form.ReportError):
        form.post_report({"id": "R-12345678"})
    monkeypatch.setattr(form.urllib.request, "urlopen", lambda *_a, **_k: Answer({"ok": True, "id": "R-12345678"}))
    form.post_report({"id": "R-12345678"})


# --- What the app already knows -------------------------------------------------------


@pytest.mark.parametrize(
    ("release", "expected"),
    (
        ({"ID": "bazzite", "ID_LIKE": "fedora"}, "Bazzite"),
        ({"ID": "fedora", "VARIANT_ID": "nobara"}, "Nobara"),
        ({"ID": "manjaro", "ID_LIKE": "arch"}, "Manjaro"),
        ({"ID": "arch"}, "Arch Linux"),
        ({"ID": "fedora", "PRETTY_NAME": "Fedora Linux 44"}, "Fedora"),
        # A derivative not listed answers with its own name, under "Other".
        ({"ID": "pop", "ID_LIKE": "ubuntu debian", "PRETTY_NAME": "Pop!_OS 24.04 LTS"}, "Pop!_OS 24.04 LTS"),
    ),
)
def test_the_distribution_is_answered_from_os_release(release, expected):
    assert form.suggested_distribution(release) == expected


def test_the_bios_variant_read_from_the_board_is_the_answer():
    assert form.suggested_bios("MeiMeiDXE v3") == "MeiMeiDXE v3"
    assert form.suggested_bios("ASRock") == "Stock BIOS"
    # DMI cannot tell the P3.00 images apart: the owner answers.
    assert form.suggested_bios("") == ""


def test_the_installation_row_maps_to_the_forms_choice():
    assert form.suggested_install("Package (pacman: bc250-control-center)") == form.INSTALLS[0]
    assert form.suggested_install("Source checkout") == form.INSTALLS[2]


def test_the_diagnosis_is_one_attachment_per_section_and_none_twice(monkeypatch):
    monkeypatch.setattr(
        report_attachments.diag, "collect_diagnostics",
        lambda sections, **_kwargs: "\n\n".join(f"== {title} ==\nhw {title}" for title, _read in sections),
    )
    monkeypatch.setattr(
        report_attachments, "collect_system_state",
        lambda: "== Storage ==\nstate storage\n\n== Kernel ==\nduplicate\n\n== Packages ==\nstate packages",
    )
    titles = [title for title, _text in report_attachments.collect_attachments()]
    assert len(titles) == len({title.lower() for title in titles})
    assert "Storage" in titles and "Packages" in titles
    assert dict(report_attachments.collect_attachments())["Storage"] == "state storage"


# --- The dialog ---------------------------------------------------------------------


def test_an_error_window_opens_the_form_already_filled_and_explained(qtbot):
    dialog = _dialog(
        qtbot, code="BC250-GPU-001", summary="Could not update Cyan compatibility settings",
        context="GPU governor", area_hint="GPU", reference="BC250-GPU-001 @ GPU-0172",
        where="Origin: GPU-0172 · gpu_governor_state.py:1053 · report_failure",
        raw="Traceback (most recent call last):\nRuntimeError: gpu-usage.method=kernel was requested",
    )
    report = dialog.report()
    assert report.area == "GPU governor (Cyan)"
    assert form.SEEN[0] in report.seen
    assert report.error.code == "BC250-GPU-001"
    assert report.error.what and report.error.fix
    assert report.error.raw.endswith("was requested")
    assert report.distribution == "Manjaro" and report.bios == "MeiMeiDXE v3"
    assert report.firmware["date"] == "12/09/2021"


def test_the_detected_system_is_shown_under_the_answers(qtbot):
    dialog = _dialog(qtbot)
    assert "Manjaro Linux" in dialog.distribution_detected.text()
    assert "MeiMeiDXE v3" in dialog.bios_detected.text()


def test_a_distribution_not_listed_is_typed_under_other(qtbot):
    facts = dict(FACTS, distribution="Pop!_OS 24.04 LTS")
    dialog = _dialog(qtbot, facts)
    assert dialog.distribution.choice.value() == form.OTHER
    assert not dialog.distribution.other.isHidden()
    assert dialog.report().distribution == "Pop!_OS 24.04 LTS"


def test_choosing_other_opens_a_box_for_the_answer(qtbot):
    dialog = _dialog(qtbot, dict(FACTS, bios=""))
    assert dialog.bios.other.isHidden()
    dialog.bios.choice.set_value(form.OTHER)
    assert not dialog.bios.other.isHidden()
    dialog.bios.other.setText("P5.00 with my own mod")
    assert dialog.report().bios == "P5.00 with my own mod"


def test_a_terminal_report_carries_the_workflow_log(qtbot):
    dialog = _dialog(qtbot, summary="Update failed", terminal="sha256sum: FAILED\nDiagnostic code: BC250-NET-001",
                     code="BC250-NET-001", opened_from="Terminal")
    report = dialog.report()
    assert form.SEEN[1] in report.seen and form.SEEN[0] not in report.seen
    assert report.workflow_title == "Update failed"
    assert report.workflow_log.startswith("sha256sum: FAILED")
    assert report.error.code == "BC250-NET-001" and report.error.what


def test_the_preview_is_the_document_that_is_sent(qtbot):
    dialog = _dialog(qtbot, summary="Fans stop")
    document = json.loads(dialog.preview_text())
    assert document["summary"] == "Fans stop"
    assert [item["name"] for item in document["attachments"]] == ["Modules", "Storage"]


def test_the_automatic_report_can_be_left_out(qtbot):
    dialog = _dialog(qtbot, summary="x")
    dialog.attach.setChecked(False)
    document = json.loads(dialog.preview_text())
    assert not {"system", "firmware", "attachments", "history"} & document.keys()


def test_send_without_the_required_answer_points_at_it(qtbot):
    sent = []
    dialog = _dialog(qtbot, submit=sent.append)
    dialog._send()
    assert not sent and not dialog.status.isHidden()


def test_a_sent_report_shows_the_thanks_page(qtbot):
    dialog = _dialog(qtbot, summary="Fans stop", submit=lambda report: report.id)
    dialog._send()
    qtbot.waitUntil(lambda: dialog.pages.currentIndex() == 2)


def test_a_failed_send_keeps_the_text_and_says_where_the_copy_is(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(form, "saved_directory", lambda: tmp_path)

    def fail(report):
        form.save_copy(form.payload(report), tmp_path)
        raise form.ReportError("The report service could not be reached. Check the internet connection.")

    dialog = _dialog(qtbot, summary="Fans stop", submit=fail)
    dialog._send()
    qtbot.waitUntil(lambda: dialog.send_button.isEnabled())
    assert dialog.summary.text() == "Fans stop"
    assert str(tmp_path.name) in dialog.status.text() or "~" in dialog.status.text()


def test_an_idea_needs_only_the_idea(qtbot):
    sent = []
    dialog = _dialog(qtbot, idea=True, submit=sent.append)
    dialog.ideas.setPlainText("Dark mode for the LCD")
    dialog._send()
    qtbot.waitUntil(lambda: bool(sent))
    assert sent[0].kind == form.KIND_IDEA and sent[0].notes == "Dark mode for the LCD"


def test_send_waits_for_the_automatic_report(qtbot):
    gate = threading.Event()
    dialog = FeedbackDialog(read_report=lambda: (gate.wait(5), FACTS)[1], summary="x", needs_password=lambda: False)
    qtbot.addWidget(dialog)
    assert not dialog.send_button.isEnabled()
    gate.set()
    qtbot.waitUntil(dialog.send_button.isEnabled)
    assert dialog.report().system["Kernel"] == "7.1.13"


def test_a_report_on_its_way_cannot_be_cancelled(qtbot):
    gate = threading.Event()
    dialog = _dialog(qtbot, summary="Fans stop", submit=lambda report: gate.wait(5))
    dialog._send()
    assert not dialog.cancel_button.isEnabled()
    dialog.reject()
    assert dialog._sending
    gate.set()
    qtbot.waitUntil(lambda: dialog.pages.currentIndex() == 2)


def test_the_password_note_shows_only_when_polkit_will_ask(qtbot):
    for needed in (True, False):
        dialog = FeedbackDialog(read_report=lambda: {}, needs_password=lambda needed=needed: needed)
        qtbot.addWidget(dialog)
        assert dialog.polkit_note.isHidden() is (not needed)


def test_the_area_is_where_it_failed_not_the_page_that_showed_it():
    shown = SimpleNamespace(section="GPU")
    # HelixSR runs from the GPU governor page; its failures are upscaling.
    assert form.AREA_BY_SECTION[form.area_section(SimpleNamespace(section="UPS"), shown)].startswith("Upscaling")
    # Code every part shares (the terminal launcher) says nothing: the page does.
    assert form.area_section(SimpleNamespace(section="SYS"), shown) == "GPU"
    assert form.area_section(None, None) == ""


def test_every_section_a_person_would_recognise_has_an_area():
    from bc250cc.shared.error_origins import SECTIONS

    named = {code for code, _name, _patterns in SECTIONS} - form.GENERIC_SECTIONS - {"SYS"}
    assert named <= form.AREA_BY_SECTION.keys()
    assert set(form.AREA_BY_SECTION.values()) <= set(form.AREAS)
    assert form.suggested_area("HelixSR could not be installed") == "Upscaling (FSR4, HelixSR, OptiScaler)"
    assert form.suggested_area("BC250 GDDR6 memory temperature failed") == "Telemetry, sensors and performance"
    assert form.suggested_area("Apply TTM failed") == "Memory (VRAM, TTM, swap)"
    assert form.suggested_area("Corsair devices (OpenLinkHub) failed") == "Drivers, accessories and TV control"


def test_a_terminal_report_takes_its_area_from_the_workflow_name(qtbot):
    dialog = _dialog(qtbot, summary="Thermalright LCD failed", terminal="nothing provides x", opened_from="Terminal")
    assert dialog.report().area == "Drivers, accessories and TV control"


def test_a_code_from_the_window_rules_is_explained_too(qtbot):
    dialog = _dialog(qtbot, code="BC250-GPU-007", summary="Could not update Cyan compatibility settings",
                     reference="BC250-GPU-007 @ GPU-0172", raw="Traceback\nGovernorTomlError: config.toml missing")
    error = dialog.report().error
    assert error.what.startswith("Cyan is not installed") and error.fix


def test_the_contact_the_owner_typed_is_never_redacted(monkeypatch):
    monkeypatch.setattr(report_attachments.getpass, "getuser", lambda: "alice")
    document = form.payload(form.Report(summary="x", contact="@alice", steps="/home/alice/game"))
    assert document["contact"] == "@alice"
    assert "alice" not in document["problem"]["steps"]
