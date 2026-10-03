"""The GPU memory limit in Game Mode goes through the desktop's own helper.

One implementation (privileged/lib/system_setup_ttm.py) and one state: the
panel asks the root Quick Access helper, which asks bc250-system-setup-helper,
which is what the desktop runs too. Nothing here writes a kernel argument.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from tests.quick_access.test_quick_access_backend import _backend_module
from tests.quick_access.test_quick_access_helper import (
    helper_module,  # noqa: F401 - fixture
)

STATE = {
    "supported": True, "backend": "limine", "reason": "", "page_size": 4096,
    "presets_gib": [8, 10, 12], "manual_arguments": {"8": "ttm.pages_limit=2097152"},
    "physical_ram_bytes": 16_000_000_000, "next_boot_ram_bytes": None,
    "live_pages": 1_900_000, "boot_pages": None, "configured_pages": 2_097_152,
    "managed": True, "managed_pages": 2_097_152, "external": False, "external_pages": None,
    "gtt_total_bytes": 7_516_192_768, "gtt_override": None, "legacy_pages": None,
    "reboot_required": True,
}


def _completed(stdout="", stderr="", code=0):
    return subprocess.CompletedProcess([], code, stdout, stderr)


@pytest.fixture(autouse=True)
def runtime(helper_module, monkeypatch):  # noqa: F811 - fixture
    """Root, systemd and a BC-250 are the helper's own preconditions, tested elsewhere."""
    monkeypatch.setattr(helper_module, "require_runtime", lambda: "")
    monkeypatch.setattr(helper_module, "load_contract", lambda: None)


@pytest.fixture()
def helper(helper_module, monkeypatch):  # noqa: F811 - fixture
    calls = []
    monkeypatch.setattr(helper_module, "trusted_file", lambda path, executable=False: True)

    def run(command, timeout=45, extra_env=None, keep_running=False):
        calls.append((list(command), timeout))
        if command[1] == "ttm-apply":
            assert keep_running  # a late answer must never kill the change
        if command[1] == "ttm-status":
            return _completed(json.dumps(STATE) + "\n")
        if command[1:3] == ["ttm-apply", "--ttm"]:
            return _completed(json.dumps({**STATE, "configured_pages": 2_621_440}) + "\nThe GPU memory limit ...\nBC250_RESULT status=ok\n")
        raise AssertionError(command)

    monkeypatch.setattr(helper_module, "run", run)
    helper_module.calls = calls
    return helper_module


