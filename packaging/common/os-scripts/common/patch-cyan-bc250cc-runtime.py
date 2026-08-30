#!/usr/bin/python3
"""Apply the reviewed BC250 Control Center runtime fixes to Cyan.

BC250 Control Center builds Cyan from one immutable upstream commit on Bazzite.
This transformer carries two narrowly scoped fixes that are required by the GPU
control contract:

* requested frequency limits and thermal throttling use independent state, so a
  lower SetRange/SetFixedFrequency request cannot become a sticky hidden cap;
* the SMU firmware temperature limit follows Cyan's configured throttling
  threshold instead of being silently hard-coded to 80 C.

The transformer is intentionally strict.  It validates the Git blob identity of
all upstream files before changing anything and applies exact source
transformations.  Upstream drift therefore fails closed instead of receiving a
fuzzy patch.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REVIEWED_GOVERNOR_BLOB_SHA1 = "f9c4941f8893cf4458f22a9c7f2953c30d174f17"
REVIEWED_GPU_BLOB_SHA1 = "3b451f5e1332ccb9c22c8a7ecf76638a06bc9475"
PATCH_REVISION = "bc250cc.2"
PATCH_MARKER = f"BC250CC_RUNTIME_PATCH={PATCH_REVISION}"


def git_blob_sha1(payload: bytes) -> str:
    """Return Git's SHA-1 object id for one blob (not a security digest)."""

    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload, usedforsecurity=False).hexdigest()


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Cyan source contract changed for {label}: expected one match, found {count}."
        )
    return text.replace(old, new, 1)


