"""Pure normalization and presentation plans for live performance samples."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping


@dataclass(frozen=True)
class ResourceSamplePlan:
    key: str
    primary: str
    context: str
    graph_values: tuple[tuple[str, float], ...]
    stats: tuple[str, str, str, str]


def _number(value: object, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else float(default)
    except (TypeError, ValueError):
        return float(default)


def format_bytes(value: object, *, decimals: int = 1) -> str:
    amount = max(0.0, _number(value))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    index = 0
    while amount >= 1024.0 and index < len(units) - 1:
        amount /= 1024.0
        index += 1
    return f"{amount:.0f} {units[index]}" if index == 0 else f"{amount:.{decimals}f} {units[index]}"


def format_rate(value: object) -> str:
    return f"{format_bytes(value)}/s"


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _cpu_plan(cpu: Mapping[str, object], peaks: Mapping[str, float], translate: Callable[[str], str]) -> ResourceSamplePlan:
    cpu_usage = max(0.0, min(100.0, _number(cpu.get("usage_percent"))))
    cpu_freq = max(0.0, _number(cpu.get("frequency_mhz")))
    cpu_temp_raw = cpu.get("temperature_c")
    load_raw = cpu.get("load_average")
    load = load_raw if isinstance(load_raw, (list, tuple)) else ()
    cpu_peak = max(_number(peaks.get("cpu")), cpu_usage)
    return ResourceSamplePlan(
        "cpu",
        f"{cpu_usage:.0f}%",
        f"{cpu_freq / 1000:.2f} GHz" if cpu_freq else translate("Frequency unavailable"),
        (("Usage", cpu_usage),),
        (
            f"{cpu_freq / 1000:.2f} GHz" if cpu_freq else "--",
            f"{_number(cpu_temp_raw):.1f} °C" if cpu_temp_raw is not None and math.isfinite(_number(cpu_temp_raw, math.nan)) else "--",
            f"{_number(load[0]):.2f}" if load and math.isfinite(_number(load[0], math.nan)) else "--",
            f"{cpu_peak:.0f}%",
        ),
    )


def _gpu_plan(gpu: Mapping[str, object], peaks: Mapping[str, float]) -> ResourceSamplePlan:
    gpu_usage_raw = gpu.get("usage_percent")
    gpu_usage = max(0.0, min(100.0, _number(gpu_usage_raw)))
    gpu_freq = max(0.0, _number(gpu.get("frequency_mhz")))
    gpu_temp_raw = gpu.get("temperature_c")
    gpu_power_raw = gpu.get("power_w")
    gpu_peak = max(_number(peaks.get("gpu")), gpu_usage)
    return ResourceSamplePlan(
        "gpu",
        f"{gpu_usage:.0f}%" if gpu_usage_raw is not None and math.isfinite(_number(gpu_usage_raw, math.nan)) else "--",
        f"{gpu_freq:.0f} MHz" if gpu_freq else "AMDGPU",
        (("Usage", gpu_usage),),
        (
            f"{gpu_freq:.0f} MHz" if gpu_freq else "--",
            f"{_number(gpu_temp_raw):.1f} °C" if gpu_temp_raw is not None and math.isfinite(_number(gpu_temp_raw, math.nan)) else "--",
            f"{_number(gpu_power_raw):.1f} W" if gpu_power_raw is not None and math.isfinite(_number(gpu_power_raw, math.nan)) else "--",
            f"{gpu_peak:.0f}%",
        ),
    )


def _vram_plan(gpu: Mapping[str, object], peaks: Mapping[str, float], translate: Callable[[str], str]) -> ResourceSamplePlan:
    vram_used = max(0.0, _number(gpu.get("vram_used")))
    vram_total = max(0.0, _number(gpu.get("vram_total")))
    raw_vram_percent = vram_used * 100.0 / vram_total if vram_total > 0 else 0.0
    vram_percent = max(0.0, min(100.0, raw_vram_percent))
    vram_available = max(0.0, vram_total - vram_used)
    vram_peak = max(_number(peaks.get("vram")), vram_percent)
    return ResourceSamplePlan(
        "vram",
        f"{vram_percent:.0f}%" if vram_total else "--",
        f"{format_bytes(vram_used)} / {format_bytes(vram_total)}" if vram_total else translate("Counters unavailable"),
        (("Used", vram_percent),),
        (
            format_bytes(vram_used) if vram_total else "--",
            format_bytes(vram_available) if vram_total else "--",
            format_bytes(vram_total) if vram_total else "--",
            f"{vram_peak:.0f}%" if vram_total else "--",
        ),
    )


def _memory_plan(memory: Mapping[str, object], peaks: Mapping[str, float]) -> ResourceSamplePlan:
    memory_percent = max(0.0, min(100.0, _number(memory.get("usage_percent"))))
    memory_used = max(0.0, _number(memory.get("used")))
    memory_total = max(0.0, _number(memory.get("total")))
    memory_available = max(0.0, _number(memory.get("available")))
    swap_percent = max(0.0, min(100.0, _number(memory.get("swap_percent"))))
    memory_peak = max(_number(peaks.get("memory")), memory_percent)
    compression = []
    if bool(memory.get("zram_active")):
        compression.append(f"ZRAM {format_bytes(memory.get('zram_total_bytes'))}")
    if memory.get("zswap_enabled") is True:
        compression.append("ZSWAP ON")
    ttm_bytes = max(0.0, _number(memory.get("ttm_limit_bytes")))
    if ttm_bytes:
        compression.append(f"TTM {format_bytes(ttm_bytes, decimals=0)}")
    context = f"{format_bytes(memory_used)} / {format_bytes(memory_total)}"
    if compression:
        context += " · " + " · ".join(compression)
    return ResourceSamplePlan(
        "memory",
        f"{memory_percent:.0f}%",
        context,
        (("Used", memory_percent),),
        (format_bytes(memory_used), format_bytes(memory_available), f"{swap_percent:.0f}%", f"{memory_peak:.0f}%"),
    )


def _disk_plan(disk: Mapping[str, object], peaks: Mapping[str, float], translate: Callable[[str], str]) -> ResourceSamplePlan:
    disk_usage = _number(disk.get("usage_percent"), -1.0)
    disk_used = max(0.0, _number(disk.get("used")))
    disk_total = max(0.0, _number(disk.get("total")))
    disk_available = max(0.0, disk_total - disk_used)
    read_bps = max(0.0, _number(disk.get("read_bps")))
    write_bps = max(0.0, _number(disk.get("write_bps")))
    active = max(0.0, min(100.0, _number(disk.get("active_percent"))))
    disk_peak = max(_number(peaks.get("disk")), read_bps, write_bps)
    disk_available_flag = disk_total > 0 and 0 <= disk_usage <= 100
    capacity = (
        f"{format_bytes(disk_used)} / {format_bytes(disk_total)}"
        if disk_available_flag
        else translate("Capacity unavailable")
    )
    return ResourceSamplePlan(
        "disk",
        f"{disk_usage:.0f}%" if disk_available_flag else "--",
        f"{capacity} · ↓ {format_rate(read_bps)} · ↑ {format_rate(write_bps)}",
        (("Read", read_bps), ("Write", write_bps)),
        (
            format_bytes(disk_used) if disk_available_flag else "--",
            format_bytes(disk_available) if disk_available_flag else "--",
            f"{active:.0f}%",
            format_rate(disk_peak),
        ),
    )


def _network_plan(network: Mapping[str, object], peaks: Mapping[str, float], translate: Callable[[str], str]) -> ResourceSamplePlan:
    download = max(0.0, _number(network.get("download_bps")))
    upload = max(0.0, _number(network.get("upload_bps")))
    network_peak = max(_number(peaks.get("network")), download, upload)
    interface = str(network.get("interface") or translate("not detected"))
    return ResourceSamplePlan(
        "network",
        f"↓ {format_rate(download)}",
        f"↑ {format_rate(upload)} · {interface}",
        (("Download", download), ("Upload", upload)),
        (interface, format_rate(download), format_rate(upload), format_rate(network_peak)),
    )


def present_performance_sample(
    sample: Mapping[str, object],
    *,
    previous_peaks: Mapping[str, float],
    translate: Callable[[str], str] = lambda value: value,
) -> tuple[ResourceSamplePlan, ...]:
    """Build stable UI plans for each independently sampled resource."""

    cpu = _mapping(sample.get("cpu"))
    gpu = _mapping(sample.get("gpu"))
    return (
        _cpu_plan(cpu, previous_peaks, translate),
        _gpu_plan(gpu, previous_peaks),
        _vram_plan(gpu, previous_peaks, translate),
        _memory_plan(_mapping(sample.get("memory")), previous_peaks),
        _disk_plan(_mapping(sample.get("disk")), previous_peaks, translate),
        _network_plan(_mapping(sample.get("network")), previous_peaks, translate),
    )
