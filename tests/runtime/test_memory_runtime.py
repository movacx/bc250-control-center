from pathlib import Path

import pytest

from bc250cc.infrastructure.memory_runtime import (
    GIB,
    kernel_argument,
    parse_memtotal_bytes,
    parse_proc_swaps,
    read_memory_runtime_state,
    supported_ttm_gib_presets,
    ttm_pages_for_gib,
)


def test_ttm_presets_are_real_gib_values_not_ambiguous_vram_labels():
    assert ttm_pages_for_gib(8) == 2_097_152
    assert ttm_pages_for_gib(10) == 2_621_440
    assert ttm_pages_for_gib(12) == 3_145_728
    with pytest.raises(ValueError):
        ttm_pages_for_gib(9)


def test_proc_swaps_separates_zram_from_the_backing_swap_zswap_requires():
    state = parse_proc_swaps(
        "Filename Type Size Used Priority\n"
        "/dev/zram0 partition 8388608 0 100\n"
        "/var/swap/swapfile file 16777216 0 -2\n"
    )
    assert state == {
        "zram_active": True,
        "zram_total_bytes": 8 * GIB,
        "backing_swap_active": True,
        "backing_swap_total_bytes": 16 * GIB,
    }


def test_ttm_presets_are_limited_by_visible_physical_ram():
    physical = parse_memtotal_bytes("MemTotal:        9884384 kB\nSwapTotal: 33554432 kB\n")

    assert physical == 9_884_384 * 1024
    assert supported_ttm_gib_presets(physical) == (8,)
    assert supported_ttm_gib_presets(12 * GIB) == (8, 10, 12)
    assert supported_ttm_gib_presets(None) == ()


def test_memory_runtime_reports_live_and_boot_ttm_without_mutating(tmp_path: Path):
    swaps = tmp_path / "swaps"
    cmdline = tmp_path / "cmdline"
    zswap = tmp_path / "zswap"
    pool = tmp_path / "pool"
    pages = tmp_path / "pages"
    meminfo = tmp_path / "meminfo"
    swaps.write_text("Filename Type Size Used Priority\n/dev/zram0 partition 4194304 0 100\n", encoding="utf-8")
    cmdline.write_text("quiet ttm.pages_limit=3145728 splash\n", encoding="utf-8")
    zswap.write_text("Y\n", encoding="utf-8")
    pool.write_text("20\n", encoding="utf-8")
    pages.write_text("2621440\n", encoding="utf-8")
    meminfo.write_text("MemTotal: 12582912 kB\n", encoding="utf-8")

    state = read_memory_runtime_state(
        proc_swaps=swaps,
        proc_cmdline=cmdline,
        proc_meminfo=meminfo,
        zswap_enabled=zswap,
        zswap_pool_percent=pool,
        ttm_pages_limit=pages,
        page_size=4096,
    )

    assert state["zram_total_bytes"] == 4 * GIB
    assert state["zswap_enabled"] is True
    assert state["ttm_limit_bytes"] == 10 * GIB
    assert state["ttm_boot_limit_bytes"] == 12 * GIB
    assert state["ttm_runtime_differs_from_boot"] is True
    assert state["physical_ram_bytes"] == 12 * GIB
    assert state["supported_ttm_gib_presets"] == (8, 10, 12)
    assert kernel_argument("ttm.pages_limit=1 quiet ttm.pages_limit=2", "ttm.pages_limit") == "2"
