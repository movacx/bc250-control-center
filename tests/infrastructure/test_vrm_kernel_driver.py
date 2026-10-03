"""On the BC-250 kernel the rails come from its own driver, not from the daemon.

linux-cachyos-bc250 carries ``bc250_vrm``, a driver for the same regulator that
registers an hwmon device when a wired VRM answers. Its client sits at the
PMIC's address on every BC-250, so BC250-Telemetry's daemon is refused the bus
there. When the daemon has nothing valid, the dashboard reads the same rails
from hwmon, in the driver's units: mV, mA, m°C and µW.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from bc250cc.infrastructure import vrm_telemetry_reader as reader
from bc250cc.infrastructure.apu_telemetry_service import (
    MARKER,
    apu_telemetry_state,
    apu_telemetry_supported,
)
from bc250cc.infrastructure.vrm_telemetry_reader import (
    kernel_vrm_driver_present,
    leer_telemetria_vrm,
    sondear_telemetria_vrm,
)


@pytest.fixture(autouse=True)
def _no_cache():
    reader._kernel_cache.clear()
    yield
    reader._kernel_cache.clear()


def _driver(root: Path, *, name="bc250_vrm", attributes=None, index=3) -> Path:
    device = root / f"hwmon{index}"
    device.mkdir(parents=True)
    (device / "name").write_text(name + "\n")
    values = {
        "in0_input": 12220, "in1_input": 780, "in2_input": 650,
        "curr1_input": 2800, "curr2_input": 12000,
        "temp1_input": 45000, "temp2_input": 48000,
        "power1_input": 2_184_000, "power2_input": 7_800_000,
    }
    values.update(attributes or {})
    for key, value in values.items():
        if value is not None:
            (device / key).write_text(f"{value}\n")
    return device


def _daemon_snapshot(path: Path, *, valid: bool):
    rail = {"valid": valid, "vin": 12.0, "vout": 0.9, "iout": 3.0, "pout": 2.7, "temp": 50.0}
    path.write_text(json.dumps({"hardware": {
        "cpu": dict(rail), "gpu": dict(rail), "total_power": 5.4, "total_power_valid": valid,
    }}))


def test_the_kernels_rails_are_read_in_their_own_units(tmp_path):
    _driver(tmp_path / "hwmon")
    result = leer_telemetria_vrm(tmp_path / "absent.json", hwmon_root=tmp_path / "hwmon")

    assert result["vrm_available"] is True
    assert result["vrm_input_voltage_v"] == pytest.approx(12.22)
    assert result["vrm_cpu_voltage_v"] == pytest.approx(0.78)
    assert result["vrm_cpu_current_a"] == pytest.approx(2.8)
    assert result["vrm_cpu_temperature_c"] == pytest.approx(45.0)
    assert result["vrm_cpu_power_w"] == pytest.approx(2.184)
    assert result["vrm_gpu_voltage_v"] == pytest.approx(0.65)
    assert result["vrm_gpu_current_a"] == pytest.approx(12.0)
    assert result["vrm_gpu_temperature_c"] == pytest.approx(48.0)
    assert result["vrm_total_power_w"] == pytest.approx(9.984)


def test_the_probe_says_the_kernel_answered(tmp_path):
    _driver(tmp_path / "hwmon")
    probe = sondear_telemetria_vrm(tmp_path / "absent.json", hwmon_root=tmp_path / "hwmon")
    assert probe["daemon"] == "kernel"
    assert probe["rails"]["cpu"]["valid"] and probe["rails"]["gpu"]["valid"]
    assert probe["rails"]["cpu"]["vout"] == pytest.approx(0.78)
    assert probe["total_power_valid"] is True


def test_a_daemon_that_has_valid_rails_is_still_the_source(tmp_path):
    _driver(tmp_path / "hwmon")
    snapshot = tmp_path / "apu.json"
    _daemon_snapshot(snapshot, valid=True)
    probe = sondear_telemetria_vrm(snapshot, hwmon_root=tmp_path / "hwmon")
    assert probe["daemon"] == "running"
    assert probe["rails"]["cpu"]["vout"] == pytest.approx(0.9)


def test_a_daemon_that_gets_no_answer_does_not_hide_the_kernels_reading(tmp_path):
    _driver(tmp_path / "hwmon")
    snapshot = tmp_path / "apu.json"
    _daemon_snapshot(snapshot, valid=False)  # running, but refused the bus
    probe = sondear_telemetria_vrm(snapshot, hwmon_root=tmp_path / "hwmon")
    assert probe["daemon"] == "kernel"
    assert leer_telemetria_vrm(snapshot, hwmon_root=tmp_path / "hwmon")["vrm_cpu_voltage_v"] == pytest.approx(0.78)


def test_without_a_driver_device_nothing_changes(tmp_path):
    (tmp_path / "hwmon").mkdir()
    _driver(tmp_path / "hwmon", name="k10temp")  # some other hwmon device
    probe = sondear_telemetria_vrm(tmp_path / "absent.json", hwmon_root=tmp_path / "hwmon")
    assert probe["daemon"] == "missing" and probe["rails"] == {}
    assert leer_telemetria_vrm(tmp_path / "absent.json", hwmon_root=tmp_path / "hwmon")["vrm_available"] is False


def test_a_glitched_rail_is_marked_invalid_and_the_other_still_reads(tmp_path):
    # The driver answers EIO for a glitch; reading the file then raises.
    device = _driver(tmp_path / "hwmon", attributes={"curr2_input": None})
    (device / "curr2_input").mkdir()  # reading a directory fails like an I/O error
    probe = sondear_telemetria_vrm(tmp_path / "absent.json", hwmon_root=tmp_path / "hwmon")
    assert probe["rails"]["cpu"]["valid"] is True
    assert probe["rails"]["gpu"]["valid"] is False
    assert probe["total_power_valid"] is False
    result = leer_telemetria_vrm(tmp_path / "absent.json", hwmon_root=tmp_path / "hwmon")
    assert result["vrm_cpu_voltage_v"] == pytest.approx(0.78)
    assert result["vrm_gpu_voltage_v"] is None


def test_repeated_asks_in_one_refresh_read_the_hardware_once(tmp_path, monkeypatch):
    device = _driver(tmp_path / "hwmon")
    first = leer_telemetria_vrm(tmp_path / "absent.json", hwmon_root=tmp_path / "hwmon")
    (device / "temp1_input").write_text("90000\n")
    again = leer_telemetria_vrm(tmp_path / "absent.json", hwmon_root=tmp_path / "hwmon")
    assert again["vrm_cpu_temperature_c"] == first["vrm_cpu_temperature_c"] == pytest.approx(45.0)

    real = time.monotonic
    monkeypatch.setattr(reader.time, "monotonic", lambda: real() + 5)
    later = leer_telemetria_vrm(tmp_path / "absent.json", hwmon_root=tmp_path / "hwmon")
    assert later["vrm_cpu_temperature_c"] == pytest.approx(90.0)


# --------------------------------------------------- the daemon is not offered

def test_the_kernel_driver_is_recognised_by_its_module(tmp_path):
    assert kernel_vrm_driver_present(tmp_path / "bc250_vrm") is False
    (tmp_path / "bc250_vrm").mkdir()
    assert kernel_vrm_driver_present(tmp_path / "bc250_vrm") is True


def test_the_daemon_is_not_offered_where_the_kernel_reads_the_vrm_itself(tmp_path):
    module = tmp_path / "bc250_vrm"
    assert apu_telemetry_supported(family="cachyos", kernel_module=module) == (True, "")
    module.mkdir()
    supported, reason = apu_telemetry_supported(family="cachyos", kernel_module=module)
    assert supported is False
    assert "bc250_vrm" in reason and "sensors" in reason


def test_a_daemon_that_is_already_ours_can_still_be_removed_on_that_kernel(tmp_path):
    module = tmp_path / "bc250_vrm"
    module.mkdir()
    unit = tmp_path / "unit"
    unit.write_text(f"{MARKER}\n[Unit]\n")
    binary = tmp_path / "bin"
    binary.write_text("x")
    state = apu_telemetry_state(
        family="cachyos", unit=unit, binary=binary, snapshot=tmp_path / "run.json", kernel_module=module,
    )
    assert state["supported"] is False and state["managed"] is True


def _hold(path: Path, mode: int):
    import fcntl
    import os

    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, mode)
    return fd


def test_nothing_is_read_from_the_vrm_driver_while_a_cpu_tuning_run_has_the_smu(tmp_path):
    import fcntl
    import os

    _driver(tmp_path / "hwmon")
    lock = tmp_path / "run.lock"
    fd = _hold(lock, fcntl.LOCK_EX)  # the tuning helper's whole-run lock
    try:
        assert reader._kernel_vrm_hardware(tmp_path / "hwmon", run_lock=lock) is None
        probe = sondear_telemetria_vrm(tmp_path / "absent.json", hwmon_root=tmp_path / "hwmon", run_lock=lock)
        assert probe["daemon"] == "missing"
        assert leer_telemetria_vrm(
            tmp_path / "absent.json", hwmon_root=tmp_path / "hwmon", run_lock=lock
        )["vrm_available"] is False
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    # Not remembered as "no reading": the next ask, after the run, reads again.
    assert reader._kernel_vrm_hardware(tmp_path / "hwmon", run_lock=lock) is not None


def test_a_sample_in_flight_does_not_count_as_a_run(tmp_path):
    import fcntl
    import os

    _driver(tmp_path / "hwmon")
    lock = tmp_path / "run.lock"
    fd = _hold(lock, fcntl.LOCK_SH)  # the GDDR6 helpers take it shared
    try:
        assert reader._kernel_vrm_hardware(tmp_path / "hwmon", run_lock=lock) is not None
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
