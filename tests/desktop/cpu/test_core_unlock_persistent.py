"""Persistence mode of the core unlock: the boot service of movacx/core_unlock_bc250.

The temporary unlock is lost at every full power-off. The persistent one
installs a boot service that writes the core mask again early in every cold
boot (hardware-validated on the maintainer's board, 2026-11-13). Control
Center clones the tool at a pinned revision, and its root helper installs it
from a root-only staged copy, exactly like the temporary tool.

The owner's one hard constraint for the card: choosing a mode must never
change its size.
"""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from bc250cc.infrastructure import core_unlock_trust
from bc250cc.infrastructure.core_unlock_persistence import (
    BOOT_SERVICE_STATE,
    BOOT_SERVICE_UNIT,
    BOOT_SERVICE_WANTS_LINK,
    detect_core_unlock_persistence,
)
from bc250cc.infrastructure.external_tools.catalog import (
    EXTERNAL_TOOL_DIRECTORIES,
    EXTERNAL_TOOL_LIFECYCLES,
    EXTERNAL_TOOLS,
)
from bc250cc.infrastructure.preparation_workflow import core_unlock_persistent_commands
from frontends.desktop.pages.cpu_control_view import (
    UNLOCK_MODE_PERSISTENT,
    UNLOCK_MODE_TEMPORARY,
    CoreUnlockState,
    CpuControlState,
    CpuControlView,
)

HELPER = Path(__file__).resolve().parents[3] / "privileged" / "helpers" / "bc250-core-unlock-helper"
GIT = Path("/usr/bin/git")
PERSISTENT_URL = "https://github.com/movacx/core_unlock_bc250"

# Stands in for the tool: says how it was run instead of installing anything.
SCRIPT = (
    b"import json, sys\n"
    b"print(json.dumps({'file': __file__, 'argv': sys.argv[1:]}))\n"
)


# ------------------------------------------------------------------ pins


def test_the_tool_is_pinned_once_and_the_helper_agrees_with_it():
    spec = EXTERNAL_TOOLS["core_unlock_persistent"]
    assert spec.upstream == PERSISTENT_URL
    assert len(spec.reviewed_revision) == 40
    assert spec.automated and spec.hardware_writes
    assert "core_unlock_persistent" in EXTERNAL_TOOL_LIFECYCLES
    assert EXTERNAL_TOOL_DIRECTORIES["core_unlock_persistent"] == "core_unlock_bc250"
    assert core_unlock_trust.PERSISTENT_REVIEWED_REVISION == spec.reviewed_revision

    helper = runpy.run_path(str(HELPER))
    assert helper["PERSISTENT_REVIEWED_REVISION"] == spec.reviewed_revision
    assert helper["PERSISTENT_REVIEWED_SCRIPT_SHA256"] == core_unlock_trust.PERSISTENT_REVIEWED_SCRIPT_SHA256
    assert helper["PERSISTENT_OFFICIAL_ORIGINS"] == {PERSISTENT_URL, PERSISTENT_URL + ".git"}
    assert helper["PERSISTENT_REPOSITORY_NAME"] == "core_unlock_bc250"


def test_preparation_clones_it_at_the_pinned_revision_and_secures_the_executable(tmp_path):
    from bc250cc.infrastructure.dependencias_repository import DependenciasRepository

    repository = DependenciasRepository.__new__(DependenciasRepository)
    destination = tmp_path / "core_unlock_bc250"
    script = "\n".join(core_unlock_persistent_commands(repository, PERSISTENT_URL, destination, None))
    assert EXTERNAL_TOOLS["core_unlock_persistent"].reviewed_revision in script
    assert PERSISTENT_URL in script
    assert f"chmod 0755 {destination / 'bc250-core-unlock'}" in script


# ------------------------------------------------------------------ helper


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        [str(GIT), "-C", str(repository), *arguments],
        check=True, capture_output=True, text=True,
        env={
            "PATH": "/usr/bin:/bin", "HOME": str(repository),
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
        },
    ).stdout.strip()


