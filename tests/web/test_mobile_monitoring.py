"""Touch history metadata and selections must remain tied to real readings."""
import time

from bc250cc.application.system.sensors import (
    GROUP_CPU,
    TEMPERATURE,
    USAGE,
    SensorReading,
)
from frontends.desktop.core.performance_model import PerformanceRecorder
from frontends.web.data import _chart, _sensors


def test_touch_history_has_the_original_units_times_and_values():
    values = [42.5, 45.0, 44.25]
    ages = [2.0, 1.0, 0.0]
    chart = _chart([("Temperature", values)], ages, "°C", False, False)
    assert chart["unit"] == "°C" and not chart["rate"]
    assert chart["ages"] == ages
    assert chart["series"][0]["values"] == values
    rates = _chart([("Network", [1024.0, 2048.0])], [1.0, 0.0], "B/s", False, True)
    assert rates["unit"] == "B/s" and rates["rate"]


def test_filtering_does_not_drop_selected_sensors_outside_the_visible_list():
    recorder = PerformanceRecorder(inventory=object())
    recorder.log.record([
        SensorReading("cpu/usage", GROUP_CPU, "CPU", "Visible usage", USAGE, "%", 25.0),
        SensorReading("hwmon/k10temp/temp1", GROUP_CPU, "CPU", "Hidden temperature", TEMPERATURE, "°C", 55.0),
    ], time.monotonic())
    data = _sensors(recorder, {"q": "Visible"})
    assert [row["key"] for row in data["rows"] if "key" in row] == ["cpu/usage"]
    assert set(data["ticked"]) == {"cpu/usage", "hwmon/k10temp/temp1"}
    assert data["traces"][0]["key"] == "cpu/usage"
    assert data["traces"][0]["chart"]["unit"] == "%"
