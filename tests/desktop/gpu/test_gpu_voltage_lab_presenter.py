
from bc250cc.application.gpu.voltage_lab_state import VoltageLabState


def _state(**updates):
    values = {
        "is_oberon": False,
        "points": ((1000, 800), (1850, 930)),
        "current_voltages": ((1000, 800), (1850, 930)),
        "editable_frequencies": (1000, 1850),
        "profile_frequencies": (1000, 1850),
        "detected_level": 3,
        "custom_defaults": ((1000, 800), (1850, 930)),
        "active_min": 1000,
        "active_max": 1850,
        "maximum_voltage": 930,
        "curve_error_count": 0,
        "safety_valid": True,
    }
    values.update(updates)
    return VoltageLabState(**values)


def _values(text):
    return dict(text.values)