def transform_governor(text: str) -> str:
    """Separate the user requested maximum from Cyan's thermal cap."""

    if PATCH_MARKER in text:
        required = (
            "thermal_cap: u32",
            "update_thermal_cap_for_temperature",
            "effective_max",
            "gpu.set_max_temperature(params.temperature.throttling_temp)?",
        )
        if not all(fragment in text for fragment in required):
            raise RuntimeError("Cyan governor has a BC250CC marker but incomplete invariants.")
        return text

    text = _replace_once(
        text,
        "    max_freq: u32,\n    requested_range: RangeInclusive<u32>,",
        "    // " + PATCH_MARKER + "\n"
        "    // Thermal state is independent from the user's requested range.\n"
        "    thermal_cap: u32,\n    requested_range: RangeInclusive<u32>,",
        "Governor.max_freq field",
    )
    text = _replace_once(
        text,
        "        params: GovernorParams,\n"
        "        gpu: GPU,\n"
        "        gpu_usage_fix: Option<GpuUsageFix>,",
        "        params: GovernorParams,\n"
        "        mut gpu: GPU,\n"
        "        gpu_usage_fix: Option<GpuUsageFix>,",
        "Governor mutable GPU constructor argument",
    )
    text = _replace_once(
        text,
        "    ) -> Result<Self> {\n"
        "        let curr_freq = gpu.get_freq()?;",
        "    ) -> Result<Self> {\n"
        "        gpu.set_max_temperature(params.temperature.throttling_temp)?;\n"
        "        let curr_freq = gpu.get_freq()?;",
        "Governor startup firmware temperature",
    )
    text = _replace_once(
        text,
        "        let max_freq = *params.allowed_frequency_range.end();\n"
        "        let requested_range = params.initial_frequency_range.clone();",
        "        let thermal_cap = *params.allowed_frequency_range.end();\n"
        "        let requested_range = params.initial_frequency_range.clone();",
        "Governor constructor maximum",
    )
    text = _replace_once(
        text,
        "            usage_fix_cycle: 0,\n"
        "            max_freq,\n"
        "            requested_range,",
        "            usage_fix_cycle: 0,\n"
        "            thermal_cap,\n"
        "            requested_range,",
        "Governor constructor field",
    )
    text = _replace_once(
        text,
        "        let temp = self.update_max_freq_for_temperature()?;\n"
        "        if self.test_mode {\n"
        "            return Ok(());\n"
        "        }\n"
        "        let (next_target, next_status, should_apply_change) = compute_frequency_decision(\n"
        "            self.curr_freq,\n"
        "            self.target_freq,\n"
        "            self.status,\n"
        "            self.max_freq,",
        "        let temp = self.update_thermal_cap_for_temperature()?;\n"
        "        if self.test_mode {\n"
        "            return Ok(());\n"
        "        }\n"
        "        let effective_max = (*self.requested_range.end()).min(self.thermal_cap);\n"
        "        let (next_target, next_status, should_apply_change) = compute_frequency_decision(\n"
        "            self.curr_freq,\n"
        "            self.target_freq,\n"
        "            self.status,\n"
        "            effective_max,",
        "run_iteration effective maximum",
    )
    text = _replace_once(
        text,
        "        self.requested_range = *self.startup_initial_range.start()..=frequency;\n"
        "        if self.max_freq > frequency {\n"
        "            self.max_freq = frequency;\n"
        "        }\n"
        "        Ok(())",
        "        self.requested_range = *self.startup_initial_range.start()..=frequency;\n"
        "        Ok(())",
        "fixed frequency sticky cap",
    )
    text = _replace_once(
        text,
        "        if self.max_freq > *self.requested_range.end() {\n"
        "            self.max_freq = *self.requested_range.end();\n"
        "        }\n"
        "        Ok(())\n"
        "    }\n"
        "    pub fn target_cycle_interval",
        "        Ok(())\n"
        "    }\n"
        "    pub fn target_cycle_interval",
        "range sticky cap",
    )
    text = _replace_once(
        text,
        "        if throttling != 0 {\n"
        "            self.params.temperature.throttling_temp = effective_throttling;\n"
        "        }",
        "        if throttling != 0 {\n"
        "            self.gpu.set_max_temperature(effective_throttling)?;\n"
        "            self.params.temperature.throttling_temp = effective_throttling;\n"
        "        }",
        "runtime firmware temperature update",
    )
    text = _replace_once(
        text,
        "        if self.max_freq > *self.requested_range.end() {\n"
        "            self.max_freq = *self.requested_range.end();\n"
        "        }\n"
        "        info!(\n"
        "            \"Temperature thresholds updated at runtime: throttling={}C, recovery={}C\",",
        "        info!(\n"
        "            \"Temperature thresholds updated at runtime: throttling={}C, recovery={}C\",",
        "temperature command sticky cap",
    )

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
    new_thermal = '''    fn update_thermal_cap_for_temperature(&mut self) -> Result<u32> {
        let temp = self.gpu.read_temperature()?;
        if let Some(max_temp) = self.params.temperature.throttling_temp {
            let min_freq = *self.params.allowed_frequency_range.start();
            let allowed_max = *self.params.allowed_frequency_range.end();
            let requested_max = *self.requested_range.end();
            let effective_max = requested_max.min(self.thermal_cap);
            if temp > max_temp && effective_max > min_freq + self.params.significant_change {
                self.thermal_cap = effective_max
                    .saturating_sub(self.params.significant_change)
                    .max(min_freq);
                debug!("throttling temp {temp} freq {}", self.thermal_cap);
            } else if let Some(recovery_temp) = self.params.temperature.throttling_recovery_temp
                && temp < recovery_temp
                && self.thermal_cap != allowed_max
            {
                self.thermal_cap = allowed_max;
                debug!("recover throttling temp {temp} freq {}", self.thermal_cap);
            }
        }

        Ok(temp)
    }
'''
    text = _replace_once(text, old_thermal, new_thermal, "thermal maximum state machine")

    if "self.max_freq" in text or "update_max_freq_for_temperature" in text:
        raise RuntimeError("Cyan governor still contains the old shared max_freq state.")
    required = (
        PATCH_MARKER,
        "thermal_cap",
        "effective_max",
        "gpu.set_max_temperature(params.temperature.throttling_temp)?",
    )
    if not all(fragment in text for fragment in required):
        raise RuntimeError("Cyan governor patch did not establish its required invariants.")
    return text


