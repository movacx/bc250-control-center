"""Pure composition contracts for the full BC-250 GPU state snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .governor_conflicts import CYAN_GOVERNOR


@dataclass(frozen=True)
class GpuDeviceEvidence:
    path: str
    device: object
    vendor: object
    sclk_text: str
    mclk_text: str
    sclk_actual: object
    mclk_actual: object
    voltage_actual: object
    od_sclk_min: object
    od_sclk_max: object
    busy: object
    vram_total: object
    vram_used: object
    power_level: object
    power_state: object


@dataclass(frozen=True)
class GpuGovernorEvidence:
    selected: str
    context: Mapping[str, object]
    runtime: Mapping[str, object]
    safe_points: Mapping[str, object]
    frequency_range: Mapping[str, object]
    high_frequency_points: Mapping[str, object]
    cyan_telemetry: Mapping[str, object]
    tools: Mapping[str, object]


def gpu_telemetry_warning(
    selected_governor: str, cyan_telemetry: Mapping[str, object],
) -> str:
    if selected_governor != CYAN_GOVERNOR:
        return (
            "Oberon Governor does not repair BC-250 gpu_metrics. MangoHud or "
            "radeontop may report about 655% GPU usage unless the operating "
            "system image provides an independent BC-250 telemetry patch."
        )
    if cyan_telemetry.get("runtime_frequency_fix_supported"):
        return ""
    return (
        "Cyan GPU frequency reporting is not fully prepared because the active service "
        "binary does not provide fix-freq. Run Prepare everything to install and verify "
        "the official Cyan SMU runtime before changing core count."
    )


def build_gpu_state_snapshot(
    device: GpuDeviceEvidence,
    governor: GpuGovernorEvidence,
) -> dict[str, object]:
    runtime = governor.runtime
    safe = governor.safe_points
    current_min = runtime.get("current_min")
    current_max = runtime.get("current_max")
    is_cyan = governor.selected == CYAN_GOVERNOR
    telemetry = dict(governor.cyan_telemetry) if is_cyan else {}
    return {
        "gpu_path": device.path,
        "governor_backend": governor.selected,
        "governor_preference": governor.context.get("preference", "auto"),
        "governor_selection_reason": governor.context.get("reason", "default"),
        "governor_detected": governor.context.get("detected", {}),
        "telemetry_metrics_supported": is_cyan,
        "cyan_telemetry": telemetry,
        "telemetry_warning": gpu_telemetry_warning(governor.selected, telemetry),
        "device": device.device,
        "vendor": device.vendor,
        "driver": "amdgpu" if device.path else "",
        "service_active": runtime.get("service_active", ""),
        "service_sub": runtime.get("service_sub", ""),
        "service_enabled": runtime.get("service_enabled", ""),
        "service_main_pid": runtime.get("service_main_pid", 0),
        "dbus_ok": is_cyan and current_min is not None,
        "range_control_ok": current_min is not None and current_max is not None,
        "dbus_performance_enabled": runtime.get("dbus_performance"),
        "current_min": current_min,
        "current_max": current_max,
        "allowed_min": runtime.get("allowed_min"),
        "allowed_max": runtime.get("allowed_max"),
        "sclk_actual": device.sclk_actual,
        "mclk_actual": device.mclk_actual,
        "voltaje_actual": device.voltage_actual,
        "od_sclk_min": device.od_sclk_min,
        "od_sclk_max": device.od_sclk_max,
        "gpu_busy": device.busy,
        "vram_total": device.vram_total,
        "vram_usado": device.vram_used,
        "power_level": device.power_level,
        "power_state": device.power_state,
        "pp_dpm_sclk": device.sclk_text,
        "safe_points": safe.get("points", ()),
        "safe_points_with_voltage": safe.get("points_with_voltage", ()),
        "config_max_frequency": safe.get("max_frequency", 0),
        "config_max_voltage": safe.get("max_voltage", 0),
        "safe_points_missing_voltage": safe.get("missing_voltage", ()),
        "safe_points_voltage_errors": safe.get("voltage_order_errors", ()),
        "safe_points_duplicate_frequencies": safe.get("duplicate_frequencies", ()),
        "safe_points_error": safe.get("error", ""),
        "config_path": safe.get("config_path", ""),
        "high_frequency_points": dict(governor.high_frequency_points),
        "frequency_range": dict(governor.frequency_range),
        "tools": dict(governor.tools),
    }
