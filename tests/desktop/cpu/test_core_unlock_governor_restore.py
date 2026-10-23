"""A refused core unlock must not leave the GPU governor disabled.

The helper disables every GPU governor before the upstream tool runs, because
the tool talks to the SMU mailbox the governors also use. When the tool then
refused a core mask other than 0x77 (the common failure on those boards), no
reboot followed and the governor stayed disabled: the GPU ran unmanaged until
the owner noticed. It is put back now whenever the tool provably stopped
before any SMU message; after one, upstream's advice is to abort, not retry.
"""

from __future__ import annotations

import os
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[3] / "privileged" / "helpers" / "bc250-core-unlock-helper"
CYAN = "cyan-skillfish-governor-smu.service"
OBERON = "oberon-governor.service"
REFUSAL = (
    "non-0x77 presence mask detected, high probability of defective cores - STOPPING!\n"
    "pass -f to ignore and proceed anyway (at your own risk)"
)


class _Systemd:
    """Just enough systemctl for the helper, plus the upstream tool's answer."""

    def __init__(self, units: dict[str, dict], upstream=None, failing: tuple = ()):
        self.units = units
        self.upstream = upstream or subprocess.CompletedProcess([], 0, "", "")
        self.failing = failing
        self.calls: list[list[str]] = []

    def run(self, command, **_):
        command = [str(part) for part in command]
        self.calls.append(command)
        if command[0] == "/usr/bin/python3":
            if isinstance(self.upstream, BaseException):
                raise self.upstream
            return self.upstream
        verb, unit = command[1], command[-1]
        state = self.units.get(unit)
        if tuple(command[1:]) in self.failing:
            return subprocess.CompletedProcess(command, 1, "", f"{verb} failed")
        if verb == "show":
            return subprocess.CompletedProcess(command, 0, "loaded" if state else "not-found", "")
        if verb == "is-enabled":
            return subprocess.CompletedProcess(command, 0 if state["enabled"] else 1, "", "")
        if verb == "is-active":
            return subprocess.CompletedProcess(command, 0 if state["active"] else 3, "", "")
        if verb == "disable":
            state.update(enabled=False, active=False)
        elif verb == "enable":
            state["enabled"] = True
        elif verb == "start":
            state["active"] = True
        return subprocess.CompletedProcess(command, 0, "", "")


class _NoOpenRC:
    def __init__(self, path):
        self.path = str(path)

    def exists(self):
        return False

    def is_file(self):
        return self.path == "/usr/bin/git"


def _unlock(monkeypatch, tmp_path, system: _Systemd) -> tuple[list, BaseException | None]:
    helper = runpy.run_path(str(HELPER))["main"].__globals__
    monkeypatch.setitem(helper, "STAGING_PARENT", str(tmp_path))
    reboots: list = []
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(subprocess, "run", system.run)
    for name, fake in {
        "_trusted_self": lambda: True,
        "_bc250_identity_present": lambda: True,
        "Path": _NoOpenRC,
        "_invoking_user": lambda: (1000, 1000, tmp_path),
        "_validate_repository": lambda *_: b"",
        "_reboot_after_core_unlock": lambda: reboots.append(True),
    }.items():
        monkeypatch.setitem(helper, name, fake)
    try:
        helper["main"](["helper", "--repo", str(tmp_path), "--reboot"])
    except RuntimeError as error:
        return reboots, error
    return reboots, None


def _units(cyan=(True, True), oberon=(False, False)) -> dict[str, dict]:
    return {
        CYAN: {"enabled": cyan[0], "active": cyan[1]},
        OBERON: {"enabled": oberon[0], "active": oberon[1]},
    }


def test_a_refused_core_mask_puts_the_governor_back(monkeypatch, tmp_path):
    units = _units()
    upstream = subprocess.CompletedProcess([], 1, "core presence mask: 0x0000007B\n", REFUSAL)
    reboots, error = _unlock(monkeypatch, tmp_path, _Systemd(units, upstream))
    assert "non-0x77" in str(error) and "back as they were" in str(error)
    assert units[CYAN] == {"enabled": True, "active": True}
    # Oberon was installed but off; restoring must not switch it on as well.
    assert units[OBERON] == {"enabled": False, "active": False}
    assert reboots == []


def test_a_tool_that_never_read_the_mask_puts_it_back_too(monkeypatch, tmp_path):
    units = _units()
    upstream = subprocess.CompletedProcess([], 1, "", "PermissionError: /sys/bus/pci/devices/0000:00:00.0/config")
    _reboots, error = _unlock(monkeypatch, tmp_path, _Systemd(units, upstream))
    assert "back as they were" in str(error)
    assert units[CYAN] == {"enabled": True, "active": True}


def test_an_interpreter_that_cannot_start_puts_it_back(monkeypatch, tmp_path):
    units = _units()
    _reboots, error = _unlock(monkeypatch, tmp_path, _Systemd(units, FileNotFoundError("/usr/bin/python3")))
    assert "could not start" in str(error)
    assert units[CYAN] == {"enabled": True, "active": True}


