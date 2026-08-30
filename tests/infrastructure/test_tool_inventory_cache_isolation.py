import time

from bc250cc.infrastructure.dependencias_repository import DependenciasRepository


def test_cached_tool_inventory_cannot_be_mutated_by_a_consumer():
    repo = DependenciasRepository()
    repo.estado_herramientas_cache = {
        "prepare_components": {
            "runtime": {"installed": True, "dependencies": []},
        },
        "optional_dependencies": {
            "git": {"available": True, "reason": "required"},
        },
        "incompatible_gpu_governors": ["legacy.service"],
    }
    repo.estado_herramientas_cache_time = time.monotonic()

    first = repo.estado_herramientas_bc250()
    first["prepare_components"]["runtime"]["installed"] = False
    first["optional_dependencies"]["git"]["available"] = False
    first["incompatible_gpu_governors"].append("injected.service")

    second = repo.estado_herramientas_bc250()
    assert second["prepare_components"]["runtime"]["installed"] is True
    assert second["optional_dependencies"]["git"]["available"] is True
    assert second["incompatible_gpu_governors"] == ["legacy.service"]


def test_each_cached_inventory_read_returns_an_independent_snapshot():
    repo = DependenciasRepository()
    repo.estado_herramientas_cache = {"nested": {"values": [1, 2]}}
    repo.estado_herramientas_cache_time = time.monotonic()

    left = repo.estado_herramientas_bc250()
    right = repo.estado_herramientas_bc250()

    assert left is not right
    assert left["nested"] is not right["nested"]
    assert left["nested"]["values"] is not right["nested"]["values"]
