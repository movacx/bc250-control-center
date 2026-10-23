"""SteamOS can manage mitigations=off and nosmt from the application, not the CU unlock."""

from types import SimpleNamespace

import pytest

from bc250cc.infrastructure.dependencias_repository import DependenciasRepository


def _repository(family: str):
    repository = DependenciasRepository.__new__(DependenciasRepository)
    repository._os_repository = lambda: SimpleNamespace(family=family)
    repository.opened = []
    repository._abrir_terminal = lambda command, title: repository.opened.append((command, title)) or "ok"
    return repository


def test_steamos_opens_the_helper_for_mitigations(tmp_path):
    repository = _repository("steamos")
    repository.gestionar_opciones_kernel(["mitigations=off", "nosmt"])
    command, _title = repository.opened[0]
    assert "kernel-options-set --kernel-options mitigations=off,nosmt" in command


@pytest.mark.parametrize("option", ["amdgpu.bc250_cc_write_mode=3"])
def test_steamos_refuses_the_cu_unlock(option):
    repository = _repository("steamos")
    with pytest.raises(RuntimeError, match="Only mitigations=off and nosmt"):
        repository.gestionar_opciones_kernel(["mitigations=off", option])
    assert repository.opened == []


def test_bazzite_keeps_its_own_card():
    with pytest.raises(RuntimeError, match="managed differently"):
        _repository("bazzite").gestionar_opciones_kernel(["mitigations=off"])


def test_steamos_acpi_runs_with_the_root_unlocked_for_boot():
    """The archive goes beside the kernel in /boot, part of the read-only root."""
    repository = _repository("steamos")
    repository.gestionar_acpi("acpi-install")
    command, _title = repository.opened[0]
    assert "with-steamos-writable-root.sh" in command and "acpi-install" in command
    other = _repository("arch")
    other.gestionar_acpi("acpi-install")
    assert "with-steamos-writable-root.sh" not in other.opened[0][0]


@pytest.mark.parametrize("mode", ["on", "off"])
def test_smt_is_switched_through_the_protected_helper_in_the_terminal(mode):
    repository = _repository("steamos")
    repository.gestionar_smt_vivo(mode)
    command, title = repository.opened[0]
    assert f"smt-live --smt {mode}" in command and "SMT" in title


def test_anything_but_on_or_off_is_refused_for_smt():
    from bc250cc.infrastructure.system_setup import command

    repository = _repository("arch")
    with pytest.raises(ValueError):
        repository.gestionar_smt_vivo("forceoff; reboot")
    with pytest.raises(ValueError):
        command("smt-live", smt="")
    assert repository.opened == []