@pytest.mark.parametrize(
    "stderr",
    ["RuntimeError: mailbox timeout - abort, do not retry", "Q3 0x98 returned 0xFE - is the governor stopped?", "mask did not take"],
)
def test_after_an_smu_message_the_governor_stays_off(monkeypatch, tmp_path, stderr):
    units = _units()
    system = _Systemd(units, subprocess.CompletedProcess([], 1, "core presence mask: 0x00000077\n", stderr))
    reboots, error = _unlock(monkeypatch, tmp_path, system)
    assert "stay disabled" in str(error) and "Power the board off" in str(error)
    assert units[CYAN] == {"enabled": False, "active": False}
    assert not any(call[1] in {"enable", "start"} for call in system.calls if call[0] == "/usr/bin/systemctl")
    assert reboots == []


def test_a_successful_unlock_still_disables_and_reboots(monkeypatch, tmp_path):
    units = _units()
    upstream = subprocess.CompletedProcess([], 0, "core presence mask: 0x00000077\nOK. reboot\n", "")
    reboots, error = _unlock(monkeypatch, tmp_path, _Systemd(units, upstream))
    assert error is None and reboots == [True]
    assert units[CYAN] == {"enabled": False, "active": False}


def test_a_governor_that_will_not_stop_restores_the_ones_already_stopped(monkeypatch, tmp_path):
    units = _units(oberon=(True, True))
    system = _Systemd(units, failing=(("disable", "--now", OBERON),))
    _reboots, error = _unlock(monkeypatch, tmp_path, system)
    assert "disable failed" in str(error)
    assert units[CYAN] == {"enabled": True, "active": True}
    assert not any(call[0] == "/usr/bin/python3" for call in system.calls)


def test_a_restore_that_fails_is_named_in_the_error(monkeypatch, tmp_path):
    units = _units()
    upstream = subprocess.CompletedProcess([], 1, "core presence mask: 0x0000007B\n", REFUSAL)
    system = _Systemd(units, upstream, failing=(("enable", CYAN),))
    _reboots, error = _unlock(monkeypatch, tmp_path, system)
    assert f"could not be restored: {CYAN}" in str(error)
    assert "non-0x77" in str(error)


# ------------------------------------------------------------------ OpenRC


class _OpenRC:
    """rc-service / rc-update for Artix, with a default runlevel on disk."""

    def __init__(self, upstream):
        self.enabled = {"cyan-skillfish-governor-smu": True, "oberon-governor": False}
        self.active = {"cyan-skillfish-governor-smu": True, "oberon-governor": False}
        self.upstream = upstream

    def run(self, command, **_):
        command = [str(part) for part in command]
        if command[0] == "/usr/bin/python3":
            return self.upstream
        tool, *rest = command
        if tool == "rc-update":
            action, key, _runlevel = rest
            self.enabled[key] = action == "add"
        elif tool == "rc-service":
            key, action = rest
            if action == "status":
                return subprocess.CompletedProcess(command, 0 if self.active[key] else 3, "", "")
            self.active[key] = action == "start"
        return subprocess.CompletedProcess(command, 0, "", "")


def test_openrc_gets_its_runlevel_and_service_back(monkeypatch, tmp_path):
    system = _OpenRC(subprocess.CompletedProcess([], 1, "core presence mask: 0x0000007B\n", REFUSAL))

    class Path_(_NoOpenRC):
        def exists(self):
            if self.path == "/run/openrc/softlevel":
                return True
            key = self.path.rsplit("/", 1)[-1]
            return self.path.startswith("/etc/runlevels/default/") and system.enabled.get(key, False)

        def is_file(self):
            return self.path == "/usr/bin/git" or self.path.startswith("/etc/init.d/")

        def is_symlink(self):
            return False

        def __truediv__(self, other):
            return Path_(f"{self.path}/{other}")

    helper = runpy.run_path(str(HELPER))["main"].__globals__
    monkeypatch.setitem(
        helper,
        "shutil",
        type("S", (), {"which": staticmethod(lambda name: f"/sbin/{name}"), "rmtree": staticmethod(shutil.rmtree)}),
    )
    monkeypatch.setitem(helper, "STAGING_PARENT", str(tmp_path))
    monkeypatch.setattr(subprocess, "run", system.run)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    for name, fake in {
        "Path": Path_,
        "_trusted_self": lambda: True,
        "_bc250_identity_present": lambda: True,
        "_invoking_user": lambda: (1000, 1000, tmp_path),
        "_validate_repository": lambda *_: b"",
        "_reboot_after_core_unlock": lambda: None,
    }.items():
        monkeypatch.setitem(helper, name, fake)

    with pytest.raises(RuntimeError, match="back as they were"):
        helper["main"](["helper", "--repo", str(tmp_path), "--reboot"])
    assert system.enabled == {"cyan-skillfish-governor-smu": True, "oberon-governor": False}
    assert system.active == {"cyan-skillfish-governor-smu": True, "oberon-governor": False}
