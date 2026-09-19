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


def test_the_two_rails_stay_apart_and_say_where_they_came_from(tmp_path, monkeypatch):
    """One "VRM" number could not say which rail was heating up.

    The board has a CPU VRM and a GPU VRM. Reporting only the hotter of the
    two threw away the half that matters when deciding what to cool.
    """
    nct = _hwmon(tmp_path, 1, "nct6686", [("VRM MOS", 51000)])
    repository = _repository_with_hwmons([nct])
    monkeypatch.setattr(
        sistema_repository_module,
        "leer_telemetria_vrm",
        lambda: {
            "vrm_cpu_temperature_c": 45.0,
            "vrm_gpu_temperature_c": 48.0,
            "vrm_input_voltage_v": 12.22,
            "vrm_total_power_w": 10.0,
            "vrm_cpu_power_w": 2.2,
            "vrm_gpu_power_w": 7.8,
            "vrm_alerts": ("gpu_temp_warning",),
        },
    )

    result = repository.temperaturas_auxiliares(max_age=0.0)

    assert result["vrm_cpu_temperature_c"] == 45.0
    assert result["vrm_gpu_temperature_c"] == 48.0
    assert result["vrm_source"] == "pmbus"
    assert result["vrm_total_power_w"] == 10.0
    assert result["vrm_alerts"] == ("gpu_temp_warning",)


def test_the_nuvoton_fallback_is_labelled_as_the_channel_it_really_is(tmp_path, monkeypatch):
    """Without the I2C mod there is no rail measurement, only VRM MOS.

    On a BC-250 that channel tracks the board sensor, so presenting it as a
    VRM rail reading is the bug this source marker exists to prevent.
    """
    nct = _hwmon(tmp_path, 1, "nct6686", [("VRM MOS", 51000)])
    repository = _repository_with_hwmons([nct])
    monkeypatch.setattr(
        sistema_repository_module,
        "leer_telemetria_vrm",
        lambda: {"vrm_cpu_temperature_c": None, "vrm_gpu_temperature_c": None},
    )

    result = repository.temperaturas_auxiliares(max_age=0.0)

    assert result["vrm_temperature_c"] == 51.0
    assert result["vrm_source"] == "nct"
    assert result["vrm_cpu_temperature_c"] is None
    assert result["vrm_gpu_temperature_c"] is None
