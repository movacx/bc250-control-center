"""The Sensors view and the per-part views of the Performance page.

Everything the board exposes, listed the way a hardware monitor lists it, and
the CPU, GPU and VRAM tiles opening onto the same readings drawn over time.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QModelIndex, Qt

from bc250cc.infrastructure.sensor_inventory import (
    GROUP_CPU,
    SensorInventory,
    SensorReading,
    cpu_topology,
    discover_hwmon,
)
from frontends.desktop.core.performance_views import (
    VIEW_BY_KEY,
    available_views,
    series_label,
    views_for,
)
from frontends.desktop.core.sensor_log import SensorLog, format_sensor_value
from frontends.desktop.i18n import tr
from frontends.desktop.pages.performance import PerformancePage
from frontends.desktop.pages.performance_sensors import (
    NAME,
    VALUE,
    SensorBoard,
    SensorFilter,
    SensorTableModel,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def board_sysfs(tmp_path):
    """A small BC-250: k10temp, amdgpu, a Nuvoton with one dead channel, 2 cores."""
    hwmon = tmp_path / "hwmon"
    _write(hwmon / "hwmon0" / "name", "k10temp\n")
    _write(hwmon / "hwmon0" / "temp1_input", "51500\n")
    _write(hwmon / "hwmon0" / "temp1_label", "Tctl\n")
    _write(hwmon / "hwmon1" / "name", "amdgpu\n")
    _write(hwmon / "hwmon1" / "freq1_input", "1850000000\n")
    _write(hwmon / "hwmon1" / "freq1_label", "sclk\n")
    _write(hwmon / "hwmon1" / "power1_average", "45000000\n")
    _write(hwmon / "hwmon1" / "power1_input", "46000000\n")
    _write(hwmon / "hwmon1" / "power1_label", "PPT\n")
    _write(hwmon / "hwmon1" / "in0_input", "799\n")
    _write(hwmon / "hwmon1" / "in0_label", "vddgfx\n")
    _write(hwmon / "hwmon2" / "name", "nct6686\n")
    _write(hwmon / "hwmon2" / "fan2_input", "3100\n")
    _write(hwmon / "hwmon2" / "fan2_label", "Pump Fan\n")
    _write(hwmon / "hwmon2" / "temp4_input", "0\n")
    _write(hwmon / "hwmon2" / "temp4_label", "PCH\n")
    cpu = tmp_path / "cpu"
    for number, core in ((0, 0), (1, 0), (2, 4), (3, 4)):
        _write(cpu / f"cpu{number}" / "topology" / "core_id", f"{core}\n")
        _write(cpu / f"cpu{number}" / "topology" / "physical_package_id", "0\n")
    _write(tmp_path / "cpuinfo", "processor\t: 0\ncpu MHz\t\t: 3400.0\nprocessor\t: 2\ncpu MHz\t\t: 1400.0\nmodel name\t: AMD BC-250\n")
    stat = tmp_path / "stat"
    _write(stat, "cpu  4 0 4 8 0 0 0 0\ncpu0 1 0 1 2 0\ncpu1 1 0 1 2 0\ncpu2 1 0 1 2 0\ncpu3 1 0 1 2 0\n")
    return tmp_path


def _inventory(root: Path) -> SensorInventory:
    return SensorInventory(
        hwmon_root=root / "hwmon", cpu_root=root / "cpu",
        stat_path=root / "stat", cpuinfo_path=root / "cpuinfo",
    )


def test_hwmon_channels_are_discovered_with_their_kernel_labels(board_sysfs):
    channels = discover_hwmon(board_sysfs / "hwmon")
    labels = {channel.key: (channel.label, channel.kind, channel.unit) for channel in channels}
    assert labels["hwmon/k10temp/temp1"] == ("Tctl", "temperature", "°C")
    assert labels["hwmon/amdgpu/freq1"] == ("sclk", "clock", "MHz")
    # The average is the steadier power reading, and only one is listed.
    assert [key for key in labels if key.startswith("hwmon/amdgpu/power")] == ["hwmon/amdgpu/power1"]
    assert cpu_topology(board_sysfs / "cpu") == [[0, 1], [2, 3]]


def test_the_inventory_reads_every_part_and_names_the_cpu(board_sysfs):
    inventory = _inventory(board_sysfs)
    inventory.read({})
    _write(board_sysfs / "stat", "cpu  6 0 6 8 0 0 0 0\ncpu0 2 0 1 3 0\ncpu1 1 0 1 4 0\ncpu2 1 0 3 2 0\ncpu3 1 0 1 2 0\n")
    readings = {reading.key: reading for reading in inventory.read({
        "cpu": {"usage_percent": 12.0},
        "gpu": {"usage_percent": 40.0, "memory_frequency_mhz": 1750, "vram_used": 512, "vram_total": 1024},
        "memory": {"used": 4, "available": 12, "usage_percent": 25.0},
    }, gddr6_chips=[(0, 44.0), (1, 46.0)])}
    assert readings["hwmon/k10temp/temp1"].value == pytest.approx(51.5)
    assert readings["hwmon/k10temp/temp1"].device == "AMD BC-250"
    assert readings["hwmon/amdgpu/freq1"].value == pytest.approx(1850.0)
    assert readings["hwmon/amdgpu/power1"].value == pytest.approx(45.0)
    assert readings["cpu/core0/clock"].value == pytest.approx(3400.0)
    assert readings["cpu/core1/clock"].value == pytest.approx(1400.0)
    assert readings["cpu/core0/t0/usage"].value == pytest.approx(50.0)
    assert readings["gpu/vram_percent"].value == pytest.approx(50.0)
    assert readings["gddr6/hotspot"].value == pytest.approx(46.0)
    assert readings["hwmon/nct6686/fan2"].value == pytest.approx(3100.0)


def test_the_log_keeps_statistics_and_knows_a_dead_channel():
    log = SensorLog(clock=lambda: 0.0)
    for moment, value in enumerate((40.0, 50.0, 60.0)):
        log.record([
            SensorReading("t", GROUP_CPU, "CPU", "Tctl", "temperature", "°C", value),
            SensorReading("dead", GROUP_CPU, "CPU", "PCH", "temperature", "°C", 0.0),
        ], moment=moment)
    entry = log.get("t")
    assert (entry.minimum, entry.average, entry.maximum) == (40.0, 50.0, 60.0)
    assert entry.active and not log.get("dead").active
    log.reset_statistics()
    assert log.get("t").average is None
    assert format_sensor_value(3412.4, "MHz") == "3412 MHz"
    assert format_sensor_value(None, "°C") == "–"


def _log_with_sensors() -> SensorLog:
    log = SensorLog(clock=lambda: 0.0)
    log.record([
        SensorReading("hwmon/k10temp/temp1", "cpu", "AMD BC-250", "Tctl", "temperature", "°C", 51.0),
        SensorReading("cpu/core0/clock", "cpu", "AMD BC-250", "Core {core} clock", "clock", "MHz", 3400.0, (("core", 0),)),
        SensorReading("hwmon/nct6686/temp4", "hwmon:nct6686", "nct6686", "PCH", "temperature", "°C", 0.0),
        SensorReading("hwmon/nct6686/fan2", "hwmon:nct6686", "nct6686", "Pump Fan", "fan", "RPM", 3100.0),
    ])
    return log


def test_the_table_groups_sensors_under_their_part(qtbot):
    model = SensorTableModel(_log_with_sensors())
    model.sync()
    assert model.rowCount() == 2
    cpu = model.index(0, 0)
    assert model.data(cpu) == "AMD BC-250"
    assert model.rowCount(cpu) == 2
    assert model.data(model.index(1, NAME, cpu)) == tr("Core {core} clock").format(core=0)
    assert model.data(model.index(1, VALUE, cpu)) == "3400 MHz"
    assert model.headerData(VALUE, Qt.Orientation.Horizontal) == tr("Value")
    assert model.parent(model.index(0, 0, cpu)) == cpu


def test_the_filter_narrows_by_name_and_kind_and_hides_dead_channels(qtbot):
    model = SensorTableModel(_log_with_sensors())
    model.sync()
    proxy = SensorFilter()
    proxy.setSourceModel(model)

    def shown() -> set[str]:
        names = set()
        for row in range(proxy.rowCount()):
            group = proxy.index(row, 0)
            for child in range(proxy.rowCount(group)):
                names.add(proxy.data(proxy.index(child, 0, group)))
        return names

    proxy.configure(hide_unused=True)
    assert "PCH" not in shown() and "Pump Fan" in shown()
    proxy.configure(hide_unused=False)
    assert "PCH" in shown()
    proxy.configure(kinds=("fan",))
    assert shown() == {"Pump Fan"}
    proxy.configure(kinds=(), text="tctl")
    assert shown() == {"Tctl"}
    assert proxy.filterAcceptsRow(0, QModelIndex()) is False


def test_ticking_a_row_draws_it_and_the_choice_is_remembered(qtbot):
    log = _log_with_sensors()
    board = SensorBoard(log)
    qtbot.addWidget(board)
    board.model.plotted = []
    board.refresh()
    cpu = board.model.index(0, 0)
    tctl = board.model.index(0, NAME, cpu)
    board.model.setData(tctl, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert "hwmon/k10temp/temp1" in board.plots.traces
    assert "hwmon/k10temp/temp1" in str(board._settings.value("performance/sensors_plotted"))
    board.set_mode("list")
    assert board.plots.isHidden() and not board.tree.isHidden()
    board.set_mode("graphs")
    assert board.tree.isHidden()


def test_kind_chips_combine_and_all_clears_them(qtbot):
    """Temperatures and fans together, the way a curve is tuned."""
    log = _log_with_sensors()
    board = SensorBoard(log)
    qtbot.addWidget(board)
    board.refresh()
    chips = board.kind_chips
    assert chips["All sensors"].isChecked() and board.selected_kinds() == ()

    chips["Temperatures"].click()
    chips["Fans"].click()
    assert set(board.selected_kinds()) == {"temperature", "fan"}
    assert not chips["All sensors"].isChecked()
    assert set(board.proxy._kinds) == {"temperature", "fan"}
    assert board._settings.value("performance/sensors_kinds") == "Temperatures\nFans"

    chips["Memory and throughput"].click()
    assert {"data", "rate"} <= set(board.selected_kinds())

    chips["All sensors"].click()
    assert board.selected_kinds() == () and chips["All sensors"].isChecked()
    chips["Fans"].click()
    chips["Fans"].click()
    assert chips["All sensors"].isChecked()


def test_the_one_kind_chosen_before_the_chips_is_kept(qtbot):
    log = _log_with_sensors()
    board = SensorBoard(log)
    qtbot.addWidget(board)
    board._settings.remove("performance/sensors_kinds")
    board._settings.setValue("performance/sensors_kind", 7)  # "Fans", by position
    board._restore()
    assert board.selected_kinds() == ("fan",)


def test_graphs_take_as_many_columns_as_fit(qtbot):
    log = _log_with_sensors()
    board = SensorBoard(log)
    qtbot.addWidget(board)
    board.set_mode("graphs", persist=False)
    board.resize(1500, 800)
    board.show()
    qtbot.waitUntil(lambda: board.plots._columns == 3, timeout=2000)
    board.resize(800, 800)
    qtbot.waitUntil(lambda: board.plots._columns == 2, timeout=2000)
    board.set_mode("split", persist=False)
    qtbot.waitUntil(lambda: board.plots._columns == 1, timeout=2000)


def test_each_view_picks_its_series_from_the_same_list(board_sysfs):
    inventory = _inventory(board_sysfs)
    inventory.read({})
    readings = inventory.read({"gpu": {"memory_frequency_mhz": 1750}})
    names = {key: [series_label(item, tr) for item in view.series(readings)] for key, view in VIEW_BY_KEY.items()}
    assert names["cpu.clocks"] == [tr("Core {core}").format(core=0), tr("Core {core}").format(core=1)]
    assert len(names["cpu.threads"]) == 4
    assert names["gpu.clock"] == ["SCLK"]
    assert names["gpu.power"] == ["PPT"]
    assert names["cpu.temperature"] == ["Tctl"]
    assert "vram.gddr6" not in available_views(readings)
    assert [view.key for view in views_for("cpu")][0] == "cpu"


SAMPLE = {
    "cpu": {"usage_percent": 9.0, "frequency_mhz": 1070, "temperature_c": 47.4, "load_average": [1.99]},
    "gpu": {"usage_percent": 40.0, "frequency_mhz": 1500, "vram_used": 3 * 1024 ** 3, "vram_total": 8 * 1024 ** 3},
    "memory": {"usage_percent": 38.0, "used": 6 * 1024 ** 3, "total": 16 * 1024 ** 3, "available": 10 * 1024 ** 3},
    "disk": {"usage_percent": 61.0, "used": 300 * 1024 ** 3, "total": 500 * 1024 ** 3, "read_bps": 0, "write_bps": 0},
    "network": {"download_bps": 0, "upload_bps": 0, "interface": "enp3s0"},
}


def test_hovering_a_tile_offers_its_views_and_choosing_one_charts_it(qtbot, board_sysfs):
    page = PerformancePage(object())
    qtbot.addWidget(page)
    page.resize(1400, 900)
    page.show()
    inventory = _inventory(board_sysfs)
    inventory.read({})
    page._sample_ready({**SAMPLE, "sensor_readings": inventory.read(SAMPLE)})

    page._tile_hovered("cpu", True)
    qtbot.waitUntil(lambda: page.flyout.isVisible(), timeout=2000)
    assert [row.view.key for row in page.flyout.rows] == [view.key for view in views_for("cpu")]
    clocks = next(row for row in page.flyout.rows if row.view.key == "cpu.clocks")
    assert clocks.isEnabled()
    clocks.gamepad_activate()
    assert not page.flyout.isVisible()
    assert page.detail.graph.history.definition.unit == "MHz"
    assert tr("Clock per core") in page.detail.title.text()

    # Network has one view; it opens no menu.
    page._tile_hovered("network", True)
    qtbot.wait(300)
    assert not page.flyout.isVisible()


def test_sliding_from_one_tile_to_the_next_opens_a_full_menu(qtbot, board_sysfs):
    """GPU's menu open, pointer onto CPU: CPU's menu came up as an empty strip.

    Rows added to a visible menu are only shown on the next pass of the event
    loop, so the menu was measured without them.
    """
    page = PerformancePage(object())
    qtbot.addWidget(page)
    page.resize(1400, 900)
    page.show()
    inventory = _inventory(board_sysfs)
    inventory.read({})
    page._sample_ready({**SAMPLE, "sensor_readings": inventory.read(SAMPLE)})

    page._show_flyout("gpu")
    assert page.flyout.isVisible()
    gpu_height = page.flyout.height()
    page._tile_hovered("cpu", True)

    assert page.flyout.resource == "cpu"
    assert all(not row.isHidden() for row in page.flyout.rows)
    rows_height = sum(row.sizeHint().height() for row in page.flyout.rows)
    assert page.flyout.height() >= rows_height
    assert page.flyout.height() > gpu_height / 2


def test_the_sensors_switch_loads_the_list_in_the_charts_place(qtbot):
    page = PerformancePage(object())
    qtbot.addWidget(page)
    page.resize(1400, 900)
    page.show()
    page.detail.sensors_button.click()
    assert page.body.currentWidget() is page.sensor_board
    assert page.gamepad_back() is True
    assert page.body.currentWidget() is page.detail
    page.show_sensors()
    page._select_resource("gpu")
    assert page.body.currentWidget() is page.detail


def test_the_chips_narrow_the_graphs_too(qtbot):
    """With only the graphs on screen, a chip that changed nothing looked broken."""
    log = _log_with_sensors()
    board = SensorBoard(log)
    qtbot.addWidget(board)
    board.model.plotted = ["hwmon/k10temp/temp1", "hwmon/nct6686/fan2", "cpu/core0/clock"]
    board._set_kind_selection(())
    board._filter_changed()
    assert list(board.plots.traces) == board.model.plotted

    board.kind_chips["Fans"].click()
    assert list(board.plots.traces) == ["hwmon/nct6686/fan2"]
    board.kind_chips["All sensors"].click()
    board.filter_field.setText("tctl")
    assert list(board.plots.traces) == ["hwmon/k10temp/temp1"]
    # Only hidden: the ticks themselves are kept.
    assert len(board.model.plotted) == 3


def test_a_third_column_of_graphs_gets_its_share_of_the_width(qtbot):
    """Added with no stretch, it collapsed to nothing and hid its traces."""
    log = _log_with_sensors()
    board = SensorBoard(log)
    qtbot.addWidget(board)
    board.model.plotted = ["hwmon/k10temp/temp1", "hwmon/nct6686/fan2", "cpu/core0/clock"]
    board.set_mode("graphs", persist=False)
    board.resize(1500, 800)
    board.show()
    board._filter_changed()
    qtbot.waitUntil(lambda: board.plots._columns == 3, timeout=2000)
    qtbot.wait(50)
    widths = [trace.width() for trace in board.plots.traces.values()]
    assert min(widths) > 300, widths
