"""Touch history metadata and selections must remain tied to real readings."""
import threading
import time
from types import SimpleNamespace

import pytest

from bc250cc.application.system.sensors import (
    GROUP_CPU,
    TEMPERATURE,
    USAGE,
    SensorReading,
)
from frontends.desktop.core.performance_model import PerformanceRecorder
from frontends.web.data import _chart, _sensors, performance


@pytest.mark.parametrize("resource,rate", [("memory", False), ("disk", True), ("network", True)])
@pytest.mark.parametrize("view", [None, "cpu.clocks", "unknown-view"])
def test_ram_disk_and_network_draw_summary_scales_without_a_detail_view(resource, rate, view):
    recorder = PerformanceRecorder(inventory=object())
    sample = {
        "memory": {"usage_percent": 40.0, "used": 4 * 2**30, "total": 10 * 2**30, "available": 6 * 2**30},
        "disk": {"usage_percent": 25.0, "used": 25 * 2**30, "total": 100 * 2**30, "read_bps": 2048, "write_bps": 1024},
        "network": {"download_bps": 4096, "upload_bps": 1024, "interface": "eth0"},
    }
    for _ in range(3):
        recorder.record(sample, [])
    live = SimpleNamespace(recorder=recorder, ctx=SimpleNamespace(lock=threading.Lock()))
    query = {"tab": resource}
    if view is not None:
        query["view"] = view
    data = performance(live, query)
    assert data["view"] == resource and data["tab"] == resource
    assert not data["waiting"]
    assert len(data["cards"]) == 4
    chart = data["chart"]
    assert chart["rate"] is rate
    assert chart["unit"] == ("B/s" if rate else "%")
    assert data["percent"] is not rate
    assert chart["max"] > chart["min"]
    assert chart["ticks"] and all(len(item["values"]) == 3 for item in chart["series"])
    assert len(chart["series"]) == (2 if rate else 1)


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
    assert {trace["key"] for trace in data["traces"]} == {"cpu/usage", "hwmon/k10temp/temp1"}
    assert data["traces"][0]["key"] == "cpu/usage"
    assert data["traces"][0]["chart"]["unit"] == "%"
