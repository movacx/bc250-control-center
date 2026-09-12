"""Units and validity for passive BC250 readings, independent of clock limits."""

import math


def valid_number(value, minimum, maximum):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and minimum <= number <= maximum else None


# The BC-250 rails operate far inside the generic hwmon range: Oberon's own
# safe window is 920-1210 mV and an idle vddgfx reads around 800 mV. A kernel
# without the BC-250 sensor patches can report a plausible-looking but wrong
# value, which reached users as a "cosmic" reading (issue #7), so the ceiling
# is tightened to this board rather than to what hwmon permits in general.
BC250_VOLTAGE_MIN_MV = 400
BC250_VOLTAGE_MAX_MV = 1400


def voltage_mv(value):
    """hwmon in*_input is millivolts. Never infer units from magnitude."""
    number = valid_number(value, BC250_VOLTAGE_MIN_MV, BC250_VOLTAGE_MAX_MV)
    return round(number) if number is not None else None


def clock_mhz(value):
    """Reject broken firmware fields; these bounds do not authorize tuning."""
    number = valid_number(value, 100, 5000)
    return round(number) if number is not None else None
