"""Bounded passive APU diagnostics. No SMU commands or kernel writes."""

from __future__ import annotations

import re
import time
from pathlib import Path

from bc250cc.domain.telemetry import clock_mhz, valid_number, voltage_mv


def _read(path):
    try:
        with path.open(encoding="ascii", errors="replace") as stream:
            return stream.read(8192).strip()
    except OSError:
        return None


def reading(raw, source, unit, validator):
    value = validator(raw)
    return {
        "value": value, "raw": raw, "source": str(source), "unit": unit,
        "status": "valid" if value is not None else "missing" if raw is None else "invalid",
    }


def dpm_reading(path):
    raw = _read(path)
    matches = re.findall(r"(?im)^\s*\d+:\s*(\d+)\s*MHz\s*\*\s*$", raw or "")
    result = reading(matches[0] if len(matches) == 1 else None, path, "MHz", clock_mhz)
    result["raw"] = raw
    if raw is not None and len(matches) != 1:
        result["status"] = "invalid"
    return result


def collect_apu_telemetry(device=None, *, root=Path("/")):
    root = Path(root)
    pci = root / "sys/bus/pci/devices"
    if device is None:
        device = next((p for p in sorted(pci.glob("*"))
                       if _read(p / "vendor") == "0x1002" and _read(p / "device") == "0x13fe"), None)
    else:
        device = Path(device)
        if _read(device / "vendor") != "0x1002" or _read(device / "device") != "0x13fe":
            device = None
    parameters = root / "sys/module/amdgpu/parameters"
    flags = {key: _read(parameters / key) for key in (
        "cs_legacy_8core_metrics", "cs_eight_core_map", "cs_full_telemetry",
        "cs_metrics_cache_ms", "cs_gfxclk_cache_ms", "cs_activity_cache_ms",
    )}
    topology = set()
    for cpu in (root / "sys/devices/system/cpu").glob("cpu[0-9]*"):
        package = _read(cpu / "topology/physical_package_id")
        core = _read(cpu / "topology/core_id")
        if package is not None and core is not None:
            topology.add((package, core))
    metrics = {}
    if device is not None:
        for name, filename in (("sclk", "pp_dpm_sclk"), ("mclk", "pp_dpm_mclk"),
                               ("fclk", "pp_dpm_fclk"), ("uclk", "pp_dpm_uclk")):
            metrics[name] = dpm_reading(device / filename)
        # Cyan Skillfish exports MemclkFrequency through multiple clock names.
        # A plausible number at pp_dpm_fclk does not prove independent FCLK.
        if metrics["fclk"]["value"] is not None:
            metrics["fclk"].update(value=None, status="unverified", reason="independent_fclk_unproven")
        for hwmon in sorted((device / "hwmon").glob("hwmon*")):
            if _read(hwmon / "name") != "amdgpu":
                continue
            for label in sorted(hwmon.glob("in*_label")):
                if _read(label) == "vddgfx":
                    path = label.with_name(label.name.replace("_label", "_input"))
                    metrics["voltage"] = reading(_read(path), path, "mV", voltage_mv)
            path = hwmon / "temp1_input"
            metrics["temperature"] = reading(
                _read(path), path, "°C",
                lambda raw: (valid_number(raw, 100, 130000) / 1000)
                if valid_number(raw, 100, 130000) is not None else None,
            )
    invalid = [key for key, value in metrics.items() if value["status"] == "invalid"]
    suspected = len(topology) == 8 and len(invalid) >= 2 and flags["cs_legacy_8core_metrics"] in {"N", "0"}
    return {
        "schema_version": 1, "sampled_at_monotonic": time.monotonic(),
        "boot_id": _read(root / "proc/sys/kernel/random/boot_id"),
        "kernel": _read(root / "proc/sys/kernel/osrelease"),
        "bios_version": _read(root / "sys/class/dmi/id/bios_version"),
        "physical_cores": len(topology) or None, "device": str(device) if device else None,
        "parameters": flags, "metrics": metrics,
        "status": "invalid" if invalid else "unavailable" if not metrics else "partial"
        if any(item["status"] != "valid" for item in metrics.values()) else "valid",
        "layout_mismatch_suspected": suspected,
        "recommendation": "verify_firmware_metrics_layout" if suspected else None,
    }
