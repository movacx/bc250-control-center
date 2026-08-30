from pathlib import Path

from bc250cc.infrastructure.governor_conflicts import CYAN_GOVERNOR, OBERON_GOVERNOR
from bc250cc.infrastructure.gpu_repository import GPURepository
from bc250cc.infrastructure.gpu_state import (
    GpuDeviceEvidence,
    GpuGovernorEvidence,
    build_gpu_state_snapshot,
)
from bc250cc.infrastructure.sistema_repository import SistemaRepository


def _device(**updates):
    values = {
        "path": "/sys/class/drm/card1/device",
        "device": "0x13fe",
        "vendor": "0x1002",
        "sclk_text": "0: 1000Mhz *",
        "mclk_text": "0: 800Mhz *",
        "sclk_actual": 1000,
        "mclk_actual": 800,
        "voltage_actual": 900,
        "od_sclk_min": 500,
        "od_sclk_max": 2000,
        "busy": 12,
        "vram_total": 16_000,
        "vram_used": 4_000,
        "power_level": "manual",
        "power_state": "performance",
    }
    values.update(updates)
    return GpuDeviceEvidence(**values)


def _governor(selected=CYAN_GOVERNOR, **updates):
    values = {
        "selected": selected,
        "context": {"preference": "auto", "reason": "detected", "detected": {}},
        "runtime": {
            "service_active": "active",
            "service_sub": "running",
            "service_enabled": "enabled",
            "service_main_pid": "123",
            "current_min": 1000,
            "current_max": 1850,
            "allowed_min": 500,
            "allowed_max": 2400,
            "dbus_performance": True,
        },
        "safe_points": {
            "points": ({"frequency": 1000},),
            "points_with_voltage": ({"frequency": 1000, "voltage": 800},),
            "max_frequency": 1000,
            "max_voltage": 800,
            "missing_voltage": (),
            "voltage_order_errors": (),
            "duplicate_frequencies": (),
            "config_path": "/etc/governor.toml",
        },
        "frequency_range": {"valid": True},
        "high_frequency_points": {"available": True},
        "cyan_telemetry": {"runtime_frequency_fix_supported": True},
        "tools": {"os_family": "steamos"},
    }
    values.update(updates)
    return GpuGovernorEvidence(**values)


def test_cyan_snapshot_preserves_device_runtime_and_configuration_contract():
    snapshot = build_gpu_state_snapshot(_device(), _governor())
    assert snapshot["driver"] == "amdgpu"
    assert snapshot["governor_backend"] == CYAN_GOVERNOR
    assert snapshot["dbus_ok"] is True
    assert snapshot["range_control_ok"] is True
    assert snapshot["telemetry_warning"] == ""
    assert snapshot["safe_points_with_voltage"] == (
        {"frequency": 1000, "voltage": 800},
    )
    assert snapshot["tools"] == {"os_family": "steamos"}


def test_cyan_snapshot_reports_missing_frequency_fix_without_losing_state():
    governor = _governor(cyan_telemetry={"runtime_frequency_fix_supported": False})
    snapshot = build_gpu_state_snapshot(_device(), governor)
    assert "does not provide fix-freq" in snapshot["telemetry_warning"]
    assert snapshot["telemetry_metrics_supported"] is True
    assert snapshot["cyan_telemetry"] == {"runtime_frequency_fix_supported": False}


def test_oberon_snapshot_has_range_control_without_claiming_dbus_or_metrics():
    snapshot = build_gpu_state_snapshot(_device(), _governor(OBERON_GOVERNOR))
    assert snapshot["range_control_ok"] is True
    assert snapshot["dbus_ok"] is False
    assert snapshot["telemetry_metrics_supported"] is False
    assert snapshot["cyan_telemetry"] == {}
    assert "about 655%" in snapshot["telemetry_warning"]


def test_snapshot_handles_absent_device_and_partial_safe_point_evidence():
    governor = _governor(
        runtime={"current_min": 1000, "current_max": None},
        safe_points={"error": "unreadable"},
    )
    snapshot = build_gpu_state_snapshot(_device(path=""), governor)
    assert snapshot["driver"] == ""
    assert snapshot["range_control_ok"] is False
    assert snapshot["safe_points"] == ()
    assert snapshot["safe_points_error"] == "unreadable"
    assert snapshot["config_path"] == ""


