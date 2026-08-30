"""Passive Linux memory-compression and TTM runtime inventory.

This module deliberately performs no swap, sysfs or boot mutation.  It gives
Desktop Mode and Quick Access one vocabulary for the first stage of the
Bazzite memory work while the eventual privileged transaction remains behind
a separate hardware/reboot qualification gate.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

GIB = 1024 ** 3
TTM_GIB_PRESETS = (8, 10, 12)


def ttm_pages_for_gib(gib: int, *, page_size: int = 4096) -> int:
    """Convert a visible GiB target to the TTM module's page count."""
    if type(gib) is not int or gib not in TTM_GIB_PRESETS:
        raise ValueError("TTM target must be one of the reviewed 8, 10, or 12 GiB presets.")
    if type(page_size) is not int or page_size <= 0 or GIB % page_size:
        raise ValueError("The running kernel page size cannot represent a whole GiB target.")
    return gib * GIB // page_size


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="strict").strip()
    except (OSError, UnicodeError):
        return ""


def _integer(path: Path) -> int | None:
    value = _read_text(path)
    try:
        return int(value, 10) if value else None
    except ValueError:
        return None


def _enabled(path: Path) -> bool | None:
    value = _read_text(path).strip().lower()
    if value in {"1", "y", "yes", "true"}:
        return True
    if value in {"0", "n", "no", "false"}:
        return False
    return None


def parse_proc_swaps(payload: str) -> dict[str, int | bool]:
    """Summarize active compressed and backing swap from ``/proc/swaps``."""
    zram_bytes = 0
    backing_bytes = 0
    for raw_line in str(payload or "").splitlines()[1:]:
        columns = raw_line.split()
        if len(columns) < 3:
            continue
        try:
            size_bytes = max(0, int(columns[2], 10)) * 1024
        except ValueError:
            continue
        if Path(columns[0]).name.startswith("zram"):
            zram_bytes += size_bytes
        else:
            backing_bytes += size_bytes
    return {
        "zram_active": zram_bytes > 0,
        "zram_total_bytes": zram_bytes,
        "backing_swap_active": backing_bytes > 0,
        "backing_swap_total_bytes": backing_bytes,
    }


def kernel_argument(command_line: str, name: str) -> str:
    pattern = re.compile(rf"(?:^|\s){re.escape(name)}=([^\s]+)")
    matches = pattern.findall(str(command_line or ""))
    return matches[-1] if matches else ""


def read_memory_runtime_state(
    *,
    proc_swaps: Path = Path("/proc/swaps"),
    proc_cmdline: Path = Path("/proc/cmdline"),
    zswap_enabled: Path = Path("/sys/module/zswap/parameters/enabled"),
    zswap_pool_percent: Path = Path("/sys/module/zswap/parameters/max_pool_percent"),
    ttm_pages_limit: Path = Path("/sys/module/ttm/parameters/pages_limit"),
    page_size: int | None = None,
) -> dict[str, object]:
    """Return a bounded read-only snapshot; absent kernel features stay absent."""
    page_size = int(page_size or os.sysconf("SC_PAGE_SIZE"))
    swap = parse_proc_swaps(_read_text(proc_swaps))
    pages = _integer(ttm_pages_limit)
    runtime_bytes = pages * page_size if pages is not None and pages >= 0 else None
    boot_raw = kernel_argument(_read_text(proc_cmdline), "ttm.pages_limit")
    try:
        boot_pages = int(boot_raw, 10) if boot_raw else None
    except ValueError:
        boot_pages = None
    return {
        **swap,
        "zswap_enabled": _enabled(zswap_enabled),
        "zswap_max_pool_percent": _integer(zswap_pool_percent),
        "ttm_pages_limit": pages,
        "ttm_limit_bytes": runtime_bytes,
        "ttm_boot_pages_limit": boot_pages,
        "ttm_boot_limit_bytes": boot_pages * page_size if boot_pages is not None else None,
        "ttm_runtime_differs_from_boot": bool(
            pages is not None and boot_pages is not None and pages != boot_pages
        ),
        "page_size": page_size,
    }

