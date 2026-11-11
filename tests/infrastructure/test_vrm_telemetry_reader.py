import json
import os
import time
from pathlib import Path

import pytest

from bc250cc.infrastructure.vrm_telemetry_reader import (
    leer_memoria_telemetria,
    leer_telemetria_vrm,
)

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


FULL_SNAPSHOT = {
    "hardware": {
        "cpu": {
            "valid": True, "vin": 12.22, "vout": 0.78, "iout": 2.8,
            "pout": 2.2, "temp": 45.0, "iout_warning": False,
            "iout_fault": False, "temp_warning": False, "temp_fault": False,
        },
        "gpu": {
            "valid": True, "vin": 12.20, "vout": 0.646, "iout": 12.0,
            "pout": 7.8, "temp": 48.0, "iout_warning": True,
            "iout_fault": False, "temp_warning": False, "temp_fault": True,
        },
        "total_power": 10.0,
        "total_power_valid": True,
    },
}


def test_the_whole_rail_is_read_not_only_its_temperature(tmp_path):
    """The PMIC reports volts, amps and watts per rail; we used to drop them.

    A VRM temperature on its own cannot tell the difference between a hot rail
    and a rail pulling too much current, which is the failure this hardware
    actually has.
    """
    snapshot = tmp_path / "apu_telemetry.json"
    _write_snapshot(snapshot, FULL_SNAPSHOT)

    result = leer_telemetria_vrm(snapshot)

    assert result["vrm_available"] is True
    assert result["vrm_input_voltage_v"] == 12.22
    assert result["vrm_total_power_w"] == 10.0
    assert result["vrm_cpu_voltage_v"] == 0.78
    assert result["vrm_cpu_current_a"] == 2.8
    assert result["vrm_cpu_power_w"] == 2.2
    assert result["vrm_gpu_voltage_v"] == 0.646
    assert result["vrm_gpu_current_a"] == 12.0
    assert result["vrm_gpu_power_w"] == 7.8


def test_the_status_bits_the_pmic_raises_are_carried_through(tmp_path):
    snapshot = tmp_path / "apu_telemetry.json"
    _write_snapshot(snapshot, FULL_SNAPSHOT)

    result = leer_telemetria_vrm(snapshot)

    assert result["vrm_alerts"] == ("gpu_iout_warning", "gpu_temp_fault")


def test_a_rail_that_did_not_answer_reports_nothing_rather_than_minus_one(tmp_path):
    """The daemon writes -1 for "no answer"; -1 °C is not a reading."""
    snapshot = tmp_path / "apu_telemetry.json"
    _write_snapshot(snapshot, {
        "hardware": {
            "cpu": {"valid": True, "vin": -1, "vout": -1, "iout": -1,
                    "pout": -1, "temp": -1},
            "gpu": {"valid": False, "temp": 48.0},
            "total_power": -1, "total_power_valid": False,
        },
    })

    result = leer_telemetria_vrm(snapshot)

    assert result["vrm_cpu_temperature_c"] is None
    assert result["vrm_input_voltage_v"] is None
    assert result["vrm_total_power_w"] is None
    # The GPU rail said it was invalid, so nothing of it is believed.
    assert result["vrm_gpu_temperature_c"] is None
    assert result["vrm_available"] is False


# ------------------------------------------------------ the GDDR6 collector


def _memory(**fields):
    base = {
        "valid": True,
        "status": "ok",
        "raw": [9766, 9509, 10794, 9766, 9766, 10537, 10537, 10023],
    }
    return {"memory": {**base, **fields}}


def test_an_active_collector_yields_its_eight_readings(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps(_memory()))
    state = leer_memoria_telemetria(path)
    assert state["state"] == "active"
    assert [chip["temperature_c"] for chip in state["chips"]] == [36, 34, 44, 36, 36, 42, 42, 38]
    assert state["hotspot_chip"] == 2


@pytest.mark.parametrize(
    "fields, expected",
    [
        ({"valid": False, "status": "starting", "raw": []}, "waiting"),
        ({"valid": False, "status": "invalid_reading"}, "waiting"),
        ({"valid": False, "status": "stale", "raw": []}, "stale"),
        ({"valid": False, "status": "stopped", "raw": []}, ""),
        ({"valid": False, "status": "unavailable", "raw": []}, ""),
        # One impossible code invalidates the sample, as it does upstream.
        ({"raw": [9766] * 7 + [0x51]}, "waiting"),
    ],
)
def test_the_collector_state_follows_what_it_published(tmp_path, fields, expected):
    path = tmp_path / "t.json"
    path.write_text(json.dumps(_memory(**fields)))
    state = leer_memoria_telemetria(path)
    assert state["state"] == expected
    if expected != "active":
        assert state["chips"] == []


def test_a_file_the_daemon_stopped_writing_is_not_a_running_collector(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps(_memory()))
    old = time.time() - 60
    os.utime(path, (old, old))
    assert leer_memoria_telemetria(path)["state"] == ""
    assert leer_memoria_telemetria(tmp_path / "missing.json")["state"] == ""


def _kernel_memory_device(root, temps_mc, name="bc250_memory"):
    device = root / "hwmon7"
    device.mkdir(parents=True)
    (device / "name").write_text(name + "\n")
    for index, value in enumerate(temps_mc):
        (device / f"temp{index + 3}_input").write_text(f"{value}\n")
    return device


def test_memory_comes_from_the_kernel_module_when_no_collector_runs(tmp_path):
    _kernel_memory_device(tmp_path / "hwmon", [36000, 34000, 44000, 36000, 36000, 42000, 42000, 38000])
    state = leer_memoria_telemetria(tmp_path / "missing.json", hwmon_root=tmp_path / "hwmon")
    assert state["state"] == "active"
    assert state["status"] == "kernel"
    assert state["hotspot_c"] == 44.0
    assert state["hotspot_chip"] == 2
    assert state["average_c"] == 38.5


def test_kernel_memory_with_an_implausible_chip_is_not_used(tmp_path):
    _kernel_memory_device(tmp_path / "hwmon", [36000] * 7 + [500000])
    assert leer_memoria_telemetria(tmp_path / "missing.json", hwmon_root=tmp_path / "hwmon")["state"] == ""


def test_other_hwmon_devices_are_not_taken_for_the_memory_module(tmp_path):
    _kernel_memory_device(tmp_path / "hwmon", [36000] * 8, name="amdgpu")
    assert leer_memoria_telemetria(tmp_path / "missing.json", hwmon_root=tmp_path / "hwmon")["state"] == ""