def test_repository_device_probe_has_one_explicit_absent_device_path():
    repository = GPURepository.__new__(GPURepository)
    calls = []
    repository._gpu_busy_percent = lambda path: calls.append(path) or 0

    evidence = repository._gpu_device_evidence(None)

    assert evidence.path == ""
    assert evidence.device is None
    assert evidence.busy == 0
    assert calls == [None]


def test_repository_device_probe_collects_a_coherent_sysfs_sample(tmp_path):
    repository = GPURepository.__new__(GPURepository)
    reads = []
    integers = []
    repository._leer_texto = lambda path: reads.append(path.name) or {
        "pp_dpm_sclk": "0: 1000Mhz *",
        "pp_dpm_mclk": "0: 800Mhz *",
        "pp_od_clk_voltage": "OD_SCLK:\n0: 500Mhz\n1: 1850Mhz",
        "device": "0x13fe",
        "vendor": "0x1002",
        "power_dpm_force_performance_level": "manual",
        "power_dpm_state": "performance",
    }.get(path.name)
    repository._leer_entero = lambda path: integers.append(path.name) or 4096
    repository._parse_od = lambda _text: {
        "sclk": 1850, "vddc": 930,
        "range_sclk_min": 500, "range_sclk_max": 2000,
    }
    repository._parse_dpm_actual = lambda text: 800 if "800" in str(text) else 1000
    repository._gpu_busy_percent = lambda path: 25 if path == tmp_path else 0

    evidence = repository._gpu_device_evidence(tmp_path)

    assert (evidence.sclk_actual, evidence.mclk_actual) == (1000, 800)
    assert (evidence.device, evidence.vendor) == ("0x13fe", "0x1002")
    assert evidence.busy == 25
    assert set(integers) == {"mem_info_vram_total", "mem_info_vram_used"}
    assert set(reads) == {
        "pp_dpm_sclk", "pp_dpm_mclk", "pp_od_clk_voltage", "device", "vendor",
        "power_dpm_force_performance_level", "power_dpm_state",
    }


def test_repository_prefers_live_amdgpu_hwmon_sclk_and_vddgfx(tmp_path):
    repository = GPURepository.__new__(GPURepository)
    hwmon = tmp_path / "hwmon" / "hwmon0"
    hwmon.mkdir(parents=True)
    files = {
        hwmon / "freq1_label": "sclk",
        hwmon / "freq1_input": "500000000",
        hwmon / "in0_label": "vddgfx",
        hwmon / "in0_input": "699",
        hwmon / "in1_label": "vddnb",
        hwmon / "in1_input": "1199",
    }
    for path, value in files.items():
        path.write_text(value, encoding="utf-8")
    repository._leer_texto = lambda path: Path(path).read_text(encoding="utf-8") if Path(path).exists() else None
    repository._leer_entero = lambda path: int(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else None

    assert repository._gpu_hwmon_live_metrics(tmp_path) == (500, 699)


def test_gpu_busy_rejects_impossible_sysfs_metric_and_uses_fdinfo(tmp_path):
    repository = SistemaRepository.__new__(SistemaRepository)
    repository.gpu_busy_cache = 17
    repository.gpu_busy_cache_time = 10**12
    repository._leer_entero = lambda _path: 655
    repository._gpu_busy_fdinfo = lambda: 42

    assert repository._gpu_busy_percent(tmp_path) == 42
    assert repository.gpu_busy_cache == 42


def test_gpu_busy_accepts_valid_sysfs_metric_without_fdinfo(tmp_path):
    repository = SistemaRepository.__new__(SistemaRepository)
    repository.gpu_busy_cache = None
    repository.gpu_busy_cache_time = 0
    repository._leer_entero = lambda _path: 88
    repository._gpu_busy_fdinfo = lambda: (_ for _ in ()).throw(AssertionError("fdinfo"))

    assert repository._gpu_busy_percent(tmp_path) == 88
