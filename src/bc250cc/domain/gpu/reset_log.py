"""GPU hangs and resets, read from the kernel log.

When a game freezes the screen or the desktop falls back to a login prompt,
amdgpu says so in the kernel log: the ring that stopped answering, whether the
driver managed to reset just that ring, and, when it did not, the full GPU reset
that loses the VRAM and every graphics client with it. A support thread starts
there, and people paste those lines by hand. This turns them into a short
summary the diagnostic report and the Quick Access panel can show.

Pure parsing, no I/O: ``summarize`` takes the log's lines. Reading the log is
the caller's job (``infrastructure/gpu_reset_log.py``), and the Decky plugin
carries the same few patterns in its own ``main.py`` because it cannot import
this package; ``tests/quick_access`` keeps the two in step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: ``ring gfx_0.0.0 timeout, signaled seq=…`` (the job watchdog).
_TIMEOUT = re.compile(r"\bring (\S+) timeout\b")
#: ``Ring gfx_0.0.0 reset failed`` (the per-ring reset the kernel tries first).
_RING_FAILED = re.compile(r"\bring (\S+) reset failed\b", re.IGNORECASE)
#: ``GPU reset begin!`` starts a full reset; newer kernels number them.
_FULL_RESET = re.compile(r"\bGPU reset begin\b|\bGPU reset\(\d+\) begin\b")
#: ``Process java pid 20602 thread java:cs0 pid 20698`` (older kernels print
#: ``Process information: process java pid 20602 …``): who was on the ring.
_PROCESS = re.compile(r"\bprocess (\S+) pid (\d+)", re.IGNORECASE)
_VRAM_LOST = re.compile(r"\bVRAM is lost\b", re.IGNORECASE)
#: ``2026-10-15T16:20:00+0300`` from ``journalctl -o short-iso``, or dmesg's ``--time-format iso``.
_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})")


@dataclass(frozen=True)
class GpuResetSummary:
    """What one boot's kernel log says about GPU hangs."""

    full_resets: int = 0
    ring_timeouts: int = 0
    ring_resets_failed: int = 0
    vram_lost: bool = False
    last_at: str = ""
    last_process: str = ""
    last_ring: str = ""

    @property
    def any(self) -> bool:
        return bool(self.full_resets or self.ring_timeouts or self.ring_resets_failed)

    def label(self) -> str:
        """One line for a table cell; English, because a report is read by a maintainer."""
        if not self.any:
            return "None this boot"
        parts = []
        if self.full_resets:
            parts.append(f"{self.full_resets} full reset{'s' if self.full_resets != 1 else ''}")
        if self.ring_timeouts:
            parts.append(f"{self.ring_timeouts} ring timeout{'s' if self.ring_timeouts != 1 else ''}")
        if self.ring_resets_failed:
            parts.append(f"{self.ring_resets_failed} ring reset{'s' if self.ring_resets_failed != 1 else ''} failed")
        if self.vram_lost:
            parts.append("VRAM lost")
        last = " ".join(part for part in (self.last_at, self.last_ring, self.last_process) if part)
        return " · ".join(parts) + (f" · last {last}" if last else "")

    def to_dict(self) -> dict[str, object]:
        return {
            "full_resets": self.full_resets,
            "ring_timeouts": self.ring_timeouts,
            "ring_resets_failed": self.ring_resets_failed,
            "vram_lost": self.vram_lost,
            "last_at": self.last_at,
            "last_process": self.last_process,
            "last_ring": self.last_ring,
            "label": self.label(),
        }


def summarize(lines) -> GpuResetSummary:
    """Count the hangs in ``lines`` (kernel log text, one entry per line)."""
    full = timeouts = failed = 0
    vram_lost = False
    last_at = last_process = last_ring = ""
    for raw in lines:
        line = str(raw)
        if "amdgpu" not in line:
            continue
        stamp = _STAMP.match(line)
        when = f"{stamp.group(1)} {stamp.group(2)}" if stamp else ""
        matched = False
        match = _TIMEOUT.search(line)
        if match:
            timeouts += 1
            last_ring = match.group(1)
            matched = True
        match = _RING_FAILED.search(line)
        if match:
            failed += 1
            last_ring = match.group(1)
            matched = True
        if _FULL_RESET.search(line):
            full += 1
            matched = True
        if _VRAM_LOST.search(line):
            vram_lost = True
            matched = True
        match = _PROCESS.search(line)
        if match:
            last_process = match.group(1)
        if matched and when:
            last_at = when
    return GpuResetSummary(full, timeouts, failed, vram_lost, last_at, last_process, last_ring)
