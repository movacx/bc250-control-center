import json

import pytest

from bc250cc.infrastructure.cu_operations import (
    plan_cu_mask_operations,
    validate_cu_masks,
)
from bc250cc.infrastructure.cu_repository import CURepository


def test_mask_plan_disables_before_enabling_and_saves_last():
    operations = plan_cu_mask_operations([0x07, 0x0F, 0x1F, 0x00], save_boot=True)

    assert operations[0][:2] == ("--yes", "disable-wgp")
    assert operations[1][:2] == ("--yes", "enable-wgp")
    assert operations[2] == ("--yes", "write-service-table")
    assert "0.0.3" in operations[0]
    assert "0.0.2" in operations[1]


@pytest.mark.parametrize(
    "masks",
    (None, [0x07] * 3, [0x07, 0x07, 0x07, 0x20], [0x07, 0x07, 0x07, -1]),
)
def test_mask_validation_fails_closed(masks):
    with pytest.raises(ValueError):
        validate_cu_masks(masks)


def test_active_repository_executor_uses_the_pure_plan():
    calls = []
    repository = CURepository()
    repository._ejecutar_cu_accion_pkexec = lambda operation: calls.append(tuple(operation)) or "verified status"
    repository._estado_cu_autorizado = lambda text: {"available": text == "verified status", "active_cus": 24}

    state = repository._ejecutar_tabla_cu([0x07] * 4, save_boot=True)

    assert len(calls) == 1
    assert calls[0][0] == "batch"
    operations = json.loads(calls[0][1])
    assert operations == [list(item) for item in plan_cu_mask_operations([0x07] * 4, save_boot=True)]
    assert state["active_cus"] == 24


def test_steamos_table_executor_uses_one_polkit_batch_and_returned_status():
    repository = CURepository()
    calls = []
    cached = []
    repository._usar_steamos_cu_helper = lambda: True
    repository._ejecutar_steamos_game_helper = (
        lambda *args, **kwargs: calls.append((args, kwargs)) or (
            "+------------------------------------------------------------------------------+\n"
            "| BC-250 CU Dashboard / Live Dispatch                                          |\n"
            "+------------------------------------------------------------------------------+\n"
            "  UMR        : /usr/bin/umr\n"
            "  Source     : SPI dispatch masks + amdgpu boot CU map\n"
            "  | SE0.SH0 |  D+  |  D+  |  D+  |  --  |  --  | 0x07 | 0xfff80000 |   6/10 |\n"
            "  | SE0.SH1 |  D+  |  D+  |  D+  |  --  |  --  | 0x07 | 0xfff80000 |   6/10 |\n"
            "  | SE1.SH0 |  D+  |  D+  |  D+  |  --  |  --  | 0x07 | 0xfff80000 |   6/10 |\n"
            "  | SE1.SH1 |  D+  |  D+  |  D+  |  --  |  --  | 0x07 | 0xfff80000 |   6/10 |\n"
            "  CUs active & routed  : 24/40\n"
        )
    )
    repository._guardar_dashboard_cu_cache = cached.append
    repository.estado_herramientas_bc250 = lambda: {
        "cu_privileged_backend_ready": True,
    }

    result = repository._ejecutar_tabla_cu([0x07] * 4, save_boot=True)

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[:2] == ("cu", "batch")
    operations = json.loads(args[2])
    assert [operation[1] for operation in operations] == [
        "disable-wgp", "enable-wgp", "write-service-table"
    ]
    assert kwargs == {"timeout": 240}
    assert result["available"] is True
    assert result["active_cus"] == 24
    assert len(cached) == 1


def test_steamos_batch_rejects_missing_verified_status_without_second_prompt():
    repository = CURepository()
    calls = []
    repository._usar_steamos_cu_helper = lambda: True
    repository._ejecutar_steamos_game_helper = lambda *args, **kwargs: calls.append(args) or "OK"

    with pytest.raises(RuntimeError, match="without a validated topology"):
        repository._ejecutar_tabla_cu([0x07] * 4)

    assert len(calls) == 1


def test_steamos_factory_repair_uses_one_ordered_authorization():
    repository = CURepository()
    calls = []
    repository._usar_steamos_cu_helper = lambda: True
    repository._ejecutar_steamos_game_helper = (
        lambda *args, **kwargs: calls.append(args) or (
            "+------------------------------------------------------------------------------+\n"
            "| BC-250 CU Dashboard / Live Dispatch                                          |\n"
            "+------------------------------------------------------------------------------+\n"
            "  UMR        : /usr/bin/umr\n"
            "  Source     : SPI dispatch masks + amdgpu boot CU map\n"
            "  | SE0.SH0 |  D+  |  D+  |  D+  |  --  |  --  | 0x07 | 0xfff80000 |   6/10 |\n"
            "  | SE0.SH1 |  D+  |  D+  |  D+  |  --  |  --  | 0x07 | 0xfff80000 |   6/10 |\n"
            "  | SE1.SH0 |  D+  |  D+  |  D+  |  --  |  --  | 0x07 | 0xfff80000 |   6/10 |\n"
            "  | SE1.SH1 |  D+  |  D+  |  D+  |  --  |  --  | 0x07 | 0xfff80000 |   6/10 |\n"
            "  CUs active & routed  : 24/40\n"
        )
    )
    repository._guardar_dashboard_cu_cache = lambda _text: None
    repository.estado_herramientas_bc250 = lambda: {"cu_privileged_backend_ready": True}

    result = repository.ejecutar_accion_cu_grafica("factory_repair")

    assert len(calls) == 1
    operations = json.loads(calls[0][2])
    assert operations == [
        ["--yes", "uninstall-service"],
        ["--yes", "stock-dispatch"],
    ]
    assert result["active_cus"] == 24


@pytest.mark.parametrize(
    ("action", "expected_service", "expected_boot"),
    (
        ("save_boot", "Enabled", "saved"),
        ("install_service", "Enabled", "saved"),
        ("remove_service", "Not installed", "not_saved"),
    ),
)
def test_service_metadata_actions_never_open_second_status_prompt(
    action, expected_service, expected_boot
):
    repository = CURepository()
    calls = []
    repository._ejecutar_cu_accion_pkexec = lambda args: calls.append(tuple(args)) or "OK"
    repository.obtener_estado_cu_cache = lambda: {
        "available": True,
        "masks": [0x07] * 4,
        "active_cus": 24,
        "service": "Enabled",
        "boot_sync_key": "saved",
    }
    repository.estado_herramientas_bc250 = lambda: {"cu_privileged_backend_ready": True}
    persistence_updates = []
    repository._actualizar_persistencia_dashboard_cu_cache = persistence_updates.append

    result = repository.ejecutar_accion_cu_grafica(action)

    assert len(calls) == 1
    assert result["service"] == expected_service
    assert result["boot_sync_key"] == expected_boot
    assert persistence_updates == [action]


def test_topology_changing_action_without_verified_status_fails_without_retry():
    repository = CURepository()
    calls = []
    repository._ejecutar_cu_accion_pkexec = lambda args: calls.append(tuple(args)) or "OK"

    with pytest.raises(RuntimeError, match="without a validated topology"):
        repository.ejecutar_accion_cu_grafica("full")

    assert calls == [("--yes", "enable", "all")]


def test_dormant_undefined_command_builder_was_removed():
    assert not hasattr(CURepository, "_comandos_tabla_cu")