def test_the_state_comes_from_the_desktops_helper_and_only_its_documented_fields(helper, capsys):
    assert helper.main(["helper", "ttm-status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and payload["ttm"]["configured_pages"] == 2_097_152
    assert set(payload["ttm"]) == set(helper.TTM_FIELDS)
    command, _timeout = helper.calls[0]
    assert command == [str(helper.SYSTEM_SETUP_HELPER), "ttm-status"]


@pytest.mark.parametrize("value,argument", [("8", "8"), ("10", "10"), ("12", "12"), ("default", "-1")])
def test_each_choice_is_one_fixed_argument(helper, capsys, value, argument):
    assert helper.main(["helper", "ttm-apply", value]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] and payload["ttm"]["configured_pages"] == 2_621_440
    command, timeout = helper.calls[-1]
    assert command == [str(helper.SYSTEM_SETUP_HELPER), "ttm-apply", "--ttm", argument]
    assert timeout >= 180  # rpm-ostree writes a whole deployment


@pytest.mark.parametrize("value", ["16", "-1", "0", "8; reboot", "default "])
def test_anything_else_is_refused_before_any_helper_runs(helper, capsys, value):
    assert helper.main(["helper", "ttm-apply", value]) == 2
    assert helper.calls == []
    assert "QUICK_ACCESS_TTM" in capsys.readouterr().err


def test_the_desktop_helpers_own_reason_reaches_the_panel(helper_module, monkeypatch, capsys):  # noqa: F811
    monkeypatch.setattr(helper_module, "trusted_file", lambda path, executable=False: True)
    monkeypatch.setattr(helper_module, "run", lambda command, **_: _completed(
        stderr="ERROR: SteamOS rewrites its boot configuration on every update\nSetup was not confirmed.\n", code=1,
    ))
    assert helper_module.main(["helper", "ttm-apply", "8"]) == 51
    error = capsys.readouterr().err
    assert "QUICK_ACCESS_TTM: SteamOS rewrites its boot configuration" in error


def test_a_missing_or_unprotected_desktop_helper_is_named(helper_module, monkeypatch, capsys):  # noqa: F811
    monkeypatch.setattr(helper_module, "trusted_file", lambda path, executable=False: False)
    assert helper_module.main(["helper", "ttm-status"]) == 51
    assert "system setup helper is unavailable" in capsys.readouterr().err


def test_the_payload_drops_anything_it_does_not_know(helper_module):  # noqa: F811
    payload = helper_module.ttm_payload({
        **STATE, "presets_gib": [8, 16, "12"], "manual_arguments": {"8": "x", "99": "y"},
        "reason": "r" * 1000, "configured_pages": -5, "extra": "<script>",
    })
    assert payload["presets_gib"] == [8]
    assert payload["manual_arguments"] == {"8": "x"}
    assert len(payload["reason"]) == 400 and payload["configured_pages"] is None
    assert "extra" not in payload


def test_a_vram_size_written_from_the_desktop_shows_as_pending_here(helper_module, monkeypatch):  # noqa: F811
    bank = bytearray(28)
    bank[26:28] = (4096).to_bytes(2, "little")

    class Port:
        def close(self):
            pass

    monkeypatch.setattr(helper_module, "bc250_present", lambda: True)
    monkeypatch.setattr(helper_module, "VRAM_DEVICE", Path("/"))
    monkeypatch.setattr(helper_module, "_vram_read_bank", lambda port: bank)
    monkeypatch.setattr(helper_module, "gpu_vram_usage_mib", lambda: (100, 512))
    state = helper_module.vram_status(port_open=Port)
    assert state["uma_size_mb"] == 4096 and state["active_mb"] == 512 and state["reboot_pending"]
    monkeypatch.setattr(helper_module, "gpu_vram_usage_mib", lambda: (100, 4096))
    assert helper_module.vram_status(port_open=Port)["reboot_pending"] is False


# ------------------------------------------------------------- Decky backend


def test_the_backend_validates_then_runs_one_operation(monkeypatch):
    module = _backend_module(monkeypatch)
    plugin = module.Plugin()
    calls = []

    async def immediate(callback, *args, **kwargs):
        return callback(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", immediate)

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs.get("timeout")))
        if args == ("status",):
            return {"ok": True, "protocol": module.HELPER_PROTOCOL}
        return {"ok": True, "ttm": STATE}

    monkeypatch.setattr(plugin, "_run", fake_run)
    assert asyncio.run(plugin.apply_ttm_limit(10))["ok"] is True
    assert calls[-1][0] == ("ttm-apply", "10") and calls[-1][1] >= 240
    assert asyncio.run(plugin.apply_ttm_limit("default"))["ok"] is True
    for bad in (16, True, "8 GiB", None, 8.0):
        assert asyncio.run(plugin.apply_ttm_limit(bad))["ok"] is False
    calls.clear()
    assert asyncio.run(plugin.ttm_state())["ttm"] == STATE
    assert calls == [(("ttm-status",), 70)]
    assert plugin._recent_actions[-1]["module"] == "ttm"


def test_steamos_without_the_desktops_helper_still_gets_the_real_reason(helper_module, monkeypatch, capsys):  # noqa: F811
    monkeypatch.setattr(helper_module, "is_steamos", lambda: True)
    monkeypatch.setattr(helper_module, "trusted_file", lambda path, executable=False: False)
    assert helper_module.main(["helper", "ttm-status"]) == 0
    payload = json.loads(capsys.readouterr().out)["ttm"]
    assert payload["supported"] is False and "SteamOS" in payload["reason"]
