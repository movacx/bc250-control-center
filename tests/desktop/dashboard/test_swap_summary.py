"""The Swap row: a swapfile with nothing in it yet is still there."""

from frontends.desktop.core.state import DashboardState

GIB = 1024 ** 3


def test_an_empty_swap_reads_zero_of_its_size_not_missing():
    assert DashboardState(swap_used_bytes=0, swap_total_bytes=16 * GIB).swap_summary == "0 MB / 16.0 GB"
    assert DashboardState(swap_used_bytes=GIB, swap_total_bytes=16 * GIB).swap_summary == "1.0 GB / 16.0 GB"
    assert DashboardState(swap_used_bytes=0, swap_total_bytes=0).swap_summary == "Not detected"
