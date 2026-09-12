
import pytest

from bc250cc.domain.telemetry import voltage_mv
from bc250cc.infrastructure.apu_telemetry import collect_apu_telemetry, dpm_reading
from bc250cc.infrastructure.sistema_repository import SistemaRepository
from frontends.desktop.core.state import _voltage_millivolts


@pytest.mark.parametrize("raw", [40058, 45344, 4063234, 960000, 0.039, -1, float("nan"), float("inf"), True])
def test_corrupt_voltage_is_not_reinterpreted_as_another_unit(raw):
    assert voltage_mv(raw) is None
    assert _voltage_millivolts(raw) == 0


def test_live_voltage_validation_has_no_overdrive_fallback(tmp_path):
    sensor = tmp_path / "hwmon/hwmon1"
    sensor.mkdir(parents=True)
    (sensor / "name").write_text("amdgpu")
    (sensor / "in0_label").write_text("vddgfx")
    (sensor / "in0_input").write_text("45344")
    (tmp_path / "pp_od_clk_voltage").write_text("OD_VDDC:\n0: 45344mV *\n")
    repo = object.__new__(SistemaRepository)
    repo.hwmons = [("amdgpu", sensor)]
    repo._gpu_busy_percent = lambda _gpu: None
    assert repo.voltaje_chip("amdgpu", "vddgfx") is None
    assert repo._gpu_device_evidence(tmp_path).voltage_actual is None


@pytest.mark.parametrize("payload", ["0: 0Mhz *", "0: 2Mhz *", "0: 17411Mhz *", "0: 1000Mhz", "0: 800Mhz *\n1: 900Mhz *"])
def test_invalid_memory_clock_never_becomes_live_telemetry(tmp_path, payload):
    path = tmp_path / "pp_dpm_mclk"
    path.write_text(payload)
    assert dpm_reading(path)["value"] is None
    assert dpm_reading(path)["status"] == "invalid"
    assert object.__new__(SistemaRepository)._parse_dpm_actual(payload) is None


def test_eight_core_capture_preserves_raw_evidence_and_suspects_layout(tmp_path):
    files = {
        "sys/bus/pci/devices/0000:01:00.0/vendor": "0x1002",
        "sys/bus/pci/devices/0000:01:00.0/device": "0x13fe",
        "sys/bus/pci/devices/0000:01:00.0/pp_dpm_mclk": "0: 0Mhz *",
        "sys/bus/pci/devices/0000:01:00.0/hwmon/hwmon1/name": "amdgpu",
        "sys/bus/pci/devices/0000:01:00.0/hwmon/hwmon1/in0_label": "vddgfx",
        "sys/bus/pci/devices/0000:01:00.0/hwmon/hwmon1/in0_input": "45344",
        "sys/bus/pci/devices/0000:01:00.0/hwmon/hwmon1/temp1_input": "0",
        "sys/module/amdgpu/parameters/cs_legacy_8core_metrics": "N",
    }
    for cpu in range(16):
        files[f"sys/devices/system/cpu/cpu{cpu}/topology/physical_package_id"] = "0"
        files[f"sys/devices/system/cpu/cpu{cpu}/topology/core_id"] = str(cpu % 8)
    for name, payload in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload)
    report = collect_apu_telemetry(root=tmp_path)
    assert report["physical_cores"] == 8
    assert report["layout_mismatch_suspected"] is True
    assert report["metrics"]["voltage"]["raw"] == "45344"
    assert report["metrics"]["voltage"]["value"] is None
    assert report["metrics"]["temperature"]["status"] == "invalid"
    assert (tmp_path / "sys/module/amdgpu/parameters/cs_legacy_8core_metrics").read_text() == "N"


def test_aliased_fclk_is_not_advertised_as_an_independent_clock(tmp_path):
    device = tmp_path / "sys/bus/pci/devices/test"
    device.mkdir(parents=True)
    for name, content in {"vendor": "0x1002", "device": "0x13fe", "pp_dpm_mclk": "0: 875Mhz *", "pp_dpm_fclk": "0: 875Mhz *"}.items():
        (device / name).write_text(content)
    report = collect_apu_telemetry(root=tmp_path)
    assert report["metrics"]["mclk"]["value"] == 875
    assert report["metrics"]["fclk"]["status"] == "unverified"
    assert report["metrics"]["fclk"]["value"] is None
    assert report["metrics"]["uclk"]["status"] == "missing"
