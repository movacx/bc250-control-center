"""A patch bc250_memory left behind is read by loading that driver again, never by writing over it."""
from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

HELPER = Path(__file__).resolve().parents[2] / "privileged/helpers/bc250-gddr6-temp-helper"


@pytest.fixture
def helper(monkeypatch):
    loader = importlib.machinery.SourceFileLoader("gddr6_helper_resume", str(HELPER))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    module.calls, module.published = [], False

    def run(argv, **_kw):
        module.calls.append(argv)
        if argv == ["modprobe", "bc250_memory"]:
            module.published = module.will_publish
        if argv == ["modprobe", "-r", "bc250_memory"]:
            module.published = False
        return SimpleNamespace(returncode=0, stdout=module.log, stderr="")

    module.will_publish, module.log = True, ""
    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(module, "smn_window_lock", contextlib.nullcontext)
    monkeypatch.setattr(module, "external_collector_lock", contextlib.nullcontext)
    monkeypatch.setattr(module, "governor_unsettled", lambda: "")
    monkeypatch.setattr(module, "_installed_reader", lambda: "reader")
    monkeypatch.setattr(module, "kernel_driver_loaded", lambda: module.published)
    monkeypatch.setattr(module, "kernel_driver_silent", lambda: False)
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(module, "_read_once", lambda *_a, **_k: {
        "payload": "legacy", "patch_active": module.published, "blocked_reason": ""})
    return module


def monitor(helper):
    return helper._do_monitor(Path("/repo"), 1000, 1000, 0.0001)


def test_it_loads_the_driver_reads_and_leaves_it_unloaded(helper, capsys):
    helper.log = f"[1.0] bc250_memory {helper.DRIVER_PATCHED}"
    assert monitor(helper) == 0
    assert [argv for argv in helper.calls if argv[0] == "modprobe"] == [
        ["modprobe", "bc250_memory"], ["modprobe", "-r", "bc250_memory"]]
    assert json.loads(capsys.readouterr().out.splitlines()[0])["patch_active"]


def test_a_patch_nobody_here_made_is_still_refused(helper, monkeypatch):
    monkeypatch.setattr(helper, "bios_version", lambda: "P3.00")
    monkeypatch.setattr(helper, "staged_checkout", lambda *_a: contextlib.nullcontext(Path("/staging")))
    with pytest.raises(RuntimeError, match="GDDR6_PATCH_EXISTING"):
        monitor(helper)
    assert not [argv for argv in helper.calls if argv[0] == "modprobe"]


def test_a_starting_governor_is_waited_for(helper, monkeypatch):
    helper.log = helper.DRIVER_PATCHED
    monkeypatch.setattr(helper, "governor_unsettled", lambda: "starting")
    with pytest.raises(RuntimeError, match="GDDR6_GOVERNOR_UNSETTLED"):
        monitor(helper)
    assert not [argv for argv in helper.calls if argv[0] == "modprobe"]


def test_it_is_unloaded_even_when_reading_fails(helper, monkeypatch):
    helper.log = helper.DRIVER_PATCHED

    def broken(*_a, **_k):
        raise KeyboardInterrupt

    monkeypatch.setattr(helper, "_sample_until", broken)
    with pytest.raises(KeyboardInterrupt):
        monitor(helper)
    assert helper.calls[-1] == ["modprobe", "-r", "bc250_memory"]


def test_a_driver_that_publishes_nothing_does_not_stay_loaded(helper):
    helper.log, helper.will_publish = helper.DRIVER_PATCHED, False
    assert not helper._resume_kernel_driver()
    assert helper.calls[-1] == ["modprobe", "-r", "bc250_memory"]
