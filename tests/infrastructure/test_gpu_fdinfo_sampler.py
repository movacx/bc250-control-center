"""GPU load from amdgpu fdinfo, without reading every open file.

With Hogwarts Legacy open, the game and its wineserver held 126 000 file
descriptors. Reading each one's fdinfo took four seconds per sample, several
threads sampled at once, and the GIL they held froze the window. These tests
pin the cheaper reading: find DRM files by their link target, look inside a
process once, and read only the DRM files after that.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bc250cc.infrastructure import gpu_fdinfo
from bc250cc.infrastructure.gpu_fdinfo import DrmFdinfoSampler, busy_percent

CLK_TCK = os.sysconf("SC_CLK_TCK")


def _fdinfo(client: int, gfx_ns: int, driver: str = "amdgpu") -> str:
    return (
        "pos:\t0\nflags:\t02100002\n"
        f"drm-driver:\t{driver}\ndrm-client-id:\t{client}\n"
        f"drm-engine-gfx:\t{gfx_ns} ns\ndrm-engine-compute:\t0 ns\n"
        "drm-engine-capacity-gfx:\t1\n"
    )


class FakeProc:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.uptime(1000.0)

    def uptime(self, seconds: float) -> None:
        (self.root / "uptime").write_text(f"{seconds} 0.0\n", encoding="utf-8")

    def process(self, pid: int, *, started: float = 10.0, files: int = 0) -> Path:
        base = self.root / str(pid)
        (base / "fd").mkdir(parents=True)
        (base / "fdinfo").mkdir()
        ticks = int(started * CLK_TCK)
        fields = ["S"] + ["0"] * 18 + [str(ticks)] + ["0"] * 10
        (base / "stat").write_text(f"{pid} (proc name) " + " ".join(fields) + "\n", encoding="utf-8")
        for fd in range(100, 100 + files):  # esync-style event descriptors
            os.symlink("anon_inode:[eventfd]", base / "fd" / str(fd))
            (base / "fdinfo" / str(fd)).write_text("pos:\t0\n", encoding="utf-8")
        return base

    def drm(self, pid: int, fd: int, client: int, gfx_ns: int) -> None:
        base = self.root / str(pid)
        link = base / "fd" / str(fd)
        if not link.is_symlink():
            os.symlink("/dev/dri/renderD128", link)
        (base / "fdinfo" / str(fd)).write_text(_fdinfo(client, gfx_ns), encoding="utf-8")


@pytest.fixture
def proc(tmp_path):
    return FakeProc(tmp_path / "proc")


def test_only_drm_files_are_read_after_the_first_look(proc, monkeypatch):
    proc.process(12861, files=300)  # the game: many event fds and one GPU file
    proc.drm(12861, 7, client=41, gfx_ns=1_000)
    proc.process(12677, files=300)  # wineserver: no GPU file at all
    clock = [0.0]
    sampler = DrmFdinfoSampler(proc.root, clock=lambda: clock[0])
    assert sampler.sample() == {"41": 1_000}

    readlinks = []
    real_readlink = os.readlink
    monkeypatch.setattr(gpu_fdinfo.os, "readlink", lambda path: readlinks.append(path) or real_readlink(path))
    opened = []
    real_open = open
    monkeypatch.setattr("builtins.open", lambda path, *a, **k: opened.append(str(path)) or real_open(path, *a, **k))

    proc.drm(12861, 7, client=41, gfx_ns=5_000)
    clock[0] = 20.0  # a rediscovery: neither known process is looked into again
    assert sampler.sample() == {"41": 5_000}
    assert readlinks == []
    assert [path for path in opened if "/fdinfo/" in path] == [f"{proc.root}/12861/fdinfo/7"]


def test_a_young_process_is_looked_at_until_it_opens_the_gpu(proc):
    proc.uptime(1000.0)
    proc.process(500, started=990.0)  # ten seconds old, no GPU file yet
    clock = [0.0]
    sampler = DrmFdinfoSampler(proc.root, clock=lambda: clock[0])
    assert sampler.sample() == {}

    proc.drm(500, 9, client=7, gfx_ns=123)
    clock[0] = 16.0
    proc.uptime(1016.0)
    assert sampler.sample() == {"7": 123}


def test_an_old_process_without_the_gpu_waits_for_the_full_rescan(proc):
    proc.process(600, started=10.0)
    clock = [0.0]
    sampler = DrmFdinfoSampler(proc.root, clock=lambda: clock[0], full_rescan_seconds=300)
    assert sampler.sample() == {}
    proc.drm(600, 3, client=9, gfx_ns=50)
    clock[0] = 16.0
    assert sampler.sample() == {}
    clock[0] = 301.0
    assert sampler.sample() == {"9": 50}


def test_shared_and_foreign_files_are_counted_once_or_not_at_all(proc):
    proc.process(1)
    proc.process(2)
    proc.drm(1, 5, client=3, gfx_ns=700)
    proc.drm(2, 6, client=3, gfx_ns=700)  # the same client passed to another process
    base = proc.root / "2"
    os.symlink("/dev/dri/card1", base / "fd" / "8")
    (base / "fdinfo" / "8").write_text(_fdinfo(4, 999, driver="i915"), encoding="utf-8")
    assert DrmFdinfoSampler(proc.root).sample() == {"3": 700}


def test_load_counts_only_clients_seen_twice():
    second = 1_000_000_000
    assert busy_percent({"a": 0, "b": 0}, {"a": second // 2, "b": second // 4}, second) == 75
    # A client that appeared with years of history is no spike; one that
    # left is no drop.
    assert busy_percent({"a": 0}, {"a": second // 2, "new": 50 * second}, second) == 50
    assert busy_percent({"a": 0, "gone": 10}, {"a": second // 2}, second) == 50
    assert busy_percent({}, {}, 0) == 0


def test_the_compute_engine_is_kept_apart_with_the_process_using_it(proc):
    """drm-engine-compute only moves while work runs on the ACE queues."""
    proc.process(21)
    (proc.root / "21" / "comm").write_text("Cyberpunk2077.e\n", encoding="utf-8")
    proc.drm(21, 4, client=8, gfx_ns=1_000)
    fdinfo = proc.root / "21" / "fdinfo" / "4"
    fdinfo.write_text(fdinfo.read_text().replace("drm-engine-compute:\t0 ns", "drm-engine-compute:\t300 ns"))
    sampler = DrmFdinfoSampler(proc.root)

    assert sampler.sample() == {"8": 1_300}
    assert sampler.compute_sample() == {"8": 300}
    assert sampler.process_name("8") == "Cyberpunk2077.e"
    assert sampler.process_name("unknown") == ""


def test_the_busiest_client_is_the_one_whose_counter_moved_most():
    from bc250cc.infrastructure.gpu_fdinfo import busiest_client

    assert busiest_client({"a": 0, "b": 0}, {"a": 10, "b": 30}) == "b"
    assert busiest_client({"a": 5}, {"a": 5}) is None
    assert busiest_client({}, {"new": 99}) is None
