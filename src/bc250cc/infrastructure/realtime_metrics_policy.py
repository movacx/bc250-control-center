"""Pure normalization and counter-rate policy for real-time telemetry."""

import math


def finite_number(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def bounded_percent(value):
    return max(0.0, min(100.0, finite_number(value)))


def _counter(value, attribute):
    return max(0.0, finite_number(getattr(value, attribute, 0)))


def _rate(current, previous, attribute, interval):
    if current is None or previous is None or interval <= 0:
        return 0.0
    return max(0.0, (_counter(current, attribute) - _counter(previous, attribute)) / interval)


def disk_rates(device, current, previous_entry, interval):
    """Return read/write bytes per second and bounded disk activity."""
    if not previous_entry or current is None or interval <= 0:
        return 0.0, 0.0, 0.0
    previous_device, previous = previous_entry
    if previous_device != device or previous is None:
        return 0.0, 0.0, 0.0

    read_bps = _rate(current, previous, "read_bytes", interval)
    write_bps = _rate(current, previous, "write_bytes", interval)
    current_busy = getattr(current, "busy_time", None)
    previous_busy = getattr(previous, "busy_time", None)
    if current_busy is not None and previous_busy is not None:
        delta_ms = _counter(current, "busy_time") - _counter(previous, "busy_time")
    else:
        delta_ms = (
            _counter(current, "read_time")
            - _counter(previous, "read_time")
            + _counter(current, "write_time")
            - _counter(previous, "write_time")
        )
    activity = bounded_percent(max(0.0, delta_ms) / (interval * 10.0))
    return read_bps, write_bps, activity


def network_rates(current, previous, interval):
    """Return receive/transmit bytes per second, rejecting resets/rollovers."""
    return (
        _rate(current, previous, "bytes_recv", interval),
        _rate(current, previous, "bytes_sent", interval),
    )
