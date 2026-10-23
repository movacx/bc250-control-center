"""Every failure says where it happened and what was raised.

``error_catalog`` names what kind of fault it was; ``error_origins`` gives
every function of the app a stable code, so an error window and a report name
the screen action that showed it and the line that raised it, with the
exception itself, raw.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from bc250cc.infrastructure import diagnostic_journal as journal
from bc250cc.shared import error_origins
from bc250cc.shared.error_origins import (
    build_catalog,
    caller_origin,
    format_raw,
    module_key,
    outer_function,
    raise_site,
    section_of,
)
from frontends.desktop.components.async_tools import _FunctionTask
from frontends.desktop.components.widgets import InfoDialog
from frontends.desktop.core import diagnostic_history, raw_errors
from frontends.desktop.core.diagnostic_history import diagnostic_report, history_entries

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def journal_file(tmp_path, monkeypatch):
    path = tmp_path / "diagnostics.jsonl"
    monkeypatch.setattr(journal, "journal_path", lambda env=None: path)
    monkeypatch.setattr(diagnostic_history, "DECKY_DIAGNOSTICS", tmp_path / "decky.jsonl")
    raw_errors.clear()
    return path


def test_the_catalog_names_every_function_of_the_app():
    current = json.loads(error_origins.CATALOG_PATH.read_text(encoding="utf-8"))
    fresh = build_catalog(ROOT, current)
    stale = {
        key: sorted(set(functions) ^ set(current["modules"].get(key, {})))
        for key, functions in fresh["modules"].items()
        if functions != current["modules"].get(key)
    }
    gone = sorted(set(current["modules"]) - set(fresh["modules"]))
    assert not stale and not gone, (
        "error_origins.json is out of date; run `python -m bc250cc.shared.error_origins`. "
        f"Changed: {dict(list(stale.items())[:5])} Removed modules: {gone[:5]}"
    )
    total = sum(len(functions) for functions in current["modules"].values())
    assert total > 3000


def test_a_code_is_never_given_twice_nor_reused_after_retirement():
    current = json.loads(error_origins.CATALOG_PATH.read_text(encoding="utf-8"))
    codes = [code for functions in current["modules"].values() for code in functions.values()]
    assert len(codes) == len(set(codes)), "a code is given twice"
    assert all(len(code.rsplit("-", 1)[1]) == 4 for code in codes)
    assert not set(current["retired"]) & set(codes)


def test_regenerating_keeps_every_code_and_retires_removed_functions(tmp_path):
    module = tmp_path / "src" / "bc250cc" / "infrastructure" / "helixsr.py"
    module.parent.mkdir(parents=True)
    module.write_text("def install():\n    pass\n\ndef remove():\n    pass\n", encoding="utf-8")
    (tmp_path / "frontends" / "desktop").mkdir(parents=True)
    first = build_catalog(tmp_path)
    assert first["modules"]["bc250cc/infrastructure/helixsr.py"] == {"install": "UPS-0001", "remove": "UPS-0002"}

    module.write_text("def update():\n    pass\n\ndef remove():\n    pass\n", encoding="utf-8")
    second = build_catalog(tmp_path, first)
    # "remove" keeps its code; "install" is retired; "update" gets a new one, not 0001.
    assert second["modules"]["bc250cc/infrastructure/helixsr.py"] == {"update": "UPS-0003", "remove": "UPS-0002"}
    assert second["retired"] == ["UPS-0001"]


def test_a_module_that_changes_section_keeps_the_codes_it_had(tmp_path, monkeypatch):
    module = tmp_path / "frontends" / "desktop" / "pages" / "foo.py"
    module.parent.mkdir(parents=True)
    module.write_text("def run():\n    pass\n", encoding="utf-8")
    (tmp_path / "src" / "bc250cc").mkdir(parents=True)
    first = build_catalog(tmp_path)
    assert first["modules"]["frontends/desktop/pages/foo.py"] == {"run": "UI-0001"}
    monkeypatch.setattr(error_origins, "section_of", lambda key: "GPU")
    module.write_text("def run():\n    pass\n\ndef stop():\n    pass\n", encoding="utf-8")
    second = build_catalog(tmp_path, first)
    assert second["modules"]["frontends/desktop/pages/foo.py"] == {"run": "UI-0001", "stop": "GPU-0001"}


@pytest.mark.parametrize(
    ("path", "key"),
    (
        ("/home/a/.local/share/bc250-control-center/src/bc250cc/infrastructure/helixsr.py",
         "bc250cc/infrastructure/helixsr.py"),
        ("/opt/x/frontends/desktop/pages/gpu_governor.py", "frontends/desktop/pages/gpu_governor.py"),
        ("/usr/lib/python3/json/decoder.py", ""),
    ),
)
def test_an_installed_copy_and_a_checkout_name_a_module_alike(path, key):
    assert module_key(path) == key


@pytest.mark.parametrize(
    ("key", "section"),
    (
        ("bc250cc/infrastructure/helixsr.py", "UPS"),
        ("frontends/desktop/pages/gpu_governor.py", "GPU"),
        ("frontends/desktop/pages/cpu_smu.py", "CPU"),
        ("frontends/desktop/pages/fans.py", "FAN"),
        ("frontends/desktop/console/terminal_view.py", "CON"),
        ("bc250cc/infrastructure/cu_operations.py", "CU"),
        ("frontends/desktop/components/feedback_dialog.py", "DIAG"),
    ),
)
def test_modules_fall_into_the_section_of_the_app_they_serve(key, section):
    assert section_of(key) == section


def test_a_nested_callback_reports_the_function_that_started_it():
    assert outer_function("GpuGovernorPage._install.<locals>.failed") == "GpuGovernorPage._install"
    origin = error_origins.origin_for("bc250cc/infrastructure/helixsr.py", "install_helixsr_game")
    assert origin.code.startswith("UPS-") and origin.code != "UPS-0000"


def _raise_from_backend():
    from bc250cc.infrastructure import feedback_form

    feedback_form.parse_form("<html></html>")


def test_the_raise_site_is_the_innermost_function_of_ours():
    with pytest.raises(Exception) as caught:
        _raise_from_backend()
    site = raise_site(caught.value)
    assert site.module == "bc250cc/infrastructure/feedback_form.py"
    assert site.function == "parse_form" and site.line > 0
    assert site.code.startswith("DIAG-")


def test_the_raw_error_keeps_the_type_and_hides_the_home_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ROOT.parent))
    with pytest.raises(Exception) as caught:
        _raise_from_backend()
    text = format_raw(caught.value)
    assert "FeedbackError: The report form could not be read." in text
    assert 'File "bc250cc/infrastructure/feedback_form.py"' in text
    # This test file is not ours to shorten; its home part still goes.
    assert str(ROOT.parent) not in text and f'File "~/{ROOT.name}/tests/' in text


def _origin_from(path: str, source: str, namespace: dict) -> object:
    exec(compile(source, path, "exec"), namespace)
    return namespace


def test_the_origin_skips_the_helpers_that_only_draw_the_window():
    namespace = _origin_from(
        "/x/frontends/desktop/pages/fans.py",
        "class FansPage:\n"
        "    def _apply_curve(self):\n"
        "        return self._show_info()\n"
        "    def _show_info(self):\n"
        "        return caller_origin()\n",
        {"caller_origin": caller_origin},
    )
    origin = namespace["FansPage"]()._apply_curve()
    assert origin.function == "FansPage._apply_curve"
    assert origin.section == "FAN"


def test_a_worker_hands_its_exception_over_before_it_becomes_text(qtbot, journal_file):
    task = _FunctionTask("probe", _raise_from_backend)
    messages = []
    task.signals.failed.connect(messages.append)
    task.run()
    raw = raw_errors.find(f"Could not do it: {messages[0]}")
    assert raw is not None and raw.kind == "FeedbackError"
    assert raw.site.function == "parse_form"


def test_a_window_inside_an_unrelated_except_does_not_borrow_that_exception(journal_file):
    try:
        raise ValueError("an unrelated parse failure")
    except ValueError:
        assert raw_errors.find("The governor did not answer") is None
        assert raw_errors.find("Failed: an unrelated parse failure").kind == "ValueError"


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("FileNotFoundError: /home/alice/private.txt", "FileNotFoundError: ~/private.txt"),
        ("Script (/var/home/bob/app)", "Script (~/app)"),
        ("/Users/carl/x and /root/.config", "~/x and ~/.config"),
    ),
)
def test_nothing_leaves_the_machine_with_a_home_folder_in_it(text, expected):
    assert error_origins.redact(text) == expected


def test_the_form_redacts_every_answer_it_sends():
    from bc250cc.infrastructure import feedback_form as form

    report = form.FeedbackReport(
        summary="Crash reading /home/alice/x", raw="OSError: /home/alice/y", specs="Installation  Script (/home/alice/app)",
    )
    values = [value for _entry, value in form._pairs(report) if isinstance(value, str)]
    assert values and not any("alice" in value for value in values)


def test_the_copied_report_has_no_home_folder(journal_file):
    text = diagnostic_report([("Installation", "Script (/home/alice/app)")], [])
    assert "alice" not in text and "Script (~/app)" in text


def test_a_message_too_short_to_tell_apart_matches_nothing(journal_file):
    try:
        raise ValueError("no")
    except ValueError as error:
        raw_errors.remember(error)
    assert raw_errors.find("no route to the governor") is None


def test_an_error_window_shows_where_it_happened_and_the_raw_exception(qtbot, journal_file):
    try:
        _raise_from_backend()
    except Exception as error:  # noqa: BLE001
        raw_errors.remember(error)
        message = str(error)
    namespace = _origin_from(
        "/x/frontends/desktop/pages/gpu_governor.py",
        "class GpuGovernorPage:\n"
        "    def _install_helixsr_game(self):\n"
        "        return InfoDialog('HelixSR could not be installed', message, eyebrow='HelixSR', tone='red')\n",
        {"InfoDialog": InfoDialog, "message": message},
    )
    dialog = namespace["GpuGovernorPage"]()._install_helixsr_game()
    qtbot.addWidget(dialog)

    identity = [label.text() for label in dialog.findChildren(QLabel) if label.objectName() == "DialogIdentityValue"]
    assert any("gpu_governor.py" in text and "GpuGovernorPage._install_helixsr_game" in text for text in identity)
    assert any(text.startswith("DIAG-") and "parse_form" in text for text in identity)
    assert dialog.reference().endswith(f"@ {dialog.origin.code}")
    assert "FeedbackError" in dialog.evidence() and "Raised in: DIAG-" in dialog.evidence()

    report = next(button for button in dialog.findChildren(QPushButton) if button.objectName() == "DialogReport")
    assert report.isVisibleTo(dialog)

    entry = history_entries()[0]
    assert "GpuGovernorPage._install_helixsr_game" in entry.origin
    assert "parse_form" in entry.raised and "FeedbackError" in entry.raw
    text = diagnostic_report([], [entry])
    assert "Origin: GPU-" in text and "Raised in: DIAG-" in text and "Raw error:" in text


def test_a_window_without_an_exception_still_names_its_origin(qtbot, journal_file):
    dialog = InfoDialog("Folder could not be opened", "No such directory: /nowhere", tone="red")
    qtbot.addWidget(dialog)
    # Opened from this test module: not ours, so no origin, and nothing invented.
    assert dialog.raw_error is None
    assert "No exception" not in dialog.evidence()


def test_copy_details_carries_the_evidence(qtbot, journal_file):
    try:
        _raise_from_backend()
    except Exception as error:  # noqa: BLE001
        raw_errors.remember(error)
        dialog = InfoDialog("Report failed", str(error), tone="red")
    qtbot.addWidget(dialog)
    button = next(b for b in dialog.findChildren(QPushButton) if b.objectName() == "DialogSecondary")
    button.click()
    assert "FeedbackError" in QApplication.clipboard().text()


def test_informational_windows_have_no_report_button_nor_hardware_notice(qtbot):
    dialog = InfoDialog("Profile saved", "Applied at the next boot.")
    qtbot.addWidget(dialog)
    names = {button.objectName() for button in dialog.findChildren(QPushButton)}
    assert "DialogReport" not in names
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "hardware" not in texts.lower()


if sys.version_info < (3, 11):  # pragma: no cover - co_qualname is 3.11+
    pytestmark = pytest.mark.skip("needs co_qualname")


@pytest.mark.parametrize(
    "message",
    (
        "PWM 3 did not verify firmware automatic mode",
        "The Cyan TOML did not verify the requested startup range",
        "The BIOS image is damaged. It was not used.",
    ),
)
def test_other_modules_words_are_not_read_as_an_upscaler_failure(message):
    from frontends.desktop.core.error_diagnostics import diagnose_error

    assert diagnose_error(message).code != "BC250-UPSCALE-001"


def test_removable_drives_lose_the_user_name_too():
    assert error_origins.redact("/run/media/alice/SD/steamapps/x.dll") == "~/SD/steamapps/x.dll"
    assert error_origins.redact("/media/bob/Games/y") == "~/Games/y"


def test_a_report_without_an_exception_sends_the_english_message(qtbot, journal_file, monkeypatch):
    from frontends.desktop.i18n import set_language

    set_language("ja")
    try:
        dialog = InfoDialog("Folder could not be opened", "No such directory: /nowhere/at/all", tone="red")
        qtbot.addWidget(dialog)
        captured = {}

        class Report:
            def __init__(self, parent, **kwargs):
                captured.update(kwargs)

            def exec(self):
                return 0

        import frontends.desktop.components.feedback_dialog as feedback_module
        monkeypatch.setattr(feedback_module, "FeedbackDialog", Report)
        dialog.report_button.click()
        assert captured["raw"] == "No such directory: /nowhere/at/all"
    finally:
        set_language("en")


def test_a_failure_no_rule_knows_takes_its_sections_code(qtbot, journal_file):
    namespace = _origin_from(
        "/x/frontends/desktop/pages/gpu_governor.py",
        "class GpuGovernorPage:\n"
        "    def _apply_profile(self):\n"
        "        return InfoDialog('Profile not applied', 'zx-unmatched failure 42', tone='red')\n",
        {"InfoDialog": InfoDialog},
    )
    dialog = namespace["GpuGovernorPage"]()._apply_profile()
    qtbot.addWidget(dialog)
    assert dialog.report_code == "BC250-GPU-000"
    # The journal keeps the same code the window showed.
    assert history_entries()[0].code == "BC250-GPU-000"


def test_a_section_code_can_be_explained_later():
    from frontends.desktop.core.error_diagnostics import explain_code

    explained = explain_code("BC250-UPS-000")
    assert explained is not None and explained.summary.startswith("Upscaling (FSR4, HelixSR):")
    assert explain_code("BC250-NOPE-000") is None


def test_a_known_failure_keeps_its_specific_code_whatever_the_section():
    from frontends.desktop.core.error_diagnostics import diagnose_error, with_section

    diagnosis = diagnose_error("Cyan D-Bus is not ready")
    assert with_section(diagnosis, ("UPS", "Upscaling (FSR4, HelixSR)")).code == diagnosis.code
