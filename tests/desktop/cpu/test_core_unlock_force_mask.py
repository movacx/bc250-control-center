"""Upstream's "-f": unlock a board whose core mask is not the usual 0x77.

Asked for on Telegram (2026-09-29): a board with a different mask passed the
owner's tests, and the upstream tool (rw-r-r-0644/bc250-core-unlock) refuses
it unless run with -f. The danger zone's "Unlock support" row became a box for
it; the helper passes -f only when that box sent --ignore-core-mask.
"""

from __future__ import annotations

import os
import runpy
import subprocess
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QDialog

from bc250cc.infrastructure.cpu_repository import CORE_UNLOCK_REPOSITORY, CPURepository
from frontends.desktop.pages import cpu_smu
from frontends.desktop.pages.cpu_control_view import CoreUnlockState, CpuControlView
from frontends.desktop.pages.cpu_smu import CpuSmuPage

HELPER = Path(__file__).resolve().parents[3] / "privileged" / "helpers" / "bc250-core-unlock-helper"


# ------------------------------------------------------------------ helper


def _helper_run(monkeypatch, tmp_path, argv):
    """Run the helper's main() up to the upstream call, with nothing real."""
    helper_globals = runpy.run_path(str(HELPER))["main"].__globals__
    monkeypatch.setitem(helper_globals, "STAGING_PARENT", str(tmp_path))
    launched = []
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fakes = {
        "_trusted_self": lambda: True,
        "_bc250_identity_present": lambda: True,
        "Path": lambda _path: type("P", (), {"is_file": lambda self: True})(),
        "_invoking_user": lambda: (1000, 1000, tmp_path),
        "_validate_repository": lambda path, *_: b"print('ok')\n",
        "_stop_gpu_governors": lambda: (),
        "_reboot_after_core_unlock": lambda: None,
    }
    for name, fake in fakes.items():
        monkeypatch.setitem(helper_globals, name, fake)
    monkeypatch.setattr(
        subprocess, "run",
        lambda command, **_: launched.append(command) or subprocess.CompletedProcess(command, 0, "", ""),
    )
    helper_globals["main"](argv)
    return launched[-1]


def test_the_helper_runs_upstream_without_f_by_default(monkeypatch, tmp_path):
    command = _helper_run(monkeypatch, tmp_path, ["helper", "--repo", str(tmp_path), "--reboot"])
    assert command[:2] == ["/usr/bin/python3", "-I"]
    assert command[2].endswith("/bc250-unlock-cores.py")
    assert "-f" not in command


def test_the_helper_passes_f_only_for_the_owners_explicit_flag(monkeypatch, tmp_path):
    command = _helper_run(
        monkeypatch, tmp_path, ["helper", "--repo", str(tmp_path), "--reboot", "--ignore-core-mask"]
    )
    assert command[3:] == ["-f"]


@pytest.mark.parametrize(
    "arguments",
    [
        ["--ignore-core-mask", "--repo", "/r", "--reboot"],
        ["--repo", "/r", "--reboot", "-f"],
        ["--repo", "/r", "--reboot", "--ignore-core-mask", "--ignore-core-mask"],
        ["--repo", "/r", "--ignore-core-mask", "--reboot"],
    ],
)
def test_the_helper_refuses_any_other_argument_shape(monkeypatch, tmp_path, arguments):
    with pytest.raises(RuntimeError, match="Expected exactly"):
        _helper_run(monkeypatch, tmp_path, ["helper", *arguments])


# ------------------------------------------------------------------ command


class _Repository(CPURepository):
    def __init__(self, tools):
        self.tools = tools

    def _tool_dir(self):
        return self.tools

    def _core_unlock_helper_path(self):
        return "/usr/libexec/bc250-control-center/bc250-core-unlock-helper"

    def _command_path(self, name):
        return "/usr/bin/pkexec" if name == "pkexec" else ""

    def _core_unlock_repository_state(self, _repository):
        return CORE_UNLOCK_REPOSITORY, True, True


def test_the_command_carries_the_flag_only_when_asked(tmp_path):
    repository = tmp_path / "bc250-core-unlock"
    (repository / ".git").mkdir(parents=True)
    (repository / "bc250-unlock-cores.py").write_text("#!/usr/bin/python3\n", encoding="utf-8")
    plain = _Repository(tmp_path).comando_desbloquear_nucleos_cpu()
    forced = _Repository(tmp_path).comando_desbloquear_nucleos_cpu(ignore_core_mask=True)
    assert plain[-1] == "--reboot"
    assert forced[-2:] == ["--reboot", "--ignore-core-mask"]
    assert forced[:-1] == plain


# ------------------------------------------------------------------ page


def _page(monkeypatch):
    dialogs, operations = [], []

    class Dialog:
        def __init__(self, title, message, summary=(), **_):
            dialogs.append((message, dict(summary)))

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(cpu_smu, "ConfirmDialog", Dialog)
    requested = []
    controller = type("C", (), {
        "comando_desbloquear_nucleos_cpu": lambda self, ignore_core_mask=False: requested.append(ignore_core_mask),
    })()
    page = type("Page", (), {
        "_request_core_unlock": CpuSmuPage._request_core_unlock,
        "process": None,
        "controller": controller,
        "current_state": {"core_unlock_repository_ready": True, "core_unlock_helper_ready": True},
        "_build_and_start_process": lambda self, operation, *_: operations.append(operation),
    })()
    return page, dialogs, operations, requested


def test_the_one_confirmation_says_the_mask_check_is_skipped(monkeypatch):
    page, dialogs, operations, requested = _page(monkeypatch)
    page._request_core_unlock(ignore_core_mask=True)
    message, summary = dialogs[0]
    assert "(-f)" in message and "MCE" in message
    assert summary["Core mask check"] == "Skipped (-f)"
    operations[0]()
    assert requested == [True]


def test_without_the_box_the_confirmation_is_the_usual_one(monkeypatch):
    page, dialogs, operations, requested = _page(monkeypatch)
    page._request_core_unlock()
    message, summary = dialogs[0]
    assert "(-f)" not in message and "Core mask check" not in summary
    operations[0]()
    assert requested == [False]


# ------------------------------------------------------------------ view


def test_the_box_replaces_the_support_row_and_rides_on_the_button(qtbot):
    view = CpuControlView()
    qtbot.addWidget(view)
    assert not hasattr(view, "unlock_support_row")
    line = view.ignore_mask_line
    assert view._risk_panel.isAncestorOf(line)
    assert not line.isEnabled()

    view._apply_unlock(CoreUnlockState(helper_ready=True, unlock_allowed=True))
    assert line.isEnabled() and not line.check.isChecked()
    assert "Ready" in view.unlock_button.toolTip()

    sent = []
    view.unlock_cores_requested.connect(sent.append)
    view.unlock_button.click()
    line.check.setChecked(True)
    view.unlock_button.click()
    assert sent == [False, True]

    # Losing the unlock (helper gone, operation running) clears the box too.
    view._apply_unlock(CoreUnlockState(helper_ready=False, unlock_allowed=False))
    assert not line.isEnabled() and not line.check.isChecked()
    assert "Not installed" in view.unlock_button.toolTip()
