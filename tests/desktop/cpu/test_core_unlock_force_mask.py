"""Upstream's "-f": unlock a board whose core mask is not the usual 0x77.

Asked for on Telegram (2026-09-29): a board with a different mask passed the
owner's tests, and the upstream tool (rw-r-r-0644/bc250-core-unlock) refuses
it unless run with -f. The danger zone's "Unlock support" row became a box for
it; the helper passes -f only when that box sent --ignore-core-mask.

2026-11-19: a 0xB7 owner's report turned the box into a list of masks. A mask
other than 0x77 is sent as --accept-mask: the helper probes upstream without
-f and goes on with -f only when the board really reads the chosen mask.
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


def _helper_run(monkeypatch, tmp_path, argv, results=None):
    """Run the helper's main() up to the upstream call, with nothing real.

    ``results`` are the upstream runs' (returncode, stdout, stderr), in order;
    every run succeeds silently when it is not given."""
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
    pending = list(results or ())

    def fake_run(command, **_):
        launched.append(command)
        code, out, err = pending.pop(0) if pending else (0, "", "")
        return subprocess.CompletedProcess(command, code, out, err)

    monkeypatch.setattr(subprocess, "run", fake_run)
    helper_globals["main"](argv)
    return launched[-1] if results is None else launched


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
        ["--repo", "/r", "--reboot", "--accept-mask"],
        ["--repo", "/r", "--reboot", "--ignore-core-mask", "--accept-mask", "0xB7"],
        ["--accept-mask", "0xB7", "--repo", "/r", "--reboot"],
    ],
)
def test_the_helper_refuses_any_other_argument_shape(monkeypatch, tmp_path, arguments):
    with pytest.raises(RuntimeError, match="Expected exactly"):
        _helper_run(monkeypatch, tmp_path, ["helper", *arguments])


REFUSED = "non-0x77 presence mask detected, high probability of defective cores - STOPPING!"


def _probe(mask):
    return (1, f"core presence mask: 0x{mask:08X}\n", REFUSED)


def test_an_accepted_mask_unlocks_only_after_the_probe_reads_it(monkeypatch, tmp_path, capsys):
    runs = _helper_run(
        monkeypatch, tmp_path,
        ["helper", "--repo", str(tmp_path), "--reboot", "--accept-mask", "0xB7"],
        results=[_probe(0xB7), (0, "after write       : 0x000000FF\n", "")],
    )
    assert len(runs) == 2
    assert "-f" not in runs[0] and runs[1][3:] == ["-f"]
    assert "matches the owner's choice" in capsys.readouterr().out


def test_a_different_mask_is_refused_before_any_write(monkeypatch, tmp_path):
    launched = []
    with pytest.raises(RuntimeError, match="0x7E, not the 0xB7") as error:
        launched = _helper_run(
            monkeypatch, tmp_path,
            ["helper", "--repo", str(tmp_path), "--reboot", "--accept-mask", "0xB7"],
            results=[_probe(0x7E)],
        )
    assert "Nothing was written to the SMU" in str(error.value)
    assert launched == []  # raised on the probe: no second, forced run


def test_a_stock_board_unlocks_on_the_probe_itself(monkeypatch, tmp_path):
    runs = _helper_run(
        monkeypatch, tmp_path,
        ["helper", "--repo", str(tmp_path), "--reboot", "--accept-mask", "0xB7"],
        results=[(0, "core presence mask: 0x00000077\nOK.", "")],
    )
    assert len(runs) == 1 and "-f" not in runs[0]


@pytest.mark.parametrize("mask", ["0x77", "0xFF", "0x3F", "0x1B7", "zz", "0x00"])
def test_only_six_core_harvests_other_than_stock_are_accepted(monkeypatch, tmp_path, mask):
    with pytest.raises(RuntimeError, match="(?i)core mask"):
        _helper_run(monkeypatch, tmp_path, ["helper", "--repo", str(tmp_path), "--reboot", "--accept-mask", mask])


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
    accepted = _Repository(tmp_path).comando_desbloquear_nucleos_cpu(accept_mask=0xB7)
    assert accepted[-3:] == ["--reboot", "--accept-mask", "0xB7"]
    stock = _Repository(tmp_path).comando_desbloquear_nucleos_cpu(accept_mask=0x77)
    assert stock == plain


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
        "comando_desbloquear_nucleos_cpu": lambda self, ignore_core_mask=False, accept_mask=None: requested.append(
            (ignore_core_mask, accept_mask)
        ),
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
    assert requested == [(True, None)]


def test_a_chosen_mask_is_named_in_the_confirmation(monkeypatch):
    page, dialogs, operations, requested = _page(monkeypatch)
    page._request_core_unlock(0xB7)
    message, summary = dialogs[0]
    assert "0xB7" in message and "MCE" in message and "(-f)" not in message
    assert summary["Core mask check"] == "Only 0xB7"
    operations[0]()
    assert requested == [(False, 0xB7)]


def test_without_the_box_the_confirmation_is_the_usual_one(monkeypatch):
    page, dialogs, operations, requested = _page(monkeypatch)
    page._request_core_unlock()
    message, summary = dialogs[0]
    assert "(-f)" not in message and "Core mask check" not in summary
    operations[0]()
    assert requested == [(False, None)]


# ------------------------------------------------------------------ view


def test_the_mask_list_replaces_the_box_and_rides_on_the_button(qtbot):
    view = CpuControlView()
    qtbot.addWidget(view)
    assert not hasattr(view, "unlock_support_row")
    assert not hasattr(view, "ignore_mask_line")
    line = view.core_mask_line
    assert view._risk_panel.isAncestorOf(line)
    assert not line.isEnabled()
    masks = [line.combo.itemData(i) for i in range(line.combo.count())]
    assert masks == [0x77, 0xB7, 0x7E]

    view._apply_unlock(CoreUnlockState(helper_ready=True, unlock_allowed=True))
    assert line.isEnabled() and line.mask() == 0x77 and not line.force()
    assert "Ready" in view.unlock_button.toolTip()

    sent = []
    view.unlock_cores_requested.connect(sent.append)
    view.unlock_button.click()
    line.combo.setCurrentIndex(1)
    view.unlock_button.click()
    assert sent == [0x77, 0xB7]

    # Losing the unlock (helper gone, operation running) puts it back on 0x77.
    view._apply_unlock(CoreUnlockState(helper_ready=False, unlock_allowed=False))
    assert not line.isEnabled() and line.mask() == 0x77
    assert "Not installed" in view.unlock_button.toolTip()
