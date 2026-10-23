"""The panel reports GPU hangs from the kernel log, the same way the desktop report does."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import tempfile
import types
from pathlib import Path

import pytest

from bc250cc.domain.gpu.reset_log import summarize

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "integrations" / "decky" / "bc250-quick-access" / "main.py"

SAMPLES = {
    "reported": """\
2026-10-15T16:20:00+0300 bazzite kernel: amdgpu 0000:01:00.0:  Process java pid 20602 thread java:cs0 pid 20698
2026-10-15T16:20:00+0300 bazzite kernel: amdgpu 0000:01:00.0: Ring gfx_0.0.0 reset failed
2026-10-15T16:20:00+0300 bazzite kernel: amdgpu 0000:01:00.0: GPU reset begin!. Source:  1
2026-10-15T16:20:04+0300 bazzite kernel: amdgpu 0000:01:00.0: VRAM is lost due to GPU reset!
""",
    "timeout": """\
2026-10-15T11:00:01+0300 kernel: amdgpu 0000:01:00.0: [drm:amdgpu_job_timedout] *ERROR* ring comp_1.0.0 timeout, signaled seq=88, emitted seq=90
2026-10-15T11:00:01+0300 kernel: amdgpu 0000:01:00.0: Process information: process steam pid 4242 thread steam:cs0 pid 4300
2026-10-15T11:05:11+0300 kernel: amdgpu 0000:01:00.0: GPU reset(2) begin!
""",
    "clean": "2026-10-15T10:00:00+0300 kernel: amdgpu 0000:01:00.0: [drm] PCIE GART of 512M enabled\n",
    "other driver": "2026-10-15T10:00:00+0300 kernel: i915 ring gfx timeout\n",
    "empty": "",
}


def _backend(monkeypatch):
    decky = types.ModuleType("decky")
    decky.logger = types.SimpleNamespace(info=lambda *_a, **_k: None)
    decky.DECKY_PLUGIN_SETTINGS_DIR = tempfile.mkdtemp(prefix="bc250-qam-settings-")
    monkeypatch.setitem(sys.modules, "decky", decky)
    spec = importlib.util.spec_from_file_location("bc250_quick_access_resets_test", BACKEND)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_the_plugin_and_the_application_read_a_log_the_same_way(monkeypatch, name):
    plugin = _backend(monkeypatch)
    lines = SAMPLES[name].splitlines()
    assert plugin.summarize_gpu_resets(lines) == summarize(lines).to_dict()


def test_the_log_is_read_once_per_refresh_window_not_on_every_poll(monkeypatch):
    plugin = _backend(monkeypatch)
    reads = []
    monkeypatch.setattr(plugin, "read_gpu_resets", lambda: reads.append(1) or {"label": "None this boot"})
    clock = [1000.0]
    monkeypatch.setattr(plugin.time, "monotonic", lambda: clock[0])
    panel = plugin.Plugin()

    async def poll():
        return await panel._gpu_reset_state()

    assert asyncio.run(poll()) == {"label": "None this boot"}
    clock[0] += 5
    asyncio.run(poll())
    assert len(reads) == 1
    clock[0] += plugin.GPU_RESET_REFRESH_SECONDS
    asyncio.run(poll())
    assert len(reads) == 2


def test_an_unreadable_log_reaches_the_panel_as_unknown_not_clean(monkeypatch):
    plugin = _backend(monkeypatch)
    monkeypatch.setattr(plugin.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no journal")))
    assert plugin.read_gpu_resets() is None
