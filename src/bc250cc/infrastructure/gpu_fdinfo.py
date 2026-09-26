"""GPU busy time from amdgpu's per-client ``fdinfo``, read cheaply.

The BC-250 kernel does not expose ``gpu_busy_percent``, so GPU load is summed
from the ``drm-engine-*`` counters amdgpu publishes for every open DRM file.
The first version found those files by reading ``/proc/*/fdinfo/*`` -- every
open file of every process. A Proton game keeps tens of thousands open (esync:
Hogwarts Legacy and its wineserver held 126 000 between them), so one sample
read 130 000 files, took four seconds, and several interface threads did it at
once. The GIL they held is what made the whole window sluggish while a game
ran.

Now the DRM files are found by ``readlink`` alone -- no open, no read -- and
only now and then; between those searches just the few dozen known fdinfo
files are read. A search only looks inside processes it has not looked at yet
(and, for a couple of minutes, young ones that may not have opened the GPU so
far); everything is looked at again every few minutes. Even one pass over a
game's 60 000 descriptors holds the GIL long enough to make the interface
wait, so it should not repeat every few seconds.

Counters are keyed by ``drm-client-id`` so a file shared or duplicated
between processes is counted once, and a load is only computed for clients
present in both samples: a client that appears or goes away between two
reads is neither a spike nor a drop.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

DRM_DEVICE_PREFIX = "/dev/dri/"
#: How often /proc is searched for processes that appeared since.
REDISCOVER_SECONDS = 15.0
#: A process without a DRM file is looked at again while younger than this:
#: a game opens the GPU a moment after it starts.
YOUNG_PROCESS_SECONDS = 120.0
#: How often every process is looked at again from scratch.
FULL_RESCAN_SECONDS = 300.0


def _engine_counters(text: str) -> tuple[str | None, int, int] | None:
    """(client id, summed engine ns, compute-engine ns) for an amdgpu fdinfo.

    ``drm-engine-compute`` only advances while work runs on the compute (ACE)
    rings. A game's own client moving it is the proof that async compute is
    really in use, not just exposed by the driver.
    """
    client: str | None = None
    driver_ok = False
    total = 0
    compute = 0
    for line in text.splitlines():
        if line.startswith("drm-driver:"):
            driver_ok = line.partition(":")[2].strip() == "amdgpu"
        elif line.startswith("drm-client-id:"):
            client = line.partition(":")[2].strip() or None
        elif line.startswith("drm-engine-") and not line.startswith("drm-engine-capacity-"):
            name, _, rest = line.partition(":")
            fields = rest.split()
            if len(fields) >= 2 and fields[1] == "ns" and fields[0].isdigit():
                total += int(fields[0])
                if name == "drm-engine-compute":
                    compute += int(fields[0])
    return (client, total, compute) if driver_ok else None


class DrmFdinfoSampler:
    """Cumulative GPU engine time per DRM client, without scanning every file."""

    def __init__(
        self,
        proc: Path | str = "/proc",
        *,
        rediscover_seconds: float = REDISCOVER_SECONDS,
        young_seconds: float = YOUNG_PROCESS_SECONDS,
        full_rescan_seconds: float = FULL_RESCAN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._proc = str(proc)
        self._rediscover_seconds = float(rediscover_seconds)
        self._young_seconds = float(young_seconds)
        self._full_rescan_seconds = float(full_rescan_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._fdinfo_paths: list[str] = []
        self._discovered_at: float | None = None
        self._full_scan_at: float | None = None
        # pid -> (started, in seconds after boot, or None; its DRM fdinfo paths)
        self._by_pid: dict[str, tuple[float | None, list[str]]] = {}
        #: Compute-engine nanoseconds per client, and the process holding each
        #: client, as of the last :meth:`sample`.
        self._compute: dict[str, int] = {}
        self._owners: dict[str, str] = {}

    def _read(self, path: str) -> str | None:
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError:
            return None

    def _uptime(self) -> float | None:
        text = self._read(f"{self._proc}/uptime")
        try:
            return float(text.split()[0]) if text else None
        except (IndexError, ValueError):
            return None

    def _started(self, pid: str) -> float | None:
        """When the process started, in seconds after boot (stat field 22)."""
        text = self._read(f"{self._proc}/{pid}/stat")
        if not text:
            return None
        fields = text.rpartition(")")[2].split()
        try:
            return int(fields[19]) / os.sysconf("SC_CLK_TCK")
        except (IndexError, ValueError, OSError):
            return None

    def _scan_pid(self, pid: str) -> list[str]:
        paths: list[str] = []
        fd_dir = f"{self._proc}/{pid}/fd"
        try:
            fds = os.listdir(fd_dir)
        except OSError:  # gone, or another user's process
            return paths
        for fd in fds:
            try:
                target = os.readlink(f"{fd_dir}/{fd}")
            except OSError:
                continue
            if target.startswith(DRM_DEVICE_PREFIX):
                paths.append(f"{self._proc}/{pid}/fdinfo/{fd}")
        return paths

    def _discover(self, now: float) -> list[str]:
        try:
            pids = [name for name in os.listdir(self._proc) if name.isdigit()]
        except OSError:
            return []
        if self._full_scan_at is None or now - self._full_scan_at >= self._full_rescan_seconds:
            self._full_scan_at = now
            self._by_pid = {}
        uptime = self._uptime()
        by_pid: dict[str, tuple[float | None, list[str]]] = {}
        for pid in pids:
            known = self._by_pid.get(pid)
            if known is None:
                by_pid[pid] = (self._started(pid), self._scan_pid(pid))
                continue
            started, paths = known
            young = (
                started is not None
                and uptime is not None
                and uptime - started < self._young_seconds
            )
            by_pid[pid] = (started, self._scan_pid(pid)) if not paths and young else known
        self._by_pid = by_pid
        return [path for _started, paths in by_pid.values() for path in paths]

    def sample(self) -> dict[str, int]:
        """Engine nanoseconds per DRM client right now."""
        with self._lock:
            now = self._clock()
            if (
                self._discovered_at is None
                or now - self._discovered_at >= self._rediscover_seconds
            ):
                self._fdinfo_paths = self._discover(now)
                self._discovered_at = now
            counters: dict[str, int] = {}
            compute: dict[str, int] = {}
            owners: dict[str, str] = {}
            alive: list[str] = []
            for path in self._fdinfo_paths:
                try:
                    with open(path, encoding="utf-8", errors="ignore") as handle:
                        text = handle.read()
                except OSError:  # the process closed it or exited
                    continue
                alive.append(path)
                parsed = _engine_counters(text)
                if parsed is None:
                    continue
                client, total, compute_ns = parsed
                # Without a client id, a duplicated descriptor cannot be told
                # apart; counting it per file is the conservative choice.
                key = client or path
                counters[key] = max(counters.get(key, 0), total)
                if compute_ns >= compute.get(key, 0):
                    compute[key] = compute_ns
                    owners[key] = path[len(self._proc) + 1:].partition("/")[0]
            self._fdinfo_paths = alive
            self._compute = compute
            self._owners = owners
            return counters

    def compute_sample(self) -> dict[str, int]:
        """Compute-engine (ACE) nanoseconds per client, from the last sample."""
        with self._lock:
            return dict(self._compute)

    def process_name(self, client: str) -> str:
        """The name of the process that held ``client`` at the last sample."""
        with self._lock:
            pid = self._owners.get(client, "")
        text = self._read(f"{self._proc}/{pid}/comm") if pid.isdigit() else None
        return (text or "").strip()


def busiest_client(previous: dict[str, int], current: dict[str, int]) -> str | None:
    """The client whose counter moved most between two samples, if any moved."""
    moved = {
        client: current[client] - before
        for client, before in previous.items()
        if client in current and current[client] > before
    }
    return max(moved, key=moved.__getitem__) if moved else None


def busy_percent(
    previous: dict[str, int], current: dict[str, int], elapsed_ns: int
) -> int:
    """Share of ``elapsed_ns`` the clients seen in both samples kept the GPU busy."""
    if elapsed_ns <= 0:
        return 0
    delta = sum(
        max(0, current[client] - before)
        for client, before in previous.items()
        if client in current
    )
    return int(max(0, min(100, round(delta / elapsed_ns * 100))))
