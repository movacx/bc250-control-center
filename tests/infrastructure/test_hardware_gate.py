"""The BC-250 hardware gate (R-ffde613d and 11 more reports from one Intel PC)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bc250cc.application.compute_units.operations import ComputeUnitsPreparationNeeded
from bc250cc.infrastructure import hardware_identity, system_service
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
    malformed = tmp_path / "malformed"
    _device(malformed, "0000:00:02.0", "", "0x9bc8")
    assert _identity(malformed) == "unknown"


def test_gate_blocks_only_a_confirmed_absence(monkeypatch):
    monkeypatch.setattr(hardware_identity, "_platform_text_identity", lambda: "absent")
    monkeypatch.setattr(hardware_identity, "_bc250_drm_present", lambda: False)
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


def test_positive_board_identity_and_unreadable_dmi_override_negative_pci(tmp_path, monkeypatch):
    monkeypatch.setattr(hardware_identity, "_DMI_ROOT", tmp_path)
    monkeypatch.setattr(hardware_identity, "_CPU_INFO", tmp_path / "cpuinfo")
    monkeypatch.setattr(hardware_identity, "_bc250_drm_present", lambda: False)
    monkeypatch.setattr(hardware_identity, "bc250_identity", lambda: "absent")
    (tmp_path / "board_name").write_text("BC-250")
    hardware_identity.require_bc250_hardware()

    (tmp_path / "board_name").write_text("Other board")
    (tmp_path / "product_name").mkdir()
    hardware_identity.require_bc250_hardware()


@pytest.mark.parametrize(("name", "args"), [
    ("instalar_governor", ()),
    ("aplicar_pwm_fan", (1, 120)),
    ("ejecutar_cpu_oc_temporal", (3200, 20)),
    ("comando_aplicar_parche_vram", ()),
    ("aplicar_tabla_cu", ([1, 1, 1, 1],)),
])
def test_shared_service_stops_hardware_actions_before_dispatch(name, args, monkeypatch):
    repo = Mock()
    monkeypatch.setattr(hardware_identity, "_platform_text_identity", lambda: "absent")
    monkeypatch.setattr(hardware_identity, "_bc250_drm_present", lambda: False)
    monkeypatch.setattr(hardware_identity, "bc250_identity", lambda: "absent")

    with pytest.raises(ActionNeeded, match="no BC-250"):
        getattr(system_service.SistemaService(repo), name)(*args)

    assert not repo.mock_calls


@pytest.mark.parametrize(("packages", "restart"), [([], False), (["git", "umr"], True)])
def test_cu_service_offers_the_next_step_before_authorization(monkeypatch, packages, restart):
    monkeypatch.setattr(system_service, "require_bc250_hardware", lambda: None)
    read = Mock()
    repo = SimpleNamespace(
        obtener_estado_cu=read,
        estado_herramientas_bc250=lambda: {"bazzite_reboot_pending": {"packages": packages}},
    )
    with pytest.raises(ComputeUnitsPreparationNeeded) as captured:
        system_service.SistemaService(repo).obtener_estado_cu()
    assert captured.value.restart is restart
    read.assert_not_called()


def test_cu_service_dispatches_when_umr_is_available(monkeypatch):
    monkeypatch.setattr(system_service, "require_bc250_hardware", lambda: None)
    repo = SimpleNamespace(
        aplicar_tabla_cu=Mock(return_value={"available": True}),
        estado_herramientas_bc250=lambda: {"umr": "/usr/bin/umr"},
    )
    masks = [1, 2, 3, 4]
    assert system_service.SistemaService(repo).aplicar_tabla_cu(masks) == {"available": True}
    repo.aplicar_tabla_cu.assert_called_once_with(masks)


def test_undo_actions_stay_open_on_another_machine(monkeypatch):
    """Whoever installed something on the wrong machine must be able to remove it."""
    from unittest.mock import MagicMock

    from bc250cc.infrastructure import system_service

    def refuse():
        raise AssertionError("an undo action was gated")

    monkeypatch.setattr(system_service, "require_bc250_hardware", refuse)
    service = system_service.SistemaService.__new__(system_service.SistemaService)
    service.repo = MagicMock()
    service.desinstalar_governor("cyan")
    service.controlar_governor("stop")
    service.comando_cpu_oc_desactivar_persistente_embebido()
    service.comando_quitar_persistencia_nucleos_cpu()
    service.desactivar_nct6687_control_pwm()
    service.restaurar_pwm_automatico("pwm1")
    service.desactivar_control_fan_sistema()
