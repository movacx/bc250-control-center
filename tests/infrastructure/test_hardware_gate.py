"""The BC-250 hardware gate (R-ffde613d and 11 more reports from one Intel PC)."""

from pathlib import Path

import pytest

from bc250cc.infrastructure import hardware_identity
from bc250cc.shared.errors import ActionNeeded


def _device(root: Path, name: str, vendor: str, device: str) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "vendor").write_text(vendor + "\n")
    (folder / "device").write_text(device + "\n")


def _identity(root):
    import importlib

    module = importlib.reload(hardware_identity)
    return module.bc250_identity(root)


def test_identity_present_absent_and_unknown(tmp_path):
    bc250 = tmp_path / "bc250"
    _device(bc250, "0000:01:00.0", "0x1002", "0x13fe")
    _device(bc250, "0000:00:00.0", "0x1022", "0x1450")
    assert _identity(bc250) == "present"
    intel = tmp_path / "intel"
    _device(intel, "0000:00:02.0", "0x8086", "0x9bc8")
    _device(intel, "0000:01:00.0", "0x10de", "0x1f08")
    assert _identity(intel) == "absent"
    assert _identity(tmp_path / "missing") == "unknown"
    partial = tmp_path / "partial"
    _device(partial, "0000:00:02.0", "0x8086", "0x9bc8")
    (partial / "0000:01:00.0").mkdir()  # unreadable device: not a confirmed absence
    assert _identity(partial) == "unknown"


def test_gate_blocks_only_a_confirmed_absence(monkeypatch):
    monkeypatch.setattr(hardware_identity, "bc250_identity", lambda: "absent")
    with pytest.raises(ActionNeeded, match="1002:13fe"):
        hardware_identity.require_bc250_hardware()
    for state in ("present", "unknown"):
        monkeypatch.setattr(hardware_identity, "bc250_identity", lambda state=state: state)
        hardware_identity.require_bc250_hardware()


def test_gate_message_is_diagnosed_as_hardware():
    from bc250cc.shared.error_catalog import HARDWARE_GATE_MESSAGE
    from frontends.desktop.core.error_diagnostics import diagnose_error

    assert getattr(diagnose_error(HARDWARE_GATE_MESSAGE), "code", "") == "BC250-HW-001"
