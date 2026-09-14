from bc250cc.infrastructure.sistema_repository import SistemaRepository
from bc250cc.infrastructure.system_service import SistemaService


def test_sistema_repository_exposes_gddr6_memory_temp_methods():
    assert hasattr(SistemaRepository, "estado_gddr6_memory_temp")
    assert hasattr(SistemaRepository, "comando_estado_smu_vram")
    assert hasattr(SistemaRepository, "comando_leer_temperatura_vram")
    assert hasattr(SistemaRepository, "comando_aplicar_parche_vram")
    assert hasattr(SistemaRepository, "comando_preparar_gddr6_memory_temp")
    assert hasattr(SistemaRepository, "leer_temperatura_vram")


def test_sistema_service_exposes_gddr6_memory_temp_facade():
    assert hasattr(SistemaService, "estado_gddr6_memory_temp")
    assert hasattr(SistemaService, "comando_estado_smu_vram")
    assert hasattr(SistemaService, "comando_leer_temperatura_vram")
    assert hasattr(SistemaService, "comando_aplicar_parche_vram")
    assert hasattr(SistemaService, "comando_preparar_gddr6_memory_temp")
    assert hasattr(SistemaService, "leer_temperatura_vram")
