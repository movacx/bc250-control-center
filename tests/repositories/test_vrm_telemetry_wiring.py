from pathlib import Path

from bc250cc.infrastructure import sistema_repository as sistema_repository_module
from bc250cc.infrastructure.sistema_repository import SistemaRepository


def _hwmon(root: Path, index: int, name: str, sensors: list[tuple[str, int]]) -> tuple[str, Path]:
    directory = root / f"hwmon{index}"
    directory.mkdir()
    (directory / "name").write_text(name, encoding="utf-8")
    for sensor_index, (label, millidegrees) in enumerate(sensors, start=1):
        (directory / f"temp{sensor_index}_label").write_text(label, encoding="utf-8")
        (directory / f"temp{sensor_index}_input").write_text(str(millidegrees), encoding="utf-8")
    return name, directory


def _repository_with_hwmons(hwmons):
    repository = SistemaRepository.__new__(SistemaRepository)
    repository.hwmons = list(hwmons)
    repository._buscar_sensores = lambda: None
    return repository


def test_temperaturas_auxiliares_prefers_external_vrm_telemetry_over_nct_scan(tmp_path, monkeypatch):
    nct = _hwmon(tmp_path, 1, "nct6686", [("VRM", 39000)])
    repository = _repository_with_hwmons([nct])
    monkeypatch.setattr(
        sistema_repository_module,
        "leer_telemetria_vrm",
        lambda: {"vrm_cpu_temperature_c": 45.0, "vrm_gpu_temperature_c": 48.0},
    )

    result = repository.temperaturas_auxiliares(max_age=0.0)

    assert result["vrm_temperature_c"] == 48.0


def test_temperaturas_auxiliares_falls_back_to_nct_scan_when_daemon_not_detected(tmp_path, monkeypatch):
    nct = _hwmon(tmp_path, 1, "nct6686", [("VRM", 39000)])
    repository = _repository_with_hwmons([nct])
    monkeypatch.setattr(
        sistema_repository_module,
        "leer_telemetria_vrm",
        lambda: {"vrm_cpu_temperature_c": None, "vrm_gpu_temperature_c": None},
    )

    result = repository.temperaturas_auxiliares(max_age=0.0)

    assert result["vrm_temperature_c"] == 39.0
