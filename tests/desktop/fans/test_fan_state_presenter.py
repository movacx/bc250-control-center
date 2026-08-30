import math

from frontends.desktop.core.fan_state_presenter import present_fan_state, visible_fans

ORDER = (2, 1, 3, 4, 5)


def fan(index, rpm, *, path=True):
    return {
        "index": index,
        "label": f"Fan {index}",
        "rpm": rpm,
        "pwm": 170,
        "pwm_path": f"/hwmon/pwm{index}" if path else "",
    }


def test_visible_channels_are_filtered_and_sorted_by_board_order():
    state = {"sensores": {"fans": [fan(3, 0), fan(1, 0), fan(2, 1200), fan(8, 1), fan(4, 1, path=False)]}}

    assert [item["index"] for item in visible_fans(state, visible_order=ORDER)] == [2, 1, 3]


def test_presenter_chooses_active_main_fan_and_preserves_selected_channel():
    state = {
        "driver_control": True,
        "sensores": {"chip": "nct6686", "path": "/hwmon/4", "fans": [fan(2, 1200), fan(1, 1800)]},
        "modulos": {"nct6687": True},
    }
    view = present_fan_state(
        state, {"gpu_temp": 55, "cpu_temp": 48}, {},
        visible_order=ORDER, selected_index=1, preferred_index=2,
    )

    assert view.main_fan["index"] == 1
    assert view.selected_index == 1
    assert view.selected_percent == 67
    assert (view.driver_mode, view.driver_tone) == ("Writable PWM control", "green")


def test_non_finite_temperatures_are_not_exposed_or_used_for_curve_input():
    view = present_fan_state(
        {"sensores": {"fans": [fan(2, 1000)]}, "modulos": {}},
        {"gpu_temp": math.nan, "cpu_temp": math.inf},
        {"gpu_temp": 52},
        visible_order=ORDER, selected_index=None, preferred_index=2,
    )

    assert view.gpu_temperature == 52
    assert view.cpu_temperature is None
    assert view.driver_status == "Not detected"


def test_non_finite_fan_values_do_not_break_channel_selection():
    broken = fan(2, math.inf)
    broken["pwm"] = math.nan
    view = present_fan_state(
        {"sensores": {"fans": [broken]}, "modulos": {}},
        {},
        {},
        visible_order=ORDER,
        selected_index=2,
        preferred_index=2,
    )

    assert view.main_fan["index"] == 2
    assert view.selected_percent == 0


def test_read_only_chip_and_missing_controller_have_distinct_states():
    read_only = present_fan_state(
        {"sensores": {"chip": "nct6686"}, "modulos": {"nct6683": True}},
        {}, {}, visible_order=ORDER, selected_index=None, preferred_index=2,
    )
    missing = present_fan_state(
        {}, {}, {}, visible_order=ORDER, selected_index=None, preferred_index=2,
    )

    assert (read_only.driver, read_only.driver_mode, read_only.driver_tone) == (
        "nct6683", "Read-only monitoring", "blue",
    )
    assert (missing.driver, missing.driver_mode, missing.driver_tone) == (
        "Not loaded", "Controller not detected", "gray",
    )
