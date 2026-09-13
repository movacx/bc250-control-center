import json
import time
from pathlib import Path

from bc250cc.infrastructure.vrm_telemetry_reader import leer_telemetria_vrm

VALID_SNAPSHOT = {
    "hardware": {
        "cpu": {"valid": True, "vin": 12.22, "vout": 0.78, "iout": 2.8, "pout": 2.2, "temp": 45.0},
        "gpu": {"valid": True, "vin": 12.22, "vout": 0.646, "iout": 12.0, "pout": 7.8, "temp": 48.0},
        "total_power": 10.0,
        "total_power_valid": True,
    },
}


def _write_snapshot(path: Path, payload: dict, *, age_seconds: float = 0.0) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
    if age_seconds:
        stale_time = time.time() - age_seconds
        import os

        os.utime(path, (stale_time, stale_time))


def test_reads_cpu_and_gpu_vrm_temperature_from_fresh_snapshot(tmp_path):
    snapshot = tmp_path / "apu_telemetry.json"
    _write_snapshot(snapshot, VALID_SNAPSHOT)

    result = leer_telemetria_vrm(snapshot)

    assert result["vrm_cpu_temperature_c"] == 45.0
    assert result["vrm_gpu_temperature_c"] == 48.0


def test_missing_file_reports_unavailable(tmp_path):
    result = leer_telemetria_vrm(tmp_path / "missing.json")

    assert result["vrm_cpu_temperature_c"] is None
    assert result["vrm_gpu_temperature_c"] is None


def test_stale_snapshot_is_treated_as_unavailable(tmp_path):
    snapshot = tmp_path / "apu_telemetry.json"
    _write_snapshot(snapshot, VALID_SNAPSHOT, age_seconds=30.0)

    result = leer_telemetria_vrm(snapshot, max_age=5.0)

    assert result["vrm_cpu_temperature_c"] is None
    assert result["vrm_gpu_temperature_c"] is None


def test_malformed_json_is_treated_as_unavailable_not_a_crash(tmp_path):
    snapshot = tmp_path / "apu_telemetry.json"
    snapshot.write_text("{not valid json", encoding="utf-8")

    result = leer_telemetria_vrm(snapshot)

    assert result["vrm_cpu_temperature_c"] is None
    assert result["vrm_gpu_temperature_c"] is None


def test_invalid_rail_reading_is_not_reported_as_a_real_temperature(tmp_path):
    snapshot = tmp_path / "apu_telemetry.json"
    payload = json.loads(json.dumps(VALID_SNAPSHOT))
    payload["hardware"]["cpu"]["valid"] = False
    _write_snapshot(snapshot, payload)

    result = leer_telemetria_vrm(snapshot)

    assert result["vrm_cpu_temperature_c"] is None
    assert result["vrm_gpu_temperature_c"] == 48.0
