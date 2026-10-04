"""Cyan leaves its bind mounts behind on stop; the preflight must clear them."""
from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

PREFLIGHT = Path(__file__).resolve().parents[2] / "privileged/helpers/bc250-cyan-overlay-preflight"


def _preflight():
    loader = importlib.machinery.SourceFileLoader("bc250_cyan_preflight", str(PREFLIGHT))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


def test_deleted_cyan_sources_on_the_device_are_found(tmp_path):
    module = _preflight()
    device = tmp_path / "0000:01:00.0"
    mountinfo = "\n".join([
        f"804 43 0:26 /patched_freq_metrics//deleted {device}/hwmon/hwmon1/freq1_input rw - tmpfs tmpfs rw",
        f"391 43 0:26 /patched_gpu_metrics//deleted {device}/gpu_metrics rw - tmpfs tmpfs rw",
        f"392 43 0:26 /patched_gpu_metrics {device}/gpu_metrics rw - tmpfs tmpfs rw",
    ])

    assert module.stale_cyan_mounts(mountinfo, device) == [
        f"{device}/gpu_metrics",
        f"{device}/gpu_metrics",
        f"{device}/hwmon/hwmon1/freq1_input",
    ]


def test_unrelated_mounts_are_left_alone(tmp_path):
    module = _preflight()
    device = tmp_path / "0000:01:00.0"
    mountinfo = "\n".join([
        f"1 43 0:26 /other {device}/gpu_metrics rw - tmpfs tmpfs rw",
        "2 43 0:26 /patched_gpu_metrics //elsewhere/gpu_metrics rw - tmpfs tmpfs rw",
        f"3 43 0:26 /patched_freq_metrics {device}/hwmon/hwmon1/temp1_input rw - tmpfs tmpfs rw",
    ])

    assert module.stale_cyan_mounts(mountinfo, device) == []
