"""The GPU hang summary: what the kernel log says, in a line a report can carry."""

from __future__ import annotations

import subprocess

from bc250cc.domain.gpu.reset_log import summarize
from bc250cc.infrastructure import gpu_reset_log

#: The lines a user pasted into a support thread (Bazzite, a Java game), as
#: ``journalctl -k -o short-iso`` writes them.
REPORTED = """\
2026-10-15T16:20:00+0300 bazzite kernel: amdgpu 0000:01:00.0:  Process java pid 20602 thread java:cs0 pid 20698
2026-10-15T16:20:00+0300 bazzite kernel: amdgpu 0000:01:00.0: Starting gfx_0.0.0 ring reset
2026-10-15T16:20:00+0300 bazzite kernel: amdgpu 0000:01:00.0: Ring gfx_0.0.0 reset failed
2026-10-15T16:20:00+0300 bazzite kernel: amdgpu 0000:01:00.0: GPU reset begin!. Source:  1
2026-10-15T16:20:04+0300 bazzite kernel: amdgpu 0000:01:00.0: failed to suspend display audio
2026-10-15T16:20:04+0300 bazzite kernel: amdgpu 0000:01:00.0: MODE1 reset
2026-10-15T16:20:04+0300 bazzite kernel: amdgpu 0000:01:00.0: GPU mode1 reset
2026-10-15T16:20:04+0300 bazzite kernel: amdgpu 0000:01:00.0: GPU reset succeeded, trying to resume
2026-10-15T16:20:04+0300 bazzite kernel: amdgpu 0000:01:00.0: VRAM is lost due to GPU reset!
""".splitlines()


def test_the_reported_hang_is_one_full_reset_with_the_vram_lost():
    summary = summarize(REPORTED)
    assert summary.full_resets == 1
    assert summary.ring_resets_failed == 1
    assert summary.vram_lost is True
    assert summary.last_ring == "gfx_0.0.0"
    assert summary.last_process == "java"
    assert summary.last_at == "2026-10-15 16:20:04"
    assert summary.label() == (
        "1 full reset · 1 ring reset failed · VRAM lost · last 2026-10-15 16:20:04 gfx_0.0.0 java"
    )


def test_a_clean_log_says_none():
    summary = summarize(["2026-10-15T10:00:00+0300 kernel: amdgpu 0000:01:00.0: [drm] PCIE GART of 512M enabled"])
    assert not summary.any
    assert summary.label() == "None this boot"


def test_a_ring_timeout_counts_and_names_the_ring():
    summary = summarize([
        "2026-10-15T11:00:01+0300 kernel: amdgpu 0000:01:00.0: [drm:amdgpu_job_timedout] *ERROR* ring comp_1.0.0 timeout, signaled seq=88, emitted seq=90",
        "2026-10-15T11:00:01+0300 kernel: amdgpu 0000:01:00.0: Process information: process steam pid 4242 thread steam:cs0 pid 4300",
    ])
    assert summary.ring_timeouts == 1 and summary.full_resets == 0
    assert summary.last_ring == "comp_1.0.0"
    assert summary.last_process == "steam"
    assert summary.label().startswith("1 ring timeout · last 2026-10-15 11:00:01 comp_1.0.0 steam")


def test_lines_from_other_drivers_are_ignored():
    assert not summarize(["kernel: i915 ring gfx timeout", "kernel: nvme GPU reset begin"]).any


def test_numbered_resets_of_newer_kernels_count_too():
    assert summarize(["2026-10-15T09:00:00+0300 kernel: amdgpu 0000:01:00.0: GPU reset(1) begin!"]).full_resets == 1


def test_lines_without_a_timestamp_still_count():
    summary = summarize(["жов 15 16:20:00.801246 bazzite kernel: amdgpu 0000:01:00.0: GPU reset begin!. Source:  1"])
    assert summary.full_resets == 1 and summary.last_at == ""


def _completed(stdout: str, code: int = 0):
    return subprocess.CompletedProcess([], code, stdout, "")


def test_the_reader_uses_the_journal_first_then_dmesg_and_never_guesses(monkeypatch):
    monkeypatch.setattr(gpu_reset_log.shutil, "which", lambda name: f"/usr/bin/{name}")
    calls = []

    def fake_run(argv, **_kwargs):
        calls.append(argv[0])
        if argv[0] == "journalctl":
            return _completed("", 1)  # not allowed to read the journal
        return _completed("\n".join(REPORTED))

    monkeypatch.setattr(gpu_reset_log.subprocess, "run", fake_run)
    summary = gpu_reset_log.read_gpu_resets()
    assert calls == ["journalctl", "dmesg"]
    assert summary is not None and summary.full_resets == 1


def test_an_unreadable_log_is_unknown_not_clean(monkeypatch):
    monkeypatch.setattr(gpu_reset_log.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(gpu_reset_log.subprocess, "run", lambda *a, **k: _completed("", 1))
    assert gpu_reset_log.read_gpu_resets() is None
    monkeypatch.setattr(gpu_reset_log.shutil, "which", lambda name: None)
    assert gpu_reset_log.read_gpu_resets() is None