@pytest.fixture
def persist(tmp_path, monkeypatch):
    """main() against a real, clean clone of the tool, nothing reaching the system."""
    if not GIT.is_file():
        pytest.skip("git is needed to build a checkout the helper accepts")
    home = (tmp_path / "home").resolve()
    repository = home / "core_unlock_bc250"
    repository.mkdir(parents=True)
    home.chmod(0o755)
    repository.chmod(0o755)
    script = repository / "bc250-core-unlock"
    script.write_bytes(SCRIPT)
    script.chmod(0o755)
    _git(repository, "init", "-q")
    _git(repository, "add", "-A")
    _git(repository, "commit", "-q", "-m", "reviewed")
    _git(repository, "remote", "add", "origin", PERSISTENT_URL)

    run = tmp_path / "run"
    run.mkdir()
    helper = runpy.run_path(str(HELPER))["main"].__globals__
    state = {"threads": 12, "reboots": 0, "governors_touched": 0}

    def touched_governors():
        state["governors_touched"] += 1
        return ()

    for name, value in {
        "PERSISTENT_REVIEWED_REVISION": _git(repository, "rev-parse", "HEAD"),
        "PERSISTENT_REVIEWED_SCRIPT_SHA256": hashlib.sha256(SCRIPT).hexdigest(),
        "STAGING_PARENT": str(run),
        "_trusted_self": lambda: True,
        "_bc250_identity_present": lambda: True,
        "_systemd_running": lambda: True,
        "_invoking_user": lambda: (os.getuid(), os.getgid(), home),
        "_stop_gpu_governors": touched_governors,
        "_threads_present": lambda: state["threads"],
        "_reboot_after_core_unlock": lambda: state.__setitem__("reboots", state["reboots"] + 1),
    }.items():
        monkeypatch.setitem(helper, name, value)
    monkeypatch.setattr(os, "geteuid", lambda: 0)

    launched = []
    real_run = subprocess.run

    def run_tool_for_real(command, **kwargs):
        if command[0] == "/usr/bin/python3":
            launched.append(list(command))
            command = [sys.executable, *command[1:]]
        return real_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", run_tool_for_real)
    return helper, repository, run, launched, state


def _ran(capsys) -> dict:
    return next(
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    )


def test_install_runs_the_staged_copy_and_restarts_a_stock_board(persist, capsys):
    helper, repository, run, launched, state = persist
    assert helper["main"](["helper", "--persist-install", "--repo", str(repository)]) == 0

    report = _ran(capsys)
    assert report["argv"] == ["install"]
    # The verified bytes, staged where only root can reach, then removed.
    assert Path(report["file"]).parent.parent == run
    assert launched[-1][:2] == ["/usr/bin/python3", "-I"]
    assert list(run.iterdir()) == []
    assert state["reboots"] == 1
    # The unit runs before the governors at boot: nothing to stop here.
    assert state["governors_touched"] == 0


def test_install_on_an_unlocked_board_does_not_restart(persist, capsys):
    helper, repository, _run, _launched, state = persist
    state["threads"] = 16
    helper["main"](["helper", "--persist-install", "--repo", str(repository)])
    assert state["reboots"] == 0


def test_the_force_box_becomes_the_tool_force_mask(persist, capsys):
    helper, repository, *_ = persist
    helper["main"](["helper", "--persist-install", "--repo", str(repository), "--ignore-core-mask"])
    assert _ran(capsys)["argv"] == ["install", "--force-mask"]


def test_a_clone_at_another_revision_is_refused_before_anything_runs(persist, monkeypatch):
    helper, repository, _run, launched, state = persist
    monkeypatch.setitem(helper, "PERSISTENT_REVIEWED_REVISION", "0" * 40)
    with pytest.raises(RuntimeError, match="reviewed immutable revision"):
        helper["main"](["helper", "--persist-install", "--repo", str(repository)])
    assert launched == [] and state["reboots"] == 0


def test_the_temporary_tool_clone_cannot_be_installed_as_the_boot_service(persist, tmp_path):
    helper, *_ = persist
    other = (tmp_path / "home" / "bc250-core-unlock")
    other.mkdir()
    with pytest.raises(RuntimeError, match="not the expected"):
        helper["main"](["helper", "--persist-install", "--repo", str(other)])


def test_persistence_is_offered_on_systemd_only(persist, monkeypatch):
    helper, repository, *_ = persist
    monkeypatch.setitem(helper, "_systemd_running", lambda: False)
    with pytest.raises(RuntimeError, match="only offered on systemd"):
        helper["main"](["helper", "--persist-install", "--repo", str(repository)])


