from types import SimpleNamespace

from bc250cc.infrastructure.realtime_metrics_policy import (
    bounded_percent,
    disk_rates,
    network_rates,
)


def test_percent_normalization_rejects_nonfinite_and_bounds_values():
    assert bounded_percent(float("nan")) == 0.0
    assert bounded_percent(float("inf")) == 0.0
    assert bounded_percent("invalid") == 0.0
    assert bounded_percent(-1) == 0.0
    assert bounded_percent(120) == 100.0
    assert bounded_percent(42.5) == 42.5


def test_disk_rates_use_busy_time_and_are_bounded():
    previous = SimpleNamespace(read_bytes=100, write_bytes=200, busy_time=100)
    current = SimpleNamespace(read_bytes=300, write_bytes=500, busy_time=2600)

    rates = disk_rates("nvme0n1", current, ("nvme0n1", previous), 2.0)

    assert rates == (100.0, 150.0, 100.0)


def test_disk_rates_fall_back_to_read_and_write_time():
    previous = SimpleNamespace(read_bytes=100, write_bytes=200, read_time=20, write_time=30)
    current = SimpleNamespace(read_bytes=300, write_bytes=500, read_time=70, write_time=80)

    assert disk_rates("disk", current, ("disk", previous), 2.0) == (100.0, 150.0, 5.0)


def test_disk_identity_change_and_counter_reset_produce_zero_rate():
    previous = SimpleNamespace(read_bytes=500, write_bytes=500, busy_time=100)
    current = SimpleNamespace(read_bytes=100, write_bytes=100, busy_time=50)

    assert disk_rates("new", current, ("old", previous), 1.0) == (0.0, 0.0, 0.0)
    assert disk_rates("same", current, ("same", previous), 1.0) == (0.0, 0.0, 0.0)


def test_network_rates_handle_first_sample_and_counter_reset():
    previous = SimpleNamespace(bytes_recv=1000, bytes_sent=800)
    current = SimpleNamespace(bytes_recv=1400, bytes_sent=1000)

    assert network_rates(current, None, 2.0) == (0.0, 0.0)
    assert network_rates(current, previous, 2.0) == (200.0, 100.0)
    assert network_rates(previous, current, 2.0) == (0.0, 0.0)
