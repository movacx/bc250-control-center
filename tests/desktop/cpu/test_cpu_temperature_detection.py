from pathlib import Path

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


def test_cpu_temperature_falls_back_to_exact_nct_cpu_sensor(tmp_path):
    nct = _hwmon(
        tmp_path,
        1,
        "nct6686",
        [("CPU Socket", 0), ("CPU", 60000), ("System", 45000)],
    )
    repository = _repository_with_hwmons([nct])

    assert repository.temperatura_cpu() == 60.0


def test_cpu_temperature_prefers_k10temp_over_nct_fallback(tmp_path):
    nct = _hwmon(tmp_path, 1, "nct6686", [("CPU", 60000)])
    k10temp = _hwmon(tmp_path, 2, "k10temp", [("Tctl", 54500)])
    repository = _repository_with_hwmons([nct, k10temp])

    assert repository.temperatura_cpu() == 54.5


def test_cpu_temperature_refreshes_sensor_inventory_before_reading(tmp_path):
    nct = _hwmon(tmp_path, 1, "nct6686", [("CPU", 61250)])
    repository = SistemaRepository.__new__(SistemaRepository)
    repository.hwmons = []
    refreshes = []

    def refresh():
        refreshes.append(True)
        repository.hwmons[:] = [nct]

    repository._buscar_sensores = refresh

    assert repository.temperatura_cpu() == 61.25
    assert refreshes == [True]