@pytest.mark.parametrize("argv", [
    ["--persist-uninstall", "--reboot"],
    ["--persist-install", "--repo"],
    ["--persist-install", "/tmp/x"],
    ["--persist-uninstall", "--ignore-core-mask"],
])
def test_the_argument_grammar_stays_closed(persist, argv):
    helper, *_ = persist
    with pytest.raises(RuntimeError, match="Expected exactly"):
        helper["main"](["helper", *argv])


def test_uninstall_needs_no_clone_and_uses_the_installed_tool(persist, tmp_path, monkeypatch, capsys):
    helper, *_ = persist
    installed = tmp_path / "var" / "bc250-core-unlock"
    installed.parent.mkdir()
    installed.write_bytes(SCRIPT)
    unit = tmp_path / "etc" / "bc250-core-unlock.service"
    monkeypatch.setitem(helper, "PERSISTENT_INSTALLED_BIN", installed)
    monkeypatch.setitem(helper, "PERSISTENT_SYSTEMD_UNIT", unit)
    monkeypatch.setitem(helper, "_installed_tool_trusted", lambda path: True)
    assert helper["main"](["helper", "--persist-uninstall"]) == 0
    assert _ran(capsys)["argv"] == ["uninstall"]


def test_an_untrusted_installed_copy_is_not_run_and_the_unit_is_removed_directly(
    persist, tmp_path, monkeypatch
):
    helper, _repository, _run, launched, _state = persist
    installed = tmp_path / "var" / "bc250-core-unlock"
    installed.parent.mkdir()
    installed.write_bytes(SCRIPT)
    unit = tmp_path / "etc" / "bc250-core-unlock.service"
    unit.parent.mkdir()
    unit.write_text("[Unit]\n")
    systemctl: list = []
    real_run = subprocess.run

    def record(command, **kwargs):
        if command[0] == "/usr/bin/systemctl":
            systemctl.append(command[1:])
            return subprocess.CompletedProcess(command, 0, "", "")
        return real_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", record)
    monkeypatch.setitem(helper, "PERSISTENT_INSTALLED_BIN", installed)
    monkeypatch.setitem(helper, "PERSISTENT_SYSTEMD_UNIT", unit)
    monkeypatch.setitem(helper, "_installed_tool_trusted", lambda path: False)
    assert helper["main"](["helper", "--persist-uninstall"]) == 0
    assert not unit.exists()
    assert ["disable", "bc250-core-unlock.service"] in systemctl
    assert launched == []


# ------------------------------------------------------------------ detection


CURRENT_UNIT = (
    "[Service]\nExecStart=/usr/bin/python3 -I "
    "/var/lib/bc250-core-unlock/bin/bc250-core-unlock apply --boot\n"
)
# What core_unlock_bc250 0.1.0 wrote: SELinux refuses to execute it on Bazzite.
OUTDATED_UNIT = "[Service]\nExecStart=/var/lib/bc250-core-unlock/bin/bc250-core-unlock apply --boot\n"


def _install(root: Path, *, enabled: bool, status: str = "", note: str = "",
             unit_text: str = CURRENT_UNIT, extra: dict | None = None) -> None:
    unit = root / BOOT_SERVICE_UNIT.lstrip("/")
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(unit_text)
    if enabled:
        link = root / BOOT_SERVICE_WANTS_LINK.lstrip("/")
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(unit)
    if status:
        record = root / BOOT_SERVICE_STATE.lstrip("/")
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({"status": status, "note": note, **(extra or {})}))


def test_an_enabled_boot_service_keeps_the_unlock_across_power_off(tmp_path):
    _install(tmp_path, enabled=True, status="unlocked")
    state = detect_core_unlock_persistence(physical_cores=8, logical_cpus=16, root=tmp_path)
    assert state["mechanism"] == "boot-service"
    assert state["survives_power_off"] is True
    assert state["boot_service_active"] is True


def test_a_service_that_disabled_itself_is_not_counted_and_says_why(tmp_path):
    """Give-up disables the unit but leaves its file: the file alone is not persistence."""
    _install(tmp_path, enabled=False, status="gave-up", note="Mask still 0x77 after 2 attempt(s)")
    state = detect_core_unlock_persistence(physical_cores=8, logical_cpus=16, root=tmp_path)
    assert state["mechanism"] == "volatile"
    assert state["boot_service_installed"] is True
    assert state["boot_service_active"] is False
    assert state["boot_service_note"].startswith("Mask still 0x77")