def transform_gpu(text: str) -> str:
    """Make the SMU firmware thermal limit follow Cyan's configured threshold."""

    gpu_marker = f"// {PATCH_MARKER}: configurable SMU thermal limit"
    if gpu_marker in text:
        required = (
            "fn set_max_temperature(&mut self, _temp: Option<u32>)",
            "self.freq_strategy.set_max_temperature(temp)",
            "self.smu.set_gpu_max_temperature(temp_c)?",
        )
        if not all(fragment in text for fragment in required):
            raise RuntimeError("Cyan GPU source has a BC250CC marker but incomplete invariants.")
        return text

    text = _replace_once(
        text,
        "    fn get_freq(&self) -> Result<u32>;\n"
        "    fn shutdown(&mut self) -> Result<()> {",
        "    fn get_freq(&self) -> Result<u32>;\n"
        f"    {gpu_marker}\n"
        "    fn set_max_temperature(&mut self, _temp: Option<u32>) -> Result<()> {\n"
        "        Ok(())\n"
        "    }\n"
        "    fn shutdown(&mut self) -> Result<()> {",
        "FreqStrategy temperature capability",
    )
    text = _replace_once(
        text,
        "    pub fn get_freq(&self) -> Result<u32> {\n"
        "        self.freq_strategy.get_freq()\n"
        "    }\n\n"
        "    pub fn shutdown(&mut self) -> Result<()> {",
        "    pub fn get_freq(&self) -> Result<u32> {\n"
        "        self.freq_strategy.get_freq()\n"
        "    }\n\n"
        "    pub fn set_max_temperature(&mut self, temp: Option<u32>) -> Result<()> {\n"
        "        self.freq_strategy.set_max_temperature(temp)\n"
        "    }\n\n"
        "    pub fn shutdown(&mut self) -> Result<()> {",
        "GPU temperature capability",
    )
    text = _replace_once(
        text,
        "        info!(\"SMU communication verified\");\n"
        "        smu.set_gpu_max_temperature(80)?;\n"
        "        smu.unforce_gfx_freq()?;",
        "        info!(\"SMU communication verified\");\n"
        "        smu.unforce_gfx_freq()?;",
        "hard-coded SMU 80C limit",
    )
    text = _replace_once(
        text,
        "    fn get_freq(&self) -> Result<u32> {\n"
        "        Ok(self.smu.get_gfx_frequency()?)\n"
        "    }\n\n"
        "    fn shutdown(&mut self) -> Result<()> {",
        "    fn get_freq(&self) -> Result<u32> {\n"
        "        Ok(self.smu.get_gfx_frequency()?)\n"
        "    }\n\n"
        "    fn set_max_temperature(&mut self, temp: Option<u32>) -> Result<()> {\n"
        "        if let Some(temp_c) = temp {\n"
        "            self.smu.set_gpu_max_temperature(temp_c)?;\n"
        "            debug!(\"SMU GPU max temperature set to {} C\", temp_c);\n"
        "        }\n"
        "        Ok(())\n"
        "    }\n\n"
        "    fn shutdown(&mut self) -> Result<()> {",
        "SMU configurable temperature implementation",
    )

    if "set_gpu_max_temperature(80)" in text:
        raise RuntimeError("Cyan GPU source still contains the hidden 80C SMU limit.")
    required = (
        gpu_marker,
        "self.freq_strategy.set_max_temperature(temp)",
        "self.smu.set_gpu_max_temperature(temp_c)?",
    )
    if not all(fragment in text for fragment in required):
        raise RuntimeError("Cyan GPU patch did not establish its required invariants.")
    return text


def _load_reviewed(path: Path, expected_blob: str, label: str) -> tuple[bytes, str]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise RuntimeError(f"cannot read Cyan {label}: {error}") from error
    try:
        text = payload.decode("utf-8")
    except UnicodeError as error:
        raise RuntimeError(f"Cyan {label} is not valid UTF-8: {error}") from error
    if PATCH_MARKER not in text:
        actual_blob = git_blob_sha1(payload)
        if actual_blob != expected_blob:
            raise RuntimeError(
                f"Cyan {label} does not match reviewed blob {expected_blob} "
                f"(found {actual_blob})."
            )
    return payload, text


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} /path/to/cyan-source", file=sys.stderr)
        return 2
    source = Path(argv[1])
    governor_path = source / "src" / "governor.rs"
    gpu_path = source / "src" / "gpu.rs"
    try:
        _governor_payload, governor_text = _load_reviewed(
            governor_path, REVIEWED_GOVERNOR_BLOB_SHA1, "src/governor.rs"
        )
        _gpu_payload, gpu_text = _load_reviewed(
            gpu_path, REVIEWED_GPU_BLOB_SHA1, "src/gpu.rs"
        )
        patched_governor = transform_governor(governor_text)
        patched_gpu = transform_gpu(gpu_text)
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 61

    changed = False
    try:
        if patched_governor != governor_text:
            governor_path.write_text(patched_governor, encoding="utf-8", newline="")
            changed = True
        if patched_gpu != gpu_text:
            gpu_path.write_text(patched_gpu, encoding="utf-8", newline="")
            changed = True
    except OSError as error:
        print(f"ERROR: cannot write reviewed Cyan source: {error}", file=sys.stderr)
        return 61

    print(
        f"BC250_CYAN_PATCH_{'APPLIED' if changed else 'PRESENT'}={PATCH_REVISION}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
