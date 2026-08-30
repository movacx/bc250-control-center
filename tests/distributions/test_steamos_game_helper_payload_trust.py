"""Payload-boundary tests for the root-owned SteamOS Game Mode helper."""

from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "privileged" / "helpers" / "bc250-steamos-game-helper"


def _helper_module():
    return runpy.run_path(str(HELPER))


def test_installed_payload_contract_rejects_a_symlink_before_ownership_resolution(tmp_path):
    module = _helper_module()
    target = tmp_path / "trusted-looking-target"
    target.write_text("payload", encoding="utf-8")
    target.chmod(0o755)
    linked = tmp_path / "payload-link"
    linked.symlink_to(target)

    assert module["trusted_installed_payload"](linked, executable=True) is False


def test_gpu_voltage_action_rejects_a_symlinked_lab_before_execution(tmp_path, monkeypatch, capsys):
    module = _helper_module()
    target = tmp_path / "lab-target"
    target.write_text("#!/usr/bin/bash\nexit 0\n", encoding="utf-8")
    target.chmod(0o755)
    linked = tmp_path / "lab-link"
    linked.symlink_to(target)
    action = module["action_gpu_voltage"]
    monkeypatch.setitem(action.__globals__, "GPU_LAB_SCRIPT", linked)

    assert action(("apply", "3")) == 31
    assert "not a root-owned" in capsys.readouterr().err