def test_an_enabled_unit_whose_last_run_gave_up_is_not_active(tmp_path):
    _install(tmp_path, enabled=True, status="gave-up")
    state = detect_core_unlock_persistence(physical_cores=8, logical_cpus=16, root=tmp_path)
    assert state["boot_service_active"] is False
    assert state["survives_power_off"] is False


def test_a_stock_board_with_the_service_installed_reports_it(tmp_path):
    _install(tmp_path, enabled=True, status="idle")
    state = detect_core_unlock_persistence(physical_cores=6, logical_cpus=12, root=tmp_path)
    assert state["mechanism"] == "stock"
    assert state["boot_service_active"] is True


def _boot(root: Path, boot_id: str, cmdline: str = "quiet") -> None:
    proc = root / "proc/sys/kernel/random"
    proc.mkdir(parents=True, exist_ok=True)
    (proc / "boot_id").write_text(boot_id + "\n")
    (root / "proc/cmdline").write_text(cmdline + "\n")


def test_a_unit_selinux_cannot_execute_needs_repair_not_in_use(tmp_path):
    """Bazzite, 2026-11-13: installed and enabled, state.json still "idle",
    6 cores after the reboot, and the card said "In use"."""
    _install(tmp_path, enabled=True, status="idle", unit_text=OUTDATED_UNIT)
    state = detect_core_unlock_persistence(physical_cores=6, logical_cpus=12, root=tmp_path)
    assert state["boot_service_repair"] == "outdated"
    assert state["boot_service_active"] is False


def test_a_service_that_did_not_run_this_boot_needs_repair(tmp_path):
    _install(tmp_path, enabled=True, status="idle",
             extra={"installed_boot_id": "install-boot", "last_run_boot_id": ""})
    _boot(tmp_path, "a-later-boot")
    state = detect_core_unlock_persistence(physical_cores=6, logical_cpus=12, root=tmp_path)
    assert state["boot_service_repair"] == "not-run"
    assert state["boot_service_active"] is False


@pytest.mark.parametrize("boot_id, cmdline", [
    ("install-boot", "quiet"),            # installed in this boot: no boot has run yet
    ("ran-boot", "quiet"),                # the service ran in this boot
    ("a-later-boot", "quiet bc250.core_unlock=0"),  # skipped on purpose
])
def test_a_service_that_had_no_chance_or_ran_is_fine(tmp_path, boot_id, cmdline):
    _install(tmp_path, enabled=True, status="unlocked",
             extra={"installed_boot_id": "install-boot", "last_run_boot_id": "ran-boot"})
    _boot(tmp_path, boot_id, cmdline)
    state = detect_core_unlock_persistence(physical_cores=8, logical_cpus=16, root=tmp_path)
    assert state["boot_service_repair"] == ""
    assert state["boot_service_active"] is True


def test_the_card_offers_repair_for_a_service_that_needs_it(qtbot):
    view = CpuControlView()
    qtbot.addWidget(view)
    view._set_mode(UNLOCK_MODE_PERSISTENT)
    view._apply_unlock(CoreUnlockState(
        helper_ready=True, persistence_supported=True, persistence_source_ready=True,
        persistence_installed=True, persistence_active=False, persistence_repair="not-run",
        persist_allowed=True, remove_allowed=True,
    ))
    persistent = view._mode_buttons[UNLOCK_MODE_PERSISTENT]
    assert persistent.tag.text() == "Needs repair"
    assert view.unlock_button.text() == "Repair persistence" and view.unlock_button.isEnabled()
    assert "did not run" in view._unlock_note.text()


def test_an_older_unit_is_an_update_not_a_service_that_did_not_run(qtbot):
    """Arch, 2026-11-14: a 0.1.0 unit ran fine this boot, yet the card said
    "did not run when this system started". An older unit is an update."""
    view = CpuControlView()
    qtbot.addWidget(view)
    view._set_mode(UNLOCK_MODE_PERSISTENT)
    view._apply_unlock(CoreUnlockState(
        unlocked=True, helper_ready=True, persistence_supported=True, persistence_source_ready=False,
        persistence_installed=True, persistence_active=False, persistence_repair="outdated",
        persist_allowed=True, remove_allowed=True,
    ))
    persistent = view._mode_buttons[UNLOCK_MODE_PERSISTENT]
    assert persistent.tag.text() == "Update available"
    assert view.unlock_button.text() == "Update persistence" and view.unlock_button.isEnabled()
    assert "did not run" not in view._unlock_note.text()
    assert "earlier version" in view._unlock_note.text()


