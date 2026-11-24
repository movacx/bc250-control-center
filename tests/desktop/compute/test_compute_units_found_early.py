"""Compute units already on when the driver started: the BIOS may have put them there."""

from frontends.desktop.core.compute_units_presenter import cus_found_at_driver_start


def test_only_a_driver_count_that_was_read_and_is_above_stock_counts():
    state = {"available": True, "driver_topology_available": True, "driver_masks": [0x1F] * 4}
    assert cus_found_at_driver_start(state) == 40
    assert cus_found_at_driver_start({**state, "driver_masks": [0x07] * 4}) == 0
    assert cus_found_at_driver_start({**state, "driver_topology_available": False}) == 0
    assert cus_found_at_driver_start({**state, "available": False}) == 0
