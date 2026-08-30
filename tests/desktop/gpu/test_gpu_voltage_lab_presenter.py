from bc250cc.application.gpu.voltage_lab_presentation import present_voltage_lab
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


def test_voltage_lab_presentation_describes_ready_valid_state():
    presentation = present_voltage_lab(_state(), custom_voltage_maximum=1200)
    assert presentation.summaries[0].value.template == "2"
    assert _values(presentation.summaries[1].value) == {"level": 3}
    assert presentation.summaries[2].value.template == "930 mV"
    assert presentation.summaries[3].value.template == "1000–1850 MHz"
    assert presentation.summaries[4].value.template == "Valid"
    assert presentation.summaries[4].detail.template == "monotonic curve"
    assert (presentation.table_count, presentation.table_tone) == (2, "green")
    assert (presentation.workflow_status, presentation.workflow_tone) == ("Armed", "orange")


def test_voltage_lab_presentation_distinguishes_curve_error_from_empty_state():
    invalid = present_voltage_lab(
        _state(safety_valid=False, curve_error_count=2),
        custom_voltage_maximum=1200,
    )
    assert invalid.summaries[4].value.template == "Review"
    assert invalid.summaries[4].detail.template == "{count} curve errors"
    assert _values(invalid.summaries[4].detail) == {"count": 2}

    empty = present_voltage_lab(
        _state(
            points=(),
            current_voltages=(),
            editable_frequencies=(),
            profile_frequencies=(),
            custom_defaults=(),
            active_min=0,
            active_max=0,
            maximum_voltage=0,
            safety_valid=False,
        ),
        custom_voltage_maximum=1200,
    )
    assert empty.summaries[2].value.template == "Not detected"
    assert empty.summaries[3].value.template == "Not available"
    assert empty.summaries[4].detail.template == "no safe-points detected"
    assert (empty.table_count, empty.table_tone) == (0, "orange")
    assert (empty.workflow_status, empty.workflow_tone) == ("Locked", "gray")


def test_voltage_lab_custom_limit_is_explicit_translation_value():
    presentation = present_voltage_lab(_state(), custom_voltage_maximum=1175)
    detail = presentation.summaries[2].detail
    assert detail.template == "advanced editor range up to {maximum} mV"
    assert _values(detail) == {"maximum": 1175}