def test_a_missing_persistence_tool_is_fetched_before_the_install(monkeypatch, tmp_path):
    """A reinstall left no core_unlock_bc250 clone and Repair stayed grey. The
    install now fetches the reviewed revision first, as the desktop user."""
    from bc250cc.infrastructure import cpu_repository

    repo = object.__new__(cpu_repository.CPURepository)
    monkeypatch.setattr(repo, "_tool_dir", lambda: tmp_path, raising=False)
    monkeypatch.setattr(repo, "_core_unlock_persistent_preflight", lambda: "/usr/libexec/helper", raising=False)
    monkeypatch.setattr(
        repo, "_hardware_source_checkout_command",
        lambda url, destination, os_repo=None: f"git-checkout {url} {destination}", raising=False,
    )
    command = repo.comando_persistir_desbloqueo_nucleos_cpu()
    assert command[:2] == ["/bin/sh", "-c"]
    script = command[2]
    assert script.startswith("set -e")
    assert "git-checkout https://github.com/movacx/core_unlock_bc250" in script
    assert "chmod 0755" in script
    last = script.splitlines()[-1]
    assert last.startswith("exec ") and "--persist-install" in last and "pkexec" in last


# ------------------------------------------------------------------ card


STATES = {
    "temporary-ready": CoreUnlockState(helper_ready=True, unlock_allowed=True,
                                       persistence_supported=True, persistence_source_ready=True,
                                       persist_allowed=True),
    "persistent-unlocked": CoreUnlockState(unlocked=True, helper_ready=True, persistence_supported=True,
                                           persistence_source_ready=True, persist_allowed=True),
    "persistent-active": CoreUnlockState(unlocked=True, helper_ready=True, persistence_supported=True,
                                         persistence_installed=True, persistence_active=True,
                                         remove_allowed=True),
    "persistent-gave-up": CoreUnlockState(helper_ready=True, persistence_supported=True,
                                          persistence_installed=True, persistence_status="gave-up",
                                          persistence_note="Mask still 0x77", remove_allowed=True),
    "unsupported": CoreUnlockState(),
}


def _view(qtbot, width=1440):
    view = CpuControlView()
    qtbot.addWidget(view)
    view.resize(width, 900)
    view.show()
    qtbot.waitExposed(view)
    return view


@pytest.mark.parametrize("width", [1180, 1440])
def test_switching_mode_does_not_make_the_card_jump(qtbot, width):
    """The card may grow for a stopped service's note, never on a mode click."""
    view = _view(qtbot, width)
    panel = view._risk_panel
    for state in STATES.values():
        view.apply_state(replace(CpuControlState(), core_unlock=state))
        heights = set()
        for mode in (UNLOCK_MODE_TEMPORARY, UNLOCK_MODE_PERSISTENT, UNLOCK_MODE_TEMPORARY):
            view._choose_mode(mode)
            qtbot.wait(1)
            heights.add(panel.height())
        assert len(heights) == 1, (state, heights)


def test_clicking_anywhere_on_an_option_selects_it(qtbot):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtCore import Qt as QtCore

    view = _view(qtbot)
    view.apply_state(replace(CpuControlState(), core_unlock=STATES["temporary-ready"]))
    option = view._mode_buttons[UNLOCK_MODE_PERSISTENT]
    qtbot.mouseClick(option.description, QtCore.MouseButton.LeftButton, pos=QPoint(4, 4))
    assert view.unlock_mode() == UNLOCK_MODE_PERSISTENT
    assert option.is_selected()
    assert not view._mode_buttons[UNLOCK_MODE_TEMPORARY].is_selected()
    assert view.unlock_button.text() == "Install persistence and restart"
    # Nothing installed: no removal link next to the button.
    assert not view.firmware_button.isVisible()


