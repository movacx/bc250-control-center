"""The application's own log, and what a problem report reads from it."""

from __future__ import annotations

import logging
import sys

from bc250cc.infrastructure import report_attachments
from bc250cc.shared import logging_config


def test_the_app_logs_to_a_file_a_report_can_read(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    root = logging.getLogger()
    before = list(root.handlers)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    try:
        logging_config.configure_logging()
        logging_config.configure_logging()  # twice: still one file handler
        added = [handler for handler in root.handlers if handler not in before]
        assert len(added) == 1
        logging.getLogger("bc250cc.test").warning("the fan curve could not be read")
        added[0].flush()
        assert "the fan curve could not be read" in report_attachments._application_log()
    finally:
        for handler in root.handlers[:]:
            if handler not in before:
                root.removeHandler(handler)
                handler.close()


def test_settings_and_helper_logs_go_with_the_diagnosis(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(report_attachments.Path, "home", classmethod(lambda cls: tmp_path))
    config = tmp_path / ".config/bc250-control-center"
    config.mkdir(parents=True)
    (config / "config.json").write_text('{"gpu_governor": "cyan", "fan_preset": "balanced"}')
    helper = tmp_path / "state/bc250-control-center"
    helper.mkdir(parents=True)
    (helper / "steamos-game-helper.log").write_text("HELPER_RANGE: CPU boot-service values are outside the validated limits.\n")
    assert '"gpu_governor": "cyan"' in report_attachments._settings()
    assert "HELPER_RANGE" in report_attachments._helper_logs()
    titles = [title for title, _read in report_attachments.STATE_SECTIONS]
    assert {"Application log", "Control Center settings", "Helper logs"} <= set(titles)


def test_package_versions_are_not_taken_for_addresses():
    text = "cachyos/faugus-launcher 2.4.11.1-1 2.5.1-1\nepoch 1:2.0.0.1\ninet 192.168.1.20/24 from 10.0.0.5:22"
    clean = report_attachments.redact_machine(text)
    assert "2.4.11.1-1" in clean and "1:2.0.0.1" in clean
    assert "192.168.1.20" not in clean and "10.0.0.5" not in clean


def test_a_generic_account_name_leaves_the_apps_own_words_alone(monkeypatch):
    monkeypatch.setattr(report_attachments.getpass, "getuser", lambda: "bc250")
    text = "/tmp/bc250-helixsr.Ivb5BY/x.zip ~/.local/state/bc250-control-center/terminal"
    assert report_attachments.redact_machine(text) == text


def test_a_workflow_log_heading_does_not_start_a_section_of_the_diagnosis():
    state = (
        "== Storage ==\n/dev/nvme0n1p1 50%\n\n"
        "== Last workflow logs ==\n[workflow-1.log]\n== Staging protected SteamOS AMDGPU backend ==\n"
        "[OK] staged\nERROR: unsupported kernel\n"
    )
    sections = dict(report_attachments.split_sections(state, ("Storage", "Last workflow logs")))
    assert list(sections) == ["Storage", "Last workflow logs"]
    assert "== Staging protected SteamOS AMDGPU backend ==" in sections["Last workflow logs"]
    assert sections["Last workflow logs"].endswith("ERROR: unsupported kernel")
