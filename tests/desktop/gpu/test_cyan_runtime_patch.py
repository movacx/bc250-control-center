import shutil
import subprocess
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

PATCHER = (
    Path(__file__).resolve().parents[3]
    / "packaging/common/os-scripts/common/patch-cyan-bc250cc-runtime.py"
)
spec = spec_from_file_location("bc250_cyan_runtime_patcher", PATCHER)
assert spec and spec.loader
patcher = module_from_spec(spec)
spec.loader.exec_module(patcher)


def governor_fixture():
    old_thermal = '''    fn update_max_freq_for_temperature(&mut self) -> Result<u32> {
        let temp = self.gpu.read_temperature()?;
        if let Some(max_temp) = self.params.temperature.throttling_temp {
            let min_freq = *self.params.allowed_frequency_range.start();
            if temp > max_temp && self.max_freq > min_freq + self.params.significant_change {
                self.max_freq -= self.params.significant_change;
                debug!("throttling temp {temp} freq {}", self.max_freq);
            } else if let Some(recovery_temp) = self.params.temperature.throttling_recovery_temp
                && temp < recovery_temp
                && self.max_freq != *self.requested_range.end()
            {
                self.max_freq = *self.requested_range.end();
                debug!("recover throttling temp {temp} freq {}", self.max_freq);
            }
        }

        Ok(temp)
    }
'''
    return (
        "    max_freq: u32,\n    requested_range: RangeInclusive<u32>,\n"
        "        params: GovernorParams,\n        gpu: GPU,\n        gpu_usage_fix: Option<GpuUsageFix>,\n"
        "    ) -> Result<Self> {\n        let curr_freq = gpu.get_freq()?;\n"
        "        let max_freq = *params.allowed_frequency_range.end();\n        let requested_range = params.initial_frequency_range.clone();\n"
        "            usage_fix_cycle: 0,\n            max_freq,\n            requested_range,\n"
        "        let temp = self.update_max_freq_for_temperature()?;\n        if self.test_mode {\n            return Ok(());\n        }\n        let (next_target, next_status, should_apply_change) = compute_frequency_decision(\n            self.curr_freq,\n            self.target_freq,\n            self.status,\n            self.max_freq,\n"
        "        self.requested_range = *self.startup_initial_range.start()..=frequency;\n        if self.max_freq > frequency {\n            self.max_freq = frequency;\n        }\n        Ok(())\n"
        "        if self.max_freq > *self.requested_range.end() {\n            self.max_freq = *self.requested_range.end();\n        }\n        Ok(())\n    }\n    pub fn target_cycle_interval\n"
        "        if throttling != 0 {\n            self.params.temperature.throttling_temp = effective_throttling;\n        }\n"
        "        if self.max_freq > *self.requested_range.end() {\n            self.max_freq = *self.requested_range.end();\n        }\n        info!(\n            \"Temperature thresholds updated at runtime: throttling={}C, recovery={}C\",\n"
        + old_thermal
    )


def gpu_fixture():
    return (
        "    fn get_freq(&self) -> Result<u32>;\n    fn shutdown(&mut self) -> Result<()> {\n"
        "    pub fn get_freq(&self) -> Result<u32> {\n        self.freq_strategy.get_freq()\n    }\n\n    pub fn shutdown(&mut self) -> Result<()> {\n"
        "        info!(\"SMU communication verified\");\n        smu.set_gpu_max_temperature(80)?;\n        smu.unforce_gfx_freq()?;\n"
        "    fn get_freq(&self) -> Result<u32> {\n        Ok(self.smu.get_gfx_frequency()?)\n    }\n\n    fn shutdown(&mut self) -> Result<()> {\n"
    )


def test_governor_patch_separates_requested_range_from_thermal_cap():
    patched = patcher.transform_governor(governor_fixture())

    assert patcher.PATCH_MARKER in patched
    assert "self.max_freq" not in patched
    assert "thermal_cap: u32" in patched
    assert "requested_max.min(self.thermal_cap)" in patched
    assert "gpu.set_max_temperature(params.temperature.throttling_temp)?" in patched
    assert "self.gpu.set_max_temperature(effective_throttling)?" in patched