def test_each_option_says_whether_it_is_the_one_in_use(qtbot):
    view = _view(qtbot)
    view.apply_state(replace(CpuControlState(), core_unlock=STATES["persistent-unlocked"]))
    assert view._mode_buttons[UNLOCK_MODE_TEMPORARY].tag.text() == "In use"
    assert view._mode_buttons[UNLOCK_MODE_PERSISTENT].tag.isHidden()
    view.apply_state(replace(CpuControlState(), core_unlock=STATES["persistent-active"]))
    assert view._mode_buttons[UNLOCK_MODE_TEMPORARY].tag.isHidden()
    assert view._mode_buttons[UNLOCK_MODE_PERSISTENT].tag.text() == "In use"
    view.apply_state(replace(CpuControlState(), core_unlock=STATES["persistent-gave-up"]))
    assert view._mode_buttons[UNLOCK_MODE_PERSISTENT].tag.text() == "Service stopped"
    assert view._mode_buttons[UNLOCK_MODE_PERSISTENT].tag.property("tone") == "orange"


def test_a_board_with_the_service_installed_opens_on_persistence_until_the_owner_chooses(qtbot):
    view = _view(qtbot)
    assert view.unlock_mode() == UNLOCK_MODE_TEMPORARY
    view.apply_state(replace(CpuControlState(), core_unlock=STATES["persistent-active"]))
    assert view.unlock_mode() == UNLOCK_MODE_PERSISTENT
    assert view.unlock_button.text() == "Persistence active"
    assert not view.unlock_button.isEnabled()
    assert view.firmware_button.text() == "Remove persistence"

    view._choose_mode(UNLOCK_MODE_TEMPORARY)
    view.apply_state(replace(CpuControlState(), core_unlock=STATES["persistent-active"]))
    assert view.unlock_mode() == UNLOCK_MODE_TEMPORARY
    assert view.firmware_button.text() == "Firmware persistence guide"


def test_each_mode_sends_its_own_request(qtbot):
    view = _view(qtbot)
    sent: list = []
    view.unlock_cores_requested.connect(lambda force: sent.append(("temporary", force)))
    view.persist_unlock_requested.connect(lambda force: sent.append(("persist", force)))
    view.remove_persistence_requested.connect(lambda: sent.append(("remove",)))
    view.firmware_persistence_requested.connect(lambda: sent.append(("guide",)))

    view.apply_state(replace(CpuControlState(), core_unlock=STATES["temporary-ready"]))
    view.unlock_button.click()
    view.firmware_button.click()
    view._choose_mode(UNLOCK_MODE_PERSISTENT)
    view.ignore_mask_line.check.setChecked(True)
    view.unlock_button.click()
    assert not view.firmware_button.isVisible()  # nothing installed yet: no link
    view.apply_state(replace(CpuControlState(), core_unlock=STATES["persistent-gave-up"]))
    view.firmware_button.click()

    assert sent == [("temporary", False), ("guide",), ("persist", True), ("remove",)]


def test_a_service_that_stopped_itself_offers_a_reinstall_and_shows_why(qtbot):
    view = _view(qtbot)
    view._choose_mode(UNLOCK_MODE_PERSISTENT)
    state = replace(STATES["persistent-gave-up"], persist_allowed=True, persistence_source_ready=True)
    view.apply_state(replace(CpuControlState(), core_unlock=state))
    assert view.unlock_button.text() == "Install persistence again"
    # Said in plain sight, not in a tooltip.
    assert view._unlock_note.isVisible()
    assert "Mask still 0x77" in view._unlock_note.text()
    view._choose_mode(UNLOCK_MODE_TEMPORARY)
    assert view._unlock_note.isVisible()


def test_persistence_is_unavailable_without_systemd(qtbot):
    view = _view(qtbot)
    view.apply_state(replace(CpuControlState(), core_unlock=STATES["unsupported"]))
    assert not view._mode_buttons[UNLOCK_MODE_PERSISTENT].isEnabled()
    assert "systemd" in view._mode_buttons[UNLOCK_MODE_PERSISTENT].toolTip()


# ------------------------------------------------------------------ session console


def _console_view(qtbot, settings):
    from PyQt6.QtWidgets import QPlainTextEdit

    view = CpuControlView(settings=settings)
    qtbot.addWidget(view)
    console = QPlainTextEdit("\n".join(f"line {index}" for index in range(60)))
    view.mount_console(console)
    view.resize(1440, 1600)
    view.show()
    qtbot.waitExposed(view)
    return view


