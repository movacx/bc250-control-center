import csv
import json
import math
from pathlib import Path

import pytest

from bc250cc.infrastructure.persistence.configuracion_local import ConfiguracionLocal


@pytest.fixture
def configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return ConfiguracionLocal()


def test_metrics_reader_skips_corruption_and_filters(configuration):
    path = configuration.metricas_runtime_path()
    path.write_text(
        '{"ts":1,"datos":{"rpm":1000}}\ninvalid\n{"ts":2,"datos":{"rpm":1200}}\n',
        encoding="utf-8",
    )
    assert configuration.leer_metricas_runtime(desde=1.5) == [
        {"ts": 2.0, "datos": {"rpm": 1200}}
    ]


def test_jsonl_and_csv_exports_are_private_and_parseable(configuration, tmp_path):
    configuration.registrar_metrica_runtime({"rpm": 1100, "temp": 52})
    jsonl = configuration.exportar_metricas_runtime(tmp_path / "metrics.jsonl")
    csv_path = configuration.exportar_metricas_runtime(
        tmp_path / "metrics.csv", formato="csv"
    )
    assert json.loads(jsonl.read_text(encoding="utf-8"))["datos"]["rpm"] == 1100
    with csv_path.open(encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["rpm"] == "1100"
    assert jsonl.stat().st_mode & 0o777 == 0o600
    assert csv_path.stat().st_mode & 0o777 == 0o600


def test_invalid_export_format_fails_before_file_creation(configuration, tmp_path):
    destination = tmp_path / "metrics.bad"
    with pytest.raises(ValueError, match="jsonl or csv"):
        configuration.exportar_metricas_runtime(destination, formato="xml")
    assert not destination.exists()


def test_metrics_compaction_keeps_bounded_tail(configuration):
    for rpm in range(105):
        assert configuration.registrar_metrica_runtime({"rpm": rpm}, max_lineas=100)
    events = configuration.leer_metricas_runtime(limite=200)
    assert len(events) == 100
    assert [event["datos"]["rpm"] for event in events] == list(range(5, 105))


def test_metrics_reject_invalid_shape_and_oversized_record(configuration):
    assert configuration.registrar_metrica_runtime([1, 2, 3]) is False
    assert configuration.registrar_metrica_runtime({"blob": "x" * 70_000}) is False
    assert not configuration.metricas_runtime_path().exists()


def test_metrics_normalize_nonfinite_values_and_skip_nonfinite_timestamps(
    configuration,
):
    assert configuration.registrar_metrica_runtime(
        {"temp": math.nan, "power": math.inf}
    )
    path = configuration.metricas_runtime_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"ts":NaN,"datos":{"rpm":999}}\n')
    events = configuration.leer_metricas_runtime()
    assert len(events) == 1
    assert math.isfinite(events[0]["ts"])
    assert events[0]["datos"] == {"temp": None, "power": None}


def test_reader_ignores_oversized_corrupt_prefix(configuration, monkeypatch):
    monkeypatch.setattr(configuration, "_metric_scan_max_bytes", 128)
    path = configuration.metricas_runtime_path()
    path.write_bytes(b"x" * 256 + b'\n{"ts":2,"datos":{"rpm":1200}}\n')
    assert configuration.leer_metricas_runtime() == [
        {"ts": 2.0, "datos": {"rpm": 1200}}
    ]


def test_csv_export_is_deterministic_and_formula_safe(configuration, tmp_path):
    configuration.registrar_metrica_runtime(
        {"z": "=cmd", "nested": {"b": 2, "a": 1}, "negative": -3}
    )
    destination = configuration.exportar_metricas_runtime(
        tmp_path / "metrics.csv", formato="csv"
    )
    with destination.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        row = next(reader)
    assert reader.fieldnames == ["ts", "negative", "nested", "z"]
    assert row["z"] == "'=cmd"
    assert row["nested"] == '{"a":1,"b":2}'
    assert row["negative"] == "-3"


def test_repository_csv_export_captures_one_sample_when_history_is_empty(
    configuration, tmp_path, monkeypatch
):
    from bc250cc.infrastructure.sistema_repository import SistemaRepository

    repository = SistemaRepository.__new__(SistemaRepository)
    repository.configuracion = configuration
    monkeypatch.setattr(
        repository,
        "obtener_rendimiento",
        lambda: {"cpu": 12.5, "gpu_temp": 53.0, "fan_rpm": 1420},
    )

    destination = Path(repository.exportar_metricas_runtime(tmp_path / "fresh.csv", "csv"))
    with destination.open(encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["cpu"] == "12.5"
    assert row["gpu_temp"] == "53.0"
    assert row["fan_rpm"] == "1420"
    assert row["sample_source"] == "desktop_export"