def test_gpu_patch_removes_hidden_80c_and_uses_configured_threshold():
    patched = patcher.transform_gpu(gpu_fixture())

    assert patcher.PATCH_MARKER in patched
    assert "set_gpu_max_temperature(80)" not in patched
    assert "self.freq_strategy.set_max_temperature(temp)" in patched
    assert "self.smu.set_gpu_max_temperature(temp_c)?" in patched


def test_patch_is_idempotent_after_marker_and_invariants_are_present():
    governor = patcher.transform_governor(governor_fixture())
    gpu = patcher.transform_gpu(gpu_fixture())

    assert patcher.transform_governor(governor) == governor
    assert patcher.transform_gpu(gpu) == gpu


def test_strict_transform_fails_closed_on_upstream_drift():
    with pytest.raises(RuntimeError, match="source contract changed"):
        patcher.transform_governor("struct Governor {}")
    with pytest.raises(RuntimeError, match="source contract changed"):
        patcher.transform_gpu("trait FreqStrategy {}")


def test_git_blob_hash_helper_matches_git_object_semantics():
    assert patcher.git_blob_sha1(b"hello") == "b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0"


@pytest.mark.skipif(shutil.which("rustc") is None, reason="optional native Rust regression")
def test_patched_thermal_method_does_not_keep_a_user_range_as_a_sticky_cap(tmp_path):
    # Compile the method emitted by our real transformer, with a fake GPU.
    # This exercises the Rust implementation without opening SMU/sysfs.
    patched = patcher.transform_governor(governor_fixture())
    method = patched[patched.index("    fn update_thermal_cap_for_temperature"):]
    harness = r'''
use std::ops::RangeInclusive;
type Result<T> = std::result::Result<T, &'static str>;
macro_rules! debug { ($($arg:tt)*) => {}; }
struct Gpu { temp: u32 }
impl Gpu { fn read_temperature(&self) -> Result<u32> { Ok(self.temp) } }
struct Temperature { throttling_temp: Option<u32>, throttling_recovery_temp: Option<u32> }
struct Params { temperature: Temperature, allowed_frequency_range: RangeInclusive<u32>, significant_change: u32 }
struct Governor { gpu: Gpu, params: Params, requested_range: RangeInclusive<u32>, thermal_cap: u32 }
impl Governor {
''' + method + r'''
}
fn main() {
    let mut gov = Governor {
        gpu: Gpu { temp: 80 },
        params: Params { temperature: Temperature { throttling_temp: Some(85), throttling_recovery_temp: Some(75) }, allowed_frequency_range: 500..=2400, significant_change: 50 },
        requested_range: 1000..=2000, thermal_cap: 2400,
    };
    for maximum in [1850, 1500, 2000] {
        gov.requested_range = 1000..=maximum;
        gov.update_thermal_cap_for_temperature().unwrap();
        assert_eq!(maximum.min(gov.thermal_cap), maximum);
    }
    gov.gpu.temp = 90;
    gov.update_thermal_cap_for_temperature().unwrap();
    assert_eq!(gov.thermal_cap, 1950);
    gov.gpu.temp = 80;
    for maximum in [1500, 2000] {
        gov.requested_range = 1000..=maximum;
        gov.update_thermal_cap_for_temperature().unwrap();
        assert_eq!(gov.thermal_cap, 1950); // Preserve real thermal throttling.
    }
    gov.gpu.temp = 70;
    gov.update_thermal_cap_for_temperature().unwrap();
    assert_eq!(gov.thermal_cap, 2400);
}
'''
    source = tmp_path / "thermal.rs"
    source.write_text(harness)
    binary = tmp_path / "thermal-test"
    built = subprocess.run([shutil.which("rustc"), "--edition=2024", str(source), "-o", str(binary)], capture_output=True, text=True, timeout=30)
    assert built.returncode == 0, built.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