def test_the_console_keeps_the_height_it_was_last_dragged_to(qtbot, tmp_path):
    from PyQt6.QtCore import QSettings

    from frontends.desktop.pages.cpu_control_view import (
        CONSOLE_DEFAULT_HEIGHT,
        CONSOLE_HEIGHT_KEY,
    )

    path = str(tmp_path / "ui.ini")
    view = _console_view(qtbot, QSettings(path, QSettings.Format.IniFormat))
    assert view.console_height() == CONSOLE_DEFAULT_HEIGHT
    view.console_grip.pressed.emit()
    view.console_grip.dragged.emit(150)
    assert view.console_height() == CONSOLE_DEFAULT_HEIGHT + 150
    view._console_save_timer.timeout.emit()
    view.close()

    reopened = _console_view(qtbot, QSettings(path, QSettings.Format.IniFormat))
    assert reopened.console_height() == CONSOLE_DEFAULT_HEIGHT + 150
    assert int(QSettings(path, QSettings.Format.IniFormat).value(CONSOLE_HEIGHT_KEY)) == CONSOLE_DEFAULT_HEIGHT + 150


def test_the_console_grip_sits_below_it_and_double_click_fits_the_text(qtbot, tmp_path):
    from PyQt6.QtCore import QSettings

    from frontends.desktop.pages.cpu_control_view import CONSOLE_DEFAULT_HEIGHT

    view = _console_view(qtbot, QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat))
    console, grip = view._console, view.console_grip
    assert grip.geometry().top() >= console.geometry().bottom()
    grip.double_clicked.emit()
    assert view.console_height() > CONSOLE_DEFAULT_HEIGHT
    grip.double_clicked.emit()
    assert view.console_height() == CONSOLE_DEFAULT_HEIGHT


def test_a_broken_saved_height_falls_back_and_is_clamped(qtbot, tmp_path):
    from PyQt6.QtCore import QSettings

    from frontends.desktop.pages.cpu_control_view import (
        CONSOLE_DEFAULT_HEIGHT,
        CONSOLE_HEIGHT_KEY,
        CONSOLE_MIN_HEIGHT,
    )

    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    settings.setValue(CONSOLE_HEIGHT_KEY, "tall")
    assert _console_view(qtbot, settings).console_height() == CONSOLE_DEFAULT_HEIGHT
    settings.setValue(CONSOLE_HEIGHT_KEY, 5)
    assert _console_view(qtbot, settings).console_height() == CONSOLE_MIN_HEIGHT


# ------------------------------------------------------------------ nosmt (SteamOS)


@pytest.mark.parametrize("spec, expected", [("0-11", 12), ("0-15", 16), ("0-5,6-11", 12),
                                            ("0", 1), ("", 0), ("garbage", 0)])
def test_present_threads_are_counted_from_sysfs(tmp_path, spec, expected):
    from bc250cc.infrastructure.hardware_identity import cpu_threads_present

    path = tmp_path / "present"
    path.write_text(spec + "\n")
    assert cpu_threads_present(path) == expected


@pytest.mark.parametrize("present, online, shape, unlocked", [
    (12, 6, True, False),    # stock SteamOS board under nosmt
    (16, 8, False, True),    # unlocked SteamOS board under nosmt
    (12, 12, True, False),   # stock elsewhere
])
def test_nosmt_does_not_hide_the_stock_or_unlocked_shape(monkeypatch, tmp_path, present, online, shape, unlocked):
    """SteamOS boots with nosmt: 6 online threads on a stock board kept the
    Persistence option blocked (2026-11-13)."""
    from bc250cc.infrastructure import cpu_repository

    monkeypatch.setattr(cpu_repository, "cpu_threads_present", lambda: present)
    monkeypatch.setattr(cpu_repository.os, "cpu_count", lambda: online)
    monkeypatch.setattr(cpu_repository.psutil, "cpu_count", lambda logical=True: online // 2 if not logical else online)
    monkeypatch.setattr(cpu_repository, "is_bc250_platform", lambda: True)
    repo = object.__new__(cpu_repository.CPURepository)
    monkeypatch.setattr(repo, "_tool_dir", lambda: tmp_path, raising=False)
    monkeypatch.setattr(repo, "_ejecutar", lambda *a, **k: (1, "", ""), raising=False)
    monkeypatch.setattr(repo, "_service_state", lambda *a, **k: "inactive", raising=False)
    monkeypatch.setattr(repo, "_core_unlock_helper_path", lambda: "", raising=False)
    state = repo.estado_desbloqueo_nucleos_cpu()
    assert state["supported_stock_shape"] is shape
    assert state["unlocked"] is unlocked
    assert state["logical_cpus"] == present
